from __future__ import annotations

import json
import sqlite3
from typing import ClassVar, Final, Literal, final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from antigravity_k.engine import multimodal
from antigravity_k.engine.task_execution_context import TaskStateStoreProtocol

CONTEXT_SNAPSHOT_EVENT: Final = "context_snapshot"
_RESTORED_CONTEXT_HEADER: Final = "[Restored Task Context]"
_TRANSIENT_SYSTEM_PREFIXES: Final = ("[Recalled Memory]", _RESTORED_CONTEXT_HEADER)


SnapshotRole = Literal[
    "system",
    "developer",
    "user",
    "assistant",
    "tool",
    "function",
    "tool_result",
]


class SnapshotMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    role: SnapshotRole
    content: str = Field(max_length=1_000_000)
    name: str | None = Field(default=None, max_length=128)


class TaskContextSnapshot(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    target_model: str = Field(min_length=1, max_length=256)
    messages: tuple[SnapshotMessage, ...] = Field(min_length=1, max_length=256)


@final
class ContextSnapshotStoreError(RuntimeError):
    task_id: str
    reason: str

    def __init__(self, task_id: str, reason: str):
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"Context snapshot failed for {task_id}: {reason}")


def save_task_context_snapshot(
    state_store: TaskStateStoreProtocol,
    task_id: str,
    messages: list[dict[str, str]],
    target_model: str,
) -> int:
    try:
        snapshot = TaskContextSnapshot(
            target_model=target_model,
            messages=tuple(_snapshot_message(message) for message in messages if _is_durable_message(message)),
        )
        payload = json.dumps(
            snapshot.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return state_store.append_execution_event(task_id, CONTEXT_SNAPSHOT_EVENT, payload)
    except (ValidationError, sqlite3.Error) as error:
        raise ContextSnapshotStoreError(task_id, str(error)) from error


def load_task_context_snapshot(
    state_store: TaskStateStoreProtocol,
    task_id: str,
) -> TaskContextSnapshot | None:
    try:
        events = state_store.list_execution_events(task_id)
    except sqlite3.Error as error:
        raise ContextSnapshotStoreError(task_id, str(error)) from error

    latest = next(
        (event for event in reversed(events) if event["event_type"] == CONTEXT_SNAPSHOT_EVENT),
        None,
    )
    if latest is None:
        return None
    try:
        return TaskContextSnapshot.model_validate_json(latest["payload_json"])
    except ValidationError:
        return None


def restored_task_context_messages(snapshot: TaskContextSnapshot) -> list[dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": (
                f"{_RESTORED_CONTEXT_HEADER}\n"
                "The following messages are task-local history restored from the latest durable snapshot."
            ),
        },
    ]
    messages.extend(message.model_dump(exclude_none=True) for message in snapshot.messages)
    return messages


def _is_durable_message(message: dict[str, str]) -> bool:
    if message.get("role") != "system":
        return True
    content = multimodal.flatten_content(message.get("content", ""))
    return not content.startswith(_TRANSIENT_SYSTEM_PREFIXES)


def _snapshot_message(message: dict[str, str]) -> SnapshotMessage:
    # NX-09-F03/ADR-0005: 스냅샷은 **텍스트** 모델(SnapshotMessage.content: str)이다.
    # 멀티모달 content(파트 배열)를 그대로 넣으면 ValidationError 로 요청이 실패하고,
    # base64 를 그대로 넣으면 SQLite 이벤트가 이미지로 부푼다. 그래서 텍스트만 남긴다
    # (이미지는 그 턴의 모델 입력으로만 간다 — 이력에는 파일명 표식만 남는다).
    payload: dict[str, object] = {}
    for key in ("role", "name"):
        if key in message:
            payload[key] = message[key]
    payload["content"] = multimodal.flatten_content(message.get("content", ""))
    return SnapshotMessage.model_validate(payload)
