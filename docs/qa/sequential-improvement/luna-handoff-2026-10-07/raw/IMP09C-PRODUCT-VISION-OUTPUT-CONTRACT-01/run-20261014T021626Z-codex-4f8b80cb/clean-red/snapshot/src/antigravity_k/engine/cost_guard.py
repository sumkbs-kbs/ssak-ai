"""CostGuard — 비용 제어 가드.

============================
IronClaw cost_guard.rs 패턴 이식.

핵심 패턴:
- Thread-Safe Budget Tracking: 글로벌/사용자별 일일 예산 관리
- Rate Limiter: VecDeque 슬라이딩 윈도우 기반 시간당 액션 제한
- Precision Cost Calculation: 캐시 할인 + 출력 승수 포함 정밀 비용 계산
- UTC 자정 기준 자동 리셋

사용법:
    guard = CostGuard(daily_budget_usd=50.0, hourly_action_limit=100)

    # LLM 호출 전 예산 확인
    decision = guard.check_budget("qwen3-72b", tokens_in=500,
                                   tokens_out=200, cached_in=100)
    if not decision.allowed:
        raise BudgetExceededError(decision.reason)

    # 비용 기록
    guard.record_spend(decision.estimated_cost_usd)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from typing import TypedDict

logger = logging.getLogger("antigravity_k.engine.cost_guard")


# ── 모델별 가격표 (USD per 1M tokens) ──
# 로컬 모델은 전력 비용 기반 추정, 클라우드는 공시 가격

MODEL_PRICING: dict[str, dict[str, float]] = {
    # 로컬 모델 (전력 비용 기반 추정) — Ollama 로컬
    "default": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    "local": {"input": 0.001, "output": 0.002, "cached_input": 0.0005},
    # ─── NVIDIA NIM (build.nvidia.com 무료 — $0, rate limit으로만 보호) ───
    "nim": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    "deepseek-ai/deepseek-r1": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    "meta/llama-3.1-405b-instruct": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    "meta/llama-3.3-70b-instruct": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    "nvidia/llama-3.1-nemotron-70b-instruct": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
    # ─── OpenAI (OpenRouter 경유 시 동일 가격) ───
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached_input": 1.25},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "cached_input": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075},
    # ─── Anthropic ───
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00, "cached_input": 1.50},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00, "cached_input": 1.50},
    "claude-3-haiku": {"input": 0.25, "output": 1.25, "cached_input": 0.125},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00, "cached_input": 7.50},
    # ─── Google ───
    "google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40, "cached_input": 0.05},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached_input": 0.05},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached_input": 0.625},
    # ─── ZAI/Zhipu GLM ───
    "glm-4-plus": {"input": 0.70, "output": 0.70, "cached_input": 0.35},
    "glm-4-air": {"input": 0.10, "output": 0.10, "cached_input": 0.05},
    # ─── OpenAI 직접 (o1/o3 시리즈) ───
    "o3-mini": {"input": 1.10, "output": 4.40, "cached_input": 0.55},
    # ─── Qwen (OpenRouter) ───
    "qwen/qwen3-next-80b-a3b-instruct": {"input": 0.30, "output": 0.90, "cached_input": 0.15},
    "qwen/qwen3-72b": {"input": 0.50, "output": 1.50, "cached_input": 0.25},
    "qwen/qwen3-235b-a35b": {"input": 0.80, "output": 2.40, "cached_input": 0.40},
    # ─── 무료 모델 (OpenRouter :free 접미사) ───
    ":free": {"input": 0.0, "output": 0.0, "cached_input": 0.0},
}


def resolve_pricing(model: str) -> dict[str, float]:
    """모델명에서 가격표를 해석합니다 (접두사/접미사 매칭 지원).

    우선순위:
      1. 정확한 모델명 매칭
      2. ':free' 접미사 → 무료
      3. provider 접두사 기반 추론 (openai/, anthropic/, meta/, nvidia/, deepseek-ai/)
      4. 'default' (로컬/무료)
    """
    if not model:
        return MODEL_PRICING["default"]

    # 1. 정확한 매칭
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]

    model_lower = model.lower()

    # 2. :free 접미사
    if model_lower.endswith(":free"):
        return MODEL_PRICING[":free"]

    # 3. provider 접두사 / 키워드 기반 추론
    if "deepseek-ai/" in model_lower or "meta/llama" in model_lower or model_lower.startswith("nvidia/"):
        return MODEL_PRICING["nim"]  # NIM 무료
    if "openai/gpt-4o-mini" in model_lower or "gpt-4o-mini" in model_lower:
        return MODEL_PRICING["openai/gpt-4o-mini"]
    if "gpt-4o" in model_lower:
        return MODEL_PRICING["gpt-4o"]
    if "claude-opus" in model_lower:
        return MODEL_PRICING["anthropic/claude-opus-4"]
    if "claude-3.5-sonnet" in model_lower or "claude-3-5-sonnet" in model_lower:
        return MODEL_PRICING["anthropic/claude-3.5-sonnet"]
    if "gemini-2.5-pro" in model_lower:
        return MODEL_PRICING["gemini-2.5-pro"]
    if "gemini" in model_lower:
        return MODEL_PRICING["gemini-2.0-flash"]
    if "glm-4-plus" in model_lower:
        return MODEL_PRICING["glm-4-plus"]
    if "glm-4-air" in model_lower or "glm" in model_lower:
        return MODEL_PRICING["glm-4-air"]
    if "o3-mini" in model_lower or "o1-mini" in model_lower:
        return MODEL_PRICING["o3-mini"]
    if "qwen3-next" in model_lower:
        return MODEL_PRICING["qwen/qwen3-next-80b-a3b-instruct"]
    if "qwen3-72b" in model_lower:
        return MODEL_PRICING["qwen/qwen3-72b"]
    if "qwen3-235b" in model_lower:
        return MODEL_PRICING["qwen/qwen3-235b-a35b"]
    # 로컬 Ollama 모델 (:tag 형식)
    if ":" in model and "/" not in model:
        return MODEL_PRICING["local"]
    # MAX 모드 가드용 가상 모델명
    if model == "max_mode":
        return MODEL_PRICING["default"]

    return MODEL_PRICING["default"]


# ── 데이터 클래스 ──


@dataclass(frozen=True)
class CostDecision:
    """비용 게이트 판정 결과."""

    allowed: bool = True
    reason: str = ""
    estimated_cost_usd: float = 0.0
    remaining_budget_usd: float = 0.0
    daily_spend_usd: float = 0.0
    hourly_actions: int = 0
    hourly_limit: int = 0

    @property
    def budget_usage_percent(self) -> float:
        """Budget Usage Percent.

        Returns:
            float: The float result.

        """
        if self.remaining_budget_usd <= 0 and self.daily_spend_usd > 0:
            return 100.0
        total = self.daily_spend_usd + self.remaining_budget_usd
        if total <= 0:
            return 0.0
        return (self.daily_spend_usd / total) * 100.0


@dataclass
class SpendRecord:
    """지출 기록."""

    timestamp: float
    cost_usd: float
    model: str = ""
    user_id: str = "default"
    tokens_in: int = 0
    tokens_out: int = 0


class DailyStats(TypedDict, total=False):
    global_daily_spend_usd: float
    daily_budget_usd: float
    remaining_usd: float
    usage_percent: float
    user_spends: dict[str, float]
    hourly_actions: int
    hourly_limit: int
    reset_date: str
    budget_reset_at: str
    action_reset_at: str | None


class SpendSummary(TypedDict):
    model: str
    cost_usd: float
    tokens_in: int
    tokens_out: int
    user_id: str


class DashboardData(DailyStats):
    enabled: bool
    recent_spends: list[SpendSummary]


# ── 메인 CostGuard ──


class CostGuard:
    """비용 제어 가드.

    IronClaw의 CostGuard를 Python으로 이식.
    Thread-safe하며 글로벌/사용자별 일일 예산과 시간당 레이트 리미터를 제공합니다.
    """

    def __init__(
        self,
        daily_budget_usd: float = 50.0,
        user_daily_budget_usd: float = 20.0,
        hourly_action_limit: int = 100,
        enabled: bool = True,
    ):
        """Initialize the CostGuard.

        Args:
            daily_budget_usd (float): float daily budget usd.
            user_daily_budget_usd (float): float user daily budget usd.
            hourly_action_limit (int): int hourly action limit.
            enabled (bool): bool enabled.

        """
        self.daily_budget_usd: float = daily_budget_usd
        self.user_daily_budget_usd: float = user_daily_budget_usd
        self.hourly_action_limit: int = hourly_action_limit
        self.enabled: bool = enabled

        self._lock: threading.Lock = threading.Lock()
        self._global_daily_spend: float = 0.0
        self._user_daily_spend: dict[str, float] = {}
        self._last_reset_date: str = self._today_utc()
        self._spend_history: list[SpendRecord] = []

        # Rate limiter: VecDeque 슬라이딩 윈도우 (IronClaw 패턴)
        self._action_timestamps: deque[float] = deque()

    # ── 예산 확인 ──

    def check_budget(
        self,
        model: str = "default",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cached_in: int = 0,
        user_id: str = "default",
    ) -> CostDecision:
        """LLM 호출 전 예산과 레이트 리밋을 확인합니다.

        IronClaw 패턴: check() → CostDecision 반환.
        """
        if not self.enabled:
            return CostDecision(allowed=True, reason="cost_guard_disabled")

        with self._lock:
            self._maybe_reset_daily()

            # 1. 비용 추정
            estimated = self._estimate_cost(model, tokens_in, tokens_out, cached_in)

            # 2. 글로벌 일일 예산 확인 — 추정 비용이 남은 예산을 초과하면 차단
            remaining_global = self.daily_budget_usd - self._global_daily_spend
            if estimated > remaining_global:
                return CostDecision(
                    allowed=False,
                    reason=(
                        f"글로벌 일일 예산 초과 "
                        f"(추정 ${estimated:.4f} > 잔여 ${max(0, remaining_global):.4f}, "
                        f"일일 한도 ${self.daily_budget_usd:.2f})"
                    ),
                    estimated_cost_usd=estimated,
                    remaining_budget_usd=max(0, remaining_global),
                    daily_spend_usd=self._global_daily_spend,
                )

            # 3. 사용자별 일일 예산 확인
            user_spend = self._user_daily_spend.get(user_id, 0.0)
            remaining_user = self.user_daily_budget_usd - user_spend
            if estimated > remaining_user:
                return CostDecision(
                    allowed=False,
                    reason=(
                        f"사용자 '{user_id}' 일일 예산 초과 "
                        f"(추정 ${estimated:.4f} > 잔여 ${max(0, remaining_user):.4f})"
                    ),
                    estimated_cost_usd=estimated,
                    remaining_budget_usd=max(0, remaining_user),
                    daily_spend_usd=user_spend,
                )

            # 4. 레이트 리밋 확인 (VecDeque 슬라이딩 윈도우)
            now = time.time()
            cutoff = now - 3600  # 1시간 윈도우
            while self._action_timestamps and self._action_timestamps[0] < cutoff:
                _ = self._action_timestamps.popleft()

            hourly_count = len(self._action_timestamps)
            if hourly_count >= self.hourly_action_limit:
                return CostDecision(
                    allowed=False,
                    reason=(f"시간당 액션 한도 초과 ({hourly_count}/{self.hourly_action_limit})"),
                    estimated_cost_usd=estimated,
                    remaining_budget_usd=max(0, remaining_global),
                    daily_spend_usd=self._global_daily_spend,
                    hourly_actions=hourly_count,
                    hourly_limit=self.hourly_action_limit,
                )

            # 승인 시 이 액션을 rate-limit 윈도우에 사전 예약 (check_budget가
            # record_spend와 쌍이 아닌 단독 호출에서도 rate limit이 동작하도록).
            self._action_timestamps.append(now)
            hourly_count = len(self._action_timestamps)

            return CostDecision(
                allowed=True,
                reason="budget_available",
                estimated_cost_usd=estimated,
                remaining_budget_usd=max(0, remaining_global),
                daily_spend_usd=self._global_daily_spend,
                hourly_actions=hourly_count,
                hourly_limit=self.hourly_action_limit,
            )

    # ── 비용 기록 ──

    def record_spend(
        self,
        cost_usd: float,
        user_id: str = "default",
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """실제 비용을 기록합니다."""
        with self._lock:
            self._maybe_reset_daily()
            self._global_daily_spend += cost_usd
            self._user_daily_spend[user_id] = self._user_daily_spend.get(user_id, 0.0) + cost_usd
            self._action_timestamps.append(time.time())

            self._spend_history.append(
                SpendRecord(
                    timestamp=time.time(),
                    cost_usd=cost_usd,
                    model=model,
                    user_id=user_id,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                ),
            )

            # 이력 크기 제한
            if len(self._spend_history) > 5000:
                self._spend_history = self._spend_history[-2500:]

        logger.debug(
            "CostGuard: recorded $%s for %s (daily total: $%s)",
            cost_usd,
            user_id,
            self._global_daily_spend,
        )

    # ── 조회 API ──

    def get_remaining_budget(self, user_id: str = "default") -> float:
        """잔여 예산을 반환합니다."""
        with self._lock:
            self._maybe_reset_daily()
            global_remaining = self.daily_budget_usd - self._global_daily_spend
            user_spend = self._user_daily_spend.get(user_id, 0.0)
            user_remaining = self.user_daily_budget_usd - user_spend
            return min(max(0, global_remaining), max(0, user_remaining))

    def get_daily_stats(self) -> DailyStats:
        """일일 비용 통계를 반환합니다."""
        with self._lock:
            self._maybe_reset_daily()
            now = time.time()
            cutoff = now - 3600
            while self._action_timestamps and self._action_timestamps[0] < cutoff:
                self._action_timestamps.popleft()

            # UTC 자정 리셋 시각 (다음날 00:00:00 UTC)
            now_dt = datetime.now(timezone.utc)
            tomorrow_date = now_dt.date() + timedelta(days=1)
            budget_reset_dt = datetime.combine(tomorrow_date, dt_time.min, tzinfo=timezone.utc)
            budget_reset_at = budget_reset_dt.isoformat()

            # 시간당 액션 리셋 시각: 한도에 도달한 경우 가장 오래된 타임스탬프 + 3600초
            action_reset_at: str | None = None
            if len(self._action_timestamps) >= self.hourly_action_limit and self._action_timestamps:
                oldest_ts = self._action_timestamps[0]
                action_reset_dt = datetime.fromtimestamp(oldest_ts + 3600, tz=timezone.utc)
                action_reset_at = action_reset_dt.isoformat()

            return {
                "global_daily_spend_usd": round(self._global_daily_spend, 6),
                "daily_budget_usd": self.daily_budget_usd,
                "remaining_usd": round(max(0, self.daily_budget_usd - self._global_daily_spend), 6),
                "usage_percent": round(
                    ((self._global_daily_spend / self.daily_budget_usd * 100) if self.daily_budget_usd > 0 else 0),
                    1,
                ),
                "user_spends": {uid: round(spend, 6) for uid, spend in self._user_daily_spend.items()},
                "hourly_actions": len(self._action_timestamps),
                "hourly_limit": self.hourly_action_limit,
                "reset_date": self._last_reset_date,
                "budget_reset_at": budget_reset_at,
                "action_reset_at": action_reset_at,
            }

    def to_dashboard_data(self) -> DashboardData:
        """대시보드 UI용 데이터를 반환합니다."""
        stats = self.get_daily_stats()
        recent_spends: list[SpendSummary] = [
            {
                "model": s.model,
                "cost_usd": round(s.cost_usd, 6),
                "tokens_in": s.tokens_in,
                "tokens_out": s.tokens_out,
                "user_id": s.user_id,
            }
            for s in self._spend_history[-20:]
        ]
        return {
            **stats,
            "enabled": self.enabled,
            "recent_spends": recent_spends,
        }

    # ── 정밀 비용 계산 (IronClaw 캐시 할인 패턴) ──

    def _estimate_cost(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cached_in: int = 0,
    ) -> float:
        """토큰 수에서 비용을 추정합니다.

        IronClaw 패턴:
        - 캐시 입력: 50% 할인 (cached_input 가격 적용)
        - 일반 입력: 정가
        - 출력: 별도 가격 (일반적으로 입력의 3-4x)
        """
        pricing = resolve_pricing(model)
        if not pricing:
            return 0.0

        input_price = pricing.get("input", 0.0)
        output_price = pricing.get("output", 0.0)
        cached_price = pricing.get("cached_input", input_price * 0.5)

        # 캐시되지 않은 입력 토큰
        fresh_in = max(0, tokens_in - cached_in)

        cost = (
            (fresh_in / 1_000_000) * input_price
            + (cached_in / 1_000_000) * cached_price
            + (tokens_out / 1_000_000) * output_price
        )

        return cost

    # ── 일일 리셋 ──

    def _maybe_reset_daily(self) -> None:
        """UTC 자정 기준으로 일일 카운터를 리셋합니다."""
        today = self._today_utc()
        if today != self._last_reset_date:
            logger.info(
                "CostGuard: daily reset (%s → %s), yesterday spend: $%s",
                self._last_reset_date,
                today,
                self._global_daily_spend,
            )
            self._global_daily_spend = 0.0
            self._user_daily_spend.clear()
            self._last_reset_date = today

    @staticmethod
    def _today_utc() -> str:
        """UTC 기준 오늘 날짜 문자열."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
