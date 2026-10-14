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
