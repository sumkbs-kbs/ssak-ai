"""r34: memory-recall classification (natural phrasing) kept separate from forced-route tests.

r33 S3: "What warehouse shelf code did we agree on for the Larkspur pilot?" had no keyword hit
(GENERAL), went to the LLM router whose prompt had no memory category; qwen3.8 replied SEARCH
-> fast_search (web) instead of the general path with past_memory. These tests exercise only the
deterministic natural-language classifier; they do NOT force a route.
"""

from __future__ import annotations

import pytest

import antigravity_k.engine.intent_observability as obs
from antigravity_k.api.routes.chat import _is_memory_recall, _keyword_intent_fallback

R33_Q = "What warehouse shelf code did we agree on for the Larkspur pilot? Answer with the code only."


@pytest.mark.parametrize(
    "q",
    [
        R33_Q,
        "Which vendor did we decide on for the Quillon rollout?",
        "Remember the codename we picked for the beta? What was it?",
        "우리가 지난 회의에서 정한 창고 선반 코드가 뭐였지?",
        "지난번에 메모한 파일럿 코드 알려줘",
        "What did I note about the Larkspur pilot in my memo?",
    ],
)
def test_natural_memory_recall_is_classified_memory_not_search(q: str) -> None:
    assert _keyword_intent_fallback(q) != "SEARCH"
    assert _is_memory_recall(q)


@pytest.mark.parametrize(
    "q",
    ["오늘 서울 날씨 알려줘", "삼성전자 주가 알려줘", "Write a Python function that sums a list", "Explain recursion"],
)
def test_non_memory_requests_are_not_memory(q: str) -> None:
    assert not _is_memory_recall(q)


def test_memory_parse_label_is_kept_in_observability() -> None:
    ev = obs.record("MEMORY", "llm", True, "general", 10, model="qwen3.8:latest", parse="matched_memory")
    assert ev["parse"] == "matched_memory"
