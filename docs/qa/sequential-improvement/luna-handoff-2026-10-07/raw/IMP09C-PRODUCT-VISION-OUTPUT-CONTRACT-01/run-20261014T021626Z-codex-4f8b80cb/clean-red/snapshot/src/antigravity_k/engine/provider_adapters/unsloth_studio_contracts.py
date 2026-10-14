from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address
from typing import ClassVar, override
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, field_validator

DEFAULT_UNSLOTH_STUDIO_ENDPOINT = "http://127.0.0.1:8888/mcp/"
UNSLOTH_STUDIO_WRITE_TOOLS_ENV = "UNSLOTH_STUDIO_WRITE_TOOLS_ENABLED"


class UnslothStudioConfigurationError(ValueError):
    pass


class UnslothStudioReadTool(StrEnum):
    STATUS = "studio_status"
    MODELS = "list_local_models"
    TRAINING_STATUS = "get_training_status"
    TRAINING_RUNS = "list_training_runs"


UNSLOTH_STUDIO_READ_TOOLS: tuple[UnslothStudioReadTool, ...] = (
    UnslothStudioReadTool.STATUS,
    UnslothStudioReadTool.MODELS,
    UnslothStudioReadTool.TRAINING_STATUS,
    UnslothStudioReadTool.TRAINING_RUNS,
)


def normalize_unsloth_mcp_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnslothStudioConfigurationError(
            "Unsloth Studio MCP endpoint must be an HTTP(S) URL.",
        )
    if parsed.username or parsed.password:
        raise UnslothStudioConfigurationError(
            "Unsloth Studio MCP endpoint must not contain credentials.",
        )
    if parsed.query or parsed.fragment:
        raise UnslothStudioConfigurationError(
            "Unsloth Studio MCP endpoint must not contain query or fragment data.",
        )
    if parsed.path not in {"/mcp", "/mcp/"}:
        raise UnslothStudioConfigurationError(
            "Unsloth Studio MCP endpoint path must be /mcp/.",
        )

    host = parsed.hostname.lower()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise UnslothStudioConfigurationError(
            "Unsloth Studio MCP endpoint must use a loopback host.",
        )

    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "/mcp/", "", ""))


class UnslothStudioSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    endpoint: str = DEFAULT_UNSLOTH_STUDIO_ENDPOINT
    token: SecretStr | None = None
    timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    write_tools_enabled: bool = False

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        return normalize_unsloth_mcp_url(value)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise UnslothStudioConfigurationError(
                "Unsloth Studio MCP token must not be blank.",
            )
        return value

    @property
    def configured(self) -> bool:
        return self.token is not None

    @classmethod
    def from_env(cls) -> UnslothStudioSettings:
        raw_token = os.environ.get("UNSLOTH_STUDIO_MCP_TOKEN")
        raw_write_tools = os.environ.get(UNSLOTH_STUDIO_WRITE_TOOLS_ENV, "false").strip().lower()
        if raw_write_tools not in {"0", "1", "false", "true"}:
            raise UnslothStudioConfigurationError(
                f"{UNSLOTH_STUDIO_WRITE_TOOLS_ENV} must be true, false, 1, or 0.",
            )
        return cls(
            endpoint=os.environ.get(
                "UNSLOTH_STUDIO_MCP_URL",
                DEFAULT_UNSLOTH_STUDIO_ENDPOINT,
            ),
            token=SecretStr(raw_token) if raw_token is not None else None,
            write_tools_enabled=raw_write_tools in {"1", "true"},
        )


class UnslothStudioToolResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    tool: UnslothStudioReadTool
    ok: bool
    data: JsonValue | None = None
    error: str | None = None


class UnslothStudioSnapshot(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    configured: bool
    available: bool
    endpoint: str
    allowed_tools: tuple[UnslothStudioReadTool, ...]
    available_tools: tuple[UnslothStudioReadTool, ...] = ()
    results: tuple[UnslothStudioToolResult, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class UnslothStudioPermissionDenied(Exception):
    tool: UnslothStudioReadTool
    source: str

    @override
    def __str__(self) -> str:
        return f"Permission denied for Unsloth Studio read tool: {self.tool.value}"
