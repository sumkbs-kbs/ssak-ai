"""Computer Use 보안 Guardrail.

============================
데스크탑 자동화 액션에 대한 보안 검증 레이어입니다.
- 허용/차단 목록 기반 액션 필터링
- 위험 영역(시스템 트레이, 작업표시줄 등) 클릭 차단
- 실행 로그 감사(Audit Trail) 기록
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Final, final

from antigravity_k.security.computer_use_guard_models import (
    ActionParams,
    ActionParamValue,
    AuditEntry,
    DangerZone,
    DangerZoneRatio,
    ValidationResult,
)

logger = logging.getLogger(__name__)


def _int_param(params: ActionParams, key: str, default: int) -> int:
    value: ActionParamValue = params.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


@final
class ActionGuard:
    """Computer Use 액션에 대한 보안 게이트키퍼.

    모든 액션 실행 전에 이 클래스를 통해 검증해야 합니다.
    허용된 액션만 통과시키며, 위험 액션은 차단 또는 HITL 요구합니다.
    """

    # 기본 허용 액션 목록
    SAFE_ACTIONS: Final[frozenset[str]] = frozenset(
        {
            "screenshot",
            "mouse_move",
            "left_click",
            "right_click",
            "double_click",
            "type",
            "key",
            "scroll",
        },
    )

    # HITL (사용자 승인) 필요 액션
    HITL_REQUIRED_ACTIONS: Final[frozenset[str]] = frozenset(
        {
            "left_click_drag",
            "hold_key",
        },
    )

    # 절대 허용 불가 액션
    BLOCKED_ACTIONS: Final[frozenset[str]] = frozenset(
        {
            "run_as_admin",
            "format_disk",
            "delete_system_file",
        },
    )

    # P1 수정: 비율 기반 위험 영역 — 해상도 독립적 (런타임 계산)
    # 각 값은 0.0 ~ 1.0 비율로, 실제 해상도에 곱하여 사용
    DANGER_ZONE_RATIOS: Final[list[DangerZoneRatio]] = [
        {
            "name": "taskbar",
            "y_min_ratio": 0.963,
            "y_max_ratio": 1.0,
            "x_min_ratio": 0.0,
            "x_max_ratio": 1.0,
        },
        {
            "name": "system_tray",
            "y_min_ratio": 0.963,
            "y_max_ratio": 1.0,
            "x_min_ratio": 0.885,
            "x_max_ratio": 1.0,
        },
    ]

    @classmethod
    def get_danger_zones(cls, screen_width: int = 1920, screen_height: int = 1080) -> list[DangerZone]:
        """화면 해상도에 맞게 위험 영역 좌표를 계산합니다."""
        zones: list[DangerZone] = []
        for zone in cls.DANGER_ZONE_RATIOS:
            zones.append(
                {
                    "name": zone["name"],
                    "y_min": int(zone["y_min_ratio"] * screen_height),
                    "y_max": int(zone["y_max_ratio"] * screen_height),
                    "x_min": int(zone["x_min_ratio"] * screen_width),
                    "x_max": int(zone["x_max_ratio"] * screen_width),
                },
            )
        return zones

    def __init__(
        self,
        enabled: bool = True,
        hitl_required: bool = True,
        audit_log_path: str | None = None,
        custom_blocked_actions: list[str] | None = None,
    ):
        """Initialize the ActionGuard.

        Args:
            enabled (bool): bool enabled.
            hitl_required (bool): bool hitl required.
            audit_log_path (str | None): str | None audit log path.
            custom_blocked_actions (list[str] | None): list[str] | None custom blocked actions.

        """
        self.enabled: bool = enabled
        self.hitl_required: bool = hitl_required
        self._blocked_actions: frozenset[str] = self.BLOCKED_ACTIONS
        self._audit_log: list[AuditEntry] = []

        self._audit_file: Path | None = None
        if audit_log_path:
            self._audit_file = Path(audit_log_path)
            self._audit_file.parent.mkdir(parents=True, exist_ok=True)

        if custom_blocked_actions:
            self._blocked_actions = frozenset(self._blocked_actions | frozenset(custom_blocked_actions))

    def validate_action(self, action: str, params: ActionParams) -> ValidationResult:
        """액션을 검증합니다.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "requires_hitl": bool,  # 사용자 승인 필요 여부
            }

        """
        if not self.enabled:
            return {"allowed": True, "reason": "guard_disabled", "requires_hitl": False}

        # 1. 차단 목록 확인
        if action in self._blocked_actions:
            self._log_audit(action, params, allowed=False, reason="blocked_action")
            return {
                "allowed": False,
                "reason": f"Action '{action}' is in the BLOCKED list.",
                "requires_hitl": False,
            }

        # 2. 허용 목록 확인
        if action not in self.SAFE_ACTIONS and action not in self.HITL_REQUIRED_ACTIONS:
            self._log_audit(action, params, allowed=False, reason="unknown_action")
            return {
                "allowed": False,
                "reason": f"Unknown action '{action}'. Not in SAFE or HITL list.",
                "requires_hitl": False,
            }

        # 3. 위험 영역 클릭 검사
        if action in ("left_click", "right_click", "double_click", "mouse_move"):
            x = _int_param(params, "x", 0)
            y = _int_param(params, "y", 0)
            # P1 수정: 비율 기반 동적 위험 영역 계산
            screen_w = _int_param(params, "screen_width", 1920)
            screen_h = _int_param(params, "screen_height", 1080)
            for zone in self.get_danger_zones(screen_w, screen_h):
                if zone["x_min"] <= x <= zone["x_max"] and zone["y_min"] <= y <= zone["y_max"]:
                    self._log_audit(
                        action,
                        params,
                        allowed=False,
                        reason=f"danger_zone:{zone['name']}",
                    )
                    return {
                        "allowed": False,
                        "reason": f"Click at ({x}, {y}) is in DANGER ZONE: {zone['name']}.",
                        "requires_hitl": False,
                    }

        # 4. HITL 필요 여부 확인
        requires_hitl = (action in self.HITL_REQUIRED_ACTIONS) and self.hitl_required

        self._log_audit(action, params, allowed=True, reason="passed", requires_hitl=requires_hitl)
        return {
            "allowed": True,
            "reason": "passed",
            "requires_hitl": requires_hitl,
        }

    def get_audit_log(self) -> list[AuditEntry]:
        """감사 로그를 반환합니다."""
        return list(self._audit_log)

    def _log_audit(
        self,
        action: str,
        params: ActionParams,
        allowed: bool,
        reason: str,
        requires_hitl: bool = False,
    ) -> None:
        """감사 로그를 기록합니다."""
        entry: AuditEntry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "params": params,
            "allowed": allowed,
            "reason": reason,
            "requires_hitl": requires_hitl,
        }
        self._audit_log.append(entry)

        log_msg = f"[ActionGuard] {action} | allowed={allowed} | reason={reason}"
        if allowed:
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

        # 파일 로그
        if self._audit_file:
            try:
                import json

                with self._audit_file.open("a", encoding="utf-8") as f:
                    _ = f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except (OSError, TypeError, ValueError):
                logger.exception("Failed to write audit log")
