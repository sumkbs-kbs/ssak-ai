"""UI tool policies across real direct checkpoints and reconstructed runner threads.

Only the final tool registry execution is fake. ToolLoop dispatch, ToolExecutor,
request policy decisions, task binding and SQLite checkpoint/recovery are real.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Final
from unittest.mock import MagicMock

import anyio
import pytest
from pydantic import JsonValue

from antigravity_k.api.contracts.execution_context import RequestExecutionContext
from antigravity_k.api.project_binding import reset_bound_request_execution_context, set_bound_request_execution_context
from antigravity_k.engine import tool_executor as executor_module
from antigravity_k.engine.direct_task_execution import DirectTaskExecution
from antigravity_k.engine.task_execution_context import (
    TaskExecutionContext,
    TaskStateStoreProtocol,
    bind_task_execution_context,
    current_task_execution_context,
)
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.tool_call_parser import ToolCall
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.engine.tool_guardrails import ToolCallGuardrailController
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.base_tool import RiskLevel
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class _Probe:
    name: str
    risk: RiskLevel = RiskLevel.SAFE
    server: str = ""


@dataclass(frozen=True, slots=True)
class _PolicyCase:
    probe: _Probe
    restricted: ToolPolicy
    allowed: ToolPolicy = field(default_factory=ToolPolicy)


_CONTROL: Final = _Probe("r56_allowed_probe", server="r56-selected")
_CASES: Final = (
    _PolicyCase(_Probe("web_search"), ToolPolicy(denied_tools=frozenset({"web_search"}))),
    _PolicyCase(_Probe("run_bash_command", RiskLevel.HIGH),
                ToolPolicy(denied_tools=frozenset({"run_bash_command"}))),
    _PolicyCase(_Probe("r56_mcp_query", server="r56-excluded"),
                ToolPolicy(allowed_mcp_servers=frozenset({"r56-selected"})),
                ToolPolicy(allowed_mcp_servers=frozenset({"r56-selected", "r56-excluded"}))),
    _PolicyCase(_Probe("r56_mutation", RiskLevel.LOW), ToolPolicy(safe_only=True)),
)
_NEUTRAL_REQUEST: Final = "Continue the synthetic recovery fixture."
_POLICY_KEY: Final = "_request_tool_policy"
_UNRESTRICTED_POLICY: Final = {
    "version": 1, "denied_tools": [], "allowed_mcp_servers": None, "safe_only": False,
}


class _StreamInterrupted(RuntimeError):
    def __str__(self) -> str:
        return "synthetic direct stream interruption"


@dataclass(frozen=True, slots=True)
class _ScriptedStream:
    """Results accumulate solely to observe the real dispatcher's decisions."""

    executor: ToolExecutor
    probe: _Probe
    phase: str
    results: list[tuple[str, str]] = field(default_factory=list)
    vault_engine: None = None

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStoreProtocol) -> Iterator[None]:
        with bind_task_execution_context(TaskExecutionContext(task_id, state_store)):
            yield

    def run_stream(
        self, messages: Sequence[Mapping[str, str]], target_model: str,
        max_steps: int = 15, ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        del target_model, max_steps, ephemeral_message
        user_text = next(message["content"] for message in reversed(messages) if message["role"] == "user")
        owner = SimpleNamespace(
            project_root=self.executor.project_root,
            task_execution_context=current_task_execution_context(),
            ctx=SimpleNamespace(tool_executor=self.executor, tool_guardrail=ToolCallGuardrailController(),
                                cognitive_loop=None),
        )
        loop = ToolLoopEngine(owner)
        for probe in (self.probe, _CONTROL):
            outcome = anyio.run(
                loop._run_tool_task_async,
                ToolCall(name=probe.name, arguments={"phase": self.phase}), user_text,
            )
            self.results.append((probe.name, outcome[3]))
        yield self.phase + " checkpoint body\n"
        if self.phase == "direct":
            raise _StreamInterrupted


@dataclass(frozen=True, slots=True)
class _Recovery:
    direct: tuple[tuple[str, str], ...]
    resumed: tuple[tuple[str, str], ...]
    calls: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _InterruptedTask:
    runner: BackgroundTaskRunner
    task_id: str
    stream: _ScriptedStream
    calls: list[tuple[str, str]]


@pytest.fixture(autouse=True)
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", "false")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(executor_module, "ImmuneSystem", MagicMock(return_value=None))


def _executor(root: Path, probe: _Probe, calls: list[tuple[str, str]]) -> ToolExecutor:
    registry = MagicMock(spec=ToolRegistry)
    tools: dict[str, MagicMock] = {}
    for item in (probe, _CONTROL):
        tool = MagicMock()
        tool.name = item.name
        tool.risk_level = item.risk
        tool._server_name = item.server
        tool.parameters_schema = {"required": ["phase"]}
        tools[item.name] = tool
    registry.get = MagicMock(side_effect=tools.get)
    registry.get_tool = MagicMock(side_effect=tools.get)
    registry.get_names = MagicMock(return_value=list(tools))
    registry.__contains__ = lambda _registry, name: name in tools

    def execute_with_permission(
        name: str, args: Mapping[str, str], objective: str = "",
    ) -> tuple[Permission, str]:
        del objective
        calls.append((name, args["phase"]))
        return Permission.ALLOW, "executed:" + args["phase"]

    registry.execute_with_permission = execute_with_permission
    return ToolExecutor(registry, MagicMock(spec=PermissionGate), project_root=str(root))


def _interrupt(root: Path, case: _PolicyCase, request_text: str = _NEUTRAL_REQUEST) -> _InterruptedTask:
    calls: list[tuple[str, str]] = []
    database = root / "tasks.db"
    first = BackgroundTaskRunner(db_path=str(database))
    original = _ScriptedStream(_executor(root, case.probe, calls), case.probe, "direct")
    execution = DirectTaskExecution(original, first)
    context = RequestExecutionContext(
        request_id="r56-request", project_id="r56-project", canonical_project_root=str(root),
        conversation_id="conv_unspecified", conversation_revision=0, actor_subject="r56-owner",
        session_id="r56-session", model_id="fixture-model",
    )
    binding = set_bound_request_execution_context(context)
    policy = set_tool_policy(case.restricted)
    try:
        tracked = execution.start_stream([{"role": "user", "content": request_text}], "fixture-model", 1, None)
        with pytest.raises(_StreamInterrupted):
            list(tracked.chunks)
    finally:
        reset_tool_policy(policy)
        reset_bound_request_execution_context(binding)
    assert tracked.task_id is not None
    checkpoint = first.state_store.get_last_checkpoint(tracked.task_id)
    assert checkpoint is not None and checkpoint["output_so_far"] == "direct checkpoint body\n"
    return _InterruptedTask(first, tracked.task_id, original, calls)


def _resume(task: _InterruptedTask, probe: _Probe, caller_policy: ToolPolicy | None = None) -> _Recovery:
    resumed_runner = BackgroundTaskRunner(db_path=task.runner.db_path)
    root = Path(task.stream.executor.project_root)
    resumed = _ScriptedStream(_executor(root, probe, task.calls), probe, "resumed")
    # A new caller's unrestricted context must not widen the saved request policy.
    ambient = set_tool_policy(caller_policy)
    try:
        assert resumed_runner.resume_task(
            task.task_id, orchestrator=resumed, target_model="fixture-model", owner_subject="r56-owner",
        )
        status = resumed_runner.wait_task(task.task_id, timeout=5)
    finally:
        reset_tool_policy(ambient)
    assert status is not None and status["status"] == "done"
    return _Recovery(tuple(task.stream.results), tuple(resumed.results), tuple(task.calls))


def _recover(root: Path, case: _PolicyCase, request_text: str = _NEUTRAL_REQUEST) -> _Recovery:
    return _resume(_interrupt(root, case, request_text), case.probe, ToolPolicy())


@pytest.mark.parametrize("case", _CASES, ids=["search", "shell", "mcp-selection", "read-only"])
@pytest.mark.parametrize("restricted", [True, False], ids=["ui-off", "explicitly-allowed"])
def test_direct_checkpoint_resume_preserves_ui_tool_policy(
    tmp_path: Path, case: _PolicyCase, restricted: bool,
) -> None:
    # Given: neutral user text and either an explicit UI restriction or permission.
    policy = case.restricted if restricted else case.allowed
    selected = _PolicyCase(case.probe, policy)

    # When: real direct execution checkpoints, then a new runner thread resumes it.
    result = _recover(tmp_path, selected)

    # Then: policy decisions still govern actual calls, while an allowed probe runs.
    for observations in (result.direct, result.resumed):
        assert result_indicates_failure(observations[0][1]) is restricted, observations
        if restricted:
            assert "[BLOCKED]" in observations[0][1], observations
        assert result_indicates_failure(observations[1][1]) is False, observations
    expected = () if restricted else ((case.probe.name, "direct"), (case.probe.name, "resumed"))
    assert tuple(call for call in result.calls if call[0] == case.probe.name) == expected
    assert tuple(call for call in result.calls if call[0] == _CONTROL.name) == (
        (_CONTROL.name, "direct"), (_CONTROL.name, "resumed"),
    )


def test_user_text_search_prohibition_remains_independent_of_ui_permission(tmp_path: Path) -> None:
    # Given: UI policy allows search, while the user's text explicitly prohibits it.
    case = _PolicyCase(_Probe("web_search"), ToolPolicy())

    # When: the same real dispatcher handles the original and reconstructed task.
    result = _recover(tmp_path, case, "Do not search. Continue the synthetic recovery fixture.")

    # Then: user-text constraints block search independently; the other tool still runs.
    for observations in (result.direct, result.resumed):
        assert "[USER TOOL CONSTRAINT]" in observations[0][1], observations
        assert result_indicates_failure(observations[1][1]) is False, observations
    assert result.calls == ((_CONTROL.name, "direct"), (_CONTROL.name, "resumed"))


@pytest.mark.parametrize("case", _CASES, ids=["search", "shell", "mcp-selection", "read-only"])
def test_new_resume_restrictions_narrow_the_saved_permissions(tmp_path: Path, case: _PolicyCase) -> None:
    # Given: the original request explicitly allowed this fake tool.
    task = _interrupt(tmp_path, _PolicyCase(case.probe, case.allowed))
    # When: a new resume request applies a stricter UI policy.
    result = _resume(task, case.probe, case.restricted)
    # Then: only the original call executed; the selected safe control still runs.
    assert "[BLOCKED]" in result.resumed[0][1], result
    assert result.calls == ((case.probe.name, "direct"), (_CONTROL.name, "direct"), (_CONTROL.name, "resumed"))


def test_checkpoint_context_cannot_replace_the_saved_server_policy(tmp_path: Path) -> None:
    # Given: the server's direct checkpoint forbids search.
    case = _CASES[0]
    task = _interrupt(tmp_path, case)
    # When: model/caller context attempts to replace it with unrestricted policy.
    assert task.runner._save_checkpoint(task.task_id, 100, {_POLICY_KEY: _UNRESTRICTED_POLICY},
                                        "direct checkpoint body\n")
    result = _resume(task, case.probe)
    # Then: the preserved server decision still blocks the actual registry boundary.
    assert "[BLOCKED]" in result.resumed[0][1], result
    assert result.calls == ((_CONTROL.name, "direct"), (_CONTROL.name, "resumed"))


def test_background_submission_overwrites_forged_client_policy(tmp_path: Path) -> None:
    # Given: a client supplies unrestricted policy while the server forbids search.
    calls: list[tuple[str, str]] = []
    probe = _CASES[0].probe
    stream = _ScriptedStream(_executor(tmp_path, probe, calls), probe, "resumed")
    runner = BackgroundTaskRunner(db_path=str(tmp_path / "submitted.db"))
    policy = set_tool_policy(_CASES[0].restricted)
    try:
        # When: the real submission path captures authority and starts its worker.
        task_id = runner.submit_task(_NEUTRAL_REQUEST,
            context={_POLICY_KEY: _UNRESTRICTED_POLICY},
            orchestrator=stream, target_model="fixture-model")
    finally:
        reset_tool_policy(policy)
    status = runner.wait_task(task_id, timeout=5)
    # Then: the client's reserved value grants no execution, while safe work succeeds.
    assert status is not None and status["status"] == "done"
    assert "[BLOCKED]" in stream.results[0][1], stream.results
    assert calls == [(_CONTROL.name, "resumed")]


def test_empty_mcp_selection_remains_different_from_unrestricted_after_resume(tmp_path: Path) -> None:
    # Given: both MCP probes are excluded by an explicitly empty UI selection.
    case = _PolicyCase(_CASES[2].probe, ToolPolicy(allowed_mcp_servers=frozenset()))
    # When: a new caller with no selection restriction resumes the checkpoint.
    result = _recover(tmp_path, case)
    # Then: neither MCP probe sends a call in either execution.
    assert result.calls == ()
    assert all("[BLOCKED]" in output for observations in (result.direct, result.resumed)
               for _name, output in observations)


@pytest.mark.parametrize("raw", [
    None, {},
    {"version": True, "denied_tools": [], "allowed_mcp_servers": None, "safe_only": False},
    {"version": 2, "denied_tools": [], "allowed_mcp_servers": None, "safe_only": False},
    {"version": 1, "denied_tools": [], "allowed_mcp_servers": None, "safe_only": "false"},
    {"version": 1, "denied_tools": [], "allowed_mcp_servers": "r56-selected", "safe_only": False},
])
def test_malformed_saved_policy_refuses_resume_before_any_effect(tmp_path: Path, raw: JsonValue) -> None:
    # Given: storage contains a damaged present policy, rather than a legacy missing key.
    task = _interrupt(tmp_path, _CASES[0])
    task.runner.state_store.save_checkpoint(task.task_id, 100, json.dumps({_POLICY_KEY: raw}),
                                           "direct checkpoint body\n")
    before = task.runner.state_store.get_task(task.task_id)
    events = task.runner.state_store.list_execution_events(task.task_id)
    calls = tuple(task.calls)
    resumed = BackgroundTaskRunner(db_path=task.runner.db_path)
    stream = _ScriptedStream(_executor(tmp_path, _CASES[0].probe, task.calls), _CASES[0].probe, "resumed")
    # When: the reconstructed runner is asked to resume corrupted authority.
    assert resumed.resume_task(task.task_id, orchestrator=stream, target_model="fixture-model") is False
    # Then: neither a fake tool nor a state/event transition occurs.
    assert tuple(task.calls) == calls and stream.results == []
    assert resumed.state_store.get_task(task.task_id) == before
    assert resumed.state_store.list_execution_events(task.task_id) == events


def test_legacy_checkpoint_without_policy_keeps_its_tool_execution_contract(tmp_path: Path) -> None:
    # Given: an old checkpoint has no policy field at all.
    case = _PolicyCase(_Probe("web_search"), ToolPolicy())
    task = _interrupt(tmp_path, case)
    task.runner.state_store.save_checkpoint(task.task_id, 100, "{}", "direct checkpoint body\n")
    # When: a caller with no new policy resumes it.
    result = _resume(task, case.probe)
    # Then: both the old permitted tool and safe control execute normally.
    assert result.calls == ((case.probe.name, "direct"), (_CONTROL.name, "direct"),
                            (case.probe.name, "resumed"), (_CONTROL.name, "resumed"))
