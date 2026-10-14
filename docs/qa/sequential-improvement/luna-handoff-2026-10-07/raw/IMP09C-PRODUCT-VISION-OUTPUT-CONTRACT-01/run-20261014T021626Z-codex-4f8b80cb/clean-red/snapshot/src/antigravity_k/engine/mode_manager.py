"""Mode Manager — Plan/Build/Interactive 실행 모드 관리자.

========================================================
Phase 1: ModeManager가 실행 모드 전이, 검증, 자동 전환을 총괄합니다.

핵심 책임:
- 현재 모드 상태 유지 및 전환 (Plan → Build → Interactive)
- Plan → Build 자동 전환 (Plan 아티팩트 검증 완료 시)
- GatePipeline + ShieldsManager 연동
- 모드 변경 이벤트 브로드캐스트 (Dashboard 실시간 반영)
- 모드별 허용 도구 목록 관리
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from antigravity_k.engine.execution_mode import ExecutionMode

logger = logging.getLogger(__name__)


# ─── 모드 전이 기록 ─────────────────────────────────────────────────


@dataclass
class ModeTransition:
    """모드 전이 기록."""

    from_mode: str
    to_mode: str
    reason: str
    timestamp: str
    plan_artifact_path: str | None = None


# ─── 모드 이벤트 핸들러 타입 ────────────────────────────────────────

ModeChangeHandler = Callable[[ExecutionMode, ExecutionMode, str], None]


# ─── 메인 관리자 ──────────────────────────────────────────────────────


class ModeManager:
    """실행 모드 관리자.

    사용법:
        mgr = ModeManager()
        mgr.switch_to_plan("대규모 리팩토링 필요")
        mgr.switch_to_build()  # Plan 검증 후 자동 전환
        mgr.current_mode  # 현재 모드 확인
    """

    # 강제 plan이 필요한 태스크 키워드 (CEO 분석 결과와 연동)
    PLAN_TRIGGER_KEYWORDS: frozenset[str] = frozenset(
        {
            "architecture",
            "refactor",
            "migrate",
            "redesign",
            "framework",
            "아키텍처",
            "리팩토링",
            "마이그레이션",
            "대규모",
            "전면",
            "구조개선",
            "재설계",
        },
    )

    def __init__(self, initial_mode: ExecutionMode = ExecutionMode.INTERACTIVE):
        """Initialize the ModeManager.

        Args:
            initial_mode: 초기 실행 모드 (기본값: INTERACTIVE)
        """
        self._mode: ExecutionMode = initial_mode
        self._history: list[ModeTransition] = []
        self._listeners: list[ModeChangeHandler] = []

        # Plan→Build 자동 전환 조건
        self._auto_transition_enabled: bool = True
        self._plan_artifact_path: str | None = None
        self._plan_quality_passed: bool = False

        logger.info("[ModeManager] 초기화 완료 (mode=%s)", initial_mode.value)

    # ─── 속성 ───────────────────────────────────────────────────────

    @property
    def current_mode(self) -> ExecutionMode:
        """현재 실행 모드."""
        return self._mode

    @property
    def is_plan(self) -> bool:
        """Plan 모드 여부."""
        return self._mode == ExecutionMode.PLAN

    @property
    def is_build(self) -> bool:
        """Build 모드 여부."""
        return self._mode == ExecutionMode.BUILD

    @property
    def is_interactive(self) -> bool:
        """Interactive 모드 여부."""
        return self._mode == ExecutionMode.INTERACTIVE

    @property
    def plan_artifact_path(self) -> str | None:
        """현재 Plan 아티팩트 경로."""
        return self._plan_artifact_path

    @property
    def plan_quality_passed(self) -> bool:
        """Plan 품질 검증 통과 여부."""
        return self._plan_quality_passed

    @property
    def mode_history(self) -> list[ModeTransition]:
        """모드 전이 이력."""
        return list(self._history)

    # ─── 모드 전환 API ──────────────────────────────────────────────

    def switch_to_plan(self, reason: str = "") -> bool:
        """Plan 모드로 전환합니다.

        Args:
            reason: 전환 사유

        Returns:
            전환 성공 여부
        """
        if self._mode == ExecutionMode.PLAN:
            logger.debug("[ModeManager] 이미 PLAN 모드입니다.")
            return True

        previous = self._mode
        self._mode = ExecutionMode.PLAN
        self._plan_artifact_path = None
        self._plan_quality_passed = False

        self._record_transition(previous, ExecutionMode.PLAN, reason)
        self._notify_listeners(previous, ExecutionMode.PLAN, reason)
        self._publish_planning_started(reason)
        logger.info("[ModeManager] PLAN 모드 전환: %s", reason or "사용자 요청")
        return True

    def _publish_planning_started(self, reason: str) -> None:
        """EventBus로 PlanningModeStarted 이벤트를 발행합니다.

        Dashboard WebSocket(useEventWebSocket)이 이 이벤트를 수신하여
        에이전트 모니터링 패널에 계획 모드 시작 로그/타임라인을 표시합니다.
        이벤트 버스 발행은 선택적(non-critical)이므로 실패해도 모드 전환은 계속됩니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            global_event_bus.publish("PlanningModeStarted", goal=reason or "")
        except Exception:
            logger.warning("PlanningModeStarted publish 실패 (non-critical)", exc_info=True)

    def switch_to_build(self, plan_artifact_path: str | None = None, reason: str = "") -> bool:
        """Build 모드로 전환합니다.

        자동 전환 조건:
        - Plan→Build: Plan 아티팩트 생성 완료 + QualityGate 통과 (자동)
        - Interactive→Build: 직접 전환 (수동)

        Args:
            plan_artifact_path: Plan 아티팩트 경로 (Plan→Build 전환 시)
            reason: 전환 사유

        Returns:
            전환 성공 여부
        """
        if self._mode == ExecutionMode.BUILD:
            logger.debug("[ModeManager] 이미 BUILD 모드입니다.")
            return True

        # Plan→Build 전환 검증
        if self._mode == ExecutionMode.PLAN:
            if not self._auto_transition_enabled:
                logger.warning("[ModeManager] 자동 전환이 비활성화되어 있습니다.")
                return False

            # QualityGate 통과 여부 확인 (선택)
            if not self._plan_quality_passed:
                logger.warning(
                    "[ModeManager] Plan 품질 검증이 완료되지 않았습니다. QualityGate 통과 후 전환 가능합니다.",
                )
                return False

        previous = self._mode
        self._mode = ExecutionMode.BUILD
        if plan_artifact_path:
            self._plan_artifact_path = plan_artifact_path

        self._record_transition(previous, ExecutionMode.BUILD, reason)
        self._notify_listeners(previous, ExecutionMode.BUILD, reason)
        logger.info("[ModeManager] BUILD 모드 전환: %s", reason or "Plan 완료")
        return True

    def switch_to_interactive(self, reason: str = "") -> bool:
        """Interactive 모드로 전환합니다.

        Args:
            reason: 전환 사유

        Returns:
            전환 성공 여부
        """
        if self._mode == ExecutionMode.INTERACTIVE:
            logger.debug("[ModeManager] 이미 INTERACTIVE 모드입니다.")
            return True

        previous = self._mode
        self._mode = ExecutionMode.INTERACTIVE
        self._plan_artifact_path = None
        self._plan_quality_passed = False

        self._record_transition(previous, ExecutionMode.INTERACTIVE, reason)
        self._notify_listeners(previous, ExecutionMode.INTERACTIVE, reason)
        logger.info("[ModeManager] INTERACTIVE 모드 전환: %s", reason or "사용자 요청")
        return True

    # ─── Plan→Build 자동 전환 조건 설정 ──────────────────────────────

    def set_plan_artifact(self, path: str) -> None:
        """Plan 아티팩트 경로를 설정합니다.

        QualityGate 통과와 함께 Build 모드 자동 전환 조건이 충족됩니다.
        """
        self._plan_artifact_path = path
        logger.debug("[ModeManager] Plan artifact set: %s", path)

    def set_plan_quality_passed(self, passed: bool = True) -> None:
        """Plan 품질 검증 결과를 설정합니다."""
        self._plan_quality_passed = passed
        logger.debug("[ModeManager] Plan quality passed: %s", passed)

    @property
    def can_auto_transition_to_build(self) -> bool:
        """Plan→Build 자동 전환 가능 여부.

        두 조건이 모두 충족되어야 함:
        1. Plan 아티팩트가 생성됨
        2. QualityGate가 Plan을 통과함
        """
        return bool(self._plan_artifact_path) and self._plan_quality_passed

    # ─── 도구 권한 검사 ────────────────────────────────────────────

    def check_tool_permission(self, tool_name: str) -> dict[str, object]:
        """현재 모드에서 도구 실행 권한을 검사합니다.

        Args:
            tool_name: 도구 이름

        Returns:
            {"allowed": bool, "reason": str, "requires_approval": bool}
        """
        allowed = self._mode.tool_is_allowed(tool_name)
        if not allowed:
            return {
                "allowed": False,
                "reason": self._mode.get_block_reason(tool_name),
                "requires_approval": False,
            }

        requires_approval = self._mode.tool_requires_approval(tool_name)
        return {
            "allowed": True,
            "reason": "",
            "requires_approval": requires_approval,
        }

    def should_enforce_plan_mode(self, task_type: str, user_message: str) -> bool:
        """태스크가 Plan 모드를 강제해야 하는지 판단합니다.

        Args:
            task_type: CEO 분석 결과 task_type
            user_message: 사용자 메시지

        Returns:
            True이면 Plan 모드 진입 필요
        """
        if self._mode == ExecutionMode.PLAN:
            return False  # 이미 Plan 모드

        if task_type == "complex":
            return True

        if task_type == "coding":
            message_lower = user_message.lower()
            return any(kw in message_lower for kw in self.PLAN_TRIGGER_KEYWORDS)

        return False

    # ─── 이벤트 리스너 ─────────────────────────────────────────────

    def add_listener(self, handler: ModeChangeHandler) -> None:
        """모드 변경 이벤트 리스너를 등록합니다.

        Args:
            handler: (from_mode, to_mode, reason)를 인자로 받는 콜백
        """
        self._listeners.append(handler)

    def remove_listener(self, handler: ModeChangeHandler) -> None:
        """등록된 리스너를 제거합니다."""
        if handler in self._listeners:
            self._listeners.remove(handler)

    # ─── 상태 직렬화 ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, object]:
        """현재 상태를 딕셔너리로 반환합니다."""
        return {
            "current_mode": self._mode.value,
            "is_plan": self._mode.is_plan,
            "is_build": self._mode.is_build,
            "is_interactive": self._mode.is_interactive,
            "plan_artifact_path": self._plan_artifact_path,
            "plan_quality_passed": self._plan_quality_passed,
            "auto_transition_enabled": self._auto_transition_enabled,
            "history_count": len(self._history),
            "last_transition": (
                {
                    "from": self._history[-1].from_mode,
                    "to": self._history[-1].to_mode,
                    "reason": self._history[-1].reason,
                    "timestamp": self._history[-1].timestamp,
                }
                if self._history
                else None
            ),
        }

    def format_status(self) -> str:
        """사용자 친화적인 모드 상태 메시지를 반환합니다."""
        mode_emoji = {
            ExecutionMode.PLAN: "📋",
            ExecutionMode.BUILD: "🔨",
            ExecutionMode.INTERACTIVE: "💬",
        }
        emoji = mode_emoji.get(self._mode, "❓")
        lines = [
            f"{emoji} **실행 모드: {self._mode.value.upper()}**",
            "",
        ]

        if self._mode == ExecutionMode.PLAN:
            lines.append(
                "- 읽기 전용 도구(read_file, grep, glob)와 write_artifact만 허용됩니다.\n- `implementation_plan.md`를 작성하여 계획을 수립하세요.\n- Plan 완료 후 자동으로 BUILD 모드로 전환됩니다."
            )
        elif self._mode == ExecutionMode.BUILD:
            lines.append("- 모든 도구 실행이 허용됩니다.")
            if self._plan_artifact_path:
                lines.append(f"- Plan 아티팩트: `{self._plan_artifact_path}`")

        lines.extend(
            [
                "",
                f"**전환 이력**: {len(self._history)}회",
            ],
        )
        if self._history:
            last = self._history[-1]
            lines.append(f"  최근: {last.from_mode} → {last.to_mode} ({last.reason})")

        return "\n".join(lines)

    # ─── 내부 ───────────────────────────────────────────────────────

    def _record_transition(self, from_mode: ExecutionMode, to_mode: ExecutionMode, reason: str) -> None:
        """모드 전이를 기록합니다."""
        transition = ModeTransition(
            from_mode=from_mode.value,
            to_mode=to_mode.value,
            reason=reason or "No reason provided",
            timestamp=datetime.now(timezone.utc).isoformat(),
            plan_artifact_path=self._plan_artifact_path,
        )
        self._history.append(transition)

        # 최대 100개만 유지
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def _notify_listeners(self, from_mode: ExecutionMode, to_mode: ExecutionMode, reason: str) -> None:
        """등록된 리스너에 모드 변경을 알립니다.

        Phase 1 D7: Dashboard 실시간 반영을 위해 EventBus로도 ModeChanged 이벤트를 publish합니다.
        """
        # 내부 리스너 우선 호출
        for handler in self._listeners:
            try:
                handler(from_mode, to_mode, reason)
            except Exception:
                logger.exception("[ModeManager] Listener notification failed")

        # Phase 1 D7: EventBus로 ModeChanged 이벤트 publish (지연 초기화)
        self._publish_to_eventbus(from_mode, to_mode, reason)

    def _publish_to_eventbus(self, from_mode: ExecutionMode, to_mode: ExecutionMode, reason: str) -> None:
        """EventBus로 ModeChanged 이벤트를 발행합니다.

        최초 1회만 EventBus를 구독하고, 이후에는 직접 publish합니다.
        Dashboard WebSocket이 이 이벤트를 수신하여 모드 인디케이터를 업데이트합니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            global_event_bus.publish(
                "ModeChanged",
                from_mode=from_mode.value,
                to_mode=to_mode.value,
                reason=reason or "",
                timestamp=datetime.now(timezone.utc).isoformat(),
                plan_artifact_path=self._plan_artifact_path,
            )
        except Exception:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
