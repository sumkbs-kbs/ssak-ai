"""Public value objects and typed errors for remote pairing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class RemotePairingError(Exception):
    """Typed boundary error for pairing and relay operations."""

    def __init__(self, code: str, message: str) -> None:
        self.code: str = code
        super().__init__(f"{code}: {message}")


class PairingState(StrEnum):
    PENDING = "pending"
    PAIRED = "paired"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PairingAdvertisement:
    pairing_id: str
    code: str
    server_public_key: str
    expires_at: float
    qr_payload: str


@dataclass(frozen=True, slots=True)
class PairingInfo:
    pairing_id: str
    state: PairingState
    server_public_key: str
    expires_at: float
    key_epoch: int


@dataclass(frozen=True, slots=True)
class RelayEnvelope:
    version: int
    nonce: str
    ciphertext: str

    def to_dict(self) -> dict[str, object]:
        return {"version": self.version, "nonce": self.nonce, "ciphertext": self.ciphertext}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RelayEnvelope:
        version = value.get("version")
        nonce = value.get("nonce")
        ciphertext = value.get("ciphertext")
        if not isinstance(version, int) or isinstance(version, bool):
            raise RemotePairingError("invalid_envelope", "version must be an integer")
        if not isinstance(nonce, str) or not isinstance(ciphertext, str):
            raise RemotePairingError("invalid_envelope", "nonce and ciphertext are required")
        return cls(version=version, nonce=nonce, ciphertext=ciphertext)
