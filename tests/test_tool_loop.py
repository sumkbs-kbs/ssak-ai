"""Tests for tool_loop.py — ToolLoopEngine.

Covers:
- __init__ with mock orchestrator
- _native_tools_kwargs: disabled, enabled with unsupported provider, enabled with openrouter
- _post_loop_checks: cognitive_loop, quality_gate, decision_anchor, event_bus (success + error)
- _run_tool_task_async: guardrail blocks, successful execution, cognitive verify error
- run_loop: model not loaded, capacity halt/warn, text only, tool call success,
  error compress/retryable/non-retryable, tool blocked, approval required, step limit
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Generator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from antigravity_k.engine.benchmark_harness import TaskOutcome
from antigravity_k.engine.quality_gate import QualityGrade, QualityScore
from antigravity_k.engine.task_context_snapshot import load_task_context_snapshot
from antigravity_k.engine.task_state_store import TaskExecutionContext, TaskStateStore
from antigravity_k.engine.tool_call_parser import ToolCall
from antigravity_k.engine.tool_loop import TaskOutcomeRecorder, ToolExecutionResult, ToolLoopEngine


def _format_tool_response(
    engine: ToolLoopEngine,
    tool_call: ToolCall,
    tool_result: str,
    focus_terms: tuple[str, ...] = (),
) -> str:
    method = cast(Callable[[ToolCall, str, tuple[str, ...]], str], getattr(engine, "_format_tool_response"))
    return method(tool_call, tool_result, focus_terms)


def _native_tools_kwargs(
    engine: ToolLoopEngine,
    delegate_model: str,
    required_tools: tuple[str, ...] | None = None,
) -> dict[str, object]:
    method = cast(
        Callable[[str, tuple[str, ...] | None], dict[str, object]],
        getattr(engine, "_native_tools_kwargs"),
    )
    return method(delegate_model, required_tools)


def _post_loop_checks(
    engine: ToolLoopEngine,
    messages: list[dict[str, str]],
    task_type: str,
    full_output: str,
    user_task: str,
    delegate_model: str | None = None,
    evidence_context: str = "",
) -> Generator[str, None, QualityScore | None]:
    method = cast(
        Callable[
            [list[dict[str, str]], str, str, str, str | None, str],
            Generator[str, None, QualityScore | None],
        ],
        getattr(engine, "_post_loop_checks"),
    )
    return method(messages, task_type, full_output, user_task, delegate_model, evidence_context)


def _quality_revision(
    engine: ToolLoopEngine,
    user_task: str,
    full_output: str,
    feedback: str,
    delegate_model: str | None,
    evidence_context: str = "",
) -> str:
    method = cast(Callable[[str, str, str, str | None, str], str], getattr(engine, "_quality_revision"))
    return method(user_task, full_output, feedback, delegate_model, evidence_context)


async def _run_tool_task_async(engine: ToolLoopEngine, tool_call: ToolCall) -> ToolExecutionResult:
    method = cast(Callable[[ToolCall], Awaitable[ToolExecutionResult]], getattr(engine, "_run_tool_task_async"))
    return await method(tool_call)


def _run_loop(
    engine: ToolLoopEngine,
    messages: list[dict[str, str]],
    delegate_to: str,
    task_type: str,
    max_steps: int,
    target_model: str | None,
) -> Generator[str, None, None]:
    method = cast(
        Callable[[list[dict[str, str]], str, str, int, str | None], Generator[str, None, None]],
        getattr(engine, "run_loop"),
    )
    return method(messages, delegate_to, task_type, max_steps, target_model)


def _engine(
    orchestrator: MagicMock,
    outcome_recorder: TaskOutcomeRecorder | None = None,
) -> ToolLoopEngine:
    return ToolLoopEngine(cast(object, orchestrator), outcome_recorder=outcome_recorder)


def _maybe_compress_context(
    engine: ToolLoopEngine,
    shaped_messages: list[dict[str, str]],
    prompt_str: str,
    delegate_model: str,
    task_type: str,
    system_prompt: str,
    tool_prompt: str,
    skill_prompts: str,
    focus_terms: tuple[str, ...] = (),
) -> tuple[list[dict[str, str]], str, float | None, float | None]:
    """Compatibility wrapper — returns the legacy 4-tuple for existing tests."""
    method = getattr(engine, "_maybe_compress_context")
    attempt = method(
        shaped_messages,
        prompt_str,
        delegate_model,
        task_type,
        system_prompt,
        tool_prompt,
        skill_prompts,
        focus_terms,
    )
    return attempt.messages, attempt.prompt, attempt.usage_before, attempt.usage_after


def _refresh_checkpoint_context(engine: ToolLoopEngine, messages: list[dict[str, str]]) -> None:
    method = cast(Callable[[list[dict[str, str]]], None], getattr(engine, "_refresh_checkpoint_context"))
    method(messages)


def _expected_tools(engine: ToolLoopEngine) -> tuple[str, ...]:
    method = cast(Callable[[], tuple[str, ...]], getattr(engine, "_expected_tools"))
    return method()


def _outcome_recorder(outcomes: list[TaskOutcome]) -> TaskOutcomeRecorder:
    def record(outcome: TaskOutcome) -> TaskOutcome:
        outcomes.append(outcome)
        return outcome

    return cast(TaskOutcomeRecorder, record)


def _mock_path(root: MagicMock, path: tuple[str, ...]) -> MagicMock:
    current: object = root
    for name in path:
        current = cast(MagicMock, cast(object, getattr(current, name)))
    return current


def _set_mock_return(root: MagicMock, path: tuple[str, ...], value: object) -> None:
    setattr(_mock_path(root, path), "return_value", value)


def _set_mock_attr(root: MagicMock, path: tuple[str, ...], value: object) -> None:
    names = list(path)
    if not names:
        raise ValueError("mock attribute path must not be empty")
    parent = _mock_path(root, path[:-1]) if len(path) > 1 else root
    setattr(parent, names[-1], value)


def _set_mock_side_effect(root: MagicMock, path: tuple[str, ...], value: object) -> None:
    setattr(_mock_path(root, path), "side_effect", value)


def _get_mock_attr(root: MagicMock, path: tuple[str, ...]) -> object:
    current: object = root
    for name in path:
        current = cast(object, getattr(cast(MagicMock, cast(object, current)), name))
    return current


def _assert_mock_called_once_with(
    root: MagicMock,
    path: tuple[str, ...],
    *args: object,
    **kwargs: object,
) -> None:
    method = cast(Callable[..., object], cast(object, getattr(_mock_path(root, path), "assert_called_once_with")))
    _ = method(*args, **kwargs)


def _assert_mock_called_once(root: MagicMock, path: tuple[str, ...]) -> None:
    method = cast(Callable[[], object], cast(object, getattr(_mock_path(root, path), "assert_called_once")))
    _ = method()


def _assert_mock_not_called(root: MagicMock, path: tuple[str, ...]) -> None:
    method = cast(Callable[[], object], cast(object, getattr(_mock_path(root, path), "assert_not_called")))
    _ = method()


def _assert_mock_awaited_once_with(
    root: MagicMock,
    path: tuple[str, ...],
    *args: object,
    **kwargs: object,
) -> None:
    method = cast(
        Callable[..., object],
        cast(object, getattr(_mock_path(root, path), "assert_awaited_once_with")),
    )
    _ = method(*args, **kwargs)


def _assert_mock_awaited_not_called(root: MagicMock, path: tuple[str, ...]) -> None:
    method = cast(Callable[[], object], cast(object, getattr(_mock_path(root, path), "assert_not_awaited")))
    _ = method()


def _mock_call_count(root: MagicMock, path: tuple[str, ...]) -> int:
    return cast(int, cast(object, getattr(_mock_path(root, path), "call_count")))


def _mock_call_args(root: MagicMock, path: tuple[str, ...]) -> tuple[tuple[object, ...], dict[str, object]]:
    call_args = cast(object, getattr(_mock_path(root, path), "call_args"))
    args = cast(tuple[object, ...], cast(object, getattr(call_args, "args")))
    kwargs = cast(dict[str, object], cast(object, getattr(call_args, "kwargs")))
    return args, kwargs


def _mock_call_kwargs_list(root: MagicMock, path: tuple[str, ...]) -> list[dict[str, object]]:
    raw_calls = cast(object, getattr(_mock_path(root, path), "call_args_list"))
    return [cast(dict[str, object], getattr(call, "kwargs")) for call in cast(list[object], raw_calls)]


def _mock_await_args_list(root: MagicMock, path: tuple[str, ...]) -> list[tuple[tuple[object, ...], dict[str, object]]]:
    raw_calls = cast(object, getattr(_mock_path(root, path), "await_args_list"))
    return [
        (
            cast(tuple[object, ...], getattr(call, "args")),
            cast(dict[str, object], getattr(call, "kwargs")),
        )
        for call in cast(list[object], raw_calls)
    ]


class _RaisingIter:
    """Iterator that raises exc on first __next__().

    Use as stream_generate.return_value to test exception handling
    inside the try/except block (not during stream_generate() call,
    which is OUTSIDE the try block).
    """

    def __init__(self, exc: Exception):
        self.exc: Exception = exc

    def __iter__(self) -> _RaisingIter:
        return self

    def __next__(self) -> str:
        raise self.exc


# ─── Mock Orchestrator Fixture ──────────────────────────────────


@pytest.fixture
def mock_orch() -> MagicMock:
    """Mock orchestrator with minimal attributes for ToolLoopEngine."""
    orch = MagicMock()
    orch.config = {}
    orch.project_root = "/tmp/test"
    orch._skill_prompts_cache = ""
    orch._last_agent_output = ""
    _set_mock_attr(orch, ("manager",), MagicMock())
    _set_mock_attr(orch, ("manager", "_registry"), MagicMock())
    _set_mock_attr(orch, ("manager", "router"), MagicMock())
    _set_mock_return(orch, ("manager", "is_loaded"), True)
    _set_mock_return(
        orch,
        ("_prepare_agent_prompt",),
        (
            "delegate_model",
            "system_prompt_part",
            "tool_prompt_part",
            "skill_prompts_part",
            "prompt_str",
            [{"role": "user", "content": "test"}],
        ),
    )

    # Context with guardrail
    ctx = MagicMock()
    ctx.tool_guardrail = MagicMock()
    before_call_result = MagicMock()
    setattr(before_call_result, "allows_execution", True)
    _set_mock_return(ctx, ("tool_guardrail", "before_call"), before_call_result)
    after_call_result = MagicMock()
    setattr(after_call_result, "action", "allow")
    _set_mock_return(ctx, ("tool_guardrail", "after_call"), after_call_result)
    setattr(_mock_path(ctx, ("tool_guardrail",)), "reset", MagicMock())
    ctx.cognitive_loop = MagicMock()
    ctx.quality_gate = MagicMock()
    quality_result = MagicMock()
    setattr(quality_result, "user_message", "")
    setattr(quality_result, "should_retry", False)
    _set_mock_return(ctx, ("quality_gate", "evaluate"), quality_result)
    ctx.decision_anchor = MagicMock()
    _set_mock_return(ctx, ("decision_anchor", "auto_extract"), None)
    _set_mock_attr(ctx, ("tool_executor",), MagicMock())
    _set_mock_attr(ctx, ("tool_executor", "execute_async"), AsyncMock(return_value="result_ok"))

    orch.ctx = ctx
    return orch


# ─── Init ────────────────────────────────────────────────────────


class TestToolLoopEngineInit:
    def test_stores_orchestrator(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        assert cast(object, getattr(engine, "orch")) is mock_orch

    def test_accepts_task_outcome_recorder(self, mock_orch: MagicMock):
        recorder = MagicMock()
        engine = ToolLoopEngine(mock_orch, outcome_recorder=recorder)
        assert engine.outcome_recorder is recorder

    def test_compacts_large_tool_result_with_source_provenance(self, mock_orch: MagicMock):
        raw_result = "BEGIN\n" + ("x" * 20_000) + "\nEND"
        formatted = _format_tool_response(
            _engine(mock_orch),
            ToolCall(name="read_file", arguments={"file_path": "README.md"}),
            raw_result,
        )

        assert len(formatted) < 7_000
        assert '"source": "README.md"' in formatted
        assert '"original_chars": 20010' in formatted
        assert '"context_artifact_ref": "artifact-' in formatted
        assert '"context_artifact_tool": "read_context_artifact"' in formatted
        assert "BEGIN" in formatted
        assert "END" in formatted

    def test_restores_stored_tool_artifact(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        formatted = _format_tool_response(
            engine,
            ToolCall(name="read_file", arguments={"file_path": "README.md"}),
            "A" * 20_000,
        )
        marker = '"context_artifact_ref": "'
        ref_id = formatted.split(marker, 1)[1].split('"', 1)[0]

        assert engine.restore_context_artifact(ref_id) == "A" * 20_000

    def test_preserves_query_matched_middle_evidence_when_compacting(self, mock_orch: MagicMock):
        raw_result = "header\n" + ("x" * 8_000) + "\nagent_models:\n  default: qwen3.6:latest\n" + ("y" * 8_000)
        formatted = _format_tool_response(
            _engine(mock_orch),
            ToolCall(name="read_file", arguments={"file_path": "config.yaml"}),
            raw_result,
            focus_terms=("agent_models",),
        )

        assert "agent_models:" in formatted
        assert "default: qwen3.6:latest" in formatted

    def test_redacts_secrets_in_tool_result_before_context_injection(self, mock_orch: MagicMock):
        raw_result = "NVIDIA_API_KEY=nvapi-abc123def456789012345678901234567890\nexport OPENAI_API_KEY=sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        formatted = _format_tool_response(
            _engine(mock_orch),
            ToolCall(name="read_file", arguments={"file_path": ".env"}),
            raw_result,
        )

        assert "nvapi-abc123def456789012345678901234567890" not in formatted
        assert "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in formatted
        assert "<REDACTED>" in formatted

    def test_redacts_secrets_even_when_large_tool_result_is_truncated(self, mock_orch: MagicMock):
        # Secret sits near the head so it lands in the truncated head slice.
        raw_result = "OPENAI_API_KEY=sk-proj-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZ" + chr(10) + ("x" * 20_000) + chr(10) + "END"
        formatted = _format_tool_response(
            _engine(mock_orch),
            ToolCall(name="read_file", arguments={"file_path": "big.env"}),
            raw_result,
        )

        assert "sk-proj-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZ" not in formatted
        assert "<REDACTED>" in formatted


class TestToolLoopEngineNativeToolsKwargs:
    def test_disabled_by_default(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert result == {}

    def test_enabled_but_unsupported_provider(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "mlx")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert result == {}

    def test_enabled_with_openrouter_success(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "openrouter")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [{"name": "run_bash"}])
        setattr(mock_orch, "tool_registry", tool_registry)
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert "tools" in result
        assert result["tools"] == [{"name": "run_bash"}]

    def test_enabled_with_ollama_success(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "ollama")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        _set_mock_return(mock_orch, ("manager", "provider_capability"), {"native_tool_calling": "supported"})
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [{"name": "read_file"}])
        setattr(mock_orch, "tool_registry", tool_registry)
        engine = _engine(mock_orch)

        result = _native_tools_kwargs(engine, "qwen3.6:latest")

        assert result["tools"] == [{"name": "read_file"}]

    def test_enabled_ollama_limits_schemas_to_required_tools(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "ollama")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        _set_mock_return(mock_orch, ("manager", "provider_capability"), {"native_tool_calling": "supported"})
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [{"name": "read_file"}])
        setattr(mock_orch, "tool_registry", tool_registry)

        result = _native_tools_kwargs(_engine(mock_orch), "qwen3.6:latest", ("read_file",))

        assert result["tools"] == [{"name": "read_file"}]
        _assert_mock_called_once_with(tool_registry, ("to_openai_schemas",), names=["read_file"])

    def test_enabled_with_lmstudio_native_capability_success(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "lmstudio")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        _set_mock_return(mock_orch, ("manager", "provider_capability"), {"native_tool_calling": "supported"})
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [{"name": "read_file"}])
        setattr(mock_orch, "tool_registry", tool_registry)
        engine = _engine(mock_orch)

        result = _native_tools_kwargs(engine, "lmstudio/qwen3.6")

        assert result["tools"] == [{"name": "read_file"}]

    def test_enabled_with_explicitly_unsupported_local_capability_uses_xml(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "ollama")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        _set_mock_return(mock_orch, ("manager", "provider_capability"), {"native_tool_calling": "unsupported"})
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [{"name": "read_file"}])
        setattr(mock_orch, "tool_registry", tool_registry)
        engine = _engine(mock_orch)

        result = _native_tools_kwargs(engine, "legacy-local")

        assert result == {}

    def test_enabled_with_openrouter_empty_schemas(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        setattr(profile, "provider", "openrouter")
        _set_mock_return(mock_orch, ("manager", "_registry", "get_model"), profile)
        tool_registry = MagicMock()
        _set_mock_return(tool_registry, ("to_openai_schemas",), [])
        setattr(mock_orch, "tool_registry", tool_registry)
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert result == {}

    def test_registry_get_model_raises_exception(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", {"tool_loop": {"native_function_calling": True}})
        _set_mock_side_effect(mock_orch, ("manager", "_registry", "get_model"), ValueError("not found"))
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert result == {}

    def test_config_not_dict(self, mock_orch: MagicMock):
        setattr(mock_orch, "config", None)
        engine = _engine(mock_orch)
        result = _native_tools_kwargs(engine, "some-model")
        assert result == {}


# ─── Post-Loop Checks ──────────────────────────────────────────


class TestToolLoopEnginePostLoopChecks:
    def test_uses_source_title_fallback_when_no_model_claim_is_supported(self, mock_orch: MagicMock):
        # Given: usable search records but no claim the model grounded correctly.
        evidence_context = (
            "1. [citation:python-docs] **Python 3.13 release notes**\n"
            "   [untrusted_web_content]\n"
            "Python 3.13 introduces an experimental JIT compiler.\n"
            "   [/untrusted_web_content]\n"
            "   🔗 https://docs.python.org/3/whatsnew/3.13.html\n"
        )
        invalid_output = "Python 3.13 runs a perfect JIT. [citation:wrong-id]"
        _set_mock_return(mock_orch, ("manager", "generate"), invalid_output)
        setattr(_mock_path(mock_orch, ("ctx",)), "analysis", {})
        engine = _engine(mock_orch)

        # When: model correction and claim filtering cannot retain a factual claim.
        outputs = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": "Python 3.13 JIT 기능을 알려줘"}],
                "search",
                invalid_output,
                "Python 3.13 JIT 기능을 알려줘",
                "qwen3.6:latest",
                evidence_context=evidence_context,
            ),
        )

        # Then: only an exact source title and its known ID are returned.
        assert cast(bool, getattr(engine, "_citation_validation_failed")) is False
        assert cast(str, engine.last_output) == (
            "- Python 3.13 release notes [citation:python-docs]\n\n"
            "출처: [docs.python.org](<https://docs.python.org/3/whatsnew/3.13.html>)"
        )
        analysis = cast(dict[str, object], _get_mock_attr(mock_orch, ("ctx", "analysis")))
        assert analysis["citation_recovery"] == "deterministic_source_titles"
        assert any("Citation Recovery" in output for output in outputs)

    def test_recovers_only_supported_claims_after_invalid_citation_revision(self, mock_orch: MagicMock):
        # Given: one supported claim, one unknown citation, and one unsupported claim.
        evidence_context = (
            "1. [citation:python-docs] **Python 3.13 release notes**\n"
            "   [untrusted_web_content]\n"
            "Python 3.13 introduces an experimental JIT compiler.\n"
            "   [/untrusted_web_content]\n"
            "   🔗 https://docs.python.org/3/whatsnew/3.13.html\n"
        )
        invalid_output = (
            "Python 3.13 introduces an experimental JIT compiler. "
            "[citation:python-docs][citation:wrong-id]\n"
            "Python 3.13 removes all GIL limitations. [citation:python-docs]"
        )
        _set_mock_return(mock_orch, ("manager", "generate"), invalid_output)
        setattr(_mock_path(mock_orch, ("ctx",)), "analysis", {})
        engine = _engine(mock_orch)

        # When: the model revision preserves invalid citations and unsupported content.
        outputs = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": "Python 3.13 JIT 기능을 알려줘"}],
                "chat",
                invalid_output,
                "Python 3.13 JIT 기능을 알려줘",
                "qwen3.6:latest",
                evidence_context=evidence_context,
            ),
        )

        # Then: only the mechanically supported claim remains with its known citation.
        assert cast(bool, getattr(engine, "_citation_validation_failed")) is False
        assert cast(str, engine.last_output) == (
            "- Python 3.13 introduces an experimental JIT compiler. [citation:python-docs]\n\n"
            "출처: [docs.python.org](<https://docs.python.org/3/whatsnew/3.13.html>)"
        )
        analysis = cast(dict[str, object], _get_mock_attr(mock_orch, ("ctx", "analysis")))
        assert analysis["citation_recovery"] == "deterministic_claim_filter"
        citation_evaluation = cast(dict[str, object], analysis["citation_evaluation"])
        assert citation_evaluation["unknown_citation_count"] == 0
        assert any("Citation Recovery" in output for output in outputs)

    def test_revises_uncited_web_claim_with_available_evidence(self, mock_orch: MagicMock):
        # Given: a final answer without the available web citation.
        evidence_context = (
            "1. [citation:python-docs] **Python 3.13 release notes**\n"
            "   [untrusted_web_content]\n"
            "Python 3.13 introduces an experimental JIT compiler.\n"
            "   [/untrusted_web_content]\n"
            "   🔗 https://docs.python.org/3/whatsnew/3.13.html\n"
        )
        _set_mock_return(
            mock_orch,
            ("manager", "generate"),
            ("Python 3.13 introduces an experimental JIT compiler. [citation:python-docs]"),
        )
        engine = _engine(mock_orch)

        # When: post-loop checks receive an unsupported factual claim.
        outputs = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": "Python 3.13의 JIT 기능을 알려줘"}],
                "chat",
                "Python 3.13 offers a JIT compiler.",
                "Python 3.13의 JIT 기능을 알려줘",
                "qwen3.6:latest",
                evidence_context=evidence_context,
            ),
        )

        # Then: the corrected answer is grounded and replaces the original output.
        assert cast(bool, getattr(engine, "_citation_validation_failed")) is False
        assert cast(str, engine.last_output) == (
            "Python 3.13 introduces an experimental JIT compiler. [citation:python-docs]\n\n"
            "출처: [docs.python.org](<https://docs.python.org/3/whatsnew/3.13.html>)"
        )
        assert any("Citation Revision" in output for output in outputs)

    def test_quality_gate_uses_orchestrator_context_without_direct_attribute(self):
        quality_gate = MagicMock()
        _set_mock_return(
            quality_gate,
            ("evaluate",),
            QualityScore(
                grade=QualityGrade.A,
                score=1.0,
                feedback="",
                user_message="",
                should_retry=False,
                issues=[],
            ),
        )
        orchestrator = SimpleNamespace(
            ctx=SimpleNamespace(cognitive_loop=None, quality_gate=quality_gate, decision_anchor=None),
            project_root="/tmp/test",
        )

        _ = list(
            _post_loop_checks(
                ToolLoopEngine(orchestrator),
                [{"role": "user", "content": "write code"}],
                "code",
                "```python\ndef valid():\n    return 1\n```",
                "write code",
            )
        )

        _assert_mock_called_once(quality_gate, ("evaluate",))

    def test_cognitive_loop_reflect_called(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        method = cast(
            Callable[[str, str], object],
            cast(
                object, getattr(_mock_path(mock_orch, ("ctx", "cognitive_loop", "reflect")), "assert_called_once_with")
            ),
        )
        _ = method("do something", "output")

    def test_quality_gate_evaluate_called(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        _assert_mock_called_once(mock_orch, ("ctx", "quality_gate", "evaluate"))

    def test_quality_gate_user_message_yielded(self, mock_orch: MagicMock):
        _set_mock_attr(
            mock_orch, ("ctx", "quality_gate", "evaluate", "return_value", "user_message"), "Quality issue detected"
        )
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        res = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        assert any("Quality issue detected" in r for r in res)

    def test_quality_gate_retry_marked(self, mock_orch: MagicMock):
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "evaluate", "return_value", "should_retry"), True)
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "evaluate", "return_value", "feedback"), "needs improvement")
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "evaluate", "return_value", "user_message"), "")
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        _assert_mock_called_once(mock_orch, ("ctx", "quality_gate", "mark_retry"))

    def test_quality_gate_revision_replaces_output_and_outcome(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=True, feedback="보완 필요", score=0.3)
        revised = MagicMock(user_message="", should_retry=False, feedback="", score=0.9)
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("_get_model_for_role",), "qwen3.6:latest")
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter(["초안"]))
        _set_mock_return(mock_orch, ("manager", "generate"), "보완된 최종 답변")
        outcomes: list[TaskOutcome] = []

        with patch("antigravity_k.engine.event_bus.global_event_bus") as event_bus:
            engine = ToolLoopEngine(mock_orch, outcome_recorder=_outcome_recorder(outcomes))
            result = list(engine.run_loop([{"role": "user", "content": "요청"}], "CODER", "chat"))

        assert any("보완된 최종 답변" in chunk for chunk in result)
        assert cast(str, engine.last_output) == "보완된 최종 답변"
        assert outcomes[0].retry_count == 1
        # 토큰 집계는 단일 추정기(CJK 인식) 기준 — 하드코딩 공식이 아니다
        from antigravity_k.engine.tokenizer import TokenEstimator

        assert outcomes[0].tokens_out == TokenEstimator.estimate_text("보완된 최종 답변")
        # AgentTurnCompleted가 정확히 1회 발행됐는지 확인 — 다른 이벤트
        # (ToolLoopProtocolStats 등)와 무관하게 해당 인자로 호출된 경우만 센다.
        publish_calls = [c for c in event_bus.publish.call_args_list if c.args and c.args[0] == "AgentTurnCompleted"]
        assert len(publish_calls) == 1
        assert publish_calls[0].kwargs == {
            "user_message": "요청",
            "assistant_response": "보완된 최종 답변",
            "project_root": "/tmp/test",
        }
        _assert_mock_called_once(mock_orch, ("manager", "generate"))

    def test_quality_revision_retries_until_gate_budget_is_exhausted(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=True, feedback="중국어 혼입", score=0.3)
        first_revision = MagicMock(user_message="", should_retry=True, feedback="여전히 중국어 혼입", score=0.7)
        second_revision = MagicMock(user_message="", should_retry=False, feedback="", score=0.95)
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "max_retries"), 2)
        _set_mock_side_effect(
            mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, first_revision, second_revision]
        )
        _set_mock_side_effect(mock_orch, ("manager", "generate"), ["개선되었지만 중국어 포함", "최종 한국어 답변"])

        engine = _engine(mock_orch)
        chunks = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": "request"}],
                "coding",
                "draft",
                "request",
                "qwen3.6:latest",
            )
        )

        assert _mock_call_count(mock_orch, ("manager", "generate")) == 2
        assert cast(str, engine.last_output) == "최종 한국어 답변"
        assert any("최종 한국어 답변" in chunk for chunk in chunks)

    def test_quality_gate_receives_normalized_local_language_output(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=False, feedback="", score=1.0)
        _set_mock_return(mock_orch, ("ctx", "quality_gate", "evaluate"), initial)

        engine = _engine(mock_orch)
        _ = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": "request"}],
                "coding",
                "시간复杂도와 공간复杂도를 설명합니다.",
                "request",
            )
        )

        args, _ = _mock_call_args(mock_orch, ("ctx", "quality_gate", "evaluate"))
        assert args[2] == "시간복잡도와 공간복잡도를 설명합니다."
        assert cast(str, engine.last_output) == "시간복잡도와 공간복잡도를 설명합니다."

    def test_qwen_quality_revision_uses_measured_stable_sampling(self, mock_orch: MagicMock):
        _set_mock_return(mock_orch, ("manager", "generate"), "revised")

        _ = _quality_revision(
            _engine(mock_orch),
            "request",
            "draft",
            "feedback",
            "qwen3.6:latest",
        )

        _, kwargs = _mock_call_args(mock_orch, ("manager", "generate"))
        assert kwargs["temperature"] == 0.08
        assert kwargs["repeat_penalty"] == 1.15

    def test_quality_gate_keeps_original_grade_when_revision_scores_lower(self, mock_orch: MagicMock):
        initial = QualityScore(
            grade=QualityGrade.C,
            score=0.5,
            feedback="draft feedback",
            user_message="",
            should_retry=True,
            issues=["draft issue"],
        )
        revised = QualityScore(
            grade=QualityGrade.F,
            score=0.0,
            feedback="revision feedback",
            user_message="",
            should_retry=False,
            issues=["revision issue"],
        )
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter(["draft output"]))
        _set_mock_return(mock_orch, ("manager", "generate"), "revision output")
        outcomes: list[TaskOutcome] = []

        _ = list(
            (engine := ToolLoopEngine(mock_orch, outcome_recorder=_outcome_recorder(outcomes))).run_loop(
                [{"role": "user", "content": "request"}],
                "CODER",
                "chat",
            )
        )

        assert engine.last_output == "draft output"
        assert outcomes[0].error == "quality_gate_failed: draft feedback"

    def test_decomposition_recovery_used_when_revision_still_fails(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=True, feedback="워크플로 누락", score=0.3)
        revised = MagicMock(user_message="", should_retry=True, feedback="여전히 누락", score=0.2)
        decomposed = MagicMock(user_message="", should_retry=False, feedback="", score=0.9)
        mock_orch.config = {
            "amplification": {
                "task_decomposition": {"escalate_on_revision_failure": True},
            },
        }
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised, decomposed])
        _set_mock_return(mock_orch, ("manager", "generate"), "여전히 부족한 재생성")
        _set_mock_return(mock_orch, ("manager", "generate_decomposed"), "분해로 복구된 워크플로")

        engine = _engine(mock_orch)
        chunks = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": ""}],
                "long_horizon",
                "초안",
                "코드 마이그레이션 워크플로를 복구하세요",
                "qwen3.6:latest",
            )
        )

        _assert_mock_called_once(mock_orch, ("manager", "generate_decomposed"))
        assert cast(str, engine.last_output) == "분해로 복구된 워크플로"
        assert any("분해로 복구된 워크플로" in chunk for chunk in chunks)

    def test_decomposition_recovery_respects_config_toggle(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=True, feedback="워크플로 누락", score=0.3)
        revised = MagicMock(user_message="", should_retry=True, feedback="여전히 누락", score=0.2)
        setattr(
            mock_orch,
            "config",
            {
                "amplification": {
                    "task_decomposition": {"escalate_on_revision_failure": False},
                },
            },
        )
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("manager", "generate"), "여전히 부족한 재생성")

        engine = _engine(mock_orch)
        _ = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": ""}],
                "long_horizon",
                "초안",
                "코드 마이그레이션 워크플로를 복구하세요",
                "qwen3.6:latest",
            )
        )

        _assert_mock_not_called(mock_orch, ("manager", "generate_decomposed"))

    def test_decomposition_recovery_keeps_original_when_it_scores_lower(self, mock_orch: MagicMock):
        initial = MagicMock(user_message="", should_retry=True, feedback="워크플로 누락", score=0.3)
        revised = MagicMock(user_message="", should_retry=True, feedback="여전히 누락", score=0.2)
        decomposed = MagicMock(user_message="", should_retry=True, feedback="악화", score=0.1)
        setattr(
            mock_orch,
            "config",
            {
                "amplification": {
                    "task_decomposition": {"escalate_on_revision_failure": True},
                },
            },
        )
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised, decomposed])
        _set_mock_return(mock_orch, ("manager", "generate"), "여전히 부족한 재생성")
        _set_mock_return(mock_orch, ("manager", "generate_decomposed"), "더 나쁜 분해 결과")
        setattr(mock_orch, "_last_agent_output", "초안")

        engine = _engine(mock_orch)
        _ = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": ""}],
                "long_horizon",
                "초안",
                "코드 마이그레이션 워크플로를 복구하세요",
                "qwen3.6:latest",
            )
        )

        assert cast(str, engine.last_output) == "초안"

    def test_quality_revision_preserves_verified_tool_execution_evidence(self, mock_orch: MagicMock):
        # Given: a coding task whose tool loop produced real run_bash_command evidence.
        initial = MagicMock(user_message="", should_retry=True, feedback="구조 보완", score=0.5)
        revised = MagicMock(user_message="", should_retry=False, feedback="", score=0.9)
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("_get_model_for_role",), "qwen3.6:latest")
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter(["초안 5050"]))
        _set_mock_return(mock_orch, ("manager", "generate"), "보완된 답변")
        evidence_context = (
            "\n<tool_response>\n"
            '[TOOL_EVIDENCE] {"tool": "run_bash_command", "source": "python3 -c ..."}\n'
            "[UNTRUSTED_TOOL_RESULT]\nsum_to(100) = 5050\n[//UNTRUSTED_TOOL_RESULT]\n"
            "</tool_response>"
        )
        engine = _engine(mock_orch)

        # When: post-loop checks run with that execution evidence present.
        _ = list(
            _post_loop_checks(
                engine,
                [{"role": "user", "content": ""}],
                "code",
                "초안 5050",
                "sum_to를 실행해줘",
                "qwen3.6:latest",
                evidence_context=evidence_context,
            )
        )

        # Then: the revision prompt is constrained by the verified execution result so a
        # surface-only rewrite cannot drop or contradict the real tool output.
        _, generate_kwargs = _mock_call_args(mock_orch, ("manager", "generate"))
        revision_prompt = cast(str, generate_kwargs["prompt"])
        assert "5050" in revision_prompt
        assert "run_bash_command" in revision_prompt

    def test_decision_anchor_extract(self, mock_orch: MagicMock):
        _set_mock_return(
            mock_orch,
            ("ctx", "decision_anchor", "auto_extract"),
            {
                "decision": "refactor",
                "category": "code",
            },
        )
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        _assert_mock_called_once(mock_orch, ("ctx", "decision_anchor", "add"))

    def test_event_bus_published(self, mock_orch: MagicMock):
        with patch("antigravity_k.engine.event_bus.global_event_bus") as mock_bus:
            engine = _engine(mock_orch)
            messages = [{"role": "user", "content": "do something"}]
            _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
            _assert_mock_called_once_with(
                mock_bus,
                ("publish",),
                "AgentTurnCompleted",
                user_message="do something",
                assistant_response="output",
                project_root="/tmp/test",
            )

    def test_exception_in_reflect_does_not_block(self, mock_orch: MagicMock):
        _set_mock_side_effect(mock_orch, ("ctx", "cognitive_loop", "reflect"), RuntimeError("reflect fail"))
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))
        _assert_mock_called_once(mock_orch, ("ctx", "quality_gate", "evaluate"))

    def test_no_cognitive_loop_skips(self, mock_orch: MagicMock):
        setattr(_mock_path(mock_orch, ("ctx",)), "cognitive_loop", None)
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))

    def test_no_quality_gate_skips(self, mock_orch: MagicMock):
        setattr(_mock_path(mock_orch, ("ctx",)), "quality_gate", None)
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))

    def test_no_decision_anchor_skips(self, mock_orch: MagicMock):
        setattr(_mock_path(mock_orch, ("ctx",)), "decision_anchor", None)
        engine = _engine(mock_orch)
        messages = [{"role": "user", "content": "do something"}]
        _ = list(_post_loop_checks(engine, messages, "code", "output", "do something"))


# ─── Run Tool Task Async ────────────────────────────────────────


class TestToolLoopEngineRunToolTaskAsync:
    @pytest.mark.asyncio
    async def test_read_only_benchmark_blocks_mutating_tool(self, mock_orch: MagicMock, tmp_path: Path):
        from antigravity_k.engine.tool_call_parser import ToolCall

        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("benchmark-read-only", "benchmark prompt", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "benchmark-read-only",
            0,
            json.dumps({"benchmark_read_only": True}),
            "",
        )
        setattr(mock_orch, "task_execution_context", TaskExecutionContext("benchmark-read-only", store))
        tc = ToolCall(name="write_file", arguments={"path": "result.py", "content": "print('changed')"})

        _, pre_decision, _, tool_result, blocked = await _run_tool_task_async(_engine(mock_orch), tc)

        assert blocked is True
        assert pre_decision is None
        assert "BENCHMARK READ-ONLY" in str(tool_result)
        _assert_mock_not_called(mock_orch, ("ctx", "tool_guardrail", "before_call"))
        _assert_mock_awaited_not_called(mock_orch, ("ctx", "tool_executor", "execute_async"))

    @pytest.mark.asyncio
    async def test_guardrail_blocks_execution(self, mock_orch: MagicMock):
        from antigravity_k.engine.tool_call_parser import ToolCall

        pre_decision = MagicMock()
        pre_decision.allows_execution = False
        pre_decision.message = "Tool blocked by guardrail"
        pre_decision.action = "block"
        pre_decision.should_halt = False
        pre_decision.reason = "security"
        setattr(
            pre_decision,
            "to_dict",
            MagicMock(
                return_value={
                    "action": "block",
                    "message": "Tool blocked by guardrail",
                    "reason": "security",
                }
            ),
        )
        _set_mock_return(mock_orch, ("ctx", "tool_guardrail", "before_call"), pre_decision)

        tc = ToolCall(name="run_bash", arguments={"command": "ls"})
        engine = _engine(mock_orch)
        result = await _run_tool_task_async(engine, tc)
        _, _, _, synthetic, blocked = result
        assert blocked is True
        assert "blocked" in str(synthetic).lower()
        _assert_mock_awaited_not_called(mock_orch, ("ctx", "tool_executor", "execute_async"))

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_orch: MagicMock):
        from antigravity_k.engine.tool_call_parser import ToolCall

        _set_mock_return(mock_orch, ("ctx", "tool_executor", "execute_async"), "command output")
        tc = ToolCall(name="run_bash", arguments={"command": "ls"})
        engine = _engine(mock_orch)
        result = await _run_tool_task_async(engine, tc)
        _, _, _, tool_result, blocked = result
        assert blocked is False
        assert tool_result == "command output"
        _assert_mock_awaited_once_with(
            mock_orch,
            ("ctx", "tool_executor", "execute_async"),
            "run_bash",
            {"command": "ls"},
            guardrail_prechecked=True,
        )
        _assert_mock_called_once(mock_orch, ("ctx", "tool_guardrail", "before_call"))
        _assert_mock_called_once(mock_orch, ("ctx", "tool_guardrail", "after_call"))

    @pytest.mark.asyncio
    async def test_cognitive_verify_error_handled(self, mock_orch: MagicMock):
        from antigravity_k.engine.tool_call_parser import ToolCall

        _set_mock_side_effect(mock_orch, ("ctx", "cognitive_loop", "verify_tool_result"), ValueError("verify fail"))
        tc = ToolCall(name="search", arguments={"query": "test"})
        engine = _engine(mock_orch)
        result = await _run_tool_task_async(engine, tc)
        _, _, _, tool_result, blocked = result
        assert blocked is False
        assert tool_result is not None

    @pytest.mark.asyncio
    async def test_event_bus_exception_handled(self, mock_orch: MagicMock):
        from antigravity_k.engine.tool_call_parser import ToolCall

        with patch("antigravity_k.engine.event_bus.global_event_bus") as mock_bus:
            setattr(mock_bus, "publish", MagicMock(side_effect=RuntimeError("bus down")))
            tc = ToolCall(name="bash", arguments={"cmd": "ls"})
            engine = _engine(mock_orch)
            result = await _run_tool_task_async(engine, tc)
            _, _, _, tool_result, _ = result
            assert tool_result is not None


# ─── Run Loop ───────────────────────────────────────────────────


class TestToolLoopEngineRunLoop:
    """run_loop — stream_generate mock, DAG execution batching, error handling."""

    mock_orch: MagicMock = MagicMock()

    @pytest.fixture(autouse=True)
    def _setup_run_loop_mocks(self, mock_orch: MagicMock) -> None:
        """Common mocks for run_loop: prepare_agent_prompt, manager, combo check."""
        self.mock_orch = mock_orch
        # NOTE: get_combo must return None (not False) — run_loop checks
        # `is not None` to detect combo mode. False is not None = True,
        # which incorrectly skips the is_loaded check!
        _set_mock_return(mock_orch, ("manager", "router", "get_combo"), None)
        _set_mock_return(mock_orch, ("manager", "is_loaded"), True)
        # Don't set _capacity_checkpoint — MagicMock auto-creates it,
        # and its check_step_budget().action returns a MagicMock that won't
        # match any CapacityAction enum, making capacity check a no-op.

    def _orch(self) -> MagicMock:
        return cast(MagicMock, self.mock_orch)

    def _run(
        self,
        messages: list[dict[str, str]] | None = None,
        delegate_to: str = "CODER",
        task_type: str = "code",
        max_steps: int = 5,
        target_model: str | None = None,
    ) -> list[str]:
        """Helper: create engine and collect run_loop output."""
        orchestrator = self._orch()
        engine = _engine(orchestrator)
        msgs = messages or [{"role": "user", "content": "test task"}]
        return list(_run_loop(engine, msgs, delegate_to, task_type, max_steps, target_model))

    def test_model_not_loaded(self):
        """is_loaded=False and not a combo -> model not loaded error."""
        orchestrator = self._orch()
        _set_mock_return(orchestrator, ("manager", "router", "get_combo"), None)
        _set_mock_return(orchestrator, ("manager", "is_loaded"), False)
        results = self._run()
        assert any("모델" in r and "로드되지 않았" in r for r in results)

    def test_combo_skips_loaded_check(self):
        """combo name (coding-swarm 등)은 is_loaded 체크를 건너뜀."""
        orchestrator = self._orch()
        _set_mock_return(orchestrator, ("manager", "router", "get_combo"), "coding-swarm")
        _set_mock_return(orchestrator, ("manager", "is_loaded"), False)
        _set_mock_return(orchestrator, ("manager", "stream_generate"), iter([]))
        results = self._run()
        assert all("로드되지 않았" not in r for r in results)

    def test_qwen_agent_stream_uses_stable_local_sampling(self):
        """qwen3 도구 에이전트 경로도 실측된 안정 샘플링 파라미터를 사용한다."""
        orchestrator = self._orch()
        _set_mock_return(orchestrator, ("manager", "stream_generate"), iter(["completed"]))

        _ = self._run(target_model="qwen3.6:latest")

        _, kwargs = _mock_call_args(orchestrator, ("manager", "stream_generate"))
        assert kwargs["temperature"] == 0.2
        assert kwargs["repeat_penalty"] == 1.1
        assert kwargs["min_p"] == 0.0

    def test_capacity_halt(self):
        """CapacityAction.HALT -> capacity limit and return."""
        from antigravity_k.engine.capacity_flow import CapacityAction

        mock_cap = MagicMock()
        _set_mock_attr(mock_cap, ("check_step_budget", "return_value", "action"), CapacityAction.HALT)
        setattr(self._orch(), "_capacity_checkpoint", mock_cap)
        results = self._run()
        assert any("Capacity Limit" in r for r in results)

    def test_capacity_warn(self):
        """CapacityAction.WARN -> warning yield, then continues to stream."""
        from antigravity_k.engine.capacity_flow import CapacityAction

        mock_cap = MagicMock()
        _set_mock_attr(mock_cap, ("check_step_budget", "return_value", "action"), CapacityAction.WARN)
        orchestrator = self._orch()
        setattr(orchestrator, "_capacity_checkpoint", mock_cap)
        _set_mock_return(orchestrator, ("manager", "stream_generate"), iter([]))
        results = self._run()
        assert any("Capacity Warning" in r for r in results)

    def test_text_only_no_tool_calls(self):
        """stream yields text only, no tool calls -> breaks and does post_loop."""
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["Hello ", "world"]))
        results = self._run()
        assert any("Hello" in r for r in results)
        assert any("world" in r for r in results)

    def test_tool_call_success(self):
        """stream yields a tool call -> executes tool -> formats result."""
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter([tool_xml]))
        results = self._run()
        result_text = " ".join(results)
        assert "tool" in result_text.lower() or "실행" in result_text
        assert "run_bash" in result_text or "Executing" in result_text

    def test_dag_execution_batching(self):
        """waitForPreviousTools -> multiple execution batches."""
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "search", "arguments": {"query": "test"}}\n'
            "</tool_call>\n</action_call>\n"
            "<action_call>\n<tool_call>\n"
            '{"name": "write_file", "arguments": {"path": "f.txt", "waitForPreviousTools": true}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter([tool_xml]))
        results = self._run()
        result_text = " ".join(results)
        # Should have executed both tools
        assert "search" in result_text or "Executing" in result_text
        assert len(results) > 3

    def test_stream_error_retryable(self):
        """stream raises exception classified as retryable -> retry."""

        class RetryableError(Exception):
            pass

        def mock_classify(e: Exception, **kw: object):
            from antigravity_k.engine.error_classifier import ClassifiedError, FailoverReason

            _ = (e, kw)
            return ClassifiedError(reason=FailoverReason.timeout, retryable=True)

        with patch("antigravity_k.engine.tool_loop.classify_api_error", side_effect=mock_classify):
            # stream_generate returns a RaisingIter — exception is raised
            # INSIDE the for-loop try/except, not during the call (which
            # is outside the try block)
            _set_mock_return(
                self._orch(),
                ("manager", "stream_generate"),
                _RaisingIter(
                    RetryableError("timeout"),
                ),
            )
            results = self._run(max_steps=3)
            assert any("재시도" in r or "일시적" in r for r in results)

    def test_stream_error_non_retryable(self):
        """stream raises non-retryable exception -> error message and return."""

        class FatalError(Exception):
            pass

        def mock_classify(e: Exception, **kw: object):
            from antigravity_k.engine.error_classifier import ClassifiedError, FailoverReason

            _ = (e, kw)
            return ClassifiedError(reason=FailoverReason.format_error, retryable=False)

        with patch("antigravity_k.engine.tool_loop.classify_api_error", side_effect=mock_classify):
            _set_mock_return(
                self._orch(),
                ("manager", "stream_generate"),
                _RaisingIter(
                    FatalError("bad request"),
                ),
            )
            results = self._run()
            assert any("에러" in r or "오류" in r for r in results)

    def test_stream_error_compress(self):
        """should_compress=True -> compress context and continue."""

        class ContextOverflow(Exception):
            pass

        def mock_classify(e: Exception, **kw: object):
            from antigravity_k.engine.error_classifier import ClassifiedError, FailoverReason

            _ = (e, kw)
            return ClassifiedError(reason=FailoverReason.context_overflow, retryable=True, should_compress=True)

        mock_shaper = MagicMock()
        _set_mock_return(mock_shaper, ("shape",), [{"role": "user", "content": "compressed"}])
        _set_mock_attr(self._orch(), ("context_shaper",), mock_shaper)

        # stream_generate returns RaisingIter on 1st call, normal iter on 2nd
        _set_mock_side_effect(
            self._orch(),
            ("manager", "stream_generate"),
            [
                _RaisingIter(ContextOverflow("context too long")),
                iter(["after compress"]),
            ],
        )

        with patch("antigravity_k.engine.tool_loop.classify_api_error", side_effect=mock_classify):
            results = self._run(max_steps=3)
            assert any("압축" in r for r in results)

    def test_tool_blocked_by_guardrail(self):
        """pre_decision.allows_execution=False -> blocked tool message."""
        pre_decision = MagicMock()
        pre_decision.allows_execution = False
        pre_decision.message = "Not allowed"
        pre_decision.action = "block"
        pre_decision.should_halt = True
        pre_decision.reason = "policy"
        setattr(
            pre_decision,
            "to_dict",
            MagicMock(
                return_value={
                    "action": "block",
                    "message": "Not allowed",
                    "reason": "policy",
                }
            ),
        )

        mock_orch = self._orch()
        _set_mock_return(mock_orch, ("ctx", "tool_guardrail", "before_call"), pre_decision)

        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter([tool_xml]))
        _set_mock_return(mock_orch, ("ctx", "tool_executor", "execute_async"), "result")

        results = self._run()
        result_text = " ".join(results)
        assert "Tool Blocked" in result_text or "Guardrail" in result_text

    def test_approval_required_break(self):
        """tool_result contains APPROVAL REQUIRED -> breaks loop."""
        mock_orch = self._orch()
        _set_mock_return(mock_orch, ("ctx", "tool_executor", "execute_async"), "[APPROVAL REQUIRED] Please confirm")

        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "write_file", "arguments": {"path": "test.txt"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter([tool_xml]))
        results = self._run()
        assert any("APPROVAL REQUIRED" in r for r in results)

    def test_step_limit_reached(self):
        """max_steps reached with tool calls -> step limit message."""
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter([tool_xml]))
        results = self._run(max_steps=1)
        assert any("Step Limit" in r for r in results)

    def test_excessive_max_steps_is_bounded(self):
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )

        def stream_generate(**kwargs: object) -> Iterator[str]:
            _ = kwargs
            return iter([tool_xml])

        _set_mock_side_effect(self._orch(), ("manager", "stream_generate"), stream_generate)
        _set_mock_return(self._orch(), ("ctx", "tool_executor", "execute_async"), "result")

        results = self._run(max_steps=51)

        assert any("최대 도구 호출 횟수(50)" in r for r in results)
        assert _mock_call_count(self._orch(), ("manager", "stream_generate")) == 50

    def test_non_positive_max_steps_still_runs_once(self):
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))

        _ = self._run(max_steps=0)

        assert _mock_call_count(self._orch(), ("manager", "stream_generate")) == 1

    def test_empty_messages_post_loop(self):
        """messages가 비어 있으면 post_loop는 user_task=''로 실행."""
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["output"]))
        results = self._run(messages=[])
        assert isinstance(results, list)

    def test_quality_gate_uses_original_request_when_prompt_was_refined(self):
        """state graph이 refined+RAG 프롬프트로 메시지를 바꿔도 원요청으로 평가한다."""
        augmented_message = {
            "role": "user",
            "content": "architecture context: [web evidence] Python 3.13 ...",
        }
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))

        _ = list(
            _engine(self._orch()).run_loop(
                [augmented_message],
                "CODER",
                "coding",
                evaluation_user_task="Python 3.13 출시일을 알려줘",
            )
        )

        args, _ = _mock_call_args(self._orch(), ("ctx", "quality_gate", "evaluate"))
        assert args[1] == "Python 3.13 출시일을 알려줘"

    def test_records_successful_text_task_outcome(self):
        outcomes: list[TaskOutcome] = []
        _set_mock_attr(self._orch(), ("task_id",), "loop-001")
        _set_mock_attr(self._orch(), ("expected_tools",), ())
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))
        engine = _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes))

        _ = list(engine.run_loop([{"role": "user", "content": "finish"}], "CODER", "code"))

        assert len(outcomes) == 1
        assert outcomes[0].case_id == "loop-001"
        assert outcomes[0].success is True
        assert outcomes[0].completion_reason == "done"

    def test_expected_tools_defaults_when_orchestrator_contract_is_absent(self):
        engine = ToolLoopEngine(SimpleNamespace(ctx=SimpleNamespace()))

        assert _expected_tools(engine) == ()

    def test_records_used_tools_and_expected_tools(self):
        outcomes: list[TaskOutcome] = []
        _set_mock_attr(self._orch(), ("task_id",), "loop-002")
        _set_mock_attr(self._orch(), ("expected_tools",), ("run_bash",))
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter([tool_xml]))
        engine = _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes))

        _ = list(engine.run_loop([{"role": "user", "content": "inspect"}], "CODER", "code"))

        assert len(outcomes) == 1
        assert outcomes[0].used_tools == ("run_bash",)
        assert outcomes[0].tool_accuracy == 1.0

    def test_web_search_answer_is_citation_revised_before_completion(self):
        # Given: a web-search tool result and an uncited final model response.
        primary_url = "https://docs.python.org/3/whatsnew/3.13.html"
        citation = "python-docs"
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "web_search", "arguments": {"query": "Python 3.13 JIT"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        tool_result = (
            f"1. [citation:{citation}] **Python 3.13 release notes**\n"
            "   [untrusted_web_content]\n"
            "Python 3.13 introduces an experimental JIT compiler.\n"
            "   [/untrusted_web_content]\n"
            f"   🔗 {primary_url}\n"
        )
        _set_mock_attr(self._orch(), ("expected_tools",), ("web_search",))
        _set_mock_return(self._orch(), ("ctx", "tool_executor", "execute_async"), tool_result)
        _set_mock_side_effect(
            self._orch(),
            ("manager", "stream_generate"),
            [
                iter([tool_xml]),
                iter(["Python 3.13 offers a JIT compiler."]),
            ],
        )
        _set_mock_return(
            self._orch(),
            ("manager", "generate"),
            f"Python 3.13 introduces an experimental JIT compiler. [citation:{citation}]",
        )
        outcomes: list[TaskOutcome] = []

        # When: the loop executes the search and evaluates its final answer.
        engine = _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes))
        outputs = list(
            engine.run_loop(
                [{"role": "user", "content": "Python 3.13 JIT 기능을 알려줘"}],
                "SELF",
                "chat",
            ),
        )

        # Then: the corrected, cited answer is the completed task output.
        assert outcomes[0].success is True
        assert outcomes[0].completion_reason == "done"
        last_output = engine.last_output
        assert str(last_output) == (
            f"Python 3.13 introduces an experimental JIT compiler. [citation:{citation}]\n\n"
            f"출처: [docs.python.org](<{primary_url}>)"
        )
        assert any("Citation Revision" in output for output in outputs)

    def test_reads_expected_tools_from_durable_execution_context(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("tool-contract", "read README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "tool-contract",
            0,
            '{"expected_tools": ["read_file"]}',
            "",
        )
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("tool-contract", store))

        expected_tools = _expected_tools(_engine(self._orch()))

        assert expected_tools == ("read_file",)

    def test_missing_required_tool_marks_durable_task_failed(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("required-tool", "read README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "required-tool",
            0,
            '{"expected_tools": ["read_file"]}',
            "",
        )
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("required-tool", store))
        _set_mock_attr(self._orch(), ("ctx", "quality_gate"), None)
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["ungrounded answer"]))

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "read README"}],
                "SELF",
                "chat",
            )
        )

        record = store.get_task("required-tool")
        assert record is not None
        assert record["status"] == "failed"
        assert record["error"] == "required_tools_missing: read_file"

    def test_omits_satisfied_native_tools_from_follow_up_turn(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("read-once", "read README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "read-once",
            0,
            '{"expected_tools": ["read_file"]}',
            "",
        )
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("read-once", store))
        _set_mock_attr(self._orch(), ("config",), {"tool_loop": {"native_function_calling": True}})
        profile = MagicMock()
        profile.provider = "ollama"
        _set_mock_return(self._orch(), ("manager", "_registry", "get_model"), profile)
        _set_mock_return(self._orch(), ("manager", "provider_capability"), {"native_tool_calling": "supported"})
        _set_mock_return(self._orch(), ("tool_registry", "to_openai_schemas"), [{"name": "read_file"}])
        _set_mock_return(self._orch(), ("ctx", "tool_executor", "execute_async"), "README contents")
        _set_mock_attr(self._orch(), ("ctx", "quality_gate"), None)
        tool_call = '<tool_call>\n{"name": "read_file", "arguments": {"file_path": "README.md"}}\n</tool_call>\n'
        _set_mock_side_effect(
            self._orch(),
            ("manager", "stream_generate"),
            [iter([tool_call]), iter(["grounded summary"])],
        )

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "read README"}],
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
            )
        )

        first_kwargs, second_kwargs = _mock_call_kwargs_list(self._orch(), ("manager", "stream_generate"))
        assert first_kwargs["tools"] == [{"name": "read_file"}]
        assert "tools" not in second_kwargs

    def test_recovers_a_qwen_scratchpad_action_for_one_required_tool(self, tmp_path: Path):
        # Given: Qwen plans the sole required read instead of emitting its tool-call tag.
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("qwen-plan", "read README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint("qwen-plan", 0, '{"expected_tools": ["read_file"]}', "")
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("qwen-plan", store))
        _set_mock_attr(self._orch(), ("ctx", "quality_gate"), None)
        _set_mock_return(self._orch(), ("ctx", "tool_executor", "execute_async"), "README contents")
        _set_mock_side_effect(
            self._orch(),
            ("manager", "stream_generate"),
            [
                iter(
                    [
                        "<scratch_pad>\nActions: Call read_file with file_path='README.md'.\n</scratch_pad>",
                    ],
                ),
                iter(["grounded summary"]),
            ],
        )
        # When: the required-tool loop processes Qwen's completed planning turn.
        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "read README"}],
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
            )
        )

        # Then: it executes the planned read and completes with the grounded follow-up.
        record = store.get_task("qwen-plan")
        assert record is not None
        assert record["status"] == "done"
        _assert_mock_awaited_once_with(
            self._orch(),
            ("ctx", "tool_executor", "execute_async"),
            "read_file",
            {"file_path": "README.md"},
            guardrail_prechecked=True,
        )

    def test_recovers_each_qwen_scratchpad_action_in_a_multistep_contract(self, tmp_path: Path):
        # Given: Qwen plans each of two required tools in separate scratch-pad turns.
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("qwen-multistep", "inspect README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "qwen-multistep",
            0,
            '{"expected_tools": ["read_file", "grep_search"]}',
            "",
        )
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("qwen-multistep", store))
        _set_mock_attr(self._orch(), ("ctx", "quality_gate"), None)
        _set_mock_side_effect(
            self._orch(),
            ("ctx", "tool_executor", "execute_async"),
            ["README contents", "matching defaults"],
        )
        _set_mock_side_effect(
            self._orch(),
            ("manager", "stream_generate"),
            [
                iter(["<scratch_pad>\nActions: Call read_file with file_path='README.md'.\n</scratch_pad>"]),
                iter(["<scratch_pad>\nActions: Call grep_search with query='defaults'.\n</scratch_pad>"]),
                iter(["grounded summary"]),
            ],
        )

        # When: the tool loop completes the sequential Qwen planning turns.
        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "inspect README"}],
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
            )
        )

        # Then: both contract tools execute once before the final grounded answer.
        record = store.get_task("qwen-multistep")
        assert record is not None
        assert record["status"] == "done"
        assert _mock_await_args_list(self._orch(), ("ctx", "tool_executor", "execute_async")) == [
            (("read_file", {"file_path": "README.md"}), {"guardrail_prechecked": True}),
            (("grep_search", {"query": "defaults"}), {"guardrail_prechecked": True}),
        ]

    def test_resume_uses_checkpointed_tool_progress_and_evidence(self, tmp_path: Path):
        # Given: a paused task whose required file read already completed before interruption.
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("resumed-read", "read README", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "resumed-read",
            4,
            json.dumps(
                {
                    "expected_tools": ["read_file"],
                    "tool_loop": {
                        "used_tools": ["read_file"],
                        "tool_evidence_context": '{"source": "README.md", "content": "local evidence"}',
                    },
                },
            ),
            "partial output",
        )
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("resumed-read", store))
        _set_mock_attr(self._orch(), ("ctx", "quality_gate"), None)
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["resumed summary"]))

        # When: the durable task resumes its tool loop.
        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "read README"}],
                "SELF",
                "chat",
            )
        )

        # Then: the existing tool completion satisfies the contract without a duplicate execution.
        record = store.get_task("resumed-read")
        assert record is not None
        assert record["status"] == "done"
        _assert_mock_not_called(self._orch(), ("ctx", "tool_executor", "execute_async"))

    def test_records_step_limit_as_unsuccessful(self):
        outcomes: list[TaskOutcome] = []
        tool_xml = (
            "<action_call>\n<tool_call>\n"
            '{"name": "run_bash", "arguments": {"command": "ls"}}\n'
            "</tool_call>\n</action_call>\n"
        )
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter([tool_xml]))
        engine = _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes))

        _ = list(engine.run_loop([{"role": "user", "content": "inspect"}], "CODER", "code", max_steps=1))

        assert len(outcomes) == 1
        assert outcomes[0].success is False
        assert outcomes[0].completion_reason == "step_limit"

    def test_quality_gate_failure_marks_durable_task_failed(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("quality-failed", "write code", "pending", "2026-01-01T00:00:00")
        _set_mock_attr(self._orch(), ("task_execution_context",), TaskExecutionContext("quality-failed", store))
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["invalid output"]))
        _set_mock_return(
            self._orch(),
            ("ctx", "quality_gate", "evaluate"),
            QualityScore(
                grade=QualityGrade.F,
                score=0.0,
                feedback="[QUALITY GATE] required implementation is missing",
                user_message="",
                should_retry=False,
                issues=["incomplete"],
            ),
        )
        outcomes: list[TaskOutcome] = []

        _ = list(
            _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes)).run_loop(
                [{"role": "user", "content": "write code"}],
                "CODER",
                "code",
            )
        )

        record = store.get_task("quality-failed")
        assert record is not None
        assert record["status"] == "failed"
        assert record["error"] == "quality_gate_failed: [QUALITY GATE] required implementation is missing"
        assert outcomes[0].success is False
        assert outcomes[0].completion_reason == "quality_gate_failed"

    def test_persists_approval_wait_with_tool_step_checkpoint(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("loop-durable", "write a file", "pending", "2026-01-01T00:00:00")
        self._orch().task_execution_context = TaskExecutionContext("loop-durable", store)
        _set_mock_return(
            self._orch(),
            ("ctx", "tool_executor", "execute_async"),
            "[APPROVAL REQUIRED] confirm write",
        )
        _set_mock_return(
            self._orch(),
            ("manager", "stream_generate"),
            iter(
                [
                    "<action_call>\n<tool_call>\n"
                    + '{"name": "write_file", "arguments": {"path": "report.md"}}\n'
                    + "</tool_call>\n</action_call>\n",
                ],
            ),
        )

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "write a file"}],
                "CODER",
                "code",
                target_model="qwen3.8",
            ),
        )

        record = store.get_task("loop-durable")
        checkpoint = store.get_last_checkpoint("loop-durable")
        assert record is not None
        assert record["status"] == "paused"
        assert checkpoint is not None
        assert checkpoint["step"] == 1
        assert '"completion_reason": "approval_required"' in checkpoint["context_json"]
        assert '"write_file"' in checkpoint["context_json"]
        assert '"tool_evidence_context"' in checkpoint["context_json"]
        snapshot = load_task_context_snapshot(store, "loop-durable")
        assert snapshot is not None
        assert snapshot.target_model == "qwen3.8"
        assert any(message.content == "test" for message in snapshot.messages)
        assert '"working_memory"' in checkpoint["context_json"]

    def test_read_only_benchmark_defers_completion_to_task_runner(self, tmp_path: Path):
        store = TaskStateStore(str(tmp_path / "tasks.db"))
        _ = store.create_task("benchmark-deferred", "benchmark prompt", "pending", "2026-01-01T00:00:00")
        store.save_checkpoint(
            "benchmark-deferred",
            0,
            '{"benchmark_read_only": true}',
            "",
        )
        self._orch().task_execution_context = TaskExecutionContext("benchmark-deferred", store)
        _set_mock_return(
            self._orch(),
            ("manager", "stream_generate"),
            iter(["def fibonacci(n: int): return n  # O(1), raise ValueError"]),
        )
        outcomes: list[TaskOutcome] = []

        _ = list(
            _engine(self._orch(), outcome_recorder=_outcome_recorder(outcomes)).run_loop(
                [{"role": "user", "content": "write fibonacci"}],
                "CODER",
                "code",
            )
        )

        record = store.get_task("benchmark-deferred")
        assert record is not None
        assert record["status"] == "running"
        assert outcomes == []

    def test_explicit_target_model_overrides_delegate_role(self):
        _set_mock_return(self._orch(), ("_get_model_for_role",), "role-default")
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "complete this"}],
                "CODER",
                "code",
                target_model="qwen3.6:latest",
            )
        )

        _assert_mock_called_once_with(self._orch(), ("manager", "is_loaded"), "qwen3.6:latest")
        _, kwargs = _mock_call_args(self._orch(), ("manager", "stream_generate"))
        assert kwargs["target"] == "qwen3.6:latest"

    def test_quality_gate_uses_latest_user_message_when_execution_context_follows(self):
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))

        _ = list(
            _engine(self._orch()).run_loop(
                [
                    {"role": "user", "content": "user request"},
                    {"role": "system", "content": "Task execution context: {}"},
                ],
                "CODER",
                "chat",
            )
        )

        args, _ = _mock_call_args(self._orch(), ("ctx", "quality_gate", "evaluate"))
        assert args[1] == "user request"

    def test_direct_response_skips_agent_prompt_and_native_tool_schemas(self):
        self._orch().config = {"tool_loop": {"native_function_calling": True}}
        _set_mock_return(self._orch(), ("manager", "generate"), "completed")

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "answer only"}],
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
                direct_response=True,
            )
        )

        _assert_mock_not_called(self._orch(), ("_prepare_agent_prompt",))
        _assert_mock_not_called(self._orch(), ("manager", "stream_generate"))
        _, kwargs = _mock_call_args(self._orch(), ("manager", "generate"))
        assert kwargs["temperature"] == 0.2
        assert kwargs["repeat_penalty"] == 1.1

    def test_direct_response_uses_model_aware_context_shaper(self, tmp_path: Path):
        from antigravity_k.engine.context_shaper import ContextShaper

        shaper = ContextShaper(storage_dir=str(tmp_path / "context"))
        shaper.shape_for_model = MagicMock(
            return_value=[{"role": "user", "content": "condensed request"}],
        )
        self._orch().context_shaper = shaper
        self._orch().config = {"models": {"reasoning": [{"name": "qwen3.8:27b"}]}}
        _set_mock_return(self._orch(), ("manager", "generate"), "completed")

        _ = list(
            _engine(self._orch()).run_loop(
                [{"role": "user", "content": "very large request"}],
                "SELF",
                "chat",
                target_model="qwen3.8:27b",
                direct_response=True,
            ),
        )

        shaper.shape_for_model.assert_called_once()
        assert shaper.shape_for_model.call_args.args[2] == "qwen3.8:27b"
        _, kwargs = _mock_call_args(self._orch(), ("manager", "generate"))
        assert "condensed request" in str(kwargs["prompt"])

    def test_direct_response_prompt_includes_structured_memory_context(self):
        # Given: direct mode receives one authoritative memory system record.
        _set_mock_return(self._orch(), ("manager", "generate"), "SQLite")
        messages = [
            {
                "role": "system",
                "content": (
                    "[Recalled Memory]\n[resolved:project:decision:database source=project scope=project] sqlite"
                ),
            },
            {"role": "user", "content": "데이터베이스 이름만 답해줘"},
        ]

        # When: ToolLoop generates a tool-free direct answer.
        _ = list(
            _engine(self._orch()).run_loop(
                messages,
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
                direct_response=True,
            ),
        )

        # Then: the machine-readable memory marker reaches the model prompt.
        _, kwargs = _mock_call_args(self._orch(), ("manager", "generate"))
        prompt = str(kwargs["prompt"])
        assert "[resolved:project:decision:database source=project scope=project] sqlite" in prompt

    def test_verified_authoritative_memory_answer_skips_prose_revision(self):
        # Given: direct mode returns the exact value from an authoritative memory marker.
        _set_mock_return(self._orch(), ("manager", "generate"), "sqlite")
        _set_mock_return(
            self._orch(),
            ("ctx", "quality_gate", "evaluate"),
            QualityScore(
                grade=QualityGrade.F,
                score=0.1,
                feedback="too short",
                user_message="retry",
                should_retry=True,
                issues=["short"],
            ),
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "[Recalled Memory]\n[resolved:project:decision:database source=project scope=project] sqlite"
                ),
            },
            {"role": "user", "content": "데이터베이스 이름만 답해줘"},
        ]

        # When: the tool-free direct response completes.
        engine = _engine(self._orch())
        output = "".join(
            engine.run_loop(
                messages,
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
                direct_response=True,
            ),
        )

        # Then: generic prose scoring cannot overwrite the verified short answer.
        assert output == "sqlite"
        assert engine.last_output == "sqlite"
        _assert_mock_not_called(self._orch(), ("ctx", "quality_gate", "evaluate"))
        _assert_mock_called_once(self._orch(), ("manager", "generate"))

    def test_contradictory_memory_answer_still_runs_quality_gate(self):
        # Given: direct mode returns a negated sentence containing the authoritative value.
        _set_mock_return(self._orch(), ("manager", "generate"), "not sqlite")
        messages = [
            {
                "role": "system",
                "content": (
                    "[Recalled Memory]\n[resolved:project:decision:database source=project scope=project] sqlite"
                ),
            },
            {"role": "user", "content": "데이터베이스 이름만 답해줘"},
        ]

        # When: the tool-free response completes with the contradictory text.
        _ = list(
            _engine(self._orch()).run_loop(
                messages,
                "SELF",
                "chat",
                target_model="qwen3.6:latest",
                direct_response=True,
            ),
        )

        # Then: substring overlap alone cannot bypass normal quality evaluation.
        _assert_mock_called_once(self._orch(), ("ctx", "quality_gate", "evaluate"))

    def test_recorder_failure_does_not_fail_tool_loop(self):
        recorder = MagicMock(side_effect=RuntimeError("metrics unavailable"))
        _set_mock_return(self._orch(), ("manager", "stream_generate"), iter(["completed"]))
        engine = ToolLoopEngine(self._orch(), outcome_recorder=recorder)

        results = list(engine.run_loop([{"role": "user", "content": "finish"}], "CODER", "code"))

        assert any("completed" in result for result in results)
        recorder.assert_called_once()


class TestToolLoopEngineContextCompression:
    """_maybe_compress_context — ContextCompressor 자동 트리거 가드."""

    def _long_messages(self, count: int = 20) -> list[dict[str, str]]:
        return [{"role": "system", "content": "system prompt"}] + [
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"long message {i}: " + "내용 " * 50,
            }
            for i in range(count)
        ]

    def test_compresses_when_over_budget(self, mock_orch: MagicMock):
        from antigravity_k.engine.context_compressor import ContextCompressor

        compressor = ContextCompressor(token_limit=500, keep_last_n=3)
        _set_mock_return(mock_orch, ("context_compressor_for",), compressor)
        _set_mock_return(mock_orch, ("_rebuild_prompt",), "rebuilt-prompt")
        engine = _engine(mock_orch)

        shaped, prompt, usage_before, usage_after = _maybe_compress_context(
            engine,
            self._long_messages(),
            "orig-prompt",
            "qwen3.6:latest",
            "code",
            "sys",
            "tools",
            "skills",
        )

        assert usage_before is not None
        assert usage_after is not None
        assert usage_after < usage_before
        assert prompt == "rebuilt-prompt"
        assert shaped != self._long_messages()
        assert shaped[0]["role"] == "system"  # 시스템 메시지 항상 보존

    def test_reinjects_relevant_artifact_after_compression(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)
        raw_result = "header\n" + ("x" * 8_000) + "\nagent_models:\n  default: qwen3.6:latest\n" + ("y" * 8_000)
        formatted = _format_tool_response(
            engine,
            ToolCall(name="read_file", arguments={"file_path": "config.yaml"}),
            raw_result,
        )
        compressor = MagicMock()
        _set_mock_return(compressor, ("needs_compression",), True)
        _set_mock_side_effect(compressor, ("usage_percent",), [90.0, 20.0])
        _set_mock_return(
            compressor,
            ("adaptive_compress",),
            [{"role": "user", "content": "continue"}],
        )
        _set_mock_return(mock_orch, ("context_compressor_for",), compressor)
        _set_mock_return(mock_orch, ("_rebuild_prompt",), "rebuilt-prompt")

        shaped, prompt, usage_before, usage_after = _maybe_compress_context(
            engine,
            [
                {"role": "user", "content": "inspect agent_models routing"},
                {"role": "assistant", "content": formatted},
            ],
            "orig-prompt",
            "qwen3.6:latest",
            "code",
            "sys",
            "tools",
            "skills",
            focus_terms=("agent_models",),
        )

        assert shaped == [{"role": "user", "content": "continue"}]
        assert prompt.startswith("rebuilt-prompt\n[CONTEXT_ARTIFACT_RECALL]")
        assert '"ref_id":"artifact-' in prompt
        assert "agent_models" in prompt
        assert usage_before == 90.0
        assert usage_after == 20.0

    def test_noop_within_budget(self, mock_orch: MagicMock):
        from antigravity_k.engine.context_compressor import ContextCompressor

        compressor = ContextCompressor(token_limit=5000, keep_last_n=3)
        _set_mock_return(mock_orch, ("context_compressor_for",), compressor)
        engine = _engine(mock_orch)

        messages = [{"role": "user", "content": "short"}]
        shaped, prompt, usage_before, usage_after = _maybe_compress_context(
            engine, messages, "orig-prompt", "qwen3.6:latest", "code", "sys", "tools", "skills"
        )

        assert usage_before is None and usage_after is None
        assert shaped == messages
        assert prompt == "orig-prompt"

    def test_mock_compressor_skipped(self, mock_orch: MagicMock):
        engine = _engine(mock_orch)  # context_compressor_for → MagicMock

        messages = [{"role": "user", "content": "x"}]
        shaped, prompt, usage_before, _usage_after = _maybe_compress_context(
            engine, messages, "p", "qwen3.6:latest", "code", "s", "t", "k"
        )

        assert usage_before is None
        assert shaped == messages
        assert prompt == "p"

    def test_none_compressor_skipped(self, mock_orch: MagicMock):
        _set_mock_return(mock_orch, ("context_compressor_for",), None)
        engine = _engine(mock_orch)

        messages = [{"role": "user", "content": "x"}]
        shaped, prompt, usage_before, _usage_after = _maybe_compress_context(
            engine, messages, "p", "qwen3.6:latest", "code", "s", "t", "k"
        )

        assert usage_before is None
        assert shaped == messages
        assert prompt == "p"

    def test_checkpoint_context_is_bounded_for_long_sessions(self, mock_orch: MagicMock):
        messages = [{"role": "user", "content": f"turn-{index}"} for index in range(300)]

        engine = _engine(mock_orch)
        _refresh_checkpoint_context(engine, messages)

        checkpoint_messages = cast(list[dict[str, str]], getattr(engine, "_checkpoint_messages"))
        assert len(checkpoint_messages) == 256
        assert checkpoint_messages[-1]["content"] == "turn-299"


class TestBatchDedup:
    def test_duplicate_calls_in_batch_execute_once(self, mock_orch: MagicMock) -> None:
        """동일 호출(이름+인자)이 한 배치에 여러 개면 1회만 실행하고 결과를 공유한다."""
        import asyncio as _asyncio

        calls: list[str] = []

        async def fake_execute(tool_name: str, args: object, *, guardrail_prechecked: bool = False) -> str:
            _ = args, guardrail_prechecked
            calls.append(tool_name)
            return f"result for {tool_name}"

        _set_mock_side_effect(mock_orch, ("ctx", "tool_executor", "execute_async"), fake_execute)
        engine = _engine(mock_orch)

        batch = [
            ToolCall(name="read_file", arguments={"path": "a.py"}),
            ToolCall(name="read_file", arguments={"path": "a.py"}),  # 완전 중복
            ToolCall(name="read_file", arguments={"path": "b.py"}),  # 다른 인자
        ]
        results = _asyncio.run(engine._run_batch_with_dedup(batch, "task"))

        assert calls.count("read_file") == 2  # 중복은 1회만 실행
        assert len(results) == 3  # 원래 순서/개수 유지
        # 중복 위치에는 대표 결과가 복사된다
        assert results[0][3] == results[1][3] == "result for read_file"
        assert results[2][3] == "result for read_file"
        assert engine.telemetry.deduped_calls == 1


class TestWorkingContextRecency:
    def test_rebuild_inserts_working_context_before_assistant_cue(self):
        """재구축 프롬프트의 working_context 블록은 Assistant: 큐 앞(후미 recency)에 위치한다."""
        prompt = "System: sys\nTool guide\n\nUser: hi\nAssistant: "
        result = ToolLoopEngine._insert_working_context(prompt, "SNAPSHOT|MEMO")
        assert result.index("<working_context>") < result.rindex("Assistant: ")
        assert result.index("SNAPSHOT") < result.rindex("Assistant: ")
        assert result.startswith("System: sys")  # 접두사는 그대로

    def test_empty_pinned_is_noop(self):
        prompt = "System: sys\nUser: hi\nAssistant: "
        assert ToolLoopEngine._insert_working_context(prompt, "") == prompt

    def test_cached_pinned_context_read(self, mock_orch: MagicMock):
        _set_mock_attr(mock_orch, ("_prompt_components_cache",), {"pinned_context": "PINNED"})
        engine = _engine(mock_orch)
        assert engine._cached_pinned_context() == "PINNED"


class TestConsumerExceptionPropagation:
    def test_consumer_exception_at_yield_is_not_treated_as_api_error(self, mock_orch):
        """yield 지점에서 소비자가 던진 예외는 API 오류로 분류되지 않고
        그대로 전파된다 (가짜 재시도 방지 — B19)."""
        stream_calls = {"n": 0}

        def fake_stream(**kwargs):
            stream_calls["n"] += 1
            _ = kwargs
            return iter(["안녕하세요 ", "반갑습니다"])

        _set_mock_side_effect(mock_orch, ("manager", "stream_generate"), fake_stream)
        engine = _engine(mock_orch)

        gen = engine.run_loop([{"role": "user", "content": "인사해줘"}], "CODER", "chat")
        first = next(gen)  # 첫 청크 소비
        assert first

        # 소비자가 yield 지점에서 예외 주입 — engine 밖으로 전파되어야 한다
        with pytest.raises(RuntimeError, match="consumer disconnect"):
            gen.throw(RuntimeError("consumer disconnect"))

        # API 오류로 오분류되어 재시도가 일어나지 않았는지 확인
        assert stream_calls["n"] == 1


class TestPublishQualityEvent:
    """QualityGate 결과가 QualityCheckPassed/Failed 이벤트로 발행된다."""

    def test_publish_quality_event_maps_grades_to_pass_fail(self, monkeypatch: pytest.MonkeyPatch):
        from antigravity_k.engine import tool_loop
        from antigravity_k.engine.quality_gate import QualityGrade, QualityScore

        published: list[tuple[str, dict[str, object]]] = []

        class _FakeBus:
            def publish(self, event_name: str, **kwargs: object) -> None:
                published.append((event_name, kwargs))

        monkeypatch.setattr("antigravity_k.engine.event_bus.global_event_bus", _FakeBus())

        tool_loop._publish_quality_event(
            "plan", "테스트 작업", QualityScore(QualityGrade.A, 0.9, "", "PASS", False, [])
        )
        tool_loop._publish_quality_event(
            "code", "테스트 작업", QualityScore(QualityGrade.F, 0.2, "개선 필요", "FAIL", True, ["issue1", "issue2"])
        )

        assert [name for name, _ in published] == ["QualityCheckPassed", "QualityCheckFailed"]
        _name, failed_kwargs = published[1]
        assert failed_kwargs["grade"] == "fail"
        assert failed_kwargs["score"] == 0.2
        assert failed_kwargs["issues"] == ["issue1", "issue2"]
        assert failed_kwargs["feedback"] == "개선 필요"

    def test_post_loop_publishes_final_quality_event_after_revision(self, mock_orch: MagicMock):
        """수정으로 C→B가 되면 최종 결과(B)만 QualityCheckPassed로 발행된다."""
        from antigravity_k.engine.quality_gate import QualityGrade, QualityScore

        initial = QualityScore(QualityGrade.C, 0.4, "보완 필요", "", True, ["불명확"])
        revised = QualityScore(QualityGrade.B, 0.8, "", "", False, [])
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "max_retries"), 1)
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("_get_model_for_role",), "qwen3.6:latest")
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter(["초안"]))
        _set_mock_return(mock_orch, ("manager", "generate"), "보완된 최종 답변")

        with patch("antigravity_k.engine.event_bus.global_event_bus") as event_bus:
            engine = _engine(mock_orch)
            _ = list(engine.run_loop([{"role": "user", "content": "요청"}], "CODER", "chat"))

        quality_calls = [
            c
            for c in event_bus.publish.call_args_list
            if c.args and c.args[0] in {"QualityCheckPassed", "QualityCheckFailed"}
        ]
        assert [c.args[0] for c in quality_calls] == ["QualityCheckPassed"]
        passed = quality_calls[0]
        assert passed.kwargs["grade"] == "good"
        assert passed.kwargs["issues"] == []

    def test_post_loop_publishes_failed_event_when_revision_does_not_improve(self, mock_orch: MagicMock):
        """수정이 개선되지 않으면 최종 C등급을 QualityCheckFailed로 발행한다."""
        from antigravity_k.engine.quality_gate import QualityGrade, QualityScore

        initial = QualityScore(QualityGrade.C, 0.4, "보완 필요", "", True, ["불명확"])
        revised = QualityScore(QualityGrade.C, 0.35, "여전히 부족", "", True, ["불명확", "중복"])
        _set_mock_attr(mock_orch, ("ctx", "quality_gate", "max_retries"), 1)
        _set_mock_side_effect(mock_orch, ("ctx", "quality_gate", "evaluate"), [initial, revised])
        _set_mock_return(mock_orch, ("_get_model_for_role",), "qwen3.6:latest")
        _set_mock_return(mock_orch, ("manager", "stream_generate"), iter(["초안"]))
        _set_mock_return(mock_orch, ("manager", "generate"), "여전히 부족한 답변")

        with patch("antigravity_k.engine.event_bus.global_event_bus") as event_bus:
            engine = _engine(mock_orch)
            _ = list(engine.run_loop([{"role": "user", "content": "요청"}], "CODER", "chat"))

        quality_calls = [
            c
            for c in event_bus.publish.call_args_list
            if c.args and c.args[0] in {"QualityCheckPassed", "QualityCheckFailed"}
        ]
        assert [c.args[0] for c in quality_calls] == ["QualityCheckFailed"]
        failed = quality_calls[0]
        assert failed.kwargs["grade"] == "retry"
        # final_quality는 개선 분기에서만 갱신되므로 미개선 시 초기 평가가 유지된다
        assert failed.kwargs["issues"] == ["불명확"]
