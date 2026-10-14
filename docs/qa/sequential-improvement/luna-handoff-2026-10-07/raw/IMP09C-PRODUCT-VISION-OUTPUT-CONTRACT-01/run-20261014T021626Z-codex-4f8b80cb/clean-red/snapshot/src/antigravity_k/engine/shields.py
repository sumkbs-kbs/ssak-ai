"""Shields — 에이전트 보호 레벨 시스템.

====================================
NemoClaw의 shields.ts + shields-audit.ts 패턴을 이식.

에이전트의 도구 사용 권한을 시간 제한으로 완화/복원합니다.

아키텍처:
  - Shields UP (기본): 안전 모드 — ToolsetManager를 "safe" 모드로 제한
  - Shields DOWN (시간 제한): 지정 시간 동안 "full" 접근 허용
  - 타임아웃 시 자동 복원 (Shields UP)
  - 모든 상태 변경은 감사 로그에 기록

사용법:
    shields = ShieldsManager(toolset_manager)
    shields.shields_down(reason="debugging", timeout_seconds=300)
    shields.check_timeout()  # 매 턴마다 호출
    shields.shields_up()     # 수동 복원

보안 불변식 (NemoClaw):
  - 에이전트는 스스로 shields를 변경할 수 없음 (호스트/사용자만 가능)
  - 모든 변경은 audit trail에 기록됨
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast, final

logger = logging.getLogger("antigravity_k.engine.shields")


class _ToolsetManagerLike(Protocol):
    @property
    def active_toolset(self) -> str: ...

    def set_active(self, toolset: str, /) -> bool | None: ...


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, object], value)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _boolean(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


# ── 상수 ──

DEFAULT_TIMEOUT_SECONDS = 300  # 5분
MAX_TIMEOUT_SECONDS = 3600  # 1시간


# ── 데이터 타입 ──


@dataclass
class ShieldsState:
    """현재 Shields 상태."""

    shields_down: bool = False
    shields_down_at: str | None = None
    shields_down_timeout: int | None = None
    shields_down_reason: str | None = None
    previous_toolset: str | None = None
    target_toolset: str | None = None
    permanent: bool = False
    updated_at: str | None = None

    @property
    def is_protected(self) -> bool:
        """보호 모드(UP) 여부."""
        return not self.shields_down

    @property
    def remaining_seconds(self) -> int | None:
        """남은 시간(초). None이면 영구."""
        if not self.shields_down or self.permanent:
            return None
        if not self.shields_down_at or not self.shields_down_timeout:
            return None
        import datetime

        down_at = datetime.datetime.fromisoformat(self.shields_down_at)
        elapsed = (datetime.datetime.now(datetime.timezone.utc) - down_at).total_seconds()
        return max(0, int(self.shields_down_timeout - elapsed))

    @property
    def is_expired(self) -> bool:
        """타임아웃 만료 여부."""
        remaining = self.remaining_seconds
        return remaining is not None and remaining <= 0


@dataclass
class AuditEntry:
    """감사 로그 항목."""

    action: str
    timestamp: str
    reason: str | None = None
    timeout_seconds: int | None = None
    duration_seconds: int | None = None
    restored_by: str | None = None
    previous_toolset: str | None = None
    target_toolset: str | None = None


# ── Shields Manager ──


@final
class ShieldsManager:
    """에이전트 보호 레벨 관리자.

    ToolsetManager와 연동하여 shields 상태에 따라
    활성 toolset을 자동으로 전환합니다.
    """

    def __init__(
        self,
        toolset_manager: _ToolsetManagerLike | None = None,
        state_dir: str | None = None,
        default_timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_timeout: int = MAX_TIMEOUT_SECONDS,
        default_safe_toolset: str = "safe",
    ):
        """Initialize the ShieldsManager.

        Args:
            toolset_manager: toolset manager.
            state_dir (str | None): str | None state dir.
            default_timeout (int): int default timeout.
            max_timeout (int): int max timeout.
            default_safe_toolset (str): str default safe toolset.

        """
        self._toolset_manager: _ToolsetManagerLike | None = toolset_manager
        self._state: ShieldsState = ShieldsState()
        self._audit_log: list[AuditEntry] = []
        self._default_timeout: int = default_timeout
        self._max_timeout: int = max_timeout
        self._default_safe_toolset: str = default_safe_toolset

        # 상태 파일 경로
        if state_dir:
            self._state_dir: Path = Path(state_dir)
        else:
            self._state_dir = Path.home() / ".antigravity-k" / "state"

        self._state_file: Path = self._state_dir / "shields-state.json"
        self._audit_file: Path = self._state_dir / "shields-audit.jsonl"

        # 기존 상태 로드
        self._load_state()

    @property
    def state(self) -> ShieldsState:
        """State.

        Returns:
            ShieldsState: The shieldsstate result.

        """
        return self._state

    @property
    def is_down(self) -> bool:
        """Check if down.

        Returns:
            bool: The bool result.

        """
        return self._state.shields_down

    @property
    def is_up(self) -> bool:
        """Check if up.

        Returns:
            bool: The bool result.

        """
        return not self._state.shields_down

    # ── 핵심 API ──

    def shields_down(
        self,
        reason: str | None = None,
        timeout_seconds: int | None = None,
        target_toolset: str = "full",
    ) -> ShieldsState:
        """Shields를 내립니다 (권한 완화).

        Args:
            reason: 변경 사유
            timeout_seconds: 타임아웃 (초). None이면 기본값 사용.
            target_toolset: 완화 시 사용할 toolset. 기본값 "full".

        Returns:
            업데이트된 ShieldsState

        """
        if self._state.shields_down:
            logger.warning("Shields already DOWN. Use shields_up() first.")
            return self._state

        timeout = min(
            timeout_seconds or self._default_timeout,
            self._max_timeout,
        )

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 현재 toolset 저장
        previous_toolset = None
        if self._toolset_manager:
            previous_toolset = self._toolset_manager.active_toolset

        # 상태 업데이트
        self._state = ShieldsState(
            shields_down=True,
            shields_down_at=now,
            shields_down_timeout=timeout,
            shields_down_reason=reason,
            previous_toolset=previous_toolset,
            target_toolset=target_toolset,
            permanent=False,
            updated_at=now,
        )

        # ToolsetManager 전환
        if self._toolset_manager:
            _ = self._toolset_manager.set_active(target_toolset)
            logger.info("Toolset switched to '%s' (shields down)", target_toolset)

        # 감사 로그
        self._append_audit(
            AuditEntry(
                action="shields_down",
                timestamp=now,
                reason=reason,
                timeout_seconds=timeout,
                previous_toolset=previous_toolset,
                target_toolset=target_toolset,
            ),
        )

        self._save_state()
        logger.info("Shields DOWN: timeout=%ss, reason=%s", timeout, reason)
        return self._state

    def shields_up(self, restored_by: str = "operator") -> ShieldsState:
        """Shields를 올립니다 (보호 복원).

        Args:
            restored_by: 복원 주체 ("operator", "timeout", "system")

        Returns:
            업데이트된 ShieldsState

        """
        if not self._state.shields_down:
            logger.info("Shields already UP.")
            return self._state

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 지속 시간 계산
        duration_seconds = None
        if self._state.shields_down_at:
            down_at = datetime.datetime.fromisoformat(self._state.shields_down_at)
            duration_seconds = int(
                (datetime.datetime.now(datetime.timezone.utc) - down_at).total_seconds(),
            )

        # ToolsetManager 복원
        previous_toolset = self._state.previous_toolset or self._default_safe_toolset
        if self._toolset_manager:
            _ = self._toolset_manager.set_active(previous_toolset)
            logger.info("Toolset restored to '%s' (shields up)", previous_toolset)

        # 감사 로그
        self._append_audit(
            AuditEntry(
                action="shields_up",
                timestamp=now,
                restored_by=restored_by,
                duration_seconds=duration_seconds,
                reason=self._state.shields_down_reason,
            ),
        )

        # 상태 초기화
        self._state = ShieldsState(
            shields_down=False,
            shields_down_at=None,
            shields_down_timeout=None,
            shields_down_reason=None,
            previous_toolset=None,
            target_toolset=None,
            permanent=False,
            updated_at=now,
        )

        self._save_state()
        logger.info("Shields UP: restored_by=%s, duration=%ss", restored_by, duration_seconds)
        return self._state

    def check_timeout(self) -> bool:
        """타임아웃을 확인하고 만료 시 자동 복원합니다.

        Orchestrator의 매 턴마다 호출해야 합니다.

        Returns:
            True이면 타임아웃으로 인해 shields가 UP으로 복원됨.

        """
        if not self._state.shields_down or self._state.permanent:
            return False

        if self._state.is_expired:
            logger.warning("Shields timeout expired — auto-restoring to UP")
            _ = self.shields_up(restored_by="timeout")
            return True

        return False

    def status(self) -> dict[str, object]:
        """현재 Shields 상태를 딕셔너리로 반환합니다."""
        return {
            "shields_down": self._state.shields_down,
            "is_protected": self._state.is_protected,
            "remaining_seconds": self._state.remaining_seconds,
            "reason": self._state.shields_down_reason,
            "permanent": self._state.permanent,
            "active_toolset": (self._toolset_manager.active_toolset if self._toolset_manager else None),
            "updated_at": self._state.updated_at,
        }

    def get_audit_log(self, limit: int = 50) -> list[dict[str, object]]:
        """최근 감사 로그를 반환합니다."""
        entries = self._audit_log[-limit:]
        return [asdict(e) for e in entries]

    # ── config.yaml 연동 ──

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, object] | None = None,
        *,
        toolset_manager: _ToolsetManagerLike | None = None,
        state_dir: str | None = None,
    ) -> "ShieldsManager":
        """config.yaml의 `shields` 섹션에서 인스턴스를 생성합니다."""
        if not isinstance(config, dict):
            return cls(toolset_manager=toolset_manager, state_dir=state_dir)

        default_timeout = _optional_int(config.get("default_timeout_seconds"))
        max_timeout = _optional_int(config.get("max_timeout_seconds"))
        default_mode = _optional_string(config.get("default_mode"))

        return cls(
            toolset_manager=toolset_manager,
            state_dir=state_dir,
            default_timeout=default_timeout if default_timeout is not None else DEFAULT_TIMEOUT_SECONDS,
            max_timeout=max_timeout if max_timeout is not None else MAX_TIMEOUT_SECONDS,
            default_safe_toolset=default_mode if default_mode is not None else "safe",
        )

    # ── 내부 ──

    def _load_state(self) -> None:
        """파일에서 상태를 로드합니다."""
        if self._state_file.exists():
            try:
                data = _as_mapping(cast(object, json.loads(self._state_file.read_text())))
                self._state = ShieldsState(
                    shields_down=_boolean(data.get("shields_down")),
                    shields_down_at=_optional_string(data.get("shields_down_at")),
                    shields_down_timeout=_optional_int(data.get("shields_down_timeout")),
                    shields_down_reason=_optional_string(data.get("shields_down_reason")),
                    previous_toolset=_optional_string(data.get("previous_toolset")),
                    target_toolset=_optional_string(data.get("target_toolset")),
                    permanent=_boolean(data.get("permanent")),
                    updated_at=_optional_string(data.get("updated_at")),
                )
                # 로드 직후 타임아웃 확인
                _ = self.check_timeout()
            except Exception as e:
                logger.exception("Unhandled exception")
                logger.debug("Failed to load shields state: %s", e)

    def _save_state(self) -> None:
        """상태를 파일에 저장합니다."""
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            _ = self._state_file.write_text(json.dumps(asdict(self._state), indent=2, default=str))
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to save shields state: %s", e)

    def _append_audit(self, entry: AuditEntry) -> None:
        """감사 로그에 항목을 추가합니다."""
        self._audit_log.append(entry)
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._audit_file.open("a", encoding="utf-8") as f:
                _ = f.write(json.dumps(asdict(entry), default=str) + "\n")
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("Failed to write audit log: %s", e)
