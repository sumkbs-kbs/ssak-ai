"""HeartbeatMonitor — 주기적 체크리스트 실행 데몬.

================================================
IronClaw heartbeat.rs 패턴 이식.

핵심 패턴:
- HEARTBEAT.md 기반 체크리스트: 마크다운 파일에서 주기적 작업 로드
- Quiet Hours: 설정 가능한 비활성 시간대 (기본: 23:00-07:00)
- Cost-Efficient Skip: 체크리스트가 비어 있으면 LLM 호출 생략
- AmbientWatchdog 통합: 하트비트와 워치독을 단일 데몬으로 병합

HEARTBEAT.md 형식:
    ## 시스템 상태 확인
    - [ ] pytest 실행 결과 확인 (매 30분)
    - [ ] 대시보드 빌드 상태 확인 (매 1시간)
    - [x] API 서버 응답 확인 (완료)

사용법:
    monitor = HeartbeatMonitor(project_root="/path/to/project")
    tasks = monitor.load_checklist()
    results = monitor.execute_due_tasks()
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

logger = logging.getLogger("antigravity_k.engine.heartbeat")


class HeartbeatStatusResult(TypedDict):
    task: str
    success: bool
    message: str
    duration_ms: float


class HeartbeatStatus(TypedDict):
    total_tasks: int
    due_tasks: int
    completed_tasks: int
    quiet_hours: bool
    checklist_path: str
    recent_results: list[HeartbeatStatusResult]


# ── 데이터 클래스 ──


@dataclass
class HeartbeatTask:
    """체크리스트 항목."""

    title: str
    completed: bool = False
    interval_minutes: int = 60  # 실행 주기 (분)
    last_run: float = 0.0  # 마지막 실행 시각 (unix timestamp)
    section: str = ""  # 상위 섹션 (h2 헤딩)

    @property
    def is_due(self) -> bool:
        """실행 시점이 도래했는지 확인합니다."""
        if self.completed:
            return False
        if self.last_run == 0.0:
            return True
        elapsed = time.time() - self.last_run
        return elapsed >= self.interval_minutes * 60


@dataclass
class HeartbeatResult:
    """체크리스트 실행 결과."""

    task_title: str
    success: bool = False
    message: str = ""
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ── 인터벌 파싱 정규식 ──

_INTERVAL_RE = re.compile(r"\(매\s*(\d+)\s*(분|시간|초)\)", re.IGNORECASE)
_INTERVAL_EN_RE = re.compile(r"\(every\s*(\d+)\s*(min|hour|sec|m|h|s)\w*\)", re.IGNORECASE)


# ── 메인 모니터 ──


class HeartbeatMonitor:
    """주기적 체크리스트 실행 모니터.

    IronClaw heartbeat.rs 패턴:
    HEARTBEAT.md를 파싱하여 주기적으로 작업을 실행합니다.
    AmbientWatchdog와 통합하여 단일 데몬으로 동작합니다.
    """

    def __init__(
        self,
        project_root: str = ".",
        checklist_path: str = "HEARTBEAT.md",
        quiet_hours: tuple[int, int] = (23, 7),
        default_interval_minutes: int = 60,
    ):
        """Initialize the HeartbeatMonitor.

        Args:
            project_root (str): str project root.
            checklist_path (str): str checklist path.
            quiet_hours (tuple[int, int]): tuple[int, int] quiet hours.
            default_interval_minutes (int): int default interval minutes.

        """
        self.project_root: str = os.path.abspath(project_root)
        self.checklist_path: str = os.path.join(self.project_root, checklist_path)
        self.quiet_start: int = quiet_hours[0]  # 23시
        self.quiet_end: int = quiet_hours[1]  # 07시
        self.default_interval: int = default_interval_minutes

        self._tasks: list[HeartbeatTask] = []
        self._last_load_time: float = 0.0
        self._results_history: list[HeartbeatResult] = []

    # ── 체크리스트 로드 ──

    def load_checklist(self) -> list[HeartbeatTask]:
        """HEARTBEAT.md에서 체크리스트를 파싱합니다.

        IronClaw 패턴: 마크다운 체크리스트를 구조화된 태스크 목록으로 변환.
        """
        if not os.path.isfile(self.checklist_path):
            self._tasks = []
            return []

        try:
            with open(self.checklist_path, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            logger.exception("HEARTBEAT.md 로드 실패")
            self._tasks = []
            return []

        tasks: list[HeartbeatTask] = []
        current_section = ""

        for line in content.split("\n"):
            stripped = line.strip()

            # 섹션 감지 (## 헤딩)
            if stripped.startswith("## "):
                current_section = stripped[3:].strip()
                continue

            # 체크리스트 항목 감지
            if stripped.startswith("- [ ] "):
                title = stripped[6:].strip()
                interval = self._parse_interval(title)
                tasks.append(
                    HeartbeatTask(
                        title=self._clean_title(title),
                        completed=False,
                        interval_minutes=interval,
                        section=current_section,
                    ),
                )
            elif stripped.startswith("- [x] ") or stripped.startswith("- [X] "):
                title = stripped[6:].strip()
                tasks.append(
                    HeartbeatTask(
                        title=self._clean_title(title),
                        completed=True,
                        section=current_section,
                    ),
                )

        # 기존 실행 시각 보존
        old_times = {t.title: t.last_run for t in self._tasks}
        for task in tasks:
            if task.title in old_times:
                task.last_run = old_times[task.title]

        self._tasks = tasks
        self._last_load_time = time.time()
        logger.debug("HEARTBEAT.md: %s개 항목 로드 (%s)", len(tasks), current_section)
        return tasks

    # ── 실행 ──

    def execute_due_tasks(
        self,
        executor_fn: Callable[[str], object] | None = None,
    ) -> list[HeartbeatResult]:
        """실행 시점이 도래한 태스크를 실행합니다.

        IronClaw 패턴:
        - Quiet Hours 시 스킵
        - 체크리스트가 비어 있으면 LLM 호출 생략 (비용 효율)
        - executor_fn이 None이면 태스크를 "due" 상태로만 보고
        """
        results: list[HeartbeatResult] = []

        # Quiet Hours 확인
        if self.is_quiet_hours():
            logger.debug("HeartbeatMonitor: quiet hours — 스킵")
            return results

        # 체크리스트 재로드 (5분마다)
        if time.time() - self._last_load_time > 300:
            _ = self.load_checklist()

        # 비어 있으면 스킵 (cost-efficient)
        due_tasks = [t for t in self._tasks if t.is_due]
        if not due_tasks:
            return results

        for task in due_tasks:
            start = time.time()
            try:
                if executor_fn:
                    result_msg = executor_fn(task.title)
                    success = True
                else:
                    result_msg = f"[DUE] {task.title} — executor 미설정"
                    success = True

                duration = (time.time() - start) * 1000
                result = HeartbeatResult(
                    task_title=task.title,
                    success=success,
                    message=str(result_msg)[:500],
                    duration_ms=round(duration, 1),
                )
                task.last_run = time.time()
            except Exception as e:
                logger.exception("Unhandled exception")
                duration = (time.time() - start) * 1000
                result = HeartbeatResult(
                    task_title=task.title,
                    success=False,
                    message=f"실행 실패: {e}",
                    duration_ms=round(duration, 1),
                )

            results.append(result)
            self._results_history.append(result)

        # 이력 크기 제한
        if len(self._results_history) > 200:
            self._results_history = self._results_history[-100:]

        return results

    # ── Quiet Hours (IronClaw 패턴) ──

    def is_quiet_hours(self) -> bool:
        """현재 시각이 Quiet Hours인지 확인합니다.

        IronClaw 패턴: quiet_hours 동안 LLM 호출을 억제하여 비용을 절약합니다.
        """
        current_hour = datetime.now().hour
        if self.quiet_start > self.quiet_end:
            # 자정을 걸치는 경우 (예: 23:00 ~ 07:00)
            return current_hour >= self.quiet_start or current_hour < self.quiet_end
        else:
            return self.quiet_start <= current_hour < self.quiet_end

    # ── 상태 보고 ──

    def get_status(self) -> HeartbeatStatus:
        """하트비트 모니터 상태를 반환합니다."""
        due_count = sum(1 for t in self._tasks if t.is_due)
        return {
            "total_tasks": len(self._tasks),
            "due_tasks": due_count,
            "completed_tasks": sum(1 for t in self._tasks if t.completed),
            "quiet_hours": self.is_quiet_hours(),
            "checklist_path": self.checklist_path,
            "recent_results": [
                {
                    "task": r.task_title,
                    "success": r.success,
                    "message": r.message[:100],
                    "duration_ms": r.duration_ms,
                }
                for r in self._results_history[-5:]
            ],
        }

    # ── 내부 유틸 ──

    def _parse_interval(self, title: str) -> int:
        """타이틀에서 실행 주기를 파싱합니다.

        예: "pytest 실행 (매 30분)" → 30
            "빌드 확인 (every 2 hours)" → 120
        """
        # 한국어 패턴
        match = _INTERVAL_RE.search(title)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == "시간":
                return value * 60
            elif unit == "초":
                return max(1, value // 60)
            return value

        # 영어 패턴
        match = _INTERVAL_EN_RE.search(title)
        if match:
            value = int(match.group(1))
            unit = match.group(2).lower()
            if unit in ("hour", "h"):
                return value * 60
            elif unit in ("sec", "s"):
                return max(1, value // 60)
            return value

        return self.default_interval

    @staticmethod
    def _clean_title(title: str) -> str:
        """타이틀에서 인터벌 표기를 제거합니다."""
        title = _INTERVAL_RE.sub("", title).strip()
        title = _INTERVAL_EN_RE.sub("", title).strip()
        return title
