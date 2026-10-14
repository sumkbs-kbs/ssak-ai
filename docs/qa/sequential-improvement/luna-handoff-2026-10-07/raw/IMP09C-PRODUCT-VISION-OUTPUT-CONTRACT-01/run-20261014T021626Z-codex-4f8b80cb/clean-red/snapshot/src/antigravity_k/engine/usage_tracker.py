"""Ssak-Ai: 사용량 추적기.

============================
9Router의 usageDb 패턴 이식 — 모델별 토큰·레이턴시·성공률 메트릭 추적.

핵심 기능:
- record(): 요청별 사용량 기록
- get_stats(): 기간별 통계 조회
- to_dashboard_data(): 대시보드 UI용 데이터 반환
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, TypedDict, cast

from .cost_guard import CostGuard

logger = logging.getLogger("antigravity_k.usage_tracker")


# ─── 기본 DB 경로 (단일 패치 지점) ────────────────────────────────────
#
# 이전에는 호출자(`api/dependencies.py`)가 `UsageTracker(db_path="data/token_usage.json")`
# 처럼 **CWD 상대 경로를 하드코딩**했다. `data/token_usage.json` 은 **추적 파일**이고
# `record()` 는 ``auto_save_interval``(기본 50)건마다 `_save()` 를 호출하므로, 사용량을
# 50건 이상 기록하는 테스트 조합 하나면 **검증 실행이 후보 트리를 바꿨다** —
# F-02(benchmark_harness)와 같은 결함이 두 번째 경로에 남아 있었다.
#
# 이제 경로 결정은 이 한 곳에서만 일어난다. 프로덕션 기본값은 그대로다(누적 사용량 DB).
USAGE_DB_ENV_VAR: Final[str] = "AGK_USAGE_DB"
DEFAULT_USAGE_DB_RELATIVE: Final[Path] = Path("data/token_usage.json")


def resolve_usage_db_path(environ: Mapping[str, str] | None = None) -> Path:
    """환경 값으로부터 사용량 DB 경로를 계산하는 **순수** 함수.

    ``tests/conftest.py`` 가 :func:`default_usage_db_path` 를 패치하므로, 우선순위
    규칙 자체는 이 순수 함수로 검증해야 한다(패치된 함수를 부르면 **규칙이 아니라
    패치 결과**를 검증하게 된다 — CR-14 D-15 와 같은 이유).
    """
    source = os.environ if environ is None else environ
    override = source.get(USAGE_DB_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_USAGE_DB_RELATIVE


def default_usage_db_path() -> Path:
    """사용량 DB 의 기본 경로(테스트에서는 conftest 가 이 지점을 바꾼다)."""
    return resolve_usage_db_path()


class UsageRecordPayload(TypedDict):
    model_name: str
    timestamp: float
    tokens_in: int
    tokens_out: int
    latency_ms: float
    success: bool
    error: str
    combo_name: str
    fallback_depth: int


# ─── 데이터 클래스 ───────────────────────────────────────────────────


@dataclass
class UsageRecord:
    """요청 1건의 사용량 기록."""

    model_name: str
    timestamp: float  # unix timestamp
    tokens_in: int = 0  # 입력 토큰 수
    tokens_out: int = 0  # 출력 토큰 수
    latency_ms: float = 0.0  # 응답 시간 (ms)
    success: bool = True  # 성공 여부
    error: str = ""  # 실패 시 오류 메시지
    combo_name: str = ""  # 콤보 경유 시 콤보 이름
    fallback_depth: int = 0  # 폴백 깊이 (0=첫 번째 모델)

    @property
    def total_tokens(self) -> int:
        """Total Tokens.

        Returns:
            int: The int result.

        """
        return self.tokens_in + self.tokens_out


@dataclass
class UsageStats:
    """기간별 통합 통계."""

    model_name: str
    period: str  # hourly / daily / weekly / total
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    fallback_count: int = 0  # 폴백으로 사용된 횟수

    @property
    def success_rate(self) -> float:
        """Success Rate.

        Returns:
            float: The float result.

        """
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests * 100

    @property
    def total_tokens(self) -> int:
        """Total Tokens.

        Returns:
            int: The int result.

        """
        return self.total_tokens_in + self.total_tokens_out

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        d = cast(dict[str, object], cast(object, asdict(self)))
        d["success_rate"] = round(self.success_rate, 1)
        d["total_tokens"] = self.total_tokens
        return d


# ─── 메인 추적기 ─────────────────────────────────────────────────────


class UsageTracker:
    """모델별 사용량 및 성능 메트릭 추적.

    9Router 패턴: usageDb.js의 프로바이더별 토큰·비용 추적 구조를
    로컬 JSON 파일 기반으로 구현.

    사용 예시:
        tracker = UsageTracker(db_path="./data/usage.json")
        tracker.record("qwen3-72b", tokens_in=100, tokens_out=500,
                       latency_ms=1200, success=True)
        stats = tracker.get_stats("qwen3-72b", period="daily")
    """

    def __init__(
        self,
        db_path: str | None = None,
        max_records: int = 10000,
        auto_save_interval: int = 50,
        cost_guard: CostGuard | None = None,
    ):
        """Initialize the UsageTracker.

        Args:
            db_path (str | None): str | None db path.
            max_records (int): int max records.
            auto_save_interval (int): int auto save interval.
            cost_guard (CostGuard | None): CostGuard | None cost guard.

        """
        self._db_path: Path | None = Path(db_path) if db_path else None
        self._max_records: int = max_records
        self._auto_save_interval: int = auto_save_interval
        self._records: list[UsageRecord] = []
        self._unsaved_count: int = 0
        self._cost_guard: CostGuard | None = cost_guard  # IronClaw CostGuard 통합

        # DB 파일에서 기존 기록 로드
        if self._db_path:
            self._load()

    # ─── 기록 API ────────────────────────────────────────────────────

    def record(
        self,
        model_name: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        error: str = "",
        combo_name: str = "",
        fallback_depth: int = 0,
    ) -> UsageRecord:
        """요청 사용량을 기록합니다."""
        entry = UsageRecord(
            model_name=model_name,
            timestamp=time.time(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            success=success,
            error=error,
            combo_name=combo_name,
            fallback_depth=fallback_depth,
        )

        # ── IronClaw CostGuard Integration ──
        # 비용 기록 (cost_guard가 연결된 경우)
        if self._cost_guard and success:
            self._cost_guard.record_spend(
                cost_usd=0.0,  # 로컬 모델은 비용 0
                model=model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

        self._records.append(entry)
        self._unsaved_count += 1

        # 최대 레코드 수 초과 시 오래된 기록 제거
        if len(self._records) > self._max_records:
            overflow = len(self._records) - self._max_records
            self._records = self._records[overflow:]

        # 자동 저장
        if self._db_path and self._unsaved_count >= self._auto_save_interval:
            self._save()

        logger.debug(
            "사용량 기록: %s — in=%s, out=%s, latency=%sms, %s",
            model_name,
            tokens_in,
            tokens_out,
            latency_ms,
            "성공" if success else "실패",
        )
        return entry

    # ─── 통계 조회 ───────────────────────────────────────────────────

    def get_stats(
        self,
        model_name: str | None = None,
        period: str = "daily",
    ) -> list[UsageStats]:
        """기간별 통계를 계산합니다.

        Args:
            model_name: 특정 모델만 조회 (None=전체)
            period: hourly / daily / weekly / total

        """
        cutoff = self._get_cutoff(period)
        filtered = [
            r for r in self._records if r.timestamp >= cutoff and (model_name is None or r.model_name == model_name)
        ]

        # 모델별로 그룹핑
        grouped: dict[str, list[UsageRecord]] = defaultdict(list)
        for r in filtered:
            grouped[r.model_name].append(r)

        stats_list: list[UsageStats] = []
        for name, records in grouped.items():
            stats = self._compute_stats(name, records, period)
            stats_list.append(stats)

        # 총 요청 수 내림차순 정렬
        stats_list.sort(key=lambda s: s.total_requests, reverse=True)
        return stats_list

    def get_recent(self, count: int = 20) -> list[UsageRecord]:
        """최근 N건의 기록 반환."""
        return list(reversed(self._records[-count:]))

    def get_model_names(self) -> list[str]:
        """기록에 등장한 모든 모델 이름."""
        return list({r.model_name for r in self._records})

    def get_total_tokens(self) -> int:
        """현재까지 기록된 모든 토큰 수(입력+출력) 합계 반환."""
        total = 0
        for r in self._records:
            total += r.tokens_in + r.tokens_out
        return total

    # ─── 대시보드 데이터 ─────────────────────────────────────────────

    def to_dashboard_data(self) -> dict[str, object]:
        """대시보드 UI용 전체 통계 데이터."""
        daily_stats = self.get_stats(period="daily")
        total_stats = self.get_stats(period="total")

        # 시간별 토큰 사용량 추세
        hourly_trend = self._compute_hourly_trend()

        return {
            "daily": [s.to_dict() for s in daily_stats],
            "total": [s.to_dict() for s in total_stats],
            "hourly_trend": hourly_trend,
            "total_records": len(self._records),
            "models_used": self.get_model_names(),
        }

    # ─── 영속화 ──────────────────────────────────────────────────────

    def save(self) -> None:
        """수동 저장."""
        if self._db_path:
            self._save()

    def _save(self) -> None:
        """JSON 파일로 저장."""
        if not self._db_path:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "updated_at": datetime.now().astimezone().replace(tzinfo=None).isoformat(),
            "records": [asdict(r) for r in self._records],
        }

        try:
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._unsaved_count = 0
            logger.debug("사용량 DB 저장: %s (%s건)", self._db_path, len(self._records))
        except Exception:
            logger.exception("사용량 DB 저장 실패")

    def _load(self) -> None:
        """JSON 파일에서 로드."""
        if not self._db_path or not self._db_path.exists():
            return

        try:
            with open(self._db_path, encoding="utf-8") as f:
                data = cast(object, json.load(f))

            if not isinstance(data, dict):
                return
            payload = cast(dict[str, object], cast(object, data))
            raw_records = payload.get("records", [])
            if isinstance(raw_records, list):
                records = cast(list[object], cast(object, raw_records))
                self._records = [
                    UsageRecord(**cast(UsageRecordPayload, cast(object, record)))
                    for record in records
                    if isinstance(record, dict)
                ]
            logger.info("사용량 DB 로드: %s (%s건)", self._db_path, len(self._records))
        except Exception:
            logger.exception("사용량 DB 로드 실패")
            self._records = []

    # ─── 내부 유틸 ───────────────────────────────────────────────────

    def _get_cutoff(self, period: str) -> float:
        """기간별 시작 시각 계산."""
        now = time.time()
        if period == "hourly":
            return now - 3600
        elif period == "daily":
            return now - 86400
        elif period == "weekly":
            return now - 86400 * 7
        elif period == "monthly":
            return now - 86400 * 30
        else:  # total
            return 0.0

    @staticmethod
    def _compute_stats(
        model_name: str,
        records: list[UsageRecord],
        period: str,
    ) -> UsageStats:
        """레코드 리스트에서 통합 통계 계산."""
        if not records:
            return UsageStats(model_name=model_name, period=period)

        success = [r for r in records if r.success]
        latencies = [r.latency_ms for r in success if r.latency_ms > 0]

        return UsageStats(
            model_name=model_name,
            period=period,
            total_requests=len(records),
            success_count=len(success),
            failure_count=len(records) - len(success),
            total_tokens_in=sum(r.tokens_in for r in records),
            total_tokens_out=sum(r.tokens_out for r in records),
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            fallback_count=sum(1 for r in records if r.fallback_depth > 0),
        )

    def _compute_hourly_trend(self, hours: int = 24) -> list[dict[str, int]]:
        """시간별 토큰 사용량 추세 (최근 N시간)."""
        now = time.time()
        cutoff = now - hours * 3600
        filtered = [r for r in self._records if r.timestamp >= cutoff]

        # 시간별 버킷
        buckets: dict[int, dict[str, int]] = {}
        for r in filtered:
            hour_key = int((r.timestamp - cutoff) // 3600)
            if hour_key not in buckets:
                buckets[hour_key] = {
                    "hour": hour_key,
                    "tokens": 0,
                    "requests": 0,
                }
            buckets[hour_key]["tokens"] += r.total_tokens
            buckets[hour_key]["requests"] += 1

        # 빈 시간대 채우기
        result: list[dict[str, int]] = []
        for h in range(hours):
            bucket = buckets.get(h, {"hour": h, "tokens": 0, "requests": 0})
            result.append(bucket)

        return result

    def clear(self) -> None:
        """모든 기록 삭제."""
        self._records.clear()
        self._unsaved_count = 0
        if self._db_path:
            self._save()
        logger.info("사용량 기록 전체 삭제")
