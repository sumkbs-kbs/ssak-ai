"""QR pairing and opaque encrypted relay HTTP contract."""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.remote_pairing import (
    PairingAdvertisement,
    PairingInfo,
    PairingManager,
    RelayEnvelope,
    RemotePairingError,
)

router = APIRouter(prefix="/api/remote/pairing")
_manager = PairingManager()


class CreatePairingRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    ttl_seconds: int = Field(default=300, ge=30, le=900)


class PairingAdvertisementResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    pairing_id: str
    code: str
    server_public_key: str
    expires_at: float
    qr_payload: str


class CompletePairingRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    pairing_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=8, max_length=8)
    client_public_key: str = Field(min_length=40, max_length=64)


class PairingIdRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    pairing_id: str = Field(min_length=1, max_length=128)


class PairingInfoResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    pairing_id: str
    state: str
    server_public_key: str
    expires_at: float
    key_epoch: int


class RelayEnvelopeModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1, le=1)
    nonce: str = Field(min_length=16, max_length=24)
    ciphertext: str = Field(min_length=24, max_length=1_000_000)

    def to_engine(self) -> RelayEnvelope:
        return RelayEnvelope(self.version, self.nonce, self.ciphertext)

    @classmethod
    def from_engine(cls, envelope: RelayEnvelope) -> RelayEnvelopeModel:
        return cls.model_validate(envelope.to_dict())


class RelayMessageRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    pairing_id: str = Field(min_length=1, max_length=128)
    envelope: RelayEnvelopeModel


class RelayPollRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    pairing_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=100, ge=1, le=100)


class RelayPollResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    pairing_id: str
    envelopes: tuple[RelayEnvelopeModel, ...]


def get_pairing_manager() -> PairingManager:
    return _manager


def _info_response(info: PairingInfo) -> PairingInfoResponse:
    return PairingInfoResponse(
        pairing_id=info.pairing_id,
        state=info.state.value,
        server_public_key=info.server_public_key,
        expires_at=info.expires_at,
        key_epoch=info.key_epoch,
    )


def _advertisement_response(value: PairingAdvertisement) -> PairingAdvertisementResponse:
    return PairingAdvertisementResponse(
        pairing_id=value.pairing_id,
        code=value.code,
        server_public_key=value.server_public_key,
        expires_at=value.expires_at,
        qr_payload=value.qr_payload,
    )


def _audit(action: str, pairing_id: str, info: PairingInfo | None = None) -> None:
    details: dict[str, object] = {"pairing_id": pairing_id, "action": action}
    if info is not None:
        details["key_epoch"] = info.key_epoch
        details["state"] = info.state.value
    get_audit_logger().log_event("remote_pairing", details)


def _http_error(exc: RemotePairingError) -> HTTPException:
    code = exc.code
    status_code = {
        "not_found": status.HTTP_404_NOT_FOUND,
        "expired": status.HTTP_410_GONE,
        "revoked": status.HTTP_410_GONE,
        "already_completed": status.HTTP_409_CONFLICT,
        "not_paired": status.HTTP_409_CONFLICT,
        "relay_queue_full": status.HTTP_429_TOO_MANY_REQUESTS,
        "invalid_ttl": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_limit": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail={"code": code, "message": str(exc)})


@router.post("", response_model=PairingAdvertisementResponse, status_code=status.HTTP_201_CREATED)
async def create_pairing(request: CreatePairingRequest) -> PairingAdvertisementResponse:
    try:
        advertisement = _manager.create_pairing(request.ttl_seconds)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    _audit("created", advertisement.pairing_id)
    return _advertisement_response(advertisement)


@router.post("/complete", response_model=PairingInfoResponse)
async def complete_pairing(request: CompletePairingRequest) -> PairingInfoResponse:
    try:
        info = _manager.complete_pairing(request.pairing_id, request.code, request.client_public_key)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    _audit("completed", request.pairing_id, info)
    return _info_response(info)


@router.post("/rotate", response_model=PairingInfoResponse)
async def rotate_pairing(request: PairingIdRequest) -> PairingInfoResponse:
    try:
        info = _manager.rotate(request.pairing_id)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    _audit("rotated", request.pairing_id, info)
    return _info_response(info)


@router.post("/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_pairing(request: PairingIdRequest) -> None:
    try:
        _manager.revoke(request.pairing_id)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    _audit("revoked", request.pairing_id)


@router.post("/relay", status_code=status.HTTP_202_ACCEPTED)
async def relay_message(request: RelayMessageRequest) -> dict[str, object]:
    try:
        depth = _manager.enqueue(request.pairing_id, request.envelope.to_engine())
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    return {"accepted": True, "queue_depth": depth}


@router.post("/relay/poll", response_model=RelayPollResponse)
async def poll_relay(request: RelayPollRequest) -> RelayPollResponse:
    try:
        envelopes = _manager.drain(request.pairing_id, request.limit)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    return RelayPollResponse(
        pairing_id=request.pairing_id,
        envelopes=tuple(RelayEnvelopeModel.from_engine(envelope) for envelope in envelopes),
    )


@router.get("/{pairing_id}", response_model=PairingInfoResponse)
async def pairing_info(pairing_id: str) -> PairingInfoResponse:
    try:
        info = _manager.get_info(pairing_id)
    except RemotePairingError as exc:
        raise _http_error(exc) from exc
    return _info_response(info)
