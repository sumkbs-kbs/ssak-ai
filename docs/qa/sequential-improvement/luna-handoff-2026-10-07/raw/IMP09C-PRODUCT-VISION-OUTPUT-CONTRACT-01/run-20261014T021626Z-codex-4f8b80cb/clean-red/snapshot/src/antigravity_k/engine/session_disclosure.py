"""세션 고지 빌더 — CostGuard 상태를 사용자용 고지로 변환.

벤치마킹 출처: freebuff의 "session limits + data-use notice before you start" UX.
결정론적: 같은 DailyStats 입력이면 항상 같은 고지가 나온다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time

from antigravity_k.engine.cost_guard import CostGuard, DailyStats, SpendRecord

# 등급: 잔여 0 → exhausted, 80% 이상 사용 → warning, else healthy
_LEVEL_BY_USAGE = (
    ("exhausted", 100.0),
    ("warning", 80.0),
)


def _level_for_usage(usage_percent: float) -> str:
    for level, threshold in _LEVEL_BY_USAGE:
        if usage_percent >= threshold:
            return level
    return "healthy"


_LEVEL_META: dict[str, tuple[str, str]] = {
    "healthy": ("✅", "여유"),
    "warning": ("⚠️", "주의"),
    "exhausted": ("⛔", "소진"),
}


@dataclass(frozen=True)
class LimitDisclosure:
    """하나의 한도(예산/액션)에 대한 고지."""

    kind: str  # budget | action
    label: str
    limit: float
    used: float
    remaining: float
    usage_percent: float
    level: str
    message: str
    reset_at: str = ""
    seconds_until_reset: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "usage_percent": self.usage_percent,
            "level": self.level,
            "message": self.message,
            "reset_at": self.reset_at,
            "seconds_until_reset": self.seconds_until_reset,
        }


@dataclass(frozen=True)
class SessionDisclosure:
    """세션 시작 전 사용자 고지."""

    level: str
    reset_date: str
    reset_at: str = ""
    seconds_until_reset: int = 0
    notices: list[str] = field(default_factory=list)
    limits: list[LimitDisclosure] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return _LEVEL_META.get(self.level, ("ℹ️", ""))[0]

    @property
    def label(self) -> str:
        return _LEVEL_META.get(self.level, ("", self.level))[1]

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "reset_date": self.reset_date,
            "reset_at": self.reset_at,
            "seconds_until_reset": self.seconds_until_reset,
            "notices": list(self.notices),
            "limits": [limit.to_dict() for limit in self.limits],
            "markdown": self.to_markdown(),
        }

    def to_markdown(self) -> str:
        icon, label = _LEVEL_META.get(self.level, ("ℹ️", self.level))
        lines = [f"## {icon} 세션 한도 — {label}", ""]
        if not self.limits:
            lines.append("활성화된 한도가 없습니다. 자유롭게 사용하세요.")
        else:
            for limit in self.limits:
                if limit.kind == "budget":
                    lines.append(
                        f"- **{limit.label}**: ${limit.used:.2f} / ${limit.limit:.2f}"
                        f" ({limit.usage_percent:.0f}%) — {limit.message}"
                    )
                else:
                    lines.append(
                        f"- **{limit.label}**: {limit.used:.0f} / {limit.limit:.0f} 회"
                        f" ({limit.usage_percent:.0f}%) — {limit.message}"
                    )
        if self.notices:
            lines.append("")
            for notice in self.notices:
                lines.append(f"- {notice}")
        lines.append("")
        lines.append(f"리셋 기준일(UTC): {self.reset_date}")
        return "\n".join(lines)


def format_countdown(seconds: int) -> str:
    """초 단위 시간을 카운트다운 문자열(예: '11시간 08분 29초')로 포맷."""
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}시간 {m:02d}분 {s:02d}초"
    if m > 0:
        return f"{m}분 {s:02d}초"
    return f"{s}초"


def build_session_disclosure(stats: DailyStats) -> SessionDisclosure:
    """CostGuard DailyStats → SessionDisclosure (결정론)."""
    notices: list[str] = [
        "사용 내역은 이 PC에만 저장되며 외부로 전송되지 않습니다.",
    ]
    limits: list[LimitDisclosure] = []
    now_utc = datetime.now(timezone.utc)

    # 예산 리셋 시각 (UTC 자정)
    budget_reset_at = str(stats.get("budget_reset_at") or "")
    if not budget_reset_at:
        tomorrow_date = now_utc.date() + timedelta(days=1)
        budget_reset_at = datetime.combine(tomorrow_date, dt_time.min, tzinfo=timezone.utc).isoformat()
    try:
        b_dt = datetime.fromisoformat(budget_reset_at)
        budget_seconds = max(0, int((b_dt - now_utc).total_seconds()))
    except Exception:
        budget_seconds = 0

    budget = float(stats.get("daily_budget_usd", 0.0) or 0.0)
    if budget > 0:
        used = float(stats.get("global_daily_spend_usd", 0.0) or 0.0)
        usage_percent = float(stats.get("usage_percent", 0.0) or 0.0)
        remaining = float(stats.get("remaining_usd", 0.0) or 0.0)
        level = _level_for_usage(usage_percent)
        if level == "exhausted":
            cd_str = format_countdown(budget_seconds)
            message = f"일일 예산이 소진되었습니다 — 리셋까지 {cd_str} 남음 (대기하거나 예산을 조정하세요)."
        elif level == "warning":
            message = "일일 예산의 80% 이상을 사용했습니다."
        else:
            message = "일일 예산 여유가 충분합니다."
        limits.append(
            LimitDisclosure(
                kind="budget",
                label="일일 예산",
                limit=budget,
                used=used,
                remaining=remaining,
                usage_percent=usage_percent,
                level=level,
                message=message,
                reset_at=budget_reset_at,
                seconds_until_reset=budget_seconds,
            )
        )
    else:
        notices.append("일일 예산 한도가 설정되지 않았습니다 (제한 없음).")

    # 시간당 액션 리셋 시각 (슬라이딩 윈도우)
    action_reset_at = str(stats.get("action_reset_at") or "")
    if not action_reset_at:
        action_reset_at = (now_utc + timedelta(hours=1)).isoformat()
    try:
        a_dt = datetime.fromisoformat(action_reset_at)
        action_seconds = max(0, int((a_dt - now_utc).total_seconds()))
    except Exception:
        action_seconds = 0

    hourly_limit = int(stats.get("hourly_limit", 0) or 0)
    if hourly_limit > 0:
        actions = float(stats.get("hourly_actions", 0) or 0)
        usage_percent = round((actions / hourly_limit * 100.0), 1)
        level = _level_for_usage(usage_percent)
        if level == "exhausted":
            cd_str = format_countdown(action_seconds)
            message = f"시간당 액션 한도에 도달했습니다 — 리셋까지 {cd_str} 남음 (잠시 후 재시도하세요)."
        elif level == "warning":
            message = "시간당 액션 한도의 80% 이상을 사용했습니다."
        else:
            message = "액션 한도 여유가 충분합니다."
        limits.append(
            LimitDisclosure(
                kind="action",
                label="시간당 액션",
                limit=float(hourly_limit),
                used=actions,
                remaining=float(max(0, hourly_limit - int(actions))),
                usage_percent=usage_percent,
                level=level,
                message=message,
                reset_at=action_reset_at,
                seconds_until_reset=action_seconds,
            )
        )
    else:
        notices.append("시간당 액션 한도가 설정되지 않았습니다 (제한 없음).")

    overall = "healthy"
    if limits:
        if any(limit.level == "exhausted" for limit in limits):
            overall = "exhausted"
        elif any(limit.level == "warning" for limit in limits):
            overall = "warning"

    return SessionDisclosure(
        level=overall,
        reset_date=str(stats.get("reset_date", "") or ""),
        reset_at=budget_reset_at,
        seconds_until_reset=budget_seconds,
        notices=notices,
        limits=limits,
    )


# ── 세션 한도 시딩 (벤치마킹: E2E 및 재현 가능한 개발 테스트용) ──

_SEED_PRESETS: dict[str, tuple[float, float]] = {
    # (spend_ratio, action_ratio)
    "healthy": (0.30, 0.30),
    "여유": (0.30, 0.30),
    "warning": (0.88, 0.86),
    "주의": (0.88, 0.86),
    "exhausted": (1.00, 1.00),
    "소진": (1.00, 1.00),
}


def seed_cost_guard(
    guard: CostGuard,
    *,
    seed_budget: str | float | None = None,
    seed_level: str | None = None,
    seed_actions: int | None = None,
) -> tuple[float, int, str]:
    """CostGuard 인스턴스를 지정된 예산/액션 수준으로 결정론적으로 시딩합니다.

    Args:
        guard: 시딩할 CostGuard 인스턴스.
        seed_budget: 금액($15.0, 15), 백분율(30%), 또는 프리셋 이름(healthy, warning, exhausted).
        seed_level: 바로가기 프리셋(healthy, warning, exhausted).
        seed_actions: 시간당 액션 수 수동 지정 (None인 경우 예산 비율에 비례).

    Returns:
        (target_spend_usd, target_actions, overall_level)
    """
    target_spend: float | None = None
    action_ratio: float = 0.0

    # 1. seed_level 파싱
    if seed_level is not None:
        normalized_level = str(seed_level).strip().lower()
        if normalized_level not in _SEED_PRESETS:
            raise ValueError(
                f"알 수 없는 seed_level '{seed_level}'. "
                f"지원 값: {', '.join(k for k in _SEED_PRESETS if not any(ord(c) > 127 for c in k))}"
            )
        spend_ratio, act_ratio = _SEED_PRESETS[normalized_level]
        target_spend = spend_ratio * guard.daily_budget_usd
        action_ratio = act_ratio

    # 2. seed_budget 파싱 (seed_level보다 우선하여 구체적인 값 적용 가능)
    if seed_budget is not None:
        if isinstance(seed_budget, (int, float)):
            target_spend = float(seed_budget)
            action_ratio = (target_spend / guard.daily_budget_usd) if guard.daily_budget_usd > 0 else 0.0
        elif isinstance(seed_budget, str):
            raw = seed_budget.strip()
            raw_lower = raw.lower()
            if raw_lower in _SEED_PRESETS:
                spend_ratio, act_ratio = _SEED_PRESETS[raw_lower]
                target_spend = spend_ratio * guard.daily_budget_usd
                action_ratio = act_ratio
            elif raw.endswith("%"):
                pct = float(raw[:-1].strip())
                spend_ratio = pct / 100.0
                target_spend = spend_ratio * guard.daily_budget_usd
                action_ratio = spend_ratio
            else:
                cleaned = raw.lstrip("$").strip()
                try:
                    target_spend = float(cleaned)
                    action_ratio = (target_spend / guard.daily_budget_usd) if guard.daily_budget_usd > 0 else 0.0
                except ValueError as exc:
                    raise ValueError(f"유효하지 않은 seed_budget '{seed_budget}'") from exc

    # 3. 기본값 폴백
    if target_spend is None:
        if seed_actions is not None:
            target_spend = 0.0
            action_ratio = 0.0
        else:
            return (0.0, 0, "healthy")

    target_spend = max(0.0, round(float(target_spend), 6))

    # 4. 액션 수 결정
    if seed_actions is not None:
        target_actions = max(0, int(seed_actions))
    else:
        target_actions = (
            max(0, int(round(action_ratio * guard.hourly_action_limit))) if guard.hourly_action_limit > 0 else 0
        )

    # 5. CostGuard 인스턴스에 원자적으로 적용
    with guard._lock:
        guard._global_daily_spend = target_spend
        guard._user_daily_spend["seed-system"] = target_spend
        now = time.time()
        guard._action_timestamps.clear()
        for i in range(target_actions):
            offset = (target_actions - 1 - i) * 0.1
            guard._action_timestamps.append(now - offset)
        if target_spend > 0:
            guard._spend_history = [
                SpendRecord(
                    timestamp=now,
                    cost_usd=target_spend,
                    model="e2e-seed",
                    user_id="seed-system",
                    tokens_in=1000,
                    tokens_out=500,
                )
            ]

    disclosure = build_session_disclosure(guard.get_daily_stats())
    return (target_spend, target_actions, disclosure.level)
