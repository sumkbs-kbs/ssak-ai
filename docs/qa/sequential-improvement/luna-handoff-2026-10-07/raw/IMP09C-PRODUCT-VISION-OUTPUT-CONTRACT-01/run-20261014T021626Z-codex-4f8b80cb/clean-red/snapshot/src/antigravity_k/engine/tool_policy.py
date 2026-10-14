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
from dataclasses import dataclass, field

from antigravity_k.tools.base_tool import RiskLevel


@dataclass(frozen=True)
class ToolPolicy:
    """요청 단위 도구 허용 정책."""

    denied_tools: frozenset[str] = field(default_factory=frozenset)
    allowed_mcp_servers: frozenset[str] | None = None
    safe_only: bool = False
    """True면 risk_level != SAFE(부작용 있는) 도구를 모두 차단한다(읽기 전용 모드)."""


_tool_policy_var: contextvars.ContextVar[ToolPolicy | None] = contextvars.ContextVar("agk_tool_policy", default=None)


def set_tool_policy(policy: ToolPolicy | None) -> contextvars.Token[ToolPolicy | None]:
    """Set the request-scoped tool policy. Returns a token for :func:`reset_tool_policy`."""
    return _tool_policy_var.set(policy)


def reset_tool_policy(token: contextvars.Token[ToolPolicy | None]) -> None:
    """Restore the previous tool policy captured by :func:`set_tool_policy`."""
    _tool_policy_var.reset(token)


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
