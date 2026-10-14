"""Native provider transport failures, safe to expose at API boundaries."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, NotRequired, TypedDict, assert_never


class TransportFailure(StrEnum):
    HTTP = "upstream_http_error"
    UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "provider_timeout"


class TransportErrorDetail(TypedDict):
    type: str
    code: str
    message: str
    upstream_status: NotRequired[int]


@dataclass(slots=True)
class NativeTransportError(RuntimeError):
    failure: TransportFailure
    upstream_status: int | None = None

    def __str__(self) -> str:
        match self.failure:
            case TransportFailure.HTTP:
                return "The model provider returned an unsuccessful HTTP response."
            case TransportFailure.UNAVAILABLE:
                return "The model provider is unavailable."
            case TransportFailure.TIMEOUT:
                return "The model provider request timed out."
            case unreachable:
                assert_never(unreachable)

    @property
    def status_code(self) -> int:
        match self.failure:
            case TransportFailure.HTTP:
                return 502
            case TransportFailure.UNAVAILABLE:
                return 503
            case TransportFailure.TIMEOUT:
                return 504
            case unreachable:
                assert_never(unreachable)

    def detail(self) -> TransportErrorDetail:
        result: TransportErrorDetail = {
            "type": "provider_transport_error",
            "code": self.failure.value,
            "message": str(self),
        }
        if self.upstream_status is not None:
            result["upstream_status"] = self.upstream_status
        return result


@dataclass(slots=True)
class NativeProtocolError(RuntimeError):
    code: Literal["invalid_stream", "upstream_stream_error", "incomplete_stream"]

    def __str__(self) -> str:
        return "The model provider returned an invalid or incomplete stream."

    def detail(self) -> TransportErrorDetail:
        return {"type": "provider_protocol_error", "code": self.code, "message": str(self)}
