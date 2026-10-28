"""요청 단위 도구 허용 정책 (ToolPolicy).

대시보드 컴포저의 Search/Code/MCP 칩 상태와 실행 권한 모드(읽기 전용)를 채팅 요청에
반영하기 위해 ``chat`` 라우트가 설정하고 ``ToolExecutor.execute`` 가 조회한다.
contextvar 기반이므로 요청 스레드풀 컨텍스트 안에서만 유효하다.

엔진(`tool_executor`)에서 분리한 이유: 도구 계층(MCP 도구)도 호출 직전에 **같은 규칙**을
재확인해야 하는데, 도구가 `tool_executor` 를 import 하면 `tool_executor → mcp_tool_loader`
(지연 import)와 맞물려 import 순환이 생긴다. 정책은 어느 쪽도 아닌 잎 모듈에 둔다.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated, Final, TypedDict

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictStr, ValidationError

from antigravity_k.tools.base_tool import RiskLevel


@dataclass(frozen=True)
class ToolPolicy:
    """요청 단위 도구 허용 정책."""

    denied_tools: frozenset[str] = field(default_factory=frozenset)
    allowed_mcp_servers: frozenset[str] | None = None
    safe_only: bool = False
    """True면 risk_level != SAFE(부작용 있는) 도구를 모두 차단한다(읽기 전용 모드)."""


_tool_policy_var: contextvars.ContextVar[ToolPolicy | None] = contextvars.ContextVar("agk_tool_policy", default=None)
REQUEST_TOOL_POLICY_KEY: Final = "_request_tool_policy"


class ToolPolicySnapshot(TypedDict):
    version: int
    denied_tools: list[str]
    allowed_mcp_servers: list[str] | None
    safe_only: bool


class _StoredToolPolicy(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    denied_tools: list[StrictStr]
    allowed_mcp_servers: list[StrictStr] | None
    safe_only: StrictBool


class InvalidToolPolicySnapshotError(ValueError):
    def __init__(self) -> None:
        super().__init__("Stored request tool policy is invalid.")


def get_tool_policy() -> ToolPolicy | None:
    """Return the immutable policy bound by the server for this execution."""
    return _tool_policy_var.get()


def snapshot_tool_policy() -> ToolPolicySnapshot:
    """Capture server authority independently of client or model task context."""
    return serialize_tool_policy(get_tool_policy() or ToolPolicy())


def serialize_tool_policy(policy: ToolPolicy) -> ToolPolicySnapshot:
    """Serialize a server-resolved policy without losing an empty MCP selection."""
    return {
        "version": 1,
        "denied_tools": sorted(policy.denied_tools),
        "allowed_mcp_servers": None if policy.allowed_mcp_servers is None else sorted(policy.allowed_mcp_servers),
        "safe_only": policy.safe_only,
    }


def narrow_tool_policy(saved: ToolPolicy, current: ToolPolicy | None) -> ToolPolicy:
    """Intersect permissions; a later request can add restrictions, never lift them."""
    if current is None:
        return saved
    servers = saved.allowed_mcp_servers
    if servers is None:
        servers = current.allowed_mcp_servers
    elif current.allowed_mcp_servers is not None:
        servers = servers & current.allowed_mcp_servers
    return ToolPolicy(
        denied_tools=saved.denied_tools | current.denied_tools,
        allowed_mcp_servers=servers,
        safe_only=saved.safe_only or current.safe_only,
    )


def parse_tool_policy_snapshot(raw: JsonValue) -> ToolPolicy:
    """Reject malformed saved authority rather than infer a weaker policy."""
    try:
        saved = _StoredToolPolicy.model_validate(raw)
    except ValidationError as error:
        raise InvalidToolPolicySnapshotError from error
    return ToolPolicy(
        denied_tools=frozenset(saved.denied_tools),
        allowed_mcp_servers=None if saved.allowed_mcp_servers is None else frozenset(saved.allowed_mcp_servers),
        safe_only=saved.safe_only,
    )


def set_tool_policy(policy: ToolPolicy | None) -> contextvars.Token[ToolPolicy | None]:
    """Set the request-scoped tool policy. Returns a token for :func:`reset_tool_policy`."""
    return _tool_policy_var.set(policy)


def reset_tool_policy(token: contextvars.Token[ToolPolicy | None]) -> None:
    """Restore the previous tool policy captured by :func:`set_tool_policy`."""
    _tool_policy_var.reset(token)


@contextmanager
def bind_tool_policy(policy: ToolPolicy | None) -> Iterator[None]:
    """Bind saved authority for a worker and restore its ambient context on exit."""
    token = set_tool_policy(policy)
    try:
        yield
    finally:
        reset_tool_policy(token)


def request_allows_side_effects() -> bool:
    policy = _tool_policy_var.get()
    return policy is None or not policy.safe_only


def _request_toggle_denial(policy: ToolPolicy, name: str, server_name: str) -> str | None:
    """사용자가 요청 단위로 끄는 두 스위치(도구 토글·MCP 서버 선택)를 판정한다.

    `ToolExecutor.execute` 와 도구 자기검증(`mcp_server_policy_denial`)이 **같은 규칙**을
    쓰도록 한 곳에 모은다 — 두 벌로 갈라지면 한쪽만 고쳐져 우회 경로가 생긴다.
    """
    if name in policy.denied_tools:
        return f"Tool '{name}' is disabled for this request by the user's tool toggles."
    if policy.allowed_mcp_servers is not None and server_name and server_name not in policy.allowed_mcp_servers:
        return f"MCP server '{server_name}' is disabled for this request by the user's MCP selection."
    return None


def mcp_server_policy_denial(name: str, server_name: str) -> str | None:
    """MCP 도구 호출이 요청 단위 정책을 통과하는지 도구 쪽에서 다시 확인한다.

    `ToolExecutor.execute` 는 이 검사를 하지만 승인 실행 경로(`execute_approved` →
    `execute_with_permission`)는 지나가지 않는다. 서버 허용 목록은 사용자 요청 단위
    약속이므로 MCP 도구가 호출 직전에 같은 규칙을 스스로 재확인한다(심층 방어).
    read-only(`safe_only`)는 여기서 판정하지 않는다 — 승인 프롬프트로 명시 동의한
    실행을 도구가 되돌리면 사용자 의도를 뒤집게 되기 때문이다.
    """
    policy = _tool_policy_var.get()
    if policy is None:
        return None
    return _request_toggle_denial(policy, name, server_name)


def tool_policy_denial(name: str, tool: object | None) -> str | None:
    """Return a denial message when the active policy blocks this tool, else None."""
    policy = _tool_policy_var.get()
    if policy is None:
        return None
    toggle_denial = _request_toggle_denial(policy, name, str(getattr(tool, "_server_name", "") or ""))
    if toggle_denial is not None:
        return toggle_denial
    if policy.safe_only and tool is not None:
        risk_level = getattr(tool, "risk_level", None)
        if risk_level is not None and risk_level != RiskLevel.SAFE:
            risk_value = getattr(risk_level, "value", risk_level)
            return f"Tool '{name}' has side effects (risk: {risk_value}) and is blocked in read-only mode."
    return None
