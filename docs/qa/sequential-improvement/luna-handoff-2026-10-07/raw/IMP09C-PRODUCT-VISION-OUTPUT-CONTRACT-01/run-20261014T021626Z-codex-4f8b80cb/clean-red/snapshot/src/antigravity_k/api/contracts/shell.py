"""CR-04 동기 shell 실행 경계 오류 계약 (HTTP 코드·error_code 고정).

``POST /api/agent/tools/shell/run``은 실행 전에 현재 권한 모드의 결정을 확인한다.
이 파일은 그 결정의 wire 어휘를 한 곳에 고정한다 — 정책 거부(403), 승인 필요(403),
sandbox 불가(503), timeout(504)을 상태 코드로 구분하고, 내부 경로·실행 환경은
``detail``에 넣지 않는다.
"""

from __future__ import annotations

from typing import Final

from antigravity_k.api.error_handler import APIError

SHELL_ERROR_HTTP_STATUS: Final[dict[str, int]] = {
    "shell_approval_required": 403,
    "shell_policy_denied": 403,
    "sandbox_unavailable": 503,
    "shell_timeout": 504,
}


class ShellBoundaryError(APIError):
    """Base class for CR-04 shell execution boundary failures."""

    status_code: int = 403
    error_code: str = "shell_policy_denied"
    detail: str = "Shell execution was denied by policy"


class ShellApprovalRequiredError(ShellBoundaryError):
    """현재 권한 모드의 결정이 ASK(prompt) — 승인 workflow 없이는 실행하지 않는다."""

    status_code: int = 403
    error_code: str = "shell_approval_required"
    detail: str = "Shell execution requires explicit approval in the current permission mode"


class ShellPolicyDeniedError(ShellBoundaryError):
    """현재 권한 모드의 결정이 DENY — 위험 명령/경계 밖 경로/차단 도구."""

    status_code: int = 403
    error_code: str = "shell_policy_denied"
    detail: str = "Shell execution was denied by policy"


class ShellSandboxUnavailableError(ShellBoundaryError):
    """OS sandbox를 적용할 수 없다 — raw host 실행으로 대체하지 않는다."""

    status_code: int = 503
    error_code: str = "sandbox_unavailable"
    detail: str = "OS sandbox is unavailable; shell execution is refused"


class ShellTimeoutError(ShellBoundaryError):
    """명령 자체는 실행됐지만 제한 시간을 넘겼다(정책 거부와 구분)."""

    status_code: int = 504
    error_code: str = "shell_timeout"
    detail: str = "Shell command exceeded the execution time limit"


__all__ = [
    "SHELL_ERROR_HTTP_STATUS",
    "ShellApprovalRequiredError",
    "ShellBoundaryError",
    "ShellPolicyDeniedError",
    "ShellSandboxUnavailableError",
    "ShellTimeoutError",
]
