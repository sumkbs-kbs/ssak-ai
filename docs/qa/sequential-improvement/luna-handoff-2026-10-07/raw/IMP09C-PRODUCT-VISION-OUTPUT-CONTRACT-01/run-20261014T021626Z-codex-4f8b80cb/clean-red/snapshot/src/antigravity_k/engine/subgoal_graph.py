"""Subgoal & Dependency Graph Engine — Deterministic Task DAG for 27B planning.

27B-class models struggle with planning horizons beyond 3-4 steps when managed via
loose text. This module introduces a deterministic Directed Acyclic Graph (DAG)
that enforces dependency checking, topological execution ordering, and step validation.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class TaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class SubgoalNode:
    """A discrete, verifiable unit of work."""

    task_id: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    state: TaskState = TaskState.PENDING
    result: object | None = None
    verification_rule: str = ""  # e.g., "pytest", "file_exists", "ast_check"


class SubgoalGraph:
    """Manages a DAG of subgoals to keep the 27B model on a strict, structured trajectory."""

    def __init__(self, goal: str) -> None:
        self.goal: str = goal
        self.nodes: dict[str, SubgoalNode] = {}

    def add_subgoal(
        self,
        task_id: str,
        description: str,
        depends_on: list[str] | None = None,
        verification_rule: str = "",
    ) -> SubgoalNode:
        """Add a new task node to the graph.

        Raises:
            ValueError: 존재하지 않는 의존성을 참조하거나 그래프에 사이클을
                만드는 경우 — 방치하면 해당 노드가 영구 PENDING(교착)된다.
        """
        deps = depends_on or []
        unknown = [dep for dep in deps if dep not in self.nodes]
        if unknown:
            raise ValueError(f"Subgoal '{task_id}' references unknown dependencies: {', '.join(unknown)}")
        node = SubgoalNode(
            task_id=task_id,
            description=description,
            depends_on=deps,
            verification_rule=verification_rule,
        )
        self.nodes[task_id] = node
        if self._find_cycle():
            del self.nodes[task_id]
            raise ValueError(f"Adding subgoal '{task_id}' would create a dependency cycle")
        self._update_readiness()
        return node

    def add_dependency(self, task_id: str, depends_on: str) -> bool:
        """기존 노드에 의존성을 추가한다 — 사이클/자기참조는 거부한다.

        사이클이 생기면 추가를 되돌리고 False를 반환한다 (노드가 영구
        PENDING 교착되는 것을 방지).
        """
        if task_id not in self.nodes or depends_on not in self.nodes:
            return False
        if task_id == depends_on:
            return False
        self.nodes[task_id].depends_on.append(depends_on)
        if self._find_cycle():
            self.nodes[task_id].depends_on.remove(depends_on)
            return False
        # 아직 시작하지 않은 READY 노드는 의존성이 생겼으므로 PENDING으로
        # 되돌린다 — 아니면 미완료 의존성을 무시하고 실행 가능 상태로 남는다.
        if self.nodes[task_id].state == TaskState.READY:
            self.nodes[task_id].state = TaskState.PENDING
        self._update_readiness()
        return True

    def _find_cycle(self) -> bool | None:
        """DFS로 의존성 사이클 존재 여부를 검출한다 (노드 → 의존성 방향)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {task_id: WHITE for task_id in self.nodes}

        def visit(task_id: str) -> bool:
            color[task_id] = GRAY
            for dep in self.nodes[task_id].depends_on:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and visit(dep):
                    return True
            color[task_id] = BLACK
            return False

        return any(color[t] == WHITE and visit(t) for t in list(self.nodes))

    def complete_subgoal(self, task_id: str, result: object | None = None) -> bool:
        """Mark a task as completed and propagate readiness to dependents."""
        if task_id not in self.nodes:
            return False
        self.nodes[task_id].state = TaskState.COMPLETED
        self.nodes[task_id].result = result
        self._update_readiness()
        return True

    def fail_subgoal(self, task_id: str, error: str) -> None:
        """Mark a task as failed and block dependent tasks."""
        if task_id in self.nodes:
            self.nodes[task_id].state = TaskState.FAILED
            self.nodes[task_id].result = error
            self._propagate_blocked(task_id)

    def get_ready_subgoals(self) -> list[SubgoalNode]:
        """Return all tasks whose prerequisites are completely satisfied."""
        return [n for n in self.nodes.values() if n.state == TaskState.READY]

    def is_all_completed(self) -> bool:
        """Check if all nodes in the DAG have successfully completed."""
        return bool(self.nodes) and all(n.state == TaskState.COMPLETED for n in self.nodes.values())

    def format_plan_prompt(self) -> str:
        """Format current DAG status into a compact directive block for the LLM."""
        lines = [
            f"📋 **Task DAG Execution Plan for Goal:** {self.goal}",
            "--------------------------------------------------",
        ]
        for node in self.nodes.values():
            icon = {
                TaskState.COMPLETED: "✅",
                TaskState.IN_PROGRESS: "🔄",
                TaskState.READY: "⭐ [NEXT TO EXECUTE]",
                TaskState.PENDING: "⏳",
                TaskState.FAILED: "❌",
                TaskState.BLOCKED: "🚫",
            }.get(node.state, "•")
            deps = f" (Depends on: {', '.join(node.depends_on)})" if node.depends_on else ""
            lines.append(f"{icon} [{node.task_id}] {node.description}{deps} -> {node.state.value}")
        lines.append("--------------------------------------------------")
        return "\n".join(lines)

    def _update_readiness(self) -> None:
        for node in self.nodes.values():
            if node.state == TaskState.PENDING:
                all_deps_done = all(
                    self.nodes.get(dep) and self.nodes[dep].state == TaskState.COMPLETED for dep in node.depends_on
                )
                if all_deps_done:
                    node.state = TaskState.READY

    def _propagate_blocked(self, failed_task_id: str) -> None:
        queue = deque([failed_task_id])
        while queue:
            parent = queue.popleft()
            for node in self.nodes.values():
                if parent in node.depends_on and node.state not in (TaskState.COMPLETED, TaskState.FAILED):
                    node.state = TaskState.BLOCKED
                    queue.append(node.task_id)
