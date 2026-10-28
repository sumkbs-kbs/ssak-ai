"""실행 권한 모드(전체 액세스 / 읽기 전용) 공유 상태.

대시보드 컴포저의 전체 액세스 토글이 저장하는 모드를 애플리케이션 전역에서
공유하기 위한 최소 모듈. ``system_api``가 저장하고, ``chat`` 라우트가
읽어 요청 단위 :class:`~antigravity_k.engine.tool_executor.ToolPolicy`
(safe_only)로 변환한다. 프로세스 메모리 상태이며 재시작 시 초기화된다.
"""

from __future__ import annotations

from enum import Enum


class AccessMode(str, Enum):
    """실행 권한 수준."""

    FULL_ACCESS = "full_access"
    READ_ONLY = "read_only"

    @property
    def label(self) -> str:
        """사용자 노출 한글 라벨."""
        return "전체 액세스" if self is AccessMode.FULL_ACCESS else "읽기 전용"


_current_mode: AccessMode = AccessMode.FULL_ACCESS


def get_access_mode() -> AccessMode:
    """현재 실행 권한 모드를 반환한다."""
    return _current_mode


def set_access_mode(mode: AccessMode) -> None:
    """실행 권한 모드를 저장한다."""
    global _current_mode
    _current_mode = mode


def parse_access_mode(value: object) -> AccessMode | None:
    """문자열 등 외부 입력을 :class:`AccessMode`로 변환한다(미지원 값은 None)."""
    if isinstance(value, AccessMode):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("read_only", "restricted", "readonly", "safe"):
            return AccessMode.READ_ONLY
        if normalized in ("full_access", "full", "unrestricted"):
            return AccessMode.FULL_ACCESS
        try:
            return AccessMode(value)
        except ValueError:
            return None
    return None


# ─── r39: 무인 실행 정책(auto-pilot)은 파일 접근 범위(AccessMode)와 별개다 ────────
#
# 계약 변경(r39, 숨기지 않음): 이전에는 FULL_ACCESS(기본값)가 곧 auto-pilot(셸·쓰기 등
# medium/high 위험 도구 무인 자동 승인)을 뜻했다. 이제 FULL_ACCESS는 파일 접근 범위만
# 뜻하고, 무인 실행은 아래 ExecutionPolicy로 따로 정한다. 기본값은 BALANCED(medium/high는
# 승인 요청)이며 AUTO_PILOT은 사용자가 명시적으로 선택했을 때만 적용된다:
#   * POST /api/system/execution-policy {"policy": "auto-pilot"} (프로세스 메모리, 재시작 시 초기화)
#   * 또는 서버 시작 환경변수 AGK_EXECUTION_POLICY=auto-pilot (사용자가 직접 설정한 경우)
# 사용자 전역 설정 파일은 읽거나 바꾸지 않는다. READ_ONLY에서는 AUTO_PILOT을 골라도 balanced다.


class ExecutionPolicy(str, Enum):
    """사용자 승인 없이 실행할 수 있는지에 관한 정책."""

    BALANCED = "balanced"
    AUTO_PILOT = "auto-pilot"

    @property
    def label(self) -> str:
        """사용자 노출 한글 라벨."""
        return "무인 자동 승인(auto-pilot)" if self is ExecutionPolicy.AUTO_PILOT else "승인 필요(balanced)"


EXECUTION_POLICY_ENV = "AGK_EXECUTION_POLICY"
_explicit_policy: ExecutionPolicy | None = None


def parse_execution_policy(value: object) -> ExecutionPolicy | None:
    """외부 입력을 :class:`ExecutionPolicy`로 변환한다(미지원 값은 None)."""
    if isinstance(value, ExecutionPolicy):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", "-")
        if normalized in ("auto-pilot", "autopilot"):
            return ExecutionPolicy.AUTO_PILOT
        if normalized == "balanced":
            return ExecutionPolicy.BALANCED
    return None


def get_execution_policy() -> ExecutionPolicy:
    """명시 선택(API) > 환경변수 명시 선택 > 기본 BALANCED."""
    if _explicit_policy is not None:
        return _explicit_policy
    import os

    return parse_execution_policy(os.environ.get(EXECUTION_POLICY_ENV, "")) or ExecutionPolicy.BALANCED


def set_execution_policy(policy: ExecutionPolicy | None) -> None:
    """사용자의 명시적 선택을 저장한다(None이면 해제 → 환경변수/기본값으로 복귀)."""
    global _explicit_policy
    _explicit_policy = policy


def effective_permission_mode() -> str:
    """현재 AccessMode·ExecutionPolicy → PermissionGate 모드 문자열."""
    if get_access_mode() is AccessMode.READ_ONLY:
        return ExecutionPolicy.BALANCED.value
    return get_execution_policy().value
