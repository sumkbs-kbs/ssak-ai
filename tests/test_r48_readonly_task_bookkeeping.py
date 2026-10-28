import json
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import JsonValue

from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
from antigravity_k.engine.task_runner import BackgroundTask, BackgroundTaskRunner, TaskStatus
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy


class RecordingVault:
    """Accumulate attempted storage effects without touching a vault or Git."""

    def __init__(self) -> None:
        self.snapshots: list[str] = []
        self.writes: list[str] = []
        self.restores: list[str] = []

    def create_snapshot(self, description: str) -> str:
        self.snapshots.append(description)
        return "synthetic-snapshot"

    def restore_snapshot(self, snapshot_hash: str, scope: tuple[str, ...] | None = None) -> bool:
        del scope
        self.restores.append(snapshot_hash)
        return True

    def write_note(
        self,
        *,
        relative_path: str,
        metadata: Mapping[str, JsonValue],
        content: str,
        commit_message: str,
    ) -> None:
        del metadata, content, commit_message
        self.writes.append(relative_path)


class RecordingManager:
    """Count the optional consolidation without any physical provider."""

    def __init__(self) -> None:
        self.refinements = 0
        self.restrict_before_yield = False

    def stream_generate(
        self,
        *,
        prompt: str,
        target: str,
        raw_messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]:
        del prompt, target, raw_messages, system_prompt
        self.refinements += 1
        if self.restrict_before_yield:
            set_access_mode(AccessMode.READ_ONLY)
        yield "synthetic memory"


class SyntheticOrchestrator:
    """Provide fixed task output and optionally expose a bounded pause boundary."""

    def __init__(self, *, gated: bool = False, restrict_before_output: bool = False) -> None:
        self.manager = RecordingManager()
        self.started = Event()
        self.release = Event()
        self.gated = gated
        self.restrict_before_output = restrict_before_output

    def get_model_for_role(self, role: str) -> str:
        del role
        return "synthetic-model"

    def run_stream(self, messages: list[dict[str, str]], target_model: str) -> Iterator[str]:
        del messages, target_model
        self.started.set()
        if self.gated:
            assert self.release.wait(2), "synthetic pause boundary was not released"
        if self.restrict_before_output:
            set_access_mode(AccessMode.READ_ONLY)
        yield "synthetic result;"


@pytest.fixture(autouse=True)
def restore_access_mode() -> Iterator[None]:
    previous = get_access_mode()
    set_access_mode(AccessMode.FULL_ACCESS)
    try:
        yield
    finally:
        set_access_mode(previous)


def join_task(runner: BackgroundTaskRunner, task_id: str) -> None:
    thread = runner._tasks[task_id]._thread
    assert thread is not None
    thread.join(2)
    assert not thread.is_alive()


@pytest.mark.parametrize("request_safe_only", [False, True])
def test_readonly_background_keeps_result_without_vault_effects(tmp_path: Path, request_safe_only: bool) -> None:
    # Given: either authoritative restriction applies, without a benchmark bypass.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    if not request_safe_only:
        set_access_mode(AccessMode.READ_ONLY)
    token = set_tool_policy(ToolPolicy(safe_only=request_safe_only))
    # When: the request ends while its task runs in an independent thread.
    try:
        task_id = runner.submit_task(
            "synthetic answer only",
            context={"direct_response": True, "_bookkeeping_read_only": False},
            orchestrator=orch,
        )
    finally:
        reset_tool_policy(token)
    join_task(runner, task_id)
    # Then: durable task output survives, with no snapshot, extra model call or vault write.
    record = runner.state_store.get_task(task_id)
    assert record is not None and record["status"] == TaskStatus.DONE
    assert record["output"] == "synthetic result;"
    assert runner._tasks[task_id].context["direct_response"] is True
    assert "benchmark_read_only" not in runner._tasks[task_id].context
    assert (vault.snapshots, orch.manager.refinements, vault.writes) == ([], 0, [])


def test_full_access_background_preserves_authorized_bookkeeping(tmp_path: Path) -> None:
    # Given: ordinary full access and a synthetic vault/provider.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    # When: an ordinary task completes.
    task_id = runner.submit_task("synthetic answer only", orchestrator=orch)
    join_task(runner, task_id)
    # Then: the existing snapshot, consolidation and note behavior is retained.
    assert runner._tasks[task_id].status == TaskStatus.DONE
    assert len(vault.snapshots) == 1
    assert orch.manager.refinements == 1
    assert len(vault.writes) == 1


def test_switch_to_readonly_before_completion_skips_refinement_and_write(tmp_path: Path) -> None:
    # Given: a task starts while writes are allowed.
    vault = RecordingVault()
    orch = SyntheticOrchestrator(restrict_before_output=True)
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    # When: the authoritative mode becomes read-only before the final output.
    task_id = runner.submit_task("synthetic answer only", orchestrator=orch)
    join_task(runner, task_id)
    # Then: only the previously authorized snapshot happened; no later automatic effects occur.
    assert runner._tasks[task_id].status == TaskStatus.DONE
    assert len(vault.snapshots) == 1
    assert (orch.manager.refinements, vault.writes) == (0, [])


def test_restriction_activated_during_refinement_prevents_vault_write(tmp_path: Path) -> None:
    # Given: consolidation starts with permission but the global mode changes during it.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    orch.manager.restrict_before_yield = True
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    # When: the ordinary task finishes.
    task_id = runner.submit_task("synthetic answer only", orchestrator=orch)
    join_task(runner, task_id)
    # Then: the already-started refinement is retained, but no later vault write starts.
    assert runner._tasks[task_id].status == TaskStatus.DONE
    assert orch.manager.refinements == 1
    assert vault.writes == []


def test_readonly_does_not_restore_a_previous_snapshot(tmp_path: Path) -> None:
    # Given: a task has an old snapshot but the current authority is read-only.
    vault = RecordingVault()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    task = BackgroundTask("synthetic-task", "synthetic prompt", {"snapshot_hash": "old-snapshot"})
    set_access_mode(AccessMode.READ_ONLY)
    # When: cancellation or a failure asks for automatic rollback.
    runner._rollback_snapshot(task, vault)
    # Then: the shared rollback sink performs no storage mutation.
    assert vault.restores == []


def test_legacy_checkpoint_without_trusted_policy_resumes_without_bookkeeping(tmp_path: Path) -> None:
    # Given: a synthetic legacy checkpoint has no persisted permission decision.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    task_id = "synthetic-legacy-task"
    runner.state_store.create_task(task_id, "synthetic answer only", TaskStatus.PAUSED, datetime.now(UTC).isoformat())
    runner.state_store.save_checkpoint(task_id, 0, json.dumps({"direct_response": True}), "")
    # When: current full access cannot establish what the old task originally allowed.
    assert runner.resume_task(task_id, orchestrator=orch)
    join_task(runner, task_id)
    # Then: the task can finish, while optional storage effects fail closed.
    assert runner._tasks[task_id].status == TaskStatus.DONE
    assert (vault.snapshots, orch.manager.refinements, vault.writes) == ([], 0, [])


def test_trusted_full_access_checkpoint_preserves_resume_bookkeeping(tmp_path: Path) -> None:
    # Given: a synthetic checkpoint explicitly retained the prior full-access decision.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    task_id = "synthetic-authorized-task"
    runner.state_store.create_task(task_id, "synthetic answer only", TaskStatus.PAUSED, datetime.now(UTC).isoformat())
    runner.state_store.save_checkpoint(
        task_id, 0, json.dumps({"direct_response": True, "_bookkeeping_read_only": False}), ""
    )
    # When: the task resumes while both authorities still permit side effects.
    assert runner.resume_task(task_id, orchestrator=orch)
    join_task(runner, task_id)
    # Then: snapshot, refinement and note creation keep their authorized behavior.
    assert runner._tasks[task_id].status == TaskStatus.DONE
    assert (len(vault.snapshots), orch.manager.refinements, len(vault.writes)) == (1, 1, 1)


def test_resume_does_not_start_when_restricted_checkpoint_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a legacy synthetic task needs a durable restriction before it can resume.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    task_id = "synthetic-unsaved-policy"
    runner.state_store.create_task(task_id, "synthetic answer only", TaskStatus.PAUSED, datetime.now(UTC).isoformat())
    runner.state_store.save_checkpoint(task_id, 0, "{}", "")

    def reject_checkpoint(task_id: str, step: int, context_json: str, output: str) -> None:
        del task_id, step, context_json, output
        raise sqlite3.OperationalError("synthetic checkpoint write failure")

    monkeypatch.setattr(runner.state_store, "save_checkpoint", reject_checkpoint)
    # When: durable checkpoint persistence fails.
    assert not runner.resume_task(task_id, orchestrator=orch)
    # Then: no worker or optional storage/model effect starts under an unrecorded policy.
    record = runner.state_store.get_task(task_id)
    assert record is not None and record["status"] == TaskStatus.FAILED
    assert not orch.started.is_set()
    assert (vault.snapshots, orch.manager.refinements, vault.writes) == ([], 0, [])


def test_same_step_checkpoint_returns_latest_context_and_output(tmp_path: Path) -> None:
    # Given: newer durable metadata/output is saved without pretending another model step ran.
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"))
    task_id = "synthetic-same-step"
    runner.state_store.create_task(
        task_id, "synthetic prompt", TaskStatus.PAUSED, datetime.now(UTC).isoformat(), owner_subject="alice"
    )
    runner.state_store.save_checkpoint(task_id, 7, '{"_bookkeeping_read_only":false}', "old output")
    runner.state_store.save_checkpoint(task_id, 7, '{"_bookkeeping_read_only":true}', "new output")
    # When: the owner retrieves the latest checkpoint.
    checkpoint = runner.state_store.get_last_checkpoint(task_id, owner_subject="alice")
    # Then: insertion order resolves ties, and owner filtering remains intact.
    assert checkpoint is not None and checkpoint["step"] == 7
    assert json.loads(checkpoint["context_json"])["_bookkeeping_read_only"] is True
    assert checkpoint["output_so_far"] == "new output"
    assert runner.state_store.get_last_checkpoint(task_id, owner_subject="bob") is None


def test_completed_direct_generation_has_separate_parser_delivery_chunks(tmp_path: Path) -> None:
    # Given: a completed synthetic response enters the real direct ToolLoop path as one item.
    answer = "".join(f"{number:02d}. 합성 색상 인사말 {number:02d} 끝입니다.\n" for number in range(1, 31))
    generated: list[bool] = []

    def complete_generation(**kwargs: str) -> str:
        del kwargs
        generated.append(True)
        return answer

    manager = MagicMock()
    manager.is_loaded.return_value = True
    manager.router.get_combo.return_value = None
    manager.generate.side_effect = complete_generation
    orch = SimpleNamespace(
        config={},
        project_root=tmp_path,
        manager=manager,
        task_execution_context=None,
        task_outcome_recorder=None,
        expected_tools=(),
        context_shaper=None,
        _capacity_checkpoint=None,
        ctx=SimpleNamespace(cognitive_loop=None, quality_gate=None, decision_anchor=None, expected_tools=()),
    )
    engine = ToolLoopEngine(orch)
    output = engine.run_loop(
        [{"role": "user", "content": "합성 번호 인사말만 답하세요"}],
        "SELF",
        "chat",
        target_model="synthetic-model",
        direct_response=True,
    )
    # When: the runner consumes the first real loop emission, then flushes the remainder.
    first = next(output)
    assert generated == [True]
    remainder = list(output)
    # Then: parser look-behind leaves 12 characters for EOF; generation itself is already complete.
    assert first == answer[:-12]
    assert remainder == [answer[-12:]]
    assert not first.endswith("\n") and first + "".join(remainder) == answer
    manager.generate.assert_called_once()
    manager.stream_generate.assert_not_called()


def test_direct_vault_record_entry_obeys_readonly_policy(tmp_path: Path) -> None:
    # Given: a completed synthetic task and the authoritative read-only mode.
    vault = RecordingVault()
    orch = SyntheticOrchestrator()
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "tasks.db"), vault_engine=vault)
    task = BackgroundTask("synthetic-task", "synthetic prompt")
    task.output = "synthetic result;"
    set_access_mode(AccessMode.READ_ONLY)
    # When: a caller enters the bookkeeping helper directly.
    runner._save_to_vault(task, orch)
    # Then: this shared sink blocks the refinement and write too.
    assert (orch.manager.refinements, vault.writes) == (0, [])


@pytest.mark.parametrize("restrict_at_submission", [False, True])
def test_request_restriction_is_retained_when_task_resumes_in_new_runner(
    tmp_path: Path, restrict_at_submission: bool
) -> None:
    # Given: a synthetic task pauses under a request-local restriction or gains one at resume.
    db = str(tmp_path / "tasks.db")
    vault = RecordingVault()
    orch = SyntheticOrchestrator(gated=True)
    runner = BackgroundTaskRunner(db_path=db, vault_engine=vault)
    token = set_tool_policy(ToolPolicy(safe_only=restrict_at_submission))
    try:
        task_id = runner.submit_task("synthetic answer only", orchestrator=orch)
    finally:
        reset_tool_policy(token)
    assert orch.started.wait(2)
    assert runner.pause_task(task_id) == "pausing"
    orch.release.set()
    join_task(runner, task_id)
    assert runner._tasks[task_id].status == TaskStatus.PAUSED
    assert len(vault.snapshots) == (0 if restrict_at_submission else 1)
    vault.snapshots.clear()
    restarted = BackgroundTaskRunner(db_path=db, vault_engine=vault)
    resumed_orch = SyntheticOrchestrator()
    token = set_tool_policy(ToolPolicy(safe_only=not restrict_at_submission))
    # When: a fresh runner resumes the same checkpoint, then the request policy is reset.
    try:
        assert restarted.resume_task(task_id, orchestrator=resumed_orch)
    finally:
        reset_tool_policy(token)
    join_task(restarted, task_id)
    # Then: either trusted restriction continues to protect the task across the thread boundary.
    assert restarted._tasks[task_id].status == TaskStatus.DONE
    assert (vault.snapshots, resumed_orch.manager.refinements, vault.writes) == ([], 0, [])
    checkpoint = restarted.state_store.get_last_checkpoint(task_id)
    assert checkpoint is not None
    assert json.loads(checkpoint["context_json"])["_bookkeeping_read_only"] is True
