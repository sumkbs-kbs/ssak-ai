"""CTX-03: compression failure policy and observability records.

Removes catch-all fail-open semantics for context compression. Callers must
treat compress failure as either:

* **degraded** — compress failed (or was incomplete) but the final prompt is
  still under the hard input budget; read/continue paths may proceed with an
  explicit degraded signal.
* **halted** — final prompt still exceeds the hard limit (or budget enforcement
  failed); mutation / model-provider invoke must not proceed.

Telemetry records component token ledgers, strategy, digest, elapsed time, and
a stable failure code for ops dashboards and execution diagnostics.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Final, Literal, cast

from pydantic import JsonValue

CompressOutcome = Literal["success", "degraded", "halted", "skipped", "noop"]

EVENT_COMPRESS_SUCCEEDED: Final = "context.compress.succeeded"
EVENT_COMPRESS_DEGRADED: Final = "context.compress.degraded"
EVENT_COMPRESS_HALTED: Final = "context.compress.halted"
EVENT_COMPRESS_SKIPPED: Final = "context.compress.skipped"

# Ops alert thresholds (documented in docs/09_OPERATION_GUIDE.md).
ALERT_COMPRESS_FAILURE_RATE: Final = 0.05  # 5% of compress attempts
ALERT_BUDGET_HEADROOM_PCT: Final = 15.0  # warn when remaining headroom < 15%


class CompressFailureCode(StrEnum):
    """Stable failure codes for compress / budget policy."""

    NONE = "none"
    COMPRESS_EXCEPTION = "compress_exception"
    REBUILD_UNAVAILABLE = "rebuild_unavailable"
    ADAPTIVE_COMPRESS_ERROR = "adaptive_compress_error"
    STILL_OVER_LIMIT = "still_over_limit"
    BUDGET_ENFORCE_FAILED = "budget_enforce_failed"
    OVERSIZED_COMPONENT = "oversized_component"
    PROVIDER_HALTED = "provider_halted"


@dataclass(frozen=True, slots=True)
class ComponentTokenSnapshot:
    """Before/after component token counts (ledger-compatible keys)."""

    system: int = 0
    tools: int = 0
    skills: int = 0
    memory: int = 0
    artifacts: int = 0
    messages: int = 0
    output_reserve: int = 0
    input_total: int = 0
    total_with_reserve: int = 0

    @classmethod
    def from_mapping(cls, values: Mapping[str, int] | None) -> ComponentTokenSnapshot:
        if not values:
            return cls()
        return cls(
            system=int(values.get("system", 0) or 0),
            tools=int(values.get("tools", 0) or 0),
            skills=int(values.get("skills", 0) or 0),
            memory=int(values.get("memory", 0) or 0),
            artifacts=int(values.get("artifacts", 0) or 0),
            messages=int(values.get("messages", 0) or 0),
            output_reserve=int(values.get("output_reserve", 0) or 0),
            input_total=int(values.get("input_total", 0) or 0),
            total_with_reserve=int(values.get("total_with_reserve", 0) or 0),
        )

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CompressTelemetryRecord:
    """Full compress observability payload (CTX-03)."""

    outcome: CompressOutcome
    trigger: str
    strategy: str | None = None
    digest: str | None = None
    elapsed_ms: float = 0.0
    failure_code: str | None = None
    usage_before_pct: float | None = None
    usage_after_pct: float | None = None
    tokens_before: ComponentTokenSnapshot = field(default_factory=ComponentTokenSnapshot)
    tokens_after: ComponentTokenSnapshot = field(default_factory=ComponentTokenSnapshot)
    hard_limit_input: int | None = None
    serialized_before: int | None = None
    serialized_after: int | None = None
    message: str | None = None

    def event_type(self) -> str:
        if self.outcome == "success":
            return EVENT_COMPRESS_SUCCEEDED
        if self.outcome == "degraded":
            return EVENT_COMPRESS_DEGRADED
        if self.outcome == "halted":
            return EVENT_COMPRESS_HALTED
        return EVENT_COMPRESS_SKIPPED

    def as_payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "outcome": self.outcome,
            "trigger": self.trigger,
            "strategy": self.strategy,
            "digest": self.digest,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "failure_code": self.failure_code,
            "usage_before_pct": self.usage_before_pct,
            "usage_after_pct": self.usage_after_pct,
            "tokens_before": cast(JsonValue, self.tokens_before.as_dict()),
            "tokens_after": cast(JsonValue, self.tokens_after.as_dict()),
            "hard_limit_input": self.hard_limit_input,
            "serialized_before": self.serialized_before,
            "serialized_after": self.serialized_after,
            "message": self.message,
            "alert_thresholds": cast(
                JsonValue,
                {
                    "compress_failure_rate": ALERT_COMPRESS_FAILURE_RATE,
                    "budget_headroom_pct": ALERT_BUDGET_HEADROOM_PCT,
                },
            ),
        }
        return payload

    def payload_json(self) -> str:
        return json.dumps(self.as_payload(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ContextCompressAttempt:
    """Result of a single legacy/adaptive compress attempt (pre final budget)."""

    messages: list[dict[str, str]]
    prompt: str
    usage_before: float | None
    usage_after: float | None
    attempted: bool
    failed: bool
    failure_code: str | None
    strategy: str | None
    elapsed_ms: float
    digest: str | None = None
    tokens_before: ComponentTokenSnapshot = field(default_factory=ComponentTokenSnapshot)
    tokens_after: ComponentTokenSnapshot = field(default_factory=ComponentTokenSnapshot)

    @property
    def compressed(self) -> bool:
        return self.attempted and not self.failed and self.usage_before is not None


def decide_post_compress_policy(
    *,
    compress_failed: bool,
    over_hard_limit: bool,
    budget_enforce_failed: bool = False,
) -> CompressOutcome:
    """Map compress + hard-limit state to success / degrade / halt.

    Hard-limit exceed or enforce failure → halt (no provider / mutation path).
    Compress failure while still under limit → limited degrade (read/continue OK).
    """
    if over_hard_limit or budget_enforce_failed:
        return "halted"
    if compress_failed:
        return "degraded"
    return "success"


def headroom_pct(*, input_total: int, hard_limit_input: int) -> float | None:
    if hard_limit_input <= 0:
        return None
    remaining = hard_limit_input - input_total
    return max(0.0, (remaining / hard_limit_input) * 100.0)


def should_alert_low_headroom(*, input_total: int, hard_limit_input: int) -> bool:
    pct = headroom_pct(input_total=input_total, hard_limit_input=hard_limit_input)
    return pct is not None and pct < ALERT_BUDGET_HEADROOM_PCT


class ElapsedTimer:
    """Simple monotonic timer for compress elapsed_ms."""

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0


def ui_status_line(record: CompressTelemetryRecord) -> str:
    """User-visible stream/status line matching server outcome."""
    digest = (record.digest or "")[:12]
    digest_bit = f" digest `{digest}`" if digest else ""
    strategy_bit = f" strategy={record.strategy}" if record.strategy else ""
    code_bit = f" code={record.failure_code}" if record.failure_code else ""
    if record.outcome == "success":
        before = record.usage_before_pct
        after = record.usage_after_pct
        if before is not None and after is not None:
            return f"\n📦 **[Context Compress · success]** {before:.0f}% → {after:.0f}%{strategy_bit}{digest_bit}\n\n"
        return f"\n📦 **[Context Compress · success]**{strategy_bit}{digest_bit}\n\n"
    if record.outcome == "degraded":
        return (
            f"\n⚠️ **[Context Compress · degraded]** 압축 실패·제한적 저하 "
            f"(읽기/계속 허용, hard-limit 미만){code_bit}{digest_bit}\n\n"
        )
    if record.outcome == "halted":
        detail = record.message or "최종 프롬프트가 hard-limit를 초과했습니다"
        return (
            f"\n\n🛑 **[Context Compress · halted]** / ⚠️ **[Prompt Budget]** {detail}"
            f"{code_bit}{digest_bit} — 모델 호출·mutation을 중단합니다.\n"
        )
    return ""


__all__ = [
    "ALERT_BUDGET_HEADROOM_PCT",
    "ALERT_COMPRESS_FAILURE_RATE",
    "EVENT_COMPRESS_DEGRADED",
    "EVENT_COMPRESS_HALTED",
    "EVENT_COMPRESS_SKIPPED",
    "EVENT_COMPRESS_SUCCEEDED",
    "ComponentTokenSnapshot",
    "CompressFailureCode",
    "CompressOutcome",
    "CompressTelemetryRecord",
    "ContextCompressAttempt",
    "ElapsedTimer",
    "decide_post_compress_policy",
    "headroom_pct",
    "should_alert_low_headroom",
    "ui_status_line",
]
