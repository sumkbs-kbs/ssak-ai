"""Ssak-Ai: Capacity Flow 가드레일.

======================================
DeepSeek-TUI 아키텍처 이식 — 용량 체크포인트 + 크래시 복구.

참조: Hmbown/DeepSeek-TUI
- engine/capacity_flow.rs  → Capacity guardrail checkpoints
- runtime_threads.rs       → Monotonic event sequence + durable queue
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypeGuard, cast

logger = logging.getLogger(__name__)
type CapacityMetadataValue = str | int | float | bool | None
type CapacityJsonValue = str | int | float | bool | None | list[CapacityJsonValue] | dict[str, CapacityJsonValue]
type CapacityState = dict[str, CapacityJsonValue]


def _is_capacity_json_value(value: object) -> TypeGuard[CapacityJsonValue]:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        items = cast(list[object], value)
        return all(_is_capacity_json_value(item) for item in items)
    if isinstance(value, dict):
        entries = cast(dict[object, object], value)
        return all(isinstance(key, str) and _is_capacity_json_value(item) for key, item in entries.items())
    return False


def _coerce_capacity_state(value: object) -> CapacityState | None:
    if not isinstance(value, dict):
        return None
    result: CapacityState = {}
    entries = cast(dict[object, object], value)
    for key, item in entries.items():
        if not isinstance(key, str) or not _is_capacity_json_value(item):
            return None
        result[key] = item
    return result


class CapacityAction(str, Enum):
    """Capacityaction.

    Bases: str, Enum
    """

    OK = "ok"
    WARN = "warn"
    COMPRESS = "compress"
    HALT = "halt"
    SWITCH_MODEL = "switch_model"


@dataclass(frozen=True, slots=True)
class CapacityDecision:
    """용량 체크 결과."""

    action: CapacityAction
    message: str
    usage_pct: float = 0.0
    metadata: dict[str, CapacityMetadataValue] = field(default_factory=dict)


class CapacityCheckpoint:
    """DeepSeek-TUI 패턴: 용량 가드레일 체크포인트.

    3개 축으로 용량을 모니터링:
    1. 컨텍스트 토큰 예산
    2. 실행 스텝 예산
    3. 비용 예산
    """

    def __init__(
        self,
        warn_pct: float = 70.0,
        compress_pct: float = 85.0,
        halt_pct: float = 95.0,
    ):
        """Initialize the CapacityCheckpoint.

        Args:
            warn_pct (float): float warn pct.
            compress_pct (float): float compress pct.
            halt_pct (float): float halt pct.

        """
        self.warn_pct: float = warn_pct
        self.compress_pct: float = compress_pct
        self.halt_pct: float = halt_pct

    def check_context_budget(self, current_tokens: int, max_tokens: int) -> CapacityDecision:
        """Check Context Budget.

        Args:
            current_tokens (int): int current tokens.
            max_tokens (int): int max tokens.

        Returns:
            CapacityDecision: The capacitydecision result.

        """
        if max_tokens <= 0:
            return CapacityDecision(action=CapacityAction.OK, message="No token limit set.")

        usage_pct = (current_tokens / max_tokens) * 100
        remaining = max_tokens - current_tokens

        if usage_pct >= self.halt_pct:
            return CapacityDecision(
                action=CapacityAction.HALT,
                message=f"⛔ 컨텍스트 한계 도달 ({usage_pct:.0f}%). 잔여: {remaining:,} tokens. 즉시 중단 필요.",
                usage_pct=usage_pct,
            )
        elif usage_pct >= self.compress_pct:
            return CapacityDecision(
                action=CapacityAction.COMPRESS,
                message=f"🗜️ 컨텍스트 위험 수준 ({usage_pct:.0f}%). 즉시 압축 필요. 잔여: {remaining:,} tokens.",
                usage_pct=usage_pct,
            )
        elif usage_pct >= self.warn_pct:
            return CapacityDecision(
                action=CapacityAction.WARN,
                message=f"⚠️ 컨텍스트 경고 ({usage_pct:.0f}%). 잔여: {remaining:,} tokens. 간결하게 응답하세요.",
                usage_pct=usage_pct,
            )

        return CapacityDecision(action=CapacityAction.OK, message="OK", usage_pct=usage_pct)

    def check_step_budget(self, current_step: int, max_steps: int) -> CapacityDecision:
        """Check Step Budget.

        Args:
            current_step (int): int current step.
            max_steps (int): int max steps.

        Returns:
            CapacityDecision: The capacitydecision result.

        """
        if max_steps <= 0:
            return CapacityDecision(action=CapacityAction.OK, message="No step limit.")

        usage_pct = (current_step / max_steps) * 100
        remaining = max_steps - current_step

        if usage_pct >= self.halt_pct:
            return CapacityDecision(
                action=CapacityAction.HALT,
                message=f"⛔ 스텝 한계 도달. {remaining}스텝 남음. 최종 결과를 즉시 출력하세요.",
                usage_pct=usage_pct,
            )
        elif usage_pct >= self.compress_pct:
            return CapacityDecision(
                action=CapacityAction.COMPRESS,
                message=f"🗜️ 스텝 예산 위험 ({remaining}스텝 남음). 컨텍스트를 압축하고 핵심만 유지하세요.",
                usage_pct=usage_pct,
            )
        elif usage_pct >= self.warn_pct:
            return CapacityDecision(
                action=CapacityAction.WARN,
                message=f"⚠️ 스텝 경고: {remaining}스텝 남음. 불필요한 도구 호출을 줄이세요.",
                usage_pct=usage_pct,
            )

        return CapacityDecision(action=CapacityAction.OK, message="OK", usage_pct=usage_pct)

    def check_cost_budget(self, estimated_cost: float, max_cost: float = 0.0) -> CapacityDecision:
        """Check Cost Budget.

        Args:
            estimated_cost (float): float estimated cost.
            max_cost (float): float max cost.

        Returns:
            CapacityDecision: The capacitydecision result.

        """
        if max_cost <= 0:
            return CapacityDecision(action=CapacityAction.OK, message="No cost limit.")

        usage_pct = (estimated_cost / max_cost) * 100

        if usage_pct >= self.halt_pct:
            return CapacityDecision(
                action=CapacityAction.SWITCH_MODEL,
                message=f"💰 비용 한계 ({usage_pct:.0f}%). 저비용 모델로 전환을 권고합니다.",
                usage_pct=usage_pct,
                metadata={"action": "switch_to_cheaper_model"},
            )
        elif usage_pct >= self.warn_pct:
            return CapacityDecision(
                action=CapacityAction.WARN,
                message=f"💰 비용 경고 ({usage_pct:.0f}%). 잔여 예산: ${max_cost - estimated_cost:.4f}",
                usage_pct=usage_pct,
            )

        return CapacityDecision(action=CapacityAction.OK, message="OK", usage_pct=usage_pct)


class CrashRecovery:
    """DeepSeek-TUI 패턴: 체크포인트 기반 크래시 복구.

    - 실행 중 주기적으로 상태를 JSON 스냅샷으로 저장
    - 비정상 종료 시 최근 체크포인트에서 복원
    - 미완료 프롬프트를 오프라인 큐에 저장
    """

    def __init__(self, checkpoint_dir: str | None = None):
        """Initialize the CrashRecovery.

        Args:
            checkpoint_dir (str | None): str | None checkpoint dir.

        """
        self.checkpoint_dir: Path = Path(checkpoint_dir or os.path.join("vault_data", "checkpoints"))
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, state: CapacityState, label: str = "auto") -> str:
        """Save checkpoint.

        Args:
            state (dict[str, Any]): dict[str, Any] state.
            label (str): str label.

        Returns:
            str: The str result.

        """
        filename = f"checkpoint_{label}_{int(time.time())}.json"
        filepath = self.checkpoint_dir / filename
        state["_checkpoint_meta"] = {
            "label": label,
            "timestamp": time.time(),
            "filepath": str(filepath),
        }
        try:
            _ = filepath.write_text(
                json.dumps(state, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            # 권한 보호 (vault 규약: 0600)
            filepath.chmod(0o600)
            logger.info("Checkpoint saved: %s", filepath)
        except (OSError, TypeError, ValueError):
            logger.exception("Failed to save checkpoint")
        return str(filepath)

    def restore_from_checkpoint(self, label: str = "auto") -> CapacityState | None:
        """Restore From Checkpoint.

        Args:
            label (str): str label.

        Returns:
            dict[str, Any] | None: The dict[str, any] | none result.

        """
        pattern = f"checkpoint_{label}_*.json"
        candidates = sorted(self.checkpoint_dir.glob(pattern), reverse=True)
        if not candidates:
            logger.info("No checkpoint found for label '%s'", label)
            return None
        latest = candidates[0]
        try:
            decoded = cast(object, json.loads(latest.read_text(encoding="utf-8")))
            data = _coerce_capacity_state(decoded)
            if data is None:
                return None
            logger.info("Checkpoint restored: %s", latest)
            return data
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("Failed to restore checkpoint")
            return None

    def queue_offline(self, prompt: str, context: CapacityState | None = None) -> str:
        """Queue Offline.

        Args:
            prompt (str): str prompt.
            context (dict[str, Any] | None): dict[str, Any] | None context.

        Returns:
            str: The str result.

        """
        queue_dir = self.checkpoint_dir / "offline_queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        filename = f"queued_{int(time.time())}_{uuid.uuid4().hex[:6]}.json"
        filepath = queue_dir / filename
        entry = {
            "prompt": prompt,
            "context": context or {},
            "queued_at": time.time(),
        }
        _ = filepath.write_text(json.dumps(entry, default=str, ensure_ascii=False), encoding="utf-8")
        filepath.chmod(0o600)
        logger.info("Offline queue entry saved: %s", filepath)
        return str(filepath)

    def list_offline_queue(self) -> list[Path]:
        """List Offline Queue.

        Returns:
            list: The list result.

        """
        queue_dir = self.checkpoint_dir / "offline_queue"
        if not queue_dir.exists():
            return []
        return sorted(queue_dir.glob("queued_*.json"), reverse=True)

    def cleanup_old_checkpoints(self, max_age_hours: float = 24.0) -> int:
        """Cleanup Old Checkpoints.

        Args:
            max_age_hours (float): float max age hours.

        Returns:
            int: The int result.

        """
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0
        for f in self.checkpoint_dir.glob("checkpoint_*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        if removed:
            logger.info("Cleaned up %s old checkpoints", removed)
        return removed
