from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

SteeringMode = Literal["queued_replay"]
SteeringStatus = Literal["accepted"]


class InvalidTaskSteeringError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TaskSteeringRequest:
    steering_id: str
    task_id: str
    instruction: str


@dataclass(frozen=True, slots=True)
class TaskSteeringResult:
    status: SteeringStatus
    task_id: str
    steering_id: str
    mode: SteeringMode = "queued_replay"


class TaskSteeringQueue:
    def __init__(self) -> None:
        self._requests: defaultdict[str, deque[TaskSteeringRequest]] = defaultdict(deque)
        self._lock: threading.Lock = threading.Lock()

    def request(self, task_id: str, instruction: str) -> TaskSteeringRequest:
        normalized_task_id = task_id.strip()
        normalized_instruction = instruction.strip()
        if not normalized_task_id:
            raise InvalidTaskSteeringError("task_id must not be blank")
        if not normalized_instruction:
            raise InvalidTaskSteeringError("instruction must not be blank")
        item = TaskSteeringRequest(uuid.uuid4().hex, normalized_task_id, normalized_instruction)
        with self._lock:
            self._requests[normalized_task_id].append(item)
        return item

    def drain(self, task_id: str) -> tuple[TaskSteeringRequest, ...]:
        with self._lock:
            pending = self._requests.pop(task_id.strip(), deque())
        return tuple(pending)


__all__ = [
    "SteeringMode",
    "SteeringStatus",
    "InvalidTaskSteeringError",
    "TaskSteeringQueue",
    "TaskSteeringRequest",
    "TaskSteeringResult",
]
