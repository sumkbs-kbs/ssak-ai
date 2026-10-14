"""In-memory QR pairing and authenticated encrypted relay primitives."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .remote_pairing_types import (
    PairingAdvertisement,
    PairingInfo,
    PairingState,
    RelayEnvelope,
    RemotePairingError,
)


@dataclass(slots=True)
class _PairingRecord:
    private_key: X25519PrivateKey
    code_digest: bytes
    expires_at: float
    state: PairingState = PairingState.PENDING
    client_public_key: bytes | None = None
    shared_key: bytes | None = None
    key_epoch: int = 0
    queue: deque[RelayEnvelope] | None = None
    seen_nonces: set[str] | None = None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not value or len(value) % 4 == 1:
        raise RemotePairingError("invalid_envelope", "invalid base64url value")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise RemotePairingError("invalid_envelope", "invalid base64url value") from exc
    if _b64encode(decoded) != value.rstrip("="):
        raise RemotePairingError("invalid_envelope", "invalid base64url value")
    return decoded


class PairingManager:
    """Thread-safe pairing registry; records intentionally live for process lifetime."""

    def __init__(self, clock: Callable[[], float] = time.time, max_queue_size: int = 256) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be positive")
        self._clock: Callable[[], float] = clock
        self._max_queue_size: int = max_queue_size
        self._records: dict[str, _PairingRecord] = {}
        self._lock: threading.RLock = threading.RLock()

    def create_pairing(self, ttl_seconds: int = 300) -> PairingAdvertisement:
        if not 30 <= ttl_seconds <= 900:
            raise RemotePairingError("invalid_ttl", "ttl_seconds must be between 30 and 900")
        pairing_id = secrets.token_urlsafe(16)
        code = f"{secrets.randbelow(100_000_000):08d}"
        private_key = X25519PrivateKey.generate()
        expires_at = self._clock() + ttl_seconds
        record = _PairingRecord(
            private_key=private_key,
            code_digest=hashlib.sha256(code.encode("ascii")).digest(),
            expires_at=expires_at,
            queue=deque(),
            seen_nonces=set(),
        )
        server_public_key = _b64encode(private_key.public_key().public_bytes_raw())
        payload = json.dumps(
            {
                "v": 1,
                "pairing_id": pairing_id,
                "code": code,
                "server_public_key": server_public_key,
                "expires_at": expires_at,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._lock:
            self._records[pairing_id] = record
        return PairingAdvertisement(pairing_id, code, server_public_key, expires_at, payload)

    def complete_pairing(self, pairing_id: str, code: str, client_public_key: str) -> PairingInfo:
        with self._lock:
            record = self._record(pairing_id)
            self._expire_if_needed(record)
            if record.state is PairingState.EXPIRED:
                raise RemotePairingError("expired", "pairing has expired")
            if record.state is not PairingState.PENDING:
                raise RemotePairingError("already_completed", "pairing is no longer pending")
            try:
                digest = hashlib.sha256(code.encode("ascii", "strict")).digest()
            except UnicodeEncodeError as exc:
                raise RemotePairingError("invalid_code", "pairing code is incorrect") from exc
            if not hmac.compare_digest(record.code_digest, digest):
                raise RemotePairingError("invalid_code", "pairing code is incorrect")
            try:
                client_key = _b64decode(client_public_key)
            except RemotePairingError as exc:
                raise RemotePairingError("invalid_public_key", "client public key is invalid") from exc
            if len(client_key) != 32:
                raise RemotePairingError("invalid_public_key", "X25519 public key must be 32 bytes")
            record.client_public_key = client_key
            record.shared_key = self._derive_key(record, client_key, pairing_id)
            record.state = PairingState.PAIRED
            return self._info(pairing_id, record)

    def get_info(self, pairing_id: str) -> PairingInfo:
        with self._lock:
            record = self._record(pairing_id)
            self._expire_if_needed(record)
            return self._info(pairing_id, record)

    def seal(self, pairing_id: str, plaintext: bytes) -> RelayEnvelope:
        with self._lock:
            record = self._paired_record(pairing_id)
            nonce = secrets.token_bytes(12)
            ciphertext = self._aead(record).encrypt(nonce, plaintext, pairing_id.encode())
            return RelayEnvelope(1, _b64encode(nonce), _b64encode(ciphertext))

    def open(self, pairing_id: str, envelope: RelayEnvelope) -> bytes:
        with self._lock:
            record = self._paired_record(pairing_id)
            if envelope.version != 1:
                raise RemotePairingError("invalid_envelope", "unsupported envelope version")
            nonce = _b64decode(envelope.nonce)
            ciphertext = _b64decode(envelope.ciphertext)
            if len(nonce) != 12:
                raise RemotePairingError("invalid_envelope", "nonce must be 12 bytes")
            try:
                return self._aead(record).decrypt(nonce, ciphertext, pairing_id.encode())
            except InvalidTag as exc:
                raise RemotePairingError("invalid_envelope", "authentication failed") from exc

    def enqueue(self, pairing_id: str, envelope: RelayEnvelope) -> int:
        with self._lock:
            _ = self.open(pairing_id, envelope)
            record = self._paired_record(pairing_id)
            assert record.queue is not None
            assert record.seen_nonces is not None
            if envelope.nonce in record.seen_nonces:
                raise RemotePairingError("replayed_envelope", "relay envelope nonce was already accepted")
            if len(record.queue) >= self._max_queue_size:
                raise RemotePairingError("relay_queue_full", "relay queue is full")
            record.queue.append(envelope)
            record.seen_nonces.add(envelope.nonce)
            return len(record.queue)

    def drain(self, pairing_id: str, limit: int = 100) -> tuple[RelayEnvelope, ...]:
        if not 1 <= limit <= 100:
            raise RemotePairingError("invalid_limit", "limit must be between 1 and 100")
        with self._lock:
            record = self._paired_record(pairing_id)
            assert record.queue is not None
            items = tuple(record.queue.popleft() for _ in range(min(limit, len(record.queue))))
            return items

    def rotate(self, pairing_id: str) -> PairingInfo:
        with self._lock:
            record = self._paired_record(pairing_id)
            assert record.client_public_key is not None
            record.private_key = X25519PrivateKey.generate()
            record.shared_key = self._derive_key(record, record.client_public_key, pairing_id)
            record.key_epoch += 1
            assert record.queue is not None
            record.queue.clear()
            assert record.seen_nonces is not None
            record.seen_nonces.clear()
            return self._info(pairing_id, record)

    def revoke(self, pairing_id: str) -> None:
        with self._lock:
            record = self._record(pairing_id)
            record.state = PairingState.REVOKED
            record.shared_key = None
            record.client_public_key = None
            if record.queue is not None:
                record.queue.clear()

    def _record(self, pairing_id: str) -> _PairingRecord:
        try:
            return self._records[pairing_id]
        except KeyError as exc:
            raise RemotePairingError("not_found", "pairing does not exist") from exc

    def _paired_record(self, pairing_id: str) -> _PairingRecord:
        record = self._record(pairing_id)
        self._expire_if_needed(record)
        if record.state is PairingState.REVOKED:
            raise RemotePairingError("revoked", "pairing has been revoked")
        if record.state is not PairingState.PAIRED or record.shared_key is None:
            raise RemotePairingError("not_paired", "pairing is not complete")
        return record

    def _expire_if_needed(self, record: _PairingRecord) -> None:
        if record.state is PairingState.PENDING and self._clock() >= record.expires_at:
            record.state = PairingState.EXPIRED

    def _info(self, pairing_id: str, record: _PairingRecord) -> PairingInfo:
        return PairingInfo(
            pairing_id,
            record.state,
            _b64encode(record.private_key.public_key().public_bytes_raw()),
            record.expires_at,
            record.key_epoch,
        )

    @staticmethod
    def _derive_key(record: _PairingRecord, client_key: bytes, pairing_id: str) -> bytes:
        shared = record.private_key.exchange(X25519PublicKey.from_public_bytes(client_key))
        return HKDF(
            algorithm=hashes.SHA256(), length=32, salt=pairing_id.encode(), info=b"antigravity-k-remote-relay-v1"
        ).derive(shared)

    @staticmethod
    def _aead(record: _PairingRecord) -> ChaCha20Poly1305:
        if record.shared_key is None:
            raise RemotePairingError("not_paired", "pairing key is unavailable")
        return ChaCha20Poly1305(record.shared_key)
