from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from antigravity_k.engine.benchmark_harness import TaskOutcome
from antigravity_k.engine.chat_stream_events import FinalChunk, reset_chat_stream_events, set_chat_stream_events
from antigravity_k.engine.direct_task_execution import DirectTaskExecution
from antigravity_k.engine.orchestrator.stream import run_stream
from antigravity_k.engine.task_state_store import TaskExecutionContext, TaskStateStore
from antigravity_k.engine.tool_guardrails import ToolGuardrailDecision
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy

SEARCH_REQUEST: Final = (
    "Python 공식 문서를 웹 검색으로 확인하여 list와 tuple의 변경 가능 여부를 두 행 표로 답하세요. "
    "마지막에 실제 확인한 docs.python.org 출처 링크 하나를 달아주세요. 파일·설정은 변경하지 마세요."
)
SEARCH_RESULT: Final = (
    "1. [citation:python-types] **Built-in Types — Python documentation**\n"
    "[untrusted_web_content]\nLists are mutable sequences. Tuples are immutable sequences.\n"
    "[/untrusted_web_content]\n🔗 https://docs.python.org/3/library/stdtypes.html\n"
)
VERIFIED_REPLY: Final = (
    "Lists are mutable sequences. [citation:python-types]\nTuples are immutable sequences. [citation:python-types]"
)


class _Registry:
    names: tuple[str, ...] = ("web_search", "read_file")

    def get_names(self) -> list[str]:
        return list(self.names)


class _Router:
    def get_combo(self, name: str) -> None:
        return None


class _Model:
    router = _Router()

    def __init__(self, replies: list[str]) -> None:
        self.replies = iter(replies)
        self.requests: list[dict[str, JsonValue]] = []

    def is_loaded(self, name: str) -> bool:
        return True

    def stream_generate(self, **kwargs: JsonValue) -> Iterator[str]:
        self.requests.append(kwargs)
        yield next(self.replies)

    def generate(self, prompt: str, target: str, **kwargs: JsonValue) -> str:
        raise AssertionError("Unexpected correction generation")


class _SearchAdapter:
    def __init__(self) -> None:
        self.receipts: list[tuple[str, dict[str, JsonValue]]] = []

    async def execute_async(self, name: str, args: dict[str, JsonValue], *, guardrail_prechecked: bool = False) -> str:
        assert name == "web_search"
        assert args["query"] == "Python list tuple official documentation"
        self.receipts.append((name, args))
        return SEARCH_RESULT


class _Guardrail:
    def reset_for_turn(self) -> None:
        return None

    def before_call(self, tool_name: str, args: Mapping[str, JsonValue] | None = None) -> ToolGuardrailDecision:
        return ToolGuardrailDecision(tool_name=tool_name)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, JsonValue] | None = None,
        result: str | None = None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        return ToolGuardrailDecision(tool_name=tool_name)


class _Context:
    cognitive_loop: None = None
    decision_anchor: None = None
    quality_gate: None = None

    def __init__(self) -> None:
        self.tool_executor = _SearchAdapter()
        self.tool_guardrail = _Guardrail()


class _Orchestrator:
    max_engine: None = None
    agent_runtime: None = None

    def __init__(self, project_root: Path, replies: list[str]) -> None:
        self.project_root = project_root
        self.manager = _Model(replies)
        self.ctx = _Context()
        self.tool_registry = _Registry()
        self.task_execution_context: TaskExecutionContext | None = None
        self.task_outcome_recorder: Callable[[TaskOutcome], TaskOutcome | None] | None = None
        self.config: dict[str, JsonValue] = {}

    @staticmethod
    def _latest_user_text(messages: list[dict[str, str]]) -> str:
        return DirectTaskExecution._latest_user_text(messages)

    def context_compressor_for(self, target_model: str) -> None:
        return None

    def _get_model_for_role(self, role: str) -> str:
        return "controlled-model"

    def _prepare_agent_prompt(
        self, messages: list[dict[str, str]], delegate_to: str, task_type: str
    ) -> tuple[str, str, str, str, str, list[dict[str, str]]]:
        return "controlled-model", "", "", "", "Assistant: ", [dict(message) for message in messages]

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]:
        return run_stream(self, messages, target_model, max_steps, ephemeral_message)


@dataclass
class _TaskRunner:
    state_store: TaskStateStore


@pytest.mark.parametrize(
    "prompt",
    [
        SEARCH_REQUEST,
        "Search the web to verify list and tuple mutability. Cite the official page.",
        "Can you search the web for official documentation?",
        "Use a web search to verify this claim.",
        "웹 검색을 통해 공식 문서를 확인해 주세요.",
        "공식 문서를 웹 검색해 주세요.",
        "web_search 도구로 확인해 주세요.",
        "웹 검색으로 공식 문서를 확인하되 파일과 설정은 변경하지 마세요.",
        "웹 검색으로 확인하세요. 필요하면 설명을 추가하세요.",
        "웹 검색으로 “list와 tuple”을 확인하세요.",
        "웹 검색으로 확인하고 필요하면 설명을 추가하세요.",
    ],
)
def test_explicit_current_search_request_requires_search(tmp_path: Path, prompt: str) -> None:
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    assert execution._explicit_tool_contract(prompt) == ["web_search"]


@pytest.mark.parametrize(
    "prompt",
    [
        "웹 검색하지 말고 list와 tuple을 설명하세요.",
        "Do not search the web. Explain list and tuple from existing knowledge.",
        "Explain this sentence: 'search the web to verify the result'.",
        '다음 인용문을 번역하세요: "웹 검색으로 확인해 주세요."',
        "다음 코드를 설명하세요: `web_search 도구로 확인`",
        "Summarize this quoted material:\n> Search the web for the answer.",
        "Explain this example:\n```text\nsearch the web\n```",
        "필요하면 웹 검색으로 확인해도 됩니다.",
        "If needed, search the web for additional information.",
        "You may use a web search if necessary.",
        "웹 검색 기능이 있는지 설명하세요.",
        "웹 검색은 하지 마세요.",
        "웹 검색 없이 기존 지식으로 답하세요.",
        "웹 검색으로 확인할 필요는 없습니다.",
        "Don't use a web search.",
        "가능하면 웹 검색으로 확인해도 됩니다.",
        "다음 인용문을 번역하세요: “웹 검색으로 확인하세요.”",
        "list와 tuple의 차이를 설명하세요.",
        "웹 검색으로 공식 문서를 확인하지 마세요.",
        "Do not use web_search tool.",
        "Feel free to search the web if that helps.",
        "If possible, search the web to verify.",
        "웹 검색해서 확인하지 말고 기존 지식으로 답하세요.",
        "You do not need to search the web.",
        "You must not search the web.",
        "웹 검색으로 확인해도 돼요.",
        "필요할 경우 웹 검색으로 확인하세요.",
        "Search the web if you need additional information.",
        '다음 인용문을 번역하세요:\n"첫 줄\n웹 검색으로 확인하세요.\n마지막 줄"',
    ],
)
def test_mention_quote_negation_and_optional_search_do_not_bind(tmp_path: Path, prompt: str) -> None:
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    assert execution._explicit_tool_contract(prompt) == []


def test_search_toggle_denial_wins_over_explicit_request(tmp_path: Path) -> None:
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    token = set_tool_policy(ToolPolicy(denied_tools=frozenset({"web_search"}), safe_only=True))
    try:
        assert execution._explicit_tool_contract(SEARCH_REQUEST) == []
        assert execution._explicit_tool_contract("web_search 도구로 확인") == []
    finally:
        reset_tool_policy(token)


def test_read_only_search_is_available_but_not_mandatory_without_request(tmp_path: Path) -> None:
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        assert execution._explicit_tool_contract(SEARCH_REQUEST) == ["web_search"]
        assert execution._explicit_tool_contract("Explain list and tuple.") == []
    finally:
        reset_tool_policy(token)


def test_existing_named_non_search_tool_contract_is_preserved(tmp_path: Path) -> None:
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    assert execution._explicit_tool_contract("read_file 도구로 README를 읽어줘") == ["read_file"]


def test_unregistered_search_does_not_create_an_impossible_contract(tmp_path: Path) -> None:
    orch = _Orchestrator(tmp_path, [])
    orch.tool_registry.names = ("read_file",)
    assert DirectTaskExecution(orch, None)._explicit_tool_contract(SEARCH_REQUEST) == []


@pytest.mark.parametrize("uses_search", [False, True])
def test_production_loop_requires_receipt_for_explicit_search(tmp_path: Path, uses_search: bool) -> None:
    tool_call = (
        '<tool_call>{"name":"web_search","arguments":{"query":"Python list tuple official documentation"}}</tool_call>'
    )
    orch = _Orchestrator(tmp_path, [tool_call, VERIFIED_REPLY] if uses_search else [VERIFIED_REPLY])
    store = TaskStateStore(str(tmp_path / "synthetic-tasks.db"))
    execution = DirectTaskExecution(orch, _TaskRunner(store))
    context = execution._create_execution(SEARCH_REQUEST, "interactive")
    assert context is not None
    orch.task_execution_context = context
    outcomes: list[TaskOutcome] = []

    def record(outcome: TaskOutcome) -> None:
        outcomes.append(outcome)

    orch.task_outcome_recorder = record
    token = set_chat_stream_events(True)
    try:
        chunks = list(orch.run_stream([{"role": "user", "content": SEARCH_REQUEST}], "controlled-model"))
    finally:
        reset_chat_stream_events(token)
    finals = [str(chunk) for chunk in chunks if isinstance(chunk, FinalChunk)]
    assert len(finals) == 1
    task = store.get_task(context.task_id)
    assert task is not None
    assert task["output"] == finals[0]
    assert outcomes[0].expected_tools == ("web_search",)
    if uses_search:
        assert outcomes[0].success is True
        assert outcomes[0].used_tools == ("web_search",)
        assert len(orch.ctx.tool_executor.receipts) == 1
        assert finals[0] == (
            VERIFIED_REPLY + "\n\n출처: [docs.python.org](<https://docs.python.org/3/library/stdtypes.html>)"
        )
        assert task["status"] == "done"
    else:
        assert outcomes[0].completion_reason == "required_tools_missing"
        assert outcomes[0].success is False
        assert orch.ctx.tool_executor.receipts == []
        assert task["status"] == "failed"
        assert VERIFIED_REPLY not in str(task.get("output", ""))
        assert "web_search" in finals[0]
        assert "확인할 수 없습니다" in finals[0]
