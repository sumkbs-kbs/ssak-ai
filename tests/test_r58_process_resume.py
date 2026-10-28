"""Fixed A/B pytest workers for a supervisor-controlled OS process boundary.

Run A once, wait for its successful process exit, then select exactly one B
node in a new interpreter using the same owned family HOME/scenario. These
nodes never spawn a process. No app/server/model/provider transport is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


pytestmark = pytest.mark.skipif(
    "R58_RESTART_PHASE" not in os.environ,
    reason="External two-process supervisor required",
)


_OWNER = "r58-owner"
_FOREIGN = "r58-foreign"
_PREFIX = "A durable prefix 🌈: alpha boundary.\n"
_SUFFIX = "B fresh interpreter continuation: omega complete.\n"
_CONTENT = "# R58 synthetic artifact\nOriginal durable bytes.\n"
_REPLACEMENT = "# R58 synthetic artifact\nA regenerated replacement must not be written.\n"
_POLICY = {
    "version": 1,
    "denied_tools": ["run_bash_command", "web_search"],
    "allowed_mcp_servers": ["r58-selected"],
    "safe_only": False,
}
_DENIED = ("web_search", "run_bash_command", "r58_excluded_mcp")
_CONTROL = "r58_selected_mcp"


def _read_json(path: Path) -> Any:
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size <= 1_000_000
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_once(path: Path, value: object) -> None:
    assert not path.exists(), f"Never overwrite prior phase evidence: {path.name}"
    temporary = path.with_suffix(path.suffix + ".pending")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _append(root: Path, name: str, value: Mapping[str, object]) -> None:
    with (root / name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(value), ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _records(root: Path, name: str) -> list[dict[str, Any]]:
    path = root / name
    if not path.exists():
        return []
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _scenario(phase: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert os.environ.get("R55_GUARD_REQUIRED") == "1"
    assert os.environ.get("R58_RESTART_PHASE") == phase
    run = Path(os.environ["R55_TEST_RUN_ROOT"])
    assert run.is_absolute() and run.resolve() == run and not run.is_symlink()
    assert run.parent == Path(__file__).resolve().parents[2] / "evidence/test-runs"
    assert run.stat().st_uid == os.getuid()
    home, temporary = run / "home", run / "tmp"
    assert Path(os.environ["HOME"]) == home
    assert Path(os.environ["TMPDIR"]) == temporary
    assert Path(os.environ["R43_CAPTURE_ROOT"]) == run / f"capture-{phase}"
    root = Path(os.environ["R58_RESTART_ROOT"])
    assert root == home / "scenario" and root.resolve() == root
    assert all(path.is_dir() and not path.is_symlink() for path in (home, temporary))
    if phase == "A":
        root.mkdir(mode=0o700)
    assert root.is_dir() and not root.is_symlink() and root.stat().st_uid == os.getuid()
    monkeypatch.chdir(home)
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", "false")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    # This optional recovery subsystem is unrelated to the exercised boundary.
    # Each fresh interpreter installs this local fixture independently.
    from antigravity_k.engine import tool_executor

    monkeypatch.setattr(tool_executor, "ImmuneSystem", lambda *_args, **_kwargs: None)
    return root


class _Registry:
    """Only the final registry dispatch is fake; artifact execution stays real."""

    def __init__(self, root: Path, phase: str) -> None:
        from antigravity_k.engine.artifact_engine import register_artifact_tool
        from antigravity_k.tools.base_tool import RiskLevel

        self.root, self.phase = root, phase
        self.tools: dict[str, Any] = {}
        for name, risk, server in (
            ("web_search", RiskLevel.SAFE, ""),
            ("run_bash_command", RiskLevel.HIGH, ""),
            ("r58_excluded_mcp", RiskLevel.SAFE, "r58-excluded"),
            (_CONTROL, RiskLevel.SAFE, "r58-selected"),
        ):
            self.tools[name] = SimpleNamespace(
                name=name, risk_level=risk, _server_name=server,
                parameters_schema={"required": ["phase"]},
            )
        self.engine = register_artifact_tool(self, str(root / "project"))

    def install(self, tool: Any) -> _Registry:
        self.tools[tool.name] = tool
        return self

    def __contains__(self, name: object) -> bool:
        return name in self.tools

    def get(self, name: str) -> Any:
        return self.tools.get(name)

    get_tool = get

    def execute_with_permission(
        self, name: str, args: dict[str, object], objective: str = "",
    ) -> tuple[Any, str]:
        from antigravity_k.tools.tool_contracts import Permission

        del objective
        _append(self.root, "registry.jsonl", {
            "phase": self.phase, "pid": os.getpid(), "name": name, "args": args,
        })
        if name == "write_artifact":
            return Permission.ALLOW, self.tools[name].execute(**args)
        return Permission.ALLOW, f"executed:{self.phase}:{name}"


def _executor(root: Path, phase: str) -> Any:
    from antigravity_k.engine.tool_executor import ToolExecutor
    from antigravity_k.tools.permission_gate import PermissionGate

    return ToolExecutor(
        _Registry(root, phase), PermissionGate(project_root=str(root / "project")),
        project_root=str(root / "project"),
    )


def _observe_real_writes(root: Path, phase: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.engine import tool_execution_journal as journal

    original = journal.atomic_write

    def observed(filepath: str, content: str) -> None:
        original(filepath, content)
        _append(root, "file-effects.jsonl", {
            "phase": phase, "pid": os.getpid(), "path": filepath,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })

    monkeypatch.setattr(journal, "atomic_write", observed)


class _Stream:
    vault_engine = None

    def __init__(self, root: Path, phase: str) -> None:
        self.root, self.phase = root, phase
        self.executor = _executor(root, phase)
        self.entered, self.release = threading.Event(), threading.Event()
        self.results: dict[str, str] = {}

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: Any) -> Iterator[None]:
        from antigravity_k.engine.task_execution_context import (
            TaskExecutionContext, bind_task_execution_context,
        )

        with bind_task_execution_context(TaskExecutionContext(task_id, state_store)):
            yield

    def run_stream(
        self, messages: Sequence[Mapping[str, str]], target_model: str,
    ) -> Iterator[str]:
        from antigravity_k.api.project_binding import get_bound_request_execution_context

        assert target_model == "fixture-model"
        bound = get_bound_request_execution_context()
        assert bound is not None and bound.actor_subject == _OWNER
        assert bound.canonical_project_root == str(self.root / "project")
        if self.phase == "B":
            assert any(item["role"] == "assistant" and item["content"] == _PREFIX for item in messages)
        _append(self.root, "fake-provider.jsonl", {
            "phase": self.phase, "pid": os.getpid(), "model": target_model,
            "actor": bound.actor_subject, "project": bound.canonical_project_root,
            "messages_sha256": hashlib.sha256(json.dumps(list(messages), sort_keys=True).encode()).hexdigest(),
        })
        for name in (*_DENIED, _CONTROL):
            self.results[name] = self.executor.execute(name, {"phase": self.phase})
        args = {"target_file": "resume.md", "code_content": _CONTENT}
        self.results["artifact"] = self.executor.execute("write_artifact", args)
        if self.phase == "B":
            self.results["changed_artifact"] = self.executor.execute(
                "write_artifact", {**args, "code_content": _REPLACEMENT},
            )
            yield _SUFFIX
            return
        self.entered.set()
        assert self.release.wait(timeout=5), "Supervisor fixture did not release the pause boundary"
        yield _PREFIX


def _assert_probes(stream: _Stream) -> None:
    for name in _DENIED:
        assert "[BLOCKED]" in stream.results[name], stream.results[name]
    assert stream.results[_CONTROL] == f"executed:{stream.phase}:{_CONTROL}"
    calls = [row["name"] for row in _records(stream.root, "registry.jsonl") if row["phase"] == stream.phase]
    assert all(name not in calls for name in _DENIED)
    assert calls.count(_CONTROL) == 1


def _snapshot(runner: Any, root: Path, task_id: str) -> dict[str, Any]:
    with sqlite3.connect(str(root / "tasks.db")) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM task_history WHERE task_id = ?", (task_id,)).fetchone()
        assert row is not None
        stored_row = dict(row)
        checkpoints = [dict(row) for row in connection.execute(
            "SELECT * FROM task_checkpoints WHERE task_id = ? ORDER BY id", (task_id,),
        )]
    artifact = root / "project/artifacts/resume.md"
    data = artifact.read_bytes()
    return {
        "row": stored_row,
        "checkpoints": checkpoints,
        "events": runner.state_store.list_execution_events(task_id),
        "artifact": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                     "inode": artifact.stat().st_ino, "text": data.decode("utf-8")},
        "journal": _records(root / "project/artifacts", ".tool_journal.jsonl"),
        "registry": _records(root, "registry.jsonl"),
        "file_effects": _records(root, "file-effects.jsonl"),
        "fake_provider": _records(root, "fake-provider.jsonl"),
    }


def _assert_transitions(snapshot: Mapping[str, Any], statuses: Sequence[str]) -> None:
    events = snapshot["events"]
    assert [row["sequence"] for row in events] == list(range(1, len(events) + 1))
    transitions = [json.loads(row["payload_json"]) for row in events if row["event_type"] == "task.status"]
    assert [(row["from_status"], row["to_status"]) for row in transitions] == list(zip(statuses, statuses[1:]))
    for version, row in enumerate(transitions):
        assert row["from_version"] == version and row["to_version"] == version + 1
        assert row["terminal"] is (row["to_status"] == "done")
    assert snapshot["row"]["version"] == len(transitions)


def _phase_b(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str, dict[str, Any]]:
    from antigravity_k.engine.task_runner import BackgroundTaskRunner

    before = _read_json(root / "phase-a.json")
    assert before["phase"] == "A" and before["pid"] != os.getpid()
    assert before["executable"] == str(Path(sys.executable).resolve())
    assert before["scenario"] == str(root)
    assert not (root / "phase-b.json").exists()
    runner = BackgroundTaskRunner(db_path=str(root / "tasks.db"))
    task_id = before["task_id"]
    assert _snapshot(runner, root, task_id) == before["snapshot"]
    _observe_real_writes(root, "B", monkeypatch)
    return runner, task_id, before


def test_phase_a_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _scenario("A", monkeypatch)
    from antigravity_k.api.contracts.execution_context import RequestExecutionContext
    from antigravity_k.engine.task_runner import BackgroundTaskRunner
    from antigravity_k.engine.tool_policy import ToolPolicy, bind_tool_policy

    _observe_real_writes(root, "A", monkeypatch)
    runner = BackgroundTaskRunner(db_path=str(root / "tasks.db"))
    stream = _Stream(root, "A")
    execution = RequestExecutionContext(
        request_id="r58-synthetic-request", project_id="r58-synthetic-project",
        canonical_project_root=str(root / "project"), conversation_id="r58-conversation",
        conversation_revision=0, actor_subject=_OWNER, session_id="r58-session", model_id="fixture-model",
    )
    policy = ToolPolicy(denied_tools=frozenset(_POLICY["denied_tools"]),
                        allowed_mcp_servers=frozenset({"r58-selected"}))
    with bind_tool_policy(policy):
        task_id = runner.submit_task(
            "Continue the synthetic recovery fixture.",
            context={"direct_response": False, "benchmark_read_only": True,
                     "execution_context": execution.model_dump(mode="json")},
            orchestrator=stream, target_model="fixture-model", owner_subject=_OWNER,
        )
    status = None
    try:
        assert stream.entered.wait(timeout=5), runner.get_status(task_id, owner_subject=_OWNER)
        assert runner.pause_task(task_id, owner_subject=_OWNER) == "pausing"
    finally:
        stream.release.set()
        status = runner.wait_task(task_id, timeout=5)
    assert status is not None and status["status"] == "paused"
    _assert_probes(stream)
    assert "successfully written" in stream.results["artifact"]
    checkpoint = runner.get_last_checkpoint(task_id, owner_subject=_OWNER)
    assert checkpoint is not None and checkpoint["output_so_far"] == _PREFIX
    assert checkpoint["context"]["_request_tool_policy"] == _POLICY
    snapshot = _snapshot(runner, root, task_id)
    assert snapshot["row"]["owner_subject"] == _OWNER
    assert snapshot["row"]["output"] == _PREFIX and snapshot["row"]["owner_pid"] is None
    assert snapshot["artifact"]["text"] == _CONTENT
    assert [row["state"] for row in snapshot["journal"]] == ["intent", "executed"]
    assert len(snapshot["file_effects"]) == 1
    _assert_transitions(snapshot, ("pending", "running", "paused"))
    _write_json_once(root / "phase-a.json", {
        "phase": "A", "pid": os.getpid(), "ppid": os.getppid(),
        "executable": str(Path(sys.executable).resolve()), "scenario": str(root),
        "task_id": task_id, "snapshot": snapshot, "tool_results": stream.results,
    })


def test_phase_b_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _scenario("B", monkeypatch)
    from antigravity_k.engine.tool_policy import ToolPolicy, bind_tool_policy

    runner, task_id, before = _phase_b(root, monkeypatch)
    stream = _Stream(root, "B")
    unchanged = _snapshot(runner, root, task_id)
    assert runner.get_status(task_id, owner_subject=_FOREIGN) is None
    assert runner.get_output(task_id, owner_subject=_FOREIGN) is None
    assert runner.get_last_checkpoint(task_id, owner_subject=_FOREIGN) is None
    assert runner.list_tasks(owner_subject=_FOREIGN) == []
    assert runner.state_store.list_execution_events(task_id, owner_subject=_FOREIGN) == []
    assert runner.resume_task(task_id, orchestrator=stream, target_model="fixture-model", owner_subject=_FOREIGN) is False
    assert _snapshot(runner, root, task_id) == unchanged
    assert runner.get_output(task_id, owner_subject=_OWNER) == _PREFIX
    assert runner.get_status(task_id, owner_subject=_OWNER)["status"] == "paused"
    with bind_tool_policy(ToolPolicy()):
        assert runner.resume_task(task_id, orchestrator=stream, target_model="fixture-model", owner_subject=_OWNER)
    status = runner.wait_task(task_id, timeout=5)
    assert status is not None and status["status"] == "done", status
    _assert_probes(stream)
    assert "[ALREADY COMPLETED]" in stream.results["artifact"]
    assert "already written before resume" in stream.results["changed_artifact"]
    final = _snapshot(runner, root, task_id)
    assert final["row"]["owner_subject"] == _OWNER and final["row"]["owner_pid"] is None
    assert final["row"]["output"] == _PREFIX + _SUFFIX
    assert runner.get_output(task_id, owner_subject=_OWNER) == _PREFIX + _SUFFIX
    assert final["artifact"] == before["snapshot"]["artifact"]
    assert final["journal"] == before["snapshot"]["journal"]
    assert final["file_effects"] == before["snapshot"]["file_effects"]
    writes = [row for row in final["registry"] if row["name"] == "write_artifact"]
    assert [(row["phase"], row["args"]["code_content"]) for row in writes] == [("A", _CONTENT), ("B", _REPLACEMENT)]
    assert [(row["phase"], row["pid"]) for row in final["fake_provider"]] == [("A", before["pid"]), ("B", os.getpid())]
    completions = [json.loads(row["payload_json"]) for row in final["events"] if row["event_type"] == "task_tool.completed"]
    assert sum(row["tool"] == "write_artifact" for row in completions) == 2
    checkpoint = runner.get_last_checkpoint(task_id, owner_subject=_OWNER)
    assert checkpoint is not None and checkpoint["context"]["_request_tool_policy"] == _POLICY
    assert checkpoint["output_so_far"] == _PREFIX
    _assert_transitions(final, ("pending", "running", "paused", "resuming", "running", "done"))
    assert runner.resume_task(task_id, orchestrator=stream, target_model="fixture-model", owner_subject=_OWNER) is False
    assert _snapshot(runner, root, task_id) == final
    _write_json_once(root / "phase-b.json", {
        "phase": "B", "variant": "resume", "pid": os.getpid(), "ppid": os.getppid(),
        "executable": str(Path(sys.executable).resolve()), "scenario": str(root),
        "task_id": task_id, "prior_pid": before["pid"], "snapshot": final,
        "tool_results": stream.results,
    })


def test_phase_b_rejects_corrupted_saved_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Optional negative B; select instead of normal B in a NEW A/B family."""
    root = _scenario("B", monkeypatch)
    runner, task_id, before = _phase_b(root, monkeypatch)
    stream = _Stream(root, "B")
    # Mutate only the latest checkpoint in this synthetic DB, after proving A's
    # actual checkpoint survived the OS process boundary unchanged.
    with sqlite3.connect(str(root / "tasks.db")) as connection:
        checkpoint = connection.execute(
            "SELECT id, context_json FROM task_checkpoints WHERE task_id = ? ORDER BY step DESC, id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        assert checkpoint is not None
        context = json.loads(checkpoint[1])
        context["_request_tool_policy"]["safe_only"] = "false"
        connection.execute("UPDATE task_checkpoints SET context_json = ? WHERE id = ?", (json.dumps(context), checkpoint[0]))
    corrupted = _snapshot(runner, root, task_id)
    assert runner.resume_task(task_id, orchestrator=stream, target_model="fixture-model", owner_subject=_OWNER) is False
    assert _snapshot(runner, root, task_id) == corrupted
    assert stream.results == {}
    assert corrupted["fake_provider"] == before["snapshot"]["fake_provider"]
    assert corrupted["registry"] == before["snapshot"]["registry"]
    assert corrupted["file_effects"] == before["snapshot"]["file_effects"]
    assert corrupted["row"] == before["snapshot"]["row"]
    assert corrupted["events"] == before["snapshot"]["events"]
    _write_json_once(root / "phase-b.json", {
        "phase": "B", "variant": "corrupt-policy", "pid": os.getpid(), "ppid": os.getppid(),
        "executable": str(Path(sys.executable).resolve()), "scenario": str(root),
        "task_id": task_id, "prior_pid": before["pid"], "snapshot": corrupted,
        "tool_results": stream.results,
    })
