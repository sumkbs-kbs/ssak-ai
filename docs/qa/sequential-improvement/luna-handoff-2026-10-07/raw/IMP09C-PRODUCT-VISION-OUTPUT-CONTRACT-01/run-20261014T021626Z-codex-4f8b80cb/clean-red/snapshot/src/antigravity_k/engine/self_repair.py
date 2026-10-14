"""SelfRepairEngine — 자율 복구 엔진.

==================================
IronClaw self_repair.rs 패턴 이식.

핵심 패턴:
- Stuck Job Detection: InProgress → Stuck → Failed 3단계 상태 전이
- Protected Tool Filter: 내장 읽기 전용 도구는 복구 대상에서 제외
- Repair Strategy: 재시도 → 대체 전환 → 중단의 단계적 복구
- Notification Dedup: 동일 실패에 대한 반복 알림 해시 기반 방지

사용법:
    engine = SelfRepairEngine()

    # 작업 상태 감시
    detection = engine.detect_stuck(job_state)
    if detection.is_stuck:
        result = engine.attempt_repair(detection)

    # 알림 중복 방지
    if engine.should_notify(result.fingerprint):
        notify_user(result.message)
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from pydantic import JsonValue

logger = logging.getLogger("antigravity_k.engine.self_repair")

type FailureValue = str | float
type FailureRecord = dict[str, FailureValue]
type RepairDetails = dict[str, JsonValue]


# ── 보호 도구 목록 (IronClaw is_protected_tool_name 패턴) ──

PROTECTED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # 읽기 전용 도구 — 리빌드/재설치 불필요
        "read_file",
        "grep_search",
        "glob_search",
        "list_directory",
        "web_search",
        "web_scrape",
        "fetch_dom",
        "git_status",
        "git_log",
        "git_diff",
        "search_knowledge",
        "hex_dump",
        "impact_analyzer",
        # 시스템 내장 도구 — 항상 사용 가능
        "echo",
        "time",
        "json",
        "tool_list",
        "tool_info",
        "memory_search",
        "memory_read",
        "memory_tree",
    },
)


# ── 상태 열거형 ──


class JobState(str, Enum):
    """작업 상태 (IronClaw 3단계 전이 모델)."""

    IN_PROGRESS = "in_progress"
    STUCK = "stuck"
    FAILED = "failed"
    COMPLETED = "completed"


class RepairLevel(str, Enum):
    """복구 수준."""

    RETRY = "retry"  # Level 1: 동일 도구 재시도 (인자 변경)
    SWITCH = "switch"  # Level 2: 대체 도구/모델 전환
    ABORT = "abort"  # Level 3: 작업 중단 + 사용자 알림


# ── 데이터 클래스 ──


@dataclass(frozen=True, slots=True)
class StuckJobPolicy:
    """Stuck Job 감지 정책."""

    stuck_timeout_seconds: float = 120.0  # InProgress → Stuck 전이 타임아웃
    failed_timeout_seconds: float = 300.0  # Stuck → Failed 전이 타임아웃
    max_same_tool_failures: int = 3  # 동일 도구 반복 실패 허용 횟수
    max_total_failures: int = 8  # 작업 내 총 실패 허용 횟수


@dataclass(frozen=True, slots=True)
class StuckDetection:
    """Stuck 감지 결과."""

    is_stuck: bool = False
    job_id: str = ""
    current_state: JobState = JobState.IN_PROGRESS
    suggested_state: JobState = JobState.IN_PROGRESS
    reason: str = ""
    stuck_tool_name: str = ""
    failure_count: int = 0
    elapsed_seconds: float = 0.0

    @property
    def fingerprint(self) -> str:
        """알림 중복 제거용 핑거프린트."""
        raw = f"{self.job_id}:{self.stuck_tool_name}:{self.reason}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class RepairResult:
    """복구 시도 결과."""

    success: bool = False
    level: RepairLevel = RepairLevel.RETRY
    action_taken: str = ""
    message: str = ""
    fingerprint: str = ""
    details: RepairDetails = field(default_factory=dict)


# ── 메인 엔진 ──


class SelfRepairEngine:
    """자율 복구 엔진.

    IronClaw의 SelfRepair 트레이트를 Python으로 이식.
    GoalRunner의 Repair Loop(Step 5)를 실시간 자율 복구로 강화합니다.
    """

    def __init__(self, policy: StuckJobPolicy | None = None) -> None:
        """Initialize the SelfRepairEngine.

        Args:
            policy (StuckJobPolicy | None): StuckJobPolicy | None policy.

        """
        self.policy: StuckJobPolicy = policy or StuckJobPolicy()
        self._notified_fingerprints: set[str] = set()
        self._job_failure_history: dict[str, list[FailureRecord]] = {}
        self._job_start_times: dict[str, float] = {}
        self._max_fingerprint_cache: int = 500

    # ── 보호 도구 필터 (IronClaw defense-in-depth) ──

    @staticmethod
    def is_protected_tool(tool_name: str) -> bool:
        """도구가 보호 목록에 포함되는지 확인합니다.

        IronClaw 패턴: 내장 읽기 전용 도구는 self-repair 대상에서 제외하여
        불필요한 리빌드/재설치 사이드이펙트를 방지합니다.
        """
        return tool_name in PROTECTED_TOOL_NAMES

    # ── 작업 상태 관리 ──

    def register_job(self, job_id: str) -> None:
        """새 작업을 등록합니다."""
        self._job_start_times[job_id] = time.time()
        _ = self._job_failure_history.setdefault(job_id, [])

    def record_failure(
        self,
        job_id: str,
        tool_name: str,
        error: str = "",
        args_hash: str = "",
    ) -> None:
        """도구 실패를 기록합니다."""
        history = self._job_failure_history.setdefault(job_id, [])
        history.append(
            {
                "tool_name": tool_name,
                "error": error[:300],
                "args_hash": args_hash,
                "timestamp": time.time(),
            },
        )

    def record_success(self, job_id: str, tool_name: str) -> None:
        """도구 성공 시 해당 도구의 실패 카운트를 초기화합니다."""
        history = self._job_failure_history.get(job_id, [])
        self._job_failure_history[job_id] = [f for f in history if f["tool_name"] != tool_name]

    # ── Stuck 감지 ──

    def detect_stuck(self, job_state: Mapping[str, JsonValue]) -> StuckDetection:
        """작업 상태를 분석하여 Stuck 여부를 감지합니다.

        IronClaw 패턴: InProgress → Stuck → Failed 3단계 전이.
        """
        job_id_value = job_state.get("job_id", "")
        state_value = job_state.get("state", "in_progress")
        tool_value = job_state.get("current_tool", "")
        job_id = str(job_id_value)
        current = JobState(state_value if isinstance(state_value, str) else "in_progress")
        tool_name = str(tool_value)

        # 보호 도구는 Stuck 판정에서 제외
        if tool_name and self.is_protected_tool(tool_name):
            return StuckDetection(
                job_id=job_id,
                current_state=current,
                suggested_state=current,
                reason="protected_tool_excluded",
            )

        # 경과 시간 계산
        start_time = self._job_start_times.get(job_id, time.time())
        elapsed = time.time() - start_time

        # 실패 이력 분석
        history = self._job_failure_history.get(job_id, [])
        total_failures = len(history)

        # 동일 도구 반복 실패 카운트
        same_tool_failures = sum(1 for f in history if f["tool_name"] == tool_name) if tool_name else 0

        # Stuck 판정 기준
        is_stuck = False
        reason = ""
        suggested = current

        if total_failures >= self.policy.max_total_failures:
            is_stuck = True
            reason = f"total_failures_exceeded ({total_failures}/{self.policy.max_total_failures})"
            suggested = JobState.FAILED
        elif same_tool_failures >= self.policy.max_same_tool_failures:
            is_stuck = True
            reason = f"same_tool_failures_exceeded ({same_tool_failures}/{self.policy.max_same_tool_failures})"
            suggested = JobState.STUCK
        elif elapsed >= self.policy.failed_timeout_seconds and current == JobState.STUCK:
            is_stuck = True
            reason = f"stuck_timeout_exceeded ({elapsed:.0f}s/{self.policy.failed_timeout_seconds}s)"
            suggested = JobState.FAILED
        elif elapsed >= self.policy.stuck_timeout_seconds and current == JobState.IN_PROGRESS:
            # InProgress가 오래 지속되면 Stuck으로 전이
            if total_failures > 0:
                is_stuck = True
                reason = f"progress_stalled ({elapsed:.0f}s with {total_failures} failures)"
                suggested = JobState.STUCK

        return StuckDetection(
            is_stuck=is_stuck,
            job_id=job_id,
            current_state=current,
            suggested_state=suggested,
            reason=reason,
            stuck_tool_name=tool_name,
            failure_count=total_failures,
            elapsed_seconds=elapsed,
        )

    # ── 자동 복구 ──

    def attempt_repair(self, detection: StuckDetection) -> RepairResult:
        """Stuck 감지 결과에 따라 자동 복구를 시도합니다.

        IronClaw 패턴: Level 1(재시도) → Level 2(전환) → Level 3(중단).
        """
        if not detection.is_stuck:
            return RepairResult(
                success=True,
                level=RepairLevel.RETRY,
                action_taken="no_repair_needed",
                message="작업이 정상 진행 중입니다.",
                fingerprint=detection.fingerprint,
            )

        # Level 결정
        if detection.suggested_state == JobState.FAILED:
            level = RepairLevel.ABORT
        elif detection.failure_count >= self.policy.max_same_tool_failures:
            level = RepairLevel.SWITCH
        else:
            level = RepairLevel.RETRY

        # 복구 전략 실행
        if level == RepairLevel.RETRY:
            return RepairResult(
                success=True,
                level=level,
                action_taken="retry_with_modified_args",
                message=(
                    f"도구 '{detection.stuck_tool_name}'을(를) 수정된 인자로 재시도합니다. "
                    f"({detection.failure_count}회 실패 중)"
                ),
                fingerprint=detection.fingerprint,
                details={
                    "suggestion": "이전과 다른 인자 또는 접근 방식을 사용하세요.",
                    "job_id": detection.job_id,
                },
            )
        elif level == RepairLevel.SWITCH:
            return RepairResult(
                success=True,
                level=level,
                action_taken="switch_tool_or_model",
                message=(
                    f"도구 '{detection.stuck_tool_name}'이(가) {detection.failure_count}회 "
                    "반복 실패. 대체 도구 또는 모델로 전환합니다."
                ),
                fingerprint=detection.fingerprint,
                details={
                    "suggestion": "대체 도구를 선택하거나 모델을 전환하세요.",
                    "job_id": detection.job_id,
                    "stuck_tool": detection.stuck_tool_name,
                },
            )
        else:  # ABORT
            return RepairResult(
                success=False,
                level=level,
                action_taken="abort_job",
                message=(
                    f"작업 '{detection.job_id}'이(가) 복구 불가 상태입니다. "
                    f"사유: {detection.reason}. 사용자 개입이 필요합니다."
                ),
                fingerprint=detection.fingerprint,
                details={
                    "job_id": detection.job_id,
                    "total_failures": detection.failure_count,
                    "elapsed_seconds": detection.elapsed_seconds,
                },
            )

    # ── 알림 중복 방지 (IronClaw notification_fingerprint 패턴) ──

    def should_notify(self, fingerprint: str) -> bool:
        """동일 핑거프린트의 알림이 이미 발송되었는지 확인합니다.

        IronClaw 패턴: 해시 기반 중복 제거로 알림 스팸 방지.
        """
        if fingerprint in self._notified_fingerprints:
            return False

        self._notified_fingerprints.add(fingerprint)
        # 캐시 크기 제한
        if len(self._notified_fingerprints) > self._max_fingerprint_cache:
            # 가장 오래된 절반 제거 (set은 순서 없으므로 임의 제거)
            excess = len(self._notified_fingerprints) - self._max_fingerprint_cache // 2
            for _ in range(excess):
                _ = self._notified_fingerprints.pop()

        return True

    def clear_notifications(self, job_id: str | None = None) -> None:
        """알림 핑거프린트 캐시를 초기화합니다."""
        if job_id is None:
            self._notified_fingerprints.clear()
        # job_id 기반 선택적 클리어는 핑거프린트에 job_id가 인코딩되어 있으므로
        # 전체 클리어만 지원

    # ── 상태 보고 ──

    def get_repair_stats(self) -> dict[str, int]:
        """복구 엔진 통계를 반환합니다."""
        total_failures = sum(len(history) for history in self._job_failure_history.values())
        active_jobs = len(self._job_start_times)
        return {
            "active_jobs": active_jobs,
            "total_recorded_failures": total_failures,
            "notified_fingerprints": len(self._notified_fingerprints),
            "protected_tools_count": len(PROTECTED_TOOL_NAMES),
        }

    def cleanup_job(self, job_id: str) -> None:
        """완료된 작업의 이력을 정리합니다."""
        _ = self._job_failure_history.pop(job_id, None)
        _ = self._job_start_times.pop(job_id, None)
