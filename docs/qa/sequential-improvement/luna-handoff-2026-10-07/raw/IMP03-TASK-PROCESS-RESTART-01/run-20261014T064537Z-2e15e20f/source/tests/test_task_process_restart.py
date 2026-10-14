from __future__ import annotations

import json
import multiprocessing
import threading
from collections.abc import Buffer, Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, Protocol, cast, final

from pydantic import BaseModel, ConfigDict

from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.task_state_store import TaskStateStore


class _ProcessResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    resumed: bool
    status: str
    output: str
    event_sequences: tuple[int, ...]
    replay_sequences: tuple[int, ...]
    event_steps: tuple[int, ...]
    lifecycle_statuses: tuple[str, ...]
    effect_steps: tuple[int, ...]


class _EventPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    step: int


class _LifecyclePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    from_status: str
    from_version: int
    terminal: bool
    to_status: str
    to_version: int


class _Sender(Protocol):
    def send_bytes(self, buf: Buffer, offset: int = 0, size: int | None = None) -> None: ...


class _Receiver(Protocol):
    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...

    def poll(self, timeout: float = 0.0) -> bool: ...


class _RunnerPort(Protocol):
    state_store: TaskStateStore

    def submit_task(
        self,
        prompt: str,
        *,
        orchestrator: _CheckpointingOrchestrator,
        target_model: str,
    ) -> str: ...

    def resume_task(
        self,
        task_id: str,
        *,
        orchestrator: _CheckpointingOrchestrator,
        target_model: str,
    ) -> bool: ...

    def wait_task(self, task_id: str, timeout: float | None = None) -> object | None: ...


@final
class _CheckpointingOrchestrator:
    vault_engine: ClassVar[None] = None

    def __init__(
        self,
        effects_path: Path,
        *,
        start_step: int,
        final_step: int,
        checkpoint_sender: _Sender | None = None,
        block_after_step: int | None = None,
    ) -> None:
        self.effects_path: Path = effects_path
        self.start_step: int = start_step
        self.final_step: int = final_step
        self.checkpoint_sender: _Sender | None = checkpoint_sender
        self.block_after_step: int | None = block_after_step
        self.task_id: str = ""
        self.state_store: TaskStateStore | None = None

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore) -> Generator[None]:
        self.task_id = task_id
        self.state_store = state_store
        try:
            yield
        finally:
            self.task_id = ""
            self.state_store = None

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Generator[str]:
        del messages, target_model
        state_store = self.state_store
        if state_store is None or not self.task_id:
            raise RuntimeError("Task execution binding is required.")
        for step in range(self.start_step, self.final_step + 1):
            with self.effects_path.open("a", encoding="utf-8") as effects:
                _ = effects.write(f"{step}\n")
            _ = state_store.append_execution_event(
                self.task_id,
                "worker.chunk",
                json.dumps({"step": step}),
            )
            yield f"{step},"
            if step == self.block_after_step:
                checkpoint = state_store.get_last_checkpoint(self.task_id)
                if checkpoint is None or checkpoint["step"] != step:
                    raise RuntimeError("Expected checkpoint was not persisted.")
                if self.checkpoint_sender is None:
                    raise RuntimeError("Checkpoint signal channel is required.")
                self.checkpoint_sender.send_bytes(b"checkpointed")
                _ = threading.Event().wait()


def _result(runner: _RunnerPort, task_id: str, effects_path: Path, *, resumed: bool) -> _ProcessResult:
    record = runner.state_store.get_task(task_id)
    if record is None:
        raise RuntimeError("Task record is required.")
    events = runner.state_store.list_execution_events(task_id)
    replay = runner.state_store.list_execution_events(task_id, after_sequence=events[len(events) // 2 - 1]["sequence"])
    return _ProcessResult(
        resumed=resumed,
        status=record["status"],
        output=record["output"],
        event_sequences=tuple(event["sequence"] for event in events),
        replay_sequences=tuple(event["sequence"] for event in replay),
        event_steps=tuple(_EventPayload.model_validate_json(event["payload_json"]).step for event in events
                          if event["event_type"] == "worker.chunk"),
        lifecycle_statuses=tuple(_LifecyclePayload.model_validate_json(event["payload_json"]).to_status for event in events
                                 if event["event_type"] == "task.status"),
        effect_steps=tuple(int(line) for line in effects_path.read_text(encoding="utf-8").splitlines()),
    )


def _run_complete(db_path: str, effects_path: str, sender: _Sender) -> None:
    runner = cast(_RunnerPort, BackgroundTaskRunner(db_path=db_path))
    task_id = runner.submit_task(
        "complete all twelve steps",
        orchestrator=_CheckpointingOrchestrator(Path(effects_path), start_step=1, final_step=12),
        target_model="fixture-model",
    )
    _ = runner.wait_task(task_id, timeout=5)
    sender.send_bytes(_result(runner, task_id, Path(effects_path), resumed=False).model_dump_json().encode())


def _run_until_killed(
    db_path: str,
    effects_path: str,
    task_sender: _Sender,
    checkpoint_sender: _Sender,
) -> None:
    runner = cast(_RunnerPort, BackgroundTaskRunner(db_path=db_path))
    task_id = runner.submit_task(
        "complete all twelve steps",
        orchestrator=_CheckpointingOrchestrator(
            Path(effects_path),
            start_step=1,
            final_step=12,
            checkpoint_sender=checkpoint_sender,
            block_after_step=10,
        ),
        target_model="fixture-model",
    )
    task_sender.send_bytes(task_id.encode())
    _ = threading.Event().wait()


def _resume_after_kill(db_path: str, effects_path: str, task_id: str, sender: _Sender) -> None:
    runner = cast(_RunnerPort, BackgroundTaskRunner(db_path=db_path))
    checkpoint = runner.state_store.get_last_checkpoint(task_id)
    if checkpoint is None:
        raise RuntimeError("Resume checkpoint is required.")
    resumed = runner.resume_task(
        task_id,
        orchestrator=_CheckpointingOrchestrator(
            Path(effects_path),
            start_step=checkpoint["step"] + 1,
            final_step=12,
        ),
        target_model="fixture-model",
    )
    _ = runner.wait_task(task_id, timeout=5)
    sender.send_bytes(_result(runner, task_id, Path(effects_path), resumed=resumed).model_dump_json().encode())


type _ProcessArgument = str | _Sender


def _completed_process(
    target: Callable[..., None],
    args: tuple[_ProcessArgument, ...],
    receiver: _Receiver,
) -> _ProcessResult:
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=target, args=args)
    process.start()
    try:
        assert receiver.poll(10), "Worker process did not return a result."
        result = _ProcessResult.model_validate_json(receiver.recv_bytes())
        process.join(timeout=10)
        assert process.exitcode == 0
        return result
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_task_resume_survives_real_process_kill_without_duplicate_effects(tmp_path: Path) -> None:
    # Given: an uninterrupted reference run and a second process stopped after checkpoint ten.
    context = multiprocessing.get_context("spawn")
    baseline_receiver, baseline_sender = context.Pipe(duplex=False)
    baseline = _completed_process(
        _run_complete,
        (str(tmp_path / "baseline.db"), str(tmp_path / "baseline.effects"), baseline_sender),
        baseline_receiver,
    )
    task_receiver, task_sender = context.Pipe(duplex=False)
    checkpoint_receiver, checkpoint_sender = context.Pipe(duplex=False)
    interrupted_db = tmp_path / "interrupted.db"
    interrupted_effects = tmp_path / "interrupted.effects"
    interrupted = context.Process(
        target=_run_until_killed,
        args=(str(interrupted_db), str(interrupted_effects), task_sender, checkpoint_sender),
    )
    interrupted.start()
    task_id = task_receiver.recv_bytes().decode()
    assert checkpoint_receiver.recv_bytes() == b"checkpointed"
    assert interrupted.pid is not None
    assert interrupted.is_alive()

    # When: the owning process is killed and a fresh process explicitly resumes the same task.
    interrupted.kill()
    interrupted.join(timeout=10)
    assert interrupted.exitcode is not None and interrupted.exitcode < 0
    resume_receiver, resume_sender = context.Pipe(duplex=False)
    recovered = _completed_process(
        _resume_after_kill,
        (str(interrupted_db), str(interrupted_effects), task_id, resume_sender),
        resume_receiver,
    )

    # Then: worker output and effects match; all lifecycle/worker events replay without loss.
    assert recovered.resumed is True
    assert recovered.status == "done"
    assert recovered.output == baseline.output
    assert baseline.event_sequences == tuple(range(1, 15))
    assert recovered.event_sequences == tuple(range(1, 16))
    assert baseline.replay_sequences == baseline.event_sequences[len(baseline.event_sequences) // 2:]
    assert recovered.replay_sequences == recovered.event_sequences[len(recovered.event_sequences) // 2:]
    assert baseline.lifecycle_statuses == ("running", "done")
    assert recovered.lifecycle_statuses == ("running", "running", "done")
    assert recovered.event_steps == baseline.event_steps == tuple(range(1, 13))
    assert recovered.effect_steps == baseline.effect_steps == tuple(range(1, 13))
