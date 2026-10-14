"""
Ssak-Ai: Kanban 태스크 관리 엔진
=======================================
Agent-Teams-AI 아키텍처 이식 — Kanban 보드 기반 태스크 오케스트레이션.

참조: 777genius/agent-teams-ai
- agent-teams-controller/src/internal/kanban.js     → 칼럼 전환 + 가드레일
- agent-teams-controller/src/internal/kanbanStore.js → 상태 영속성
- agent-teams-controller/src/internal/tasks.js      → 태스크 상태 머신
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from pydantic import JsonValue

logger = logging.getLogger(__name__)

type TaskValue = str | int | float | list[str]
type TaskRecord = dict[str, TaskValue]


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


# ─── Valid transitions (Agent-Teams assertKanbanColumnAllowed 패턴) ───
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.TODO},
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: {TaskStatus.IN_REVIEW, TaskStatus.BLOCKED, TaskStatus.TODO},
    TaskStatus.IN_REVIEW: {TaskStatus.DONE, TaskStatus.IN_PROGRESS},
    TaskStatus.BLOCKED: {TaskStatus.TODO, TaskStatus.IN_PROGRESS},
    TaskStatus.DONE: set(),  # terminal
}


@dataclass
class KanbanTask:
    """칸반 보드의 단일 태스크."""

    task_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = 0  # 0=normal, 1=high, 2=critical
    depends_on: list[str] = field(default_factory=list)
    assignee: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> TaskRecord:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "assignee": self.assignee,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KanbanBoard:
    """Agent-Teams 패턴: 칸반 기반 태스크 오케스트레이션."""

    board_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Autonomous Goal Board"
    tasks: dict[str, KanbanTask] = field(default_factory=dict)
    column_order: dict[str, list[str]] = field(default_factory=dict)

    # ─── Task CRUD ──────────────────────────────────────────────

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: int = 0,
        depends_on: list[str] | None = None,
    ) -> KanbanTask:
        task = KanbanTask(
            task_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            priority=priority,
            depends_on=depends_on or [],
        )
        self.tasks[task.task_id] = task
        col = self.column_order.setdefault(TaskStatus.TODO.value, [])
        col.append(task.task_id)
        logger.debug("Kanban: added task '%s' (%s)", title, task.task_id)
        return task

    def get_task(self, task_id: str) -> KanbanTask | None:
        return self.tasks.get(task_id)

    # ─── State Transitions (Agent-Teams assertKanbanColumnAllowed) ──

    def advance_task(self, task_id: str, target: TaskStatus) -> KanbanTask:
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        allowed = _VALID_TRANSITIONS.get(task.status, set())
        if target not in allowed:
            raise ValueError(
                f"Cannot transition task '{task.title}' from {task.status.value} → {target.value}. "
                + f"Allowed: {[s.value for s in allowed]}"
            )

        # Dependency check
        if target == TaskStatus.IN_PROGRESS:
            blocked_by = self._check_dependencies(task)
            if blocked_by:
                raise ValueError(f"Task '{task.title}' is blocked by unfinished dependencies: {', '.join(blocked_by)}")

        # Move between columns
        old_col = self.column_order.get(task.status.value, [])
        if task_id in old_col:
            old_col.remove(task_id)
        new_col = self.column_order.setdefault(target.value, [])
        new_col.append(task_id)

        task.status = target
        task.updated_at = time.time()
        return task

    def _check_dependencies(self, task: KanbanTask) -> list[str]:
        blocked: list[str] = []
        for dep_id in task.depends_on:
            dep = self.tasks.get(dep_id)
            if dep and dep.status != TaskStatus.DONE:
                blocked.append(f"{dep.title} ({dep.task_id})")
        return blocked

    # ─── Query ──────────────────────────────────────────────────

    def get_next_actionable(self) -> KanbanTask | None:
        """의존성이 충족된 다음 실행 가능 태스크 반환."""
        candidates = [t for t in self.tasks.values() if t.status == TaskStatus.TODO and not self._check_dependencies(t)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (-t.priority, t.created_at))
        return candidates[0]

    def get_by_status(self, status: TaskStatus) -> list[KanbanTask]:
        return [t for t in self.tasks.values() if t.status == status]

    def is_complete(self) -> bool:
        return all(t.status == TaskStatus.DONE for t in self.tasks.values()) if self.tasks else False

    def progress_pct(self) -> float:
        if not self.tasks:
            return 0.0
        done = sum(1 for t in self.tasks.values() if t.status == TaskStatus.DONE)
        return round(done / len(self.tasks) * 100, 1)

    # ─── GoalRunner Integration ─────────────────────────────────

    def decompose_from_steps(self, steps: Sequence[object]) -> None:
        """GoalRunner의 GoalStep 리스트를 칸반 태스크로 변환."""
        prev_id: str | None = None
        for step in steps:
            title_value: object = getattr(step, "title", None)
            title = title_value if isinstance(title_value, str) else str(step)
            description_value: object = getattr(step, "purpose", None)
            desc = description_value if isinstance(description_value, str) else ""
            task = self.add_task(
                title=title,
                description=desc,
                depends_on=[prev_id] if prev_id else [],
            )
            prev_id = task.task_id

    # ─── Markdown Rendering ─────────────────────────────────────

    def to_markdown(self) -> str:
        lines = [
            f"# 📋 Kanban Board: {self.name}",
            f"**Progress:** {self.progress_pct()}% ({sum(1 for t in self.tasks.values() if t.status == TaskStatus.DONE)}/{len(self.tasks)})",
            "",
        ]

        status_icon = {
            TaskStatus.BACKLOG: "📥",
            TaskStatus.TODO: "📝",
            TaskStatus.IN_PROGRESS: "🔄",
            TaskStatus.IN_REVIEW: "🔍",
            TaskStatus.DONE: "✅",
            TaskStatus.BLOCKED: "🚫",
        }

        for status in TaskStatus:
            tasks = self.get_by_status(status)
            if not tasks:
                continue
            icon = status_icon.get(status, "")
            lines.append(f"### {icon} {status.value.upper().replace('_', ' ')} ({len(tasks)})")
            for t in tasks:
                pri = "🔴 " if t.priority >= 2 else ("🟡 " if t.priority == 1 else "")
                deps = f" ← depends: {', '.join(t.depends_on)}" if t.depends_on else ""
                lines.append(f"- {pri}`{t.task_id}` {t.title}{deps}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, str | float | dict[str, TaskRecord]]:
        return {
            "board_id": self.board_id,
            "name": self.name,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "progress_pct": self.progress_pct(),
        }
