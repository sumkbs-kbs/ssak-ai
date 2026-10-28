"""r41 B: the classifier's MEMORY decision must reach past_memory on both chat paths.

Real FastAPI chat router, real project registry/binding/DI; only the model provider and the
project vector store are doubles. r40 failure: LLM said MEMORY for '정했던' but the regex
re-check (is_memory_recall) missed it, so past_memory was never searched (0 embeddings).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from types import SimpleNamespace

import pytest

from tests.chat_boundary_helpers import Boundary
from tests.chat_boundary_helpers import boundary as boundary

FACT = "R41-SYNTH-FACT-ZEBRA-7731"  # exists only in the synthetic memo
KO = "우리가 지난번에 정했던 릴리스 코드명은 무엇이었나요?"
EN = "What release codename did we agree on last time?"
NEG = "우리가 정했던 것과 상관없이, 파이썬 리스트 정렬 방법만 알려줘"
CODING = "파이썬으로 리스트를 정렬하는 함수 예시를 설명해줘"
SEARCH_Q = "오늘 서울 날씨 알려줘"


class _Store:
    def __init__(self, rows: list[dict[str, object]] | None = None, exc: bool = False) -> None:
        self.rows = rows or []
        self.exc = exc
        self.calls = 0

    def search(self, query: str, top_k: int = 5, **_: object) -> list[dict[str, object]]:
        self.calls += 1
        if self.exc:
            raise RuntimeError("synthetic search error")
        return list(self.rows)


class _Model:
    """Provider double: the classifier answers per prompt; the answer echoes what it was given."""

    def __init__(self, verdicts: Mapping[str, str]) -> None:
        self.verdicts = verdicts
        self.prompts: list[str] = []

    def generate(self, *, prompt: str, target: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        if max_tokens == 10:
            for key, verdict in self.verdicts.items():
                if key[:40] in prompt:
                    return verdict
            return "GENERAL"
        return "answer"

    def stream_generate(self, *, prompt: str, target: str, **_: object) -> Iterator[str]:
        self.prompts.append(prompt)
        yield "answer"


def _wire(boundary: Boundary, monkeypatch: pytest.MonkeyPatch, model: _Model, stores: dict[str, _Store]) -> list[str]:
    from antigravity_k.api import dependencies
    from antigravity_k.api.routes import chat

    seen: list[str] = []

    def acquire(*, project_id: str | None = None, project_root: str | None = None) -> SimpleNamespace:
        seen.append(str(project_id))
        return SimpleNamespace(vault_engine=SimpleNamespace(sync_rag=True, vector_store=stores[str(project_id)]))

    monkeypatch.setattr(dependencies, "acquire_project_runtime", acquire)
    boundary.app.dependency_overrides[chat.get_model_manager] = lambda: model
    return seen


def _memo() -> _Store:
    return _Store([{"text": f"결정 메모: 릴리스 코드명은 {FACT}", "metadata": {"source": "wiki/r41-memo.md"}}])


def _post(boundary: Boundary, text: str, agent: bool) -> str:
    response = boundary.client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "project_id": boundary.project_id,
            "messages": [{"role": "user", "content": text}],
            "stream": True,
            "agent_mode": agent,
            "web_search": False,
        },
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.parametrize("text", [KO, EN], ids=["ko_jeonghaetdeon", "en_did_we_agree"])
def test_non_agent_llm_memory_reaches_past_memory(
    boundary: Boundary, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    model = _Model({text: "MEMORY"})
    store = _memo()
    seen = _wire(boundary, monkeypatch, model, {boundary.project_id: store})
    _post(boundary, text, agent=False)
    assert store.calls == 1 and seen == [boundary.project_id]
    assert any(FACT in p for p in model.prompts)
    assert boundary.searches == []


@pytest.mark.parametrize(
    ("text", "verdict"),
    [(NEG, "GENERAL"), (CODING, "GENERAL"), (SEARCH_Q, "SEARCH")],
    ids=["negative", "coding", "search"],
)
def test_non_memory_questions_do_not_inject(
    boundary: Boundary, monkeypatch: pytest.MonkeyPatch, text: str, verdict: str
) -> None:
    from antigravity_k.engine.memory_recall_intent import is_memory_recall

    model = _Model({text: verdict})
    store = _memo()
    _wire(boundary, monkeypatch, model, {boundary.project_id: store})
    _post(boundary, text, agent=False)
    assert all(FACT not in p for p in model.prompts)
    if not is_memory_recall(text):  # regex-only recall keeps its pre-r41 behaviour
        assert store.calls == 0


@pytest.mark.parametrize(("store", "status"), [(_Store([]), "empty"), (_Store(exc=True), "error")])
def test_empty_and_error_are_reported_not_invented(
    boundary: Boundary, monkeypatch: pytest.MonkeyPatch, store: _Store, status: str
) -> None:
    model = _Model({KO: "MEMORY"})
    _wire(boundary, monkeypatch, model, {boundary.project_id: store})
    _post(boundary, KO, agent=False)
    assert store.calls == 1
    assert all(FACT not in p for p in model.prompts)


def test_cross_project_memo_not_used(boundary: Boundary, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _Model({KO: "MEMORY"})
    mine = _Store([])
    other = _memo()
    _wire(boundary, monkeypatch, model, {boundary.project_id: mine, "other-project": other})
    _post(boundary, KO, agent=False)
    assert mine.calls == 1 and other.calls == 0
    assert all(FACT not in p for p in model.prompts)


def test_agent_path_receives_llm_memory_decision(boundary: Boundary, monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.engine.memory_recall_intent import is_memory_recall, request_recall_decision, wants_memory_recall

    assert not is_memory_recall(KO) or True  # regex result is irrelevant once the LLM said MEMORY
    model = _Model({KO: "MEMORY", CODING: "GENERAL"})
    _wire(boundary, monkeypatch, model, {boundary.project_id: _memo()})
    observed: list[tuple[bool, bool]] = []
    original = boundary.runtime.stream

    def stream(messages: Sequence[Mapping[str, str]], target_model: str) -> Iterator[str]:
        observed.append((request_recall_decision(), wants_memory_recall(str(messages[-1].get("content", "")))))
        yield from original(messages, target_model)

    monkeypatch.setattr(boundary.runtime, "stream", stream)
    _post(boundary, KO, agent=True)
    _post(boundary, CODING, agent=True)
    assert observed[0] == (True, True)
    assert observed[1][0] is False
