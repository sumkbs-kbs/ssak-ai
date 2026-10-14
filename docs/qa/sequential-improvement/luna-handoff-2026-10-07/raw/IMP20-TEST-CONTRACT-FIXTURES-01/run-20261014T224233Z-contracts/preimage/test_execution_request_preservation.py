from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import JsonValue

from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, StateContext
from tests.test_quality_context_approval import _Model, _Orchestrator

if TYPE_CHECKING:
    from antigravity_k.engine.max_engine import MaxRunResult


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class _CapturingModel(_Model):
    def __init__(self) -> None:
        super().__init__("draft")
        self.prompts: list[str] = []

    def stream_generate(self, **kwargs: JsonValue) -> Iterator[str]:
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, str):
            raise TypeError("generation prompt must be text")
        self.prompts.append(prompt)
        yield self.response


class _CapturingOrchestrator(_Orchestrator):
    def __init__(self, project_root: Path) -> None:
        super().__init__(project_root, "draft")
        self.manager = _CapturingModel()
        self.prepared: list[list[dict[str, str]]] = []
        self.delegates: list[str] = []

    def _prepare_agent_prompt(
        self, messages: list[dict[str, str]], delegate_to: str, task_type: str
    ) -> tuple[str, str, str, str, str, list[dict[str, str]]]:
        copied = [dict(message) for message in messages]
        self.prepared.append(copied)
        self.delegates.append(delegate_to)
        prompt = "\n\n".join(message["content"] for message in copied)
        return "local", "", "", "", prompt, copied


class _MaxBoundary:
    is_canonical_runtime = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[Mapping[str, JsonValue]] = []

    def run(self, task_spec: Mapping[str, JsonValue], *, orchestrator: _Orchestrator | None = None) -> MaxRunResult:
        from antigravity_k.engine.max_engine import MaxRunResult

        self.requests.append(dict(task_spec))
        if self.fail:
            raise RuntimeError("worker unavailable")
        return MaxRunResult(total_workers=1, successful=1, selected_idx=-1, final_output="worker result")

    def run_max(self, task_spec: Mapping[str, JsonValue]) -> MaxRunResult:
        return self.run(task_spec)


def _context(*, retry: bool = False, delegate: str = "SELF") -> StateContext:
    request = 'read_file("absent-qa-42.txt"); do not create files; report absence without invented contents'
    messages = [
        {"role": "user", "content": "earlier budget=600000"},
        {"role": "assistant", "content": "confirmed"},
        {"role": "user", "content": request, "images": "image-42", "image_mimes": "image/png"},
    ]
    if retry:
        messages.extend(
            [
                {"role": "assistant", "content": "draft-42"},
                {"role": "user", "content": "retry feedback: cite the read_file failure"},
            ]
        )
    return StateContext(
        user_message=request,
        custom_messages=messages,
        refined_prompt="Introduce the QA persona and offer a test plan.",
        rag_context="Retrieved context: fictional file contents.",
        target_model="local",
        delegate_to=delegate,
        retry_count=int(retry),
    )


def _execute(ctx: StateContext, orch: _CapturingOrchestrator, mode: str) -> None:
    from antigravity_k.engine.orchestrator_execution_handlers import agent_execute_handler, max_execute_handler

    graph = AgentStateGraph()
    state = AgentState.AGENT_EXECUTE if mode == "agent" else AgentState.MAX_EXECUTE
    graph.set_entry(state)
    graph.add_node(state, agent_execute_handler if mode == "agent" else max_execute_handler)
    list(graph.execute(ctx, orch))
    assert ctx.error is None


@pytest.mark.parametrize("mode", ["agent", "max_fallback", "max_error_fallback"])
def test_initial_execution_retains_original_request_after_misleading_refinement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: Literal["agent", "max_fallback", "max_error_fallback"]
) -> None:
    ctx = _context()
    original_messages = [dict(message) for message in ctx.custom_messages]
    orch = _CapturingOrchestrator(tmp_path)
    if mode == "max_error_fallback":
        monkeypatch.setattr(orch, "max_engine", _MaxBoundary(fail=True))
    _execute(ctx, orch, mode)

    submitted = orch.prepared[0][-1]
    content = submitted["content"]
    assert content.endswith(ctx.user_message)
    assert ctx.refined_prompt in content and ctx.rag_context in content
    assert content.index(ctx.refined_prompt) < content.index(ctx.user_message)
    assert content.index(ctx.rag_context) < content.index(ctx.user_message)
    assert submitted["role"] == "user"
    assert submitted["images"] == original_messages[-1]["images"]
    assert submitted["image_mimes"] == original_messages[-1]["image_mimes"]
    assert orch.prepared[0][:-1] == original_messages[:-1]
    assert content in orch.manager.prompts[0]


def test_explicit_qa_delegation_retains_requested_task_and_role(tmp_path: Path) -> None:
    ctx = _context(delegate="QA")
    ctx.user_message = "Delegate to QA: review the release checklist; report missing tests."
    ctx.custom_messages[-1]["content"] = ctx.user_message
    orch = _CapturingOrchestrator(tmp_path)

    _execute(ctx, orch, "agent")

    assert orch.delegates == ["QA"]
    assert orch.prepared[0][-1]["content"].endswith(ctx.user_message)
    assert ctx.delegate_to == "QA"


@pytest.mark.parametrize("mode", ["agent", "max_fallback"])
def test_retry_keeps_feedback_and_original_conversation(tmp_path: Path, mode: Literal["agent", "max_fallback"]) -> None:
    ctx = _context(retry=True)
    original_messages = [dict(message) for message in ctx.custom_messages]
    orch = _CapturingOrchestrator(tmp_path)
    _execute(ctx, orch, mode)

    assert orch.prepared[0] == original_messages
    assert original_messages[-1]["content"] in orch.manager.prompts[0]
    assert ctx.user_message in orch.manager.prompts[0]


@pytest.mark.parametrize("canonical", [False, True])
@pytest.mark.parametrize("retry", [False, True])
def test_max_task_spec_preserves_original_and_retry_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canonical: bool, retry: bool
) -> None:
    ctx = _context(retry=retry)
    orch = _CapturingOrchestrator(tmp_path)
    boundary = _MaxBoundary()
    monkeypatch.setattr(orch, "max_engine", boundary)
    if canonical:
        monkeypatch.setattr(orch, "agent_runtime", boundary)
    feedback = ctx.custom_messages[-1]["content"]

    _execute(ctx, orch, "max")

    prompt = boundary.requests[0]["prompt"]
    assert isinstance(prompt, str)
    assert ctx.user_message in prompt
    if retry:
        assert prompt.endswith(feedback)
        assert ctx.custom_messages[-1]["content"] == feedback
    else:
        assert prompt == ctx.custom_messages[-1]["content"]
        assert prompt.endswith(ctx.user_message)
        assert ctx.refined_prompt in prompt and ctx.rag_context in prompt


def test_no_auxiliary_context_keeps_original_message_unchanged(tmp_path: Path) -> None:
    ctx = _context()
    ctx.refined_prompt = ctx.user_message
    ctx.rag_context = ""
    original = [dict(message) for message in ctx.custom_messages]
    orch = _CapturingOrchestrator(tmp_path)

    _execute(ctx, orch, "agent")

    assert orch.prepared[0] == original
