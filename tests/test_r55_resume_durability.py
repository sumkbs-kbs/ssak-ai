"""Synthetic runner regressions for durable pause, failure output and effect replay."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import pytest

from antigravity_k.engine import tool_execution_journal as journal
from antigravity_k.engine.artifact_engine import ArtifactEngine
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskStateStore


class _Message(TypedDict):
    role: str
    content: str


class _StreamInterrupted(RuntimeError):
    def __str__(self) -> str:
        return "synthetic short stream interruption"


@dataclass(frozen=True, slots=True)
class _PauseStream:
    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    vault_engine: None = None

    def run_stream(self, messages: list[_Message], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.entered.set()
        assert self.release.wait(timeout=3), "The test must release its scripted stream"
        yield "durable pause prefix 🌈\n"


@dataclass(frozen=True, slots=True)
class _InterruptedStream:
    chunks: tuple[str, ...]
    vault_engine: None = None

    def run_stream(self, messages: list[_Message], target_model: str) -> Iterator[str]:
        del messages, target_model
        yield from self.chunks
        raise _StreamInterrupted


@dataclass(frozen=True, slots=True)
class _ArtifactStream:
    engine: ArtifactEngine
    content: str
    interrupt: bool = False
    vault_engine: None = None

    def run_stream(self, messages: list[_Message], target_model: str) -> Iterator[str]:
        del messages, target_model
        result = self.engine.write_artifact("resume.md", self.content)
        assert result["success"], result["error"]
        if self.interrupt:
            raise _StreamInterrupted
        yield "synthetic completion\n"


@pytest.fixture(autouse=True)
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


def test_pause_checkpoint_failure_is_reported_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an active synthetic stream has an initial durable checkpoint.
    db_path = tmp_path / "pause.db"
    runner = BackgroundTaskRunner(db_path=str(db_path))
    stream = _PauseStream()
    task_id = runner.submit_task(
        "synthetic pause durability", context={"benchmark_read_only": True},
        orchestrator=stream, target_model="fixture-model",
    )
    task = runner._tasks[task_id]
    try:
        assert stream.entered.wait(timeout=3)

        def reject_checkpoint(
            task_id: str, step: int, context_json: str, output: str,
        ) -> None:
            del task_id, step, context_json, output
            raise sqlite3.OperationalError("synthetic checkpoint storage unavailable")

        # When: storage rejects the checkpoint at the requested pause boundary.
        monkeypatch.setattr(runner.state_store, "save_checkpoint", reject_checkpoint)
        assert runner.pause_task(task_id) == "pausing"
        stream.release.set()
        status = runner.wait_task(task_id, timeout=3)
    finally:
        stream.release.set()
        task.join(timeout=3)

    # Then: a fresh reader sees an explicit failure, never a durable paused claim.
    assert status is not None and status["status"] == "failed"
    record = TaskStateStore(str(db_path)).get_task(task_id)
    assert record is not None and record["status"] == "failed"
    assert record["error"]


def test_short_stream_failure_preserves_the_observed_prefix_after_reconstruction(tmp_path: Path) -> None:
    # Given: fewer than ten body chunks have reached the runner before interruption.
    db_path = tmp_path / "short-stream.db"
    chunks = ("first line 🌈\n", "second line;", "unfinished tail 🌿")
    expected = "".join(chunks)
    runner = BackgroundTaskRunner(db_path=str(db_path))

    # When: the scripted old-style stream fails after delivering that exact prefix.
    task_id = runner.submit_task(
        "synthetic short stream", context={"benchmark_read_only": True},
        orchestrator=_InterruptedStream(chunks), target_model="fixture-model",
    )
    status = runner.wait_task(task_id, timeout=3)

    # Then: live output and the reconstructed row/checkpoint retain every character.
    assert status is not None and status["status"] == "failed"
    assert runner._tasks[task_id].output == expected
    reopened = TaskStateStore(str(db_path))
    record = reopened.get_task(task_id)
    checkpoint = reopened.get_last_checkpoint(task_id)
    assert record is not None and record["output"] == expected
    assert checkpoint is not None and checkpoint["output_so_far"] == expected


def test_completed_artifact_is_preserved_when_empty_output_task_resumes(tmp_path: Path) -> None:
    # Given: the first execution completed a durable effect before any body output.
    db_path = tmp_path / "empty-output.db"
    first = BackgroundTaskRunner(db_path=str(db_path))
    original = "first completed artifact 🌈\n"
    task_id = first.submit_task(
        "synthetic artifact recovery", context={"benchmark_read_only": True},
        orchestrator=_ArtifactStream(ArtifactEngine(str(tmp_path)), original, interrupt=True),
        target_model="fixture-model",
    )
    initial = first.wait_task(task_id, timeout=3)
    assert initial is not None and initial["status"] == "failed"
    checkpoint = first.state_store.get_last_checkpoint(task_id)
    assert checkpoint is not None and checkpoint["output_so_far"] == ""

    # When: a reconstructed runner regenerates changed content for that same target.
    resumed = BackgroundTaskRunner(db_path=str(db_path))
    engine = ArtifactEngine(str(tmp_path))
    assert resumed.resume_task(
        task_id, orchestrator=_ArtifactStream(engine, "regenerated replacement\n"),
        target_model="fixture-model",
    )
    final = resumed.wait_task(task_id, timeout=3)

    # Then: the task completes while the first effect remains the only actual write.
    assert final is not None and final["status"] == "done"
    artifact = tmp_path / "artifacts" / "resume.md"
    assert artifact.read_text(encoding="utf-8") == original
    execution_id = journal.execution_id(task_id, str(artifact))
    records = journal.Journal(engine.artifacts_dir).records(execution_id)
    assert sum(record.get("state") == "intent" for record in records) == 1


def test_transient_state_read_failure_does_not_leave_interrupted_task_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "read-fault.db"
    runner = BackgroundTaskRunner(db_path=str(db_path))
    trigger = threading.Event()
    injected = threading.Event()
    expected = "observed prefix before read fault 🌈\n"
    original_get = runner.state_store.get_task

    class ReadFaultStream:
        vault_engine = None

        def run_stream(self, messages: list[_Message], target_model: str) -> Iterator[str]:
            del messages, target_model
            yield expected
            trigger.set()
            raise _StreamInterrupted

    def one_shot_read_error(task_id: str, *args: object, **kwargs: object):
        if trigger.is_set() and threading.current_thread() is not threading.main_thread() and not injected.is_set():
            injected.set()
            raise sqlite3.OperationalError("synthetic state lookup unavailable once")
        return original_get(task_id, *args, **kwargs)

    monkeypatch.setattr(runner.state_store, "get_task", one_shot_read_error)
    task_id = runner.submit_task(
        "synthetic recovery read failure", context={"benchmark_read_only": True},
        orchestrator=ReadFaultStream(), target_model="fixture-model",
    )
    status = runner.wait_task(task_id, timeout=3)
    assert status is not None and status["status"] == "failed"
    assert runner._tasks[task_id].output == expected
    record = TaskStateStore(str(db_path)).get_task(task_id)
    assert record is not None and record["status"] == "failed"
    assert record["output"] == expected
    assert record["error"] == "synthetic short stream interruption"
