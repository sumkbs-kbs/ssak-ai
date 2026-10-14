#!/usr/bin/env python3
"""
Ssak-Ai: 파이프라인 지연 시간 측정기 (Pipeline Timer)
=============================================================
검색→추출 파이프라인의 각 단계별 소요 시간을 측정하고
누적 통계를 제공합니다.

사용 예:
    timer = PipelineTimer()
    with timer.measure("web_search"):
        result = search(query)
    with timer.measure("extract_all"):
        data = extract(texts)
    stats = timer.get_stats()
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import ClassVar

logger = logging.getLogger("pipeline_timer")

type TimingValue = str | int | float
type TimingRecordData = dict[str, TimingValue]
type PipelineStats = dict[
    str,
    int | float | dict[str, TimingRecordData] | list[TimingRecordData],
]


@dataclass
class TimingRecord:
    """단일 타이밍 측정 기록."""

    step: str
    duration_ms: float
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> TimingRecordData:
        return {
            "step": self.step,
            "duration_ms": round(self.duration_ms, 1),
            "timestamp": self.timestamp,
        }


@dataclass
class StepStats:
    """단일 단계의 누적 통계."""

    step: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    avg_ms: float = 0.0
    last_ms: float = 0.0

    def update(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.last_ms = duration_ms
        if self.count == 1:
            self.min_ms = duration_ms
            self.max_ms = duration_ms
        else:
            self.min_ms = min(self.min_ms, duration_ms)
            self.max_ms = max(self.max_ms, duration_ms)
        self.avg_ms = round(self.total_ms / self.count, 1)

    def to_dict(self) -> TimingRecordData:
        return {
            "step": self.step,
            "count": self.count,
            "avg_ms": round(self.avg_ms, 1),
            "min_ms": round(self.min_ms, 1),
            "max_ms": round(self.max_ms, 1),
            "last_ms": round(self.last_ms, 1),
            "total_ms": round(self.total_ms, 1),
        }


class PipelineTimer:
    """파이프라인 지연 시간 측정기 (스레드 세이프 싱글턴).

    전체 프로세스 수명 동안 각 단계별 실행 시간을 누적하여
    평균/최소/최대/최근 지연 시간을 제공합니다.
    """

    _lock: ClassVar[Lock] = Lock()
    _steps: ClassVar[dict[str, StepStats]] = {}
    _recent_records: ClassVar[list[TimingRecord]] = []
    _max_recent: ClassVar[int] = 200  # 최근 기록 최대 보관 수

    # ─── 컨텍스트 매니저 ─────────────────────────────────────

    class _Measure:
        """with 문을 사용한 측정 컨텍스트 매니저."""

        def __init__(self, timer: type["PipelineTimer"], step: str) -> None:
            self._timer: type["PipelineTimer"] = timer
            self._step: str = step
            self._start: float = 0.0

        def __enter__(self) -> "PipelineTimer._Measure":
            self._start = time.perf_counter()
            return self

        def __exit__(self, *args: object) -> None:
            duration_ms = (time.perf_counter() - self._start) * 1000
            self._timer.record(self._step, duration_ms)

    @classmethod
    def measure(cls, step: str) -> "_Measure":
        """with 문으로 사용할 측정 컨텍스트를 반환합니다.

        사용법:
            with PipelineTimer.measure("step_name"):
                do_something()
        """
        return cls._Measure(cls, step)

    # ─── 기록 ─────────────────────────────────────────────────

    @classmethod
    def record(cls, step: str, duration_ms: float) -> None:
        """단일 단계의 지연 시간을 기록합니다.

        Args:
            step: 단계 이름 (예: "web_search", "top1_json", "extract_all")
            duration_ms: 소요 시간 (밀리초)
        """
        with cls._lock:
            # 단계별 통계 업데이트
            if step not in cls._steps:
                cls._steps[step] = StepStats(step=step)
            cls._steps[step].update(duration_ms)

            # 최근 기록 추가
            record = TimingRecord(step=step, duration_ms=round(duration_ms, 1))
            cls._recent_records.append(record)

            # 최대 보관 수 유지
            if len(cls._recent_records) > cls._max_recent:
                cls._recent_records = cls._recent_records[-cls._max_recent :]

    @classmethod
    def record_step(cls, step: str, duration_ms: float) -> None:
        """record()의 별칭 (외부 호출 편의용)."""
        cls.record(step, duration_ms)

    # ─── 통계 조회 ─────────────────────────────────────────────

    @classmethod
    def get_stats(cls) -> PipelineStats:
        """전체 파이프라인 단계별 누적 통계를 반환합니다.

        Returns:
            dict: {
                total_calls: int (모든 단계의 총 호출 수),
                steps: {step_name: StepStats.to_dict(), ...},
                recent: [TimingRecord.to_dict(), ...] (최근 10개),
                pipeline_total_avg_ms: float (전체 파이프라인 평균),
            }
        """
        with cls._lock:
            steps_dict = {name: stats.to_dict() for name, stats in sorted(cls._steps.items())}

            # 전체 파이프라인 평균 (web_search + extract_all 기준)
            pipeline_avg = 0.0
            pipeline_count = 0
            web_stats = cls._steps.get("web_search")
            extract_stats = cls._steps.get("extract_all")
            if web_stats and extract_stats:
                # 동일한 호출 쌍으로 가정
                pipeline_count = min(web_stats.count, extract_stats.count)
                if pipeline_count > 0:
                    pipeline_avg = round((web_stats.total_ms + extract_stats.total_ms) / pipeline_count, 1)

            return {
                "total_calls": sum(s.count for s in cls._steps.values()),
                "steps": steps_dict,
                "recent": [r.to_dict() for r in cls._recent_records[-10:]],
                "pipeline_total_avg_ms": pipeline_avg,
            }

    @classmethod
    def get_step_stats(cls, step: str) -> StepStats | None:
        """특정 단계의 통계를 반환합니다."""
        with cls._lock:
            return cls._steps.get(step)

    @classmethod
    def get_recent(cls, limit: int = 10) -> list[TimingRecord]:
        """최근 기록을 반환합니다."""
        with cls._lock:
            return cls._recent_records[-limit:]

    @classmethod
    def reset(cls) -> None:
        """모든 타이밍 데이터를 초기화합니다 (테스트용)."""
        with cls._lock:
            cls._steps.clear()
            cls._recent_records.clear()
