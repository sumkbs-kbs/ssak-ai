"""PanelActivityTracker — 에이전트/패널별 활동 상태 실시간 추적.

=============================================================
Sidabari의 useAppStore.ts → panelActivity/panelCurrentTool 패턴을 서버 사이드로 이식.

에이전트별로 thinking/idle 상태를 추적하고,
현재 실행 중인 도구 정보를 관리합니다.

대시보드 SSE/WebSocket 연동으로 실시간 가시성을 제공합니다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Protocol, TypedDict, cast, final

logger = logging.getLogger("antigravity_k.engine.panel_activity_tracker")


class _HookEventLike(Protocol):
    kind: str
    payload: Mapping[str, object]


class _ToolData(TypedDict):
    tool: str
    detail: str
    since: float
    elapsed_seconds: float


class _ActivityData(TypedDict, total=False):
    state: str
    since: float
    elapsed_seconds: float
    current_tool: _ToolData


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


@final
class PanelActivityState:
    """패널 활동 상태 상수 (Sidabari PanelActivityState enum)."""

    THINKING: str = "thinking"
    IDLE: str = "idle"


@final
class PanelActivity:
    """패널의 현재 활동 상태.

    Sidabari useAppStore.ts PanelActivity 구조체 이식.
    """

    __slots__ = ("since", "state")
    state: str
    since: float

    def __init__(self, state: str, since: float | None = None):
        """Initialize the PanelActivity.

        Args:
            state (str): str state.
            since (float | None): float | None since.

        """
        self.state = state
        self.since = since or time.time()

    def to_dict(self) -> _ActivityData:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "state": self.state,
            "since": self.since,
            "elapsed_seconds": round(time.time() - self.since, 1),
        }


@final
class PanelCurrentTool:
    """현재 실행 중인 도구 정보.

    Sidabari useAppStore.ts PanelCurrentTool 구조체 이식.
    """

    __slots__ = ("detail", "since", "tool")
    tool: str
    detail: str
    since: float

    def __init__(self, tool: str, detail: str, since: float | None = None):
        """Initialize the PanelCurrentTool.

        Args:
            tool (str): str tool.
            detail (str): str detail.
            since (float | None): float | None since.

        """
        self.tool = tool
        self.detail = detail
        self.since = since or time.time()

    def to_dict(self) -> _ToolData:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "tool": self.tool,
            "detail": self.detail,
            "since": self.since,
            "elapsed_seconds": round(time.time() - self.since, 1),
        }


@final
class PanelActivityTracker:
    """에이전트/패널별 활동 상태 추적기.

    Sidabari useAppStore.ts의 setPanelActivity / setPanelCurrentTool /
    clearPanelCurrentTool 패턴을 서버 사이드로 이식.
    """

    def __init__(self) -> None:
        """Initialize the PanelActivityTracker."""
        self._activities: dict[str, PanelActivity] = {}
        self._current_tools: dict[str, PanelCurrentTool] = {}
        self._lock: threading.Lock = threading.Lock()
        self._change_callbacks: list[Callable[..., object]] = []

    def set_activity(self, panel_id: str, state: str) -> bool:
        """패널 활동 상태를 설정합니다.

        같은 state 유지 시 since 갱신 X — 타이머가 흔들리지 않도록.
        (Sidabari setPanelActivity 패턴)

        Returns:
            상태가 변경되었으면 True

        """
        with self._lock:
            current = self._activities.get(panel_id)
            if current and current.state == state:
                return False

            self._activities[panel_id] = PanelActivity(state=state)

            # idle 전환 시 currentTool 클리어
            # (Sidabari: turn 종료 시 currentTool 정보는 의미 없음)
            if state == PanelActivityState.IDLE:
                _ = self._current_tools.pop(panel_id, None)

        self._notify_change(panel_id, "activity", state)
        return True

    def set_current_tool(self, panel_id: str, tool: str, detail: str = "") -> None:
        """현재 실행 중인 도구를 설정합니다.

        PreToolUse 시 호출. PostToolUse는 다음 PreToolUse가 갱신할 때까지
        유지하여 깜박임 방지 (Sidabari 패턴).
        """
        with self._lock:
            self._current_tools[panel_id] = PanelCurrentTool(tool=tool, detail=detail)
        self._notify_change(panel_id, "tool", tool)

    def clear_current_tool(self, panel_id: str) -> None:
        """현재 도구 정보를 클리어합니다.

        Stop 훅에서 호출 (Idle "Bash..." 표시 방지).
        """
        with self._lock:
            if panel_id not in self._current_tools:
                return
            del self._current_tools[panel_id]
        self._notify_change(panel_id, "tool_cleared", "")

    def get_activity(self, panel_id: str) -> PanelActivity | None:
        """특정 패널의 활동 상태를 반환합니다."""
        with self._lock:
            return self._activities.get(panel_id)

    def get_current_tool(self, panel_id: str) -> PanelCurrentTool | None:
        """특정 패널의 현재 도구를 반환합니다."""
        with self._lock:
            return self._current_tools.get(panel_id)

    def get_all_activities(self) -> dict[str, _ActivityData]:
        """모든 패널의 활동 상태를 반환합니다."""
        with self._lock:
            result: dict[str, _ActivityData] = {}
            for panel_id, activity in self._activities.items():
                entry = activity.to_dict()
                tool = self._current_tools.get(panel_id)
                if tool:
                    entry["current_tool"] = tool.to_dict()
                result[panel_id] = entry
            return result

    def get_thinking_panels(self) -> list[str]:
        """현재 thinking 상태인 패널 ID 목록을 반환합니다."""
        with self._lock:
            return [pid for pid, act in self._activities.items() if act.state == PanelActivityState.THINKING]

    def on_change(self, callback: Callable[..., object]) -> None:
        """상태 변경 시 호출할 콜백을 등록합니다."""
        self._change_callbacks.append(callback)

    def _notify_change(self, panel_id: str, change_type: str, value: str) -> None:
        """변경 알림을 콜백들에게 전달합니다."""
        for callback in self._change_callbacks:
            try:
                _ = callback(
                    panel_id=panel_id,
                    change_type=change_type,
                    value=value,
                )
            except Exception:
                logger.exception("[PanelActivityTracker] 콜백 오류")

    # ── EventBus 연동 헬퍼 ──

    def handle_hook_event(self, event: _HookEventLike) -> None:
        """HookEventEmit를 받아 활동 상태를 자동 업데이트합니다.

        Sidabari HookBridge.tsx의 switch(kind) 로직 이식.
        """
        kind = event.kind
        payload = _mapping(event.payload)
        panel_id = ""

        # _antigravity 메타데이터에서 panel_id 추출
        meta = _mapping(payload.get("_antigravity", {}))
        panel_id = _text(meta.get("panel_id"))
        if not panel_id:
            panel_id = _text(payload.get("panel_id"), "default")

        if kind == "stop" or kind == "agent-turn-end":
            _ = self.set_activity(panel_id, PanelActivityState.IDLE)
            self.clear_current_tool(panel_id)

        elif kind == "session-start" or kind == "agent-turn-start":
            _ = self.set_activity(panel_id, PanelActivityState.THINKING)

        elif kind == "pretool" or kind == "tool-exec-start":
            _ = self.set_activity(panel_id, PanelActivityState.THINKING)
            tool_name = _text(payload.get("tool_name"))
            if tool_name:
                detail = self._summarize_tool(payload)
                self.set_current_tool(panel_id, tool_name, detail)

        elif kind in ("posttool", "tool-exec-finish", "user-prompt"):
            _ = self.set_activity(panel_id, PanelActivityState.THINKING)
            # currentTool은 다음 PreToolUse까지 유지 (깜박임 방지)

    @staticmethod
    def _summarize_tool(payload: Mapping[str, object]) -> str:
        """도구 호출에 대한 사용자 가시 요약을 생성합니다.

        Sidabari HookBridge.tsx의 summary() 함수 이식.
        """
        tool_name = _text(payload.get("tool_name"))
        tool_input = _mapping(payload.get("tool_input", {}))

        if tool_input:
            command = _text(tool_input.get("command"))
            if command:
                truncated = command[:80] + ("..." if len(command) > 80 else "")
                return f"{tool_name}: {truncated}"

            file_path = _text(tool_input.get("file_path"))
            if file_path:
                return f"{tool_name}: {file_path}"

        if tool_name:
            return tool_name

        notification_type = _text(payload.get("notification_type"))
        if notification_type:
            return notification_type

        return ""


# ── 글로벌 싱글톤 ──

_global_tracker: PanelActivityTracker | None = None
_global_lock = threading.Lock()


def get_panel_activity_tracker() -> PanelActivityTracker:
    """글로벌 PanelActivityTracker 인스턴스를 반환합니다."""
    global _global_tracker
    if _global_tracker is None:
        with _global_lock:
            if _global_tracker is None:
                _global_tracker = PanelActivityTracker()
    return _global_tracker


def init_panel_activity_tracker() -> PanelActivityTracker:
    """글로벌 PanelActivityTracker를 초기화하고 HookEventBus에 연결합니다."""
    tracker = get_panel_activity_tracker()

    try:
        from antigravity_k.engine.hook_event_bus import get_hook_event_bus

        hook_bus = get_hook_event_bus()
        initialized = getattr(hook_bus, "_initialized", False)
        if isinstance(initialized, bool) and initialized:
            hook_bus.subscribe_all(tracker.handle_hook_event)
            logger.info("[PanelActivityTracker] HookEventBus에 연결 완료")
    except ImportError:
        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
    except Exception:
        logger.exception("[PanelActivityTracker] HookEventBus 연결 실패")

    return tracker
