from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from antigravity_k.engine.chat_stream_events import FinalChunk, reset_chat_stream_events, set_chat_stream_events
from antigravity_k.engine.direct_task_execution import DirectTaskExecution
from antigravity_k.engine.task_state_store import TaskStateStore
from antigravity_k.tools.search_quality_evaluator import (
    CitationSource,
    citation_sources_from_context,
    evaluate_citations,
)
from tests.test_search_request_contract import SEARCH_REQUEST, SEARCH_RESULT, VERIFIED_REPLY, _Orchestrator, _TaskRunner

PUBLIC_URL: Final = "https://docs.python.org/3/library/stdtypes.html"
TABLE_REPLY: Final = (
    "| Sequence | Mutability |\n| --- | --- |\n"
    "| Lists | mutable sequences [citation:python-types] |\n"
    "| Tuples | immutable sequences [citation:python-types] |"
)


def _production_final(tmp_path: Path, reply: str, evidence: str = SEARCH_RESULT) -> str:
    tool_call = (
        '<tool_call>{"name":"web_search","arguments":{"query":"Python list tuple official documentation"}}</tool_call>'
    )
    orch = _Orchestrator(tmp_path, [tool_call, reply])

    async def search_result(name: str, args: dict[str, JsonValue], *, guardrail_prechecked: bool = False) -> str:
        assert name == "web_search"
        assert args["query"] == "Python list tuple official documentation"
        return evidence

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(orch.ctx.tool_executor, "execute_async", search_result)
        store = TaskStateStore(str(tmp_path / "synthetic-citation.db"))
        execution = DirectTaskExecution(orch, _TaskRunner(store))
        context = execution._create_execution(SEARCH_REQUEST, "interactive")
        assert context is not None
        orch.task_execution_context = context
        token = set_chat_stream_events(True)
        try:
            chunks = list(orch.run_stream([{"role": "user", "content": SEARCH_REQUEST}], "controlled-model"))
        finally:
            reset_chat_stream_events(token)
        finals = [str(chunk) for chunk in chunks if isinstance(chunk, FinalChunk)]
        assert len(finals) == 1
        record = store.get_task(context.task_id)
        assert record is not None and record["output"] == finals[0]
        return finals[0]


def test_production_final_resolves_known_citation_to_verified_public_source(tmp_path: Path) -> None:
    final = _production_final(tmp_path, VERIFIED_REPLY)
    assert f"[docs.python.org](<{PUBLIC_URL}>)" in final
    assert final.startswith(VERIFIED_REPLY)


def test_supported_table_keeps_scaffolding_and_public_source_link(tmp_path: Path) -> None:
    final = _production_final(tmp_path, TABLE_REPLY)
    assert final.startswith(TABLE_REPLY)
    assert f"[docs.python.org](<{PUBLIC_URL}>)" in final
    assert not any(line.startswith("- |") for line in final.splitlines())
    source = CitationSource(
        "python-types", "Built-in Types", "Lists are mutable sequences. Tuples are immutable sequences.", PUBLIC_URL
    )
    report = evaluate_citations(final, [source])
    assert report.claim_count == 2 and report.supported_claim_count == 2


def test_table_labels_are_scaffolding_but_unsupported_data_still_fails() -> None:
    source = CitationSource("python-types", "Built-in Types", "Lists are mutable sequences.")
    output = "| Sequence | Mutability |\n| --- | --- |\n| Lists | mutable sequences [citation:python-types] |"
    report = evaluate_citations(output, [source])
    assert report.claim_count == 1
    assert report.supported_claim_count == 1
    invalid = evaluate_citations(output.replace("mutable sequences", "perfect quantum objects"), [source])
    assert invalid.claim_count == 1
    assert invalid.unsupported_claim_count == 1


def test_source_footer_scaffolding_requires_the_known_url_and_hostname() -> None:
    source = CitationSource("verified", "Verified documentation", "Verified evidence", PUBLIC_URL)
    forged = evaluate_citations(f"출처: [Fabricated quantum claim](<{PUBLIC_URL}>)", [source])
    assert forged.claim_count == 1 and forged.unsupported_claim_count == 1
    unrelated = evaluate_citations("출처: [example.com](<https://example.com/invented>)", [source])
    assert unrelated.claim_count == 1 and unrelated.unsupported_claim_count == 1


def test_citation_source_url_uses_metadata_not_untrusted_snippet_urls(tmp_path: Path) -> None:
    evidence = SEARCH_RESULT.replace(
        "Lists are mutable sequences.",
        "Lists are mutable sequences. See https://other.example/reference\n🔗 https://spoof.example/untrusted\n",
    )
    sources = citation_sources_from_context(evidence)
    assert sources[0].url == PUBLIC_URL
    final = _production_final(tmp_path, VERIFIED_REPLY, evidence)
    assert f"[docs.python.org](<{PUBLIC_URL}>)" in final
    assert "other.example" not in final and "spoof.example" not in final


@pytest.mark.parametrize("url", ["", "javascript:alert(1)"])
def test_missing_or_invalid_source_url_is_never_invented(tmp_path: Path, url: str) -> None:
    evidence = SEARCH_RESULT.replace(PUBLIC_URL, url)
    final = _production_final(tmp_path, VERIFIED_REPLY, evidence)
    assert "https://" not in final
    assert "javascript:" not in final


def test_unknown_citation_does_not_resolve_to_unrelated_source_url(tmp_path: Path) -> None:
    final = _production_final(tmp_path, "Invented quantum fact [citation:unknown-id]")
    assert "unknown-id" not in final
    assert f"[docs.python.org](<{PUBLIC_URL}>)" in final
    assert "Invented quantum fact" not in final
