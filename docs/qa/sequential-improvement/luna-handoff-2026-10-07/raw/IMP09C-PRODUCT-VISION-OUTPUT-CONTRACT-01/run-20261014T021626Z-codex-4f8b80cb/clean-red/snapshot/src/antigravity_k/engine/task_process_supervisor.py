from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import final


@dataclass(frozen=True, slots=True)
class ProcessGroupRegistration:
    task_id: str | None
    process: subprocess.Popen[bytes]
    process_group_id: int | None


@dataclass(slots=True)
class _TaskProcessState:
    scope_count: int = 0
    cancelled: bool = False
    registrations: dict[int, ProcessGroupRegistration] = field(default_factory=dict)


@final
class TaskProcessSupervisor:
    """A regular class is required because live process ownership changes concurrently."""

    def __init__(self, termination_grace_seconds: float = 0.5) -> None:
        self._termination_grace_seconds = termination_grace_seconds
        self._lock = threading.RLock()
        self._states: dict[str, _TaskProcessState] = {}

    def enter_task_scope(self, task_id: str) -> None:
        with self._lock:
            state = self._states.setdefault(task_id, _TaskProcessState())
            state.scope_count += 1

    def exit_task_scope(self, task_id: str) -> None:
        registrations: tuple[ProcessGroupRegistration, ...] = ()
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                return
            state.scope_count = max(0, state.scope_count - 1)
            if state.scope_count > 0:
                return
            registrations = tuple(state.registrations.values())
            del self._states[task_id]
        for registration in registrations:
            self.terminate(registration)

    def register(
        self,
        task_id: str | None,
        process: subprocess.Popen[bytes],
        process_group_id: int | None,
    ) -> ProcessGroupRegistration:
        registration = ProcessGroupRegistration(task_id, process, process_group_id)
        cancel_immediately = False
        if task_id is not None:
            with self._lock:
                state = self._states.setdefault(task_id, _TaskProcessState())
                state.registrations[process.pid] = registration
                cancel_immediately = state.cancelled
        if cancel_immediately:
            self.terminate(registration)
        return registration

    def unregister(self, registration: ProcessGroupRegistration) -> None:
        if registration.task_id is None:
            return
        with self._lock:
            state = self._states.get(registration.task_id)
            if state is not None:
                _ = state.registrations.pop(registration.process.pid, None)

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                return False
            state.cancelled = True
            registrations = tuple(state.registrations.values())
        for registration in registrations:
            self.terminate(registration)
        return True

    def active_process_count(self, task_id: str) -> int:
        with self._lock:
            state = self._states.get(task_id)
            return 0 if state is None else len(state.registrations)

    def terminate(self, registration: ProcessGroupRegistration) -> None:
        process = registration.process
        group_id = registration.process_group_id
        self._signal(process, group_id, signal.SIGTERM)
        try:
            _ = process.wait(timeout=self._termination_grace_seconds)
        except subprocess.TimeoutExpired:
            pass
        self._signal(process, group_id, signal.SIGKILL)
        if process.poll() is None:
            process.kill()
            _ = process.wait()

    @staticmethod
    def _signal(process: subprocess.Popen[bytes], group_id: int | None, value: int) -> None:
        try:
            if os.name == "posix" and group_id is not None:
                os.killpg(group_id, value)
            elif process.poll() is None:
                process.send_signal(value)
        except ProcessLookupError:
            return


task_process_supervisor = TaskProcessSupervisor()


__all__ = [
    "ProcessGroupRegistration",
    "TaskProcessSupervisor",
    "task_process_supervisor",
]
