from pathlib import Path

import pytest

from antigravity_k.engine.tool_loop import ToolLoopEngine
from tests.test_citation_source_links import TABLE_REPLY
from tests.test_search_request_contract import SEARCH_RESULT, _Orchestrator


def test_source_titles_cannot_satisfy_an_explicit_table_contract(tmp_path: Path) -> None:
    # Given
    orch = _Orchestrator(tmp_path, [])
    engine = ToolLoopEngine(orch)
    draft = "Built-in Types — Python documentation [citation:python-types]"
    # When
    _ = list(engine._post_loop_checks([], "search", draft, "2행 표로 정리하세요.", "controlled-model", SEARCH_RESULT))
    # Then
    assert engine._citation_validation_failed
    assert "citation_validation_failed" in engine.last_output
    assert draft not in engine.last_output


def test_bounded_table_repair_accepts_only_cited_complete_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    orch = _Orchestrator(tmp_path, [])
    engine = ToolLoopEngine(orch)
    calls: list[str] = []

    def repair(*args: str) -> str:
        calls.append(args[1])
        return "Built-in Types — Python documentation [citation:python-types]" if len(calls) == 1 else TABLE_REPLY

    monkeypatch.setattr(engine, "_citation_revision", repair)
    # When
    _ = list(
        engine._post_loop_checks(
            [], "search", "Unknown unsupported fact.", "2행 표로 정리하세요.", "controlled-model", SEARCH_RESULT
        )
    )
    # Then
    assert len(calls) == 2
    assert engine.last_output.startswith(TABLE_REPLY)
    assert not engine._citation_validation_failed


def test_unrepairable_table_is_persisted_as_failed_in_production_loop(tmp_path: Path) -> None:
    import sqlite3

    from tests.test_citation_source_links import _production_final
    from tests.test_search_request_contract import SEARCH_REQUEST

    # Given
    request = SEARCH_REQUEST.replace("두 행 표", "2행 표")
    # When
    final = _production_final(
        tmp_path, "Built-in Types — Python documentation [citation:python-types]", request=request
    )
    assert "citation_validation_failed" in final
    assert "Built-in Types" not in final
    # Then
    with sqlite3.connect(tmp_path / "synthetic-citation.db") as connection:
        row = connection.execute("SELECT status, error FROM task_history").fetchone()
    assert row[0] == "failed"
    assert "citation_validation_failed" in row[1]


@pytest.mark.parametrize(
    "candidate",
    [
        "| Type | Value |\n|---|---|\n| x | y |\n| x | z |",
        "```markdown\n" + TABLE_REPLY + "\n```",
        TABLE_REPLY + "\n| Lists | mutable sequences [citation:python-types] |",
    ],
)
def test_incomplete_or_illustrative_table_never_satisfies_contract(candidate: str) -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_table_rows
    from antigravity_k.tools.search_quality_evaluator import citation_sources_from_context, evaluate_citations

    # Given
    report = evaluate_citations(candidate, citation_sources_from_context(SEARCH_RESULT))
    # When
    accepted = satisfies_table_rows(candidate, 2, report.supported_claim_count)
    # Then
    assert not accepted


@pytest.mark.parametrize("divider", ["| - | - |", "| -- | -- |", "| --- | --- |"])
def test_renderer_compatible_table_dividers(divider: str) -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_table_rows
    from antigravity_k.tools.search_quality_evaluator import citation_sources_from_context, evaluate_citations

    candidate = TABLE_REPLY.replace("| --- | --- |", divider)
    report = evaluate_citations(candidate, citation_sources_from_context(SEARCH_RESULT))
    assert report.supported_claim_count == 2
    assert satisfies_table_rows(candidate, 2, report.supported_claim_count)


def test_mismatched_header_is_not_a_rendered_table() -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_table_rows

    candidate = TABLE_REPLY.replace("| Sequence | Mutability |", "| Type |")
    assert not satisfies_table_rows(candidate, 2, 2)


def test_numeric_link_limit_and_inline_break_contract(tmp_path: Path) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    candidate = TABLE_REPLY.replace("mutable sequences", "mutable sequences `<br>`", 1)
    list(
        engine._post_loop_checks(
            [], "search", candidate, "2행 표 문법 예시와 링크 1개", "controlled-model", SEARCH_RESULT
        )
    )
    assert engine._citation_validation_failed


def test_one_displayed_link_allows_multiple_verified_sources() -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_presentation

    urls = {"a": "https://example.org/a", "b": "https://example.org/b"}
    assert satisfies_presentation("[citation:a] [citation:b] https://example.org/a", "출처 링크 1개", urls)
    assert not satisfies_presentation("[citation:a] https://example.org/a https://example.org/b", "출처 링크 1개", urls)
    assert satisfies_presentation("[citation:a]", "출처 링크 1개", urls)


def test_existing_verified_markdown_link_is_not_duplicated() -> None:
    from antigravity_k.tools.search_quality_evaluator import citation_sources_from_context

    sources = citation_sources_from_context(SEARCH_RESULT)
    candidate = TABLE_REPLY + f"\n[official](<{sources[0].url}>)"
    assert ToolLoopEngine._citation_source_links(candidate, sources) == ""


def test_supported_table_is_recovered_from_corrected_draft_not_rejected_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    improved = TABLE_REPLY + "\n\nUnrelated invented side claim. [citation:python-types]"
    monkeypatch.setattr(engine, "_citation_revision", lambda *args: improved)
    list(engine._post_loop_checks([], "search", "Unsupported original.", "2행 표", "controlled-model", SEARCH_RESULT))
    assert not engine._citation_validation_failed
    assert engine.last_output.startswith(TABLE_REPLY)
    assert "invented" not in engine.last_output


def test_generated_source_footer_respects_requested_displayed_count() -> None:
    from antigravity_k.tools.search_quality_evaluator import CitationSource

    sources = (
        CitationSource("a", "A", "", "https://example.org/a"),
        CitationSource("b", "B", "", "https://example.org/b"),
    )
    footer = ToolLoopEngine._citation_source_links("[citation:a] [citation:b]", sources, 1)
    assert footer.count("https://") == 1


def test_empty_search_cannot_complete_explicit_source_verification(tmp_path: Path) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    list(
        engine._post_loop_checks(
            [],
            "search",
            "General knowledge answer.",
            "web_search로 공식 출처를 확인하세요.",
            "controlled-model",
            '[TOOL_EVIDENCE] {"tool":"web_search"}\n결과 없음',
            executed_tools=("web_search",),
        )
    )
    assert engine._citation_validation_failed
    assert "citation_validation_failed" in engine.last_output
    assert "General knowledge" not in engine.last_output


def test_empty_optional_search_does_not_block_general_knowledge(tmp_path: Path) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    list(
        engine._post_loop_checks(
            [],
            "explain",
            "General knowledge answer.",
            "Explain list and tuple.",
            "controlled-model",
            '[TOOL_EVIDENCE] {"tool":"web_search"}\n결과 없음',
            executed_tools=("web_search",),
        )
    )
    assert not engine._citation_validation_failed


@pytest.mark.parametrize("executed_tools", [("read_file",), ("web_search",)])
def test_read_file_mentioning_search_is_not_search_execution(tmp_path: Path, executed_tools: tuple[str, ...]) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    list(
        engine._post_loop_checks(
            [],
            "read",
            "Source text read successfully.",
            "Do not search. Verify the source text using read_file only.",
            "controlled-model",
            '[TOOL_EVIDENCE] {"tool":"read_file"}\nThe source documents the web_search tool.',
            executed_tools=executed_tools,
        )
    )
    assert not engine._citation_validation_failed
    assert engine.last_output == "Source text read successfully."


def test_python_syntax_cells_cannot_contain_prose() -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_presentation

    candidate = "| list | `c and d are guaranteed to refer to two different lists.` [citation:a] |"
    assert not satisfies_presentation(candidate, "Python 문법 예시를 2행 표로", {"a": "https://example.org/a"})


def test_verified_original_table_does_not_need_model_rewrite_for_extra_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = ToolLoopEngine(_Orchestrator(tmp_path, []))
    calls: list[str] = []

    def repair(*args: str) -> str:
        calls.append(args[1])
        return "No useful answer."

    monkeypatch.setattr(engine, "_citation_revision", repair)
    list(
        engine._post_loop_checks(
            [], "search", TABLE_REPLY + "\n\nInvented unsupported claim.", "2행 표", "controlled-model", SEARCH_RESULT
        )
    )
    assert not engine._citation_validation_failed
    assert engine.last_output.startswith(TABLE_REPLY)
    assert calls == []


def test_actual_citation_predicates_are_persisted_in_task_audit(tmp_path: Path) -> None:
    import json
    import sqlite3

    from tests.test_citation_source_links import _production_final

    _production_final(tmp_path, TABLE_REPLY)
    with sqlite3.connect(tmp_path / "synthetic-citation.db") as connection:
        records = connection.execute(
            "SELECT payload_json FROM task_execution_events WHERE event_type = 'CitationValidationChecked'"
        ).fetchall()
    payloads = [json.loads(row[0]) for row in records]
    assert [record["stage"] for record in payloads] == ["draft", "final_candidate"]
    assert payloads[0]["output"] == TABLE_REPLY
    assert payloads[-1]["citations_valid"]


def test_verified_citation_metadata_is_not_python_example_code() -> None:
    from antigravity_k.engine.citation_table_contract import satisfies_presentation
    from antigravity_k.tools.search_quality_evaluator import citation_sources_from_context, evaluate_citations

    candidate = TABLE_REPLY.replace("[citation:python-types]", "`[citation:python-types]`")
    report = evaluate_citations(candidate, citation_sources_from_context(SEARCH_RESULT))
    recovered = ToolLoopEngine._supported_claim_fallback(report, candidate)
    assert "`[citation:" not in recovered
    assert satisfies_presentation(
        recovered, "Python 문법 예시 2행 표", {"python-types": "https://docs.python.org/3/library/stdtypes.html"}
    )


def test_audit_claim_and_syntax_details_are_bounded(tmp_path: Path) -> None:
    import json
    import sqlite3

    from tests.test_citation_source_links import _production_final

    candidate = "\n".join(
        f"| mutable {index} | `this is not valid example prose {index}` [citation:python-types] |"
        for index in range(600)
    )
    _production_final(tmp_path, candidate, request="Python web_search로 공식 출처 확인 후 문법 예시 2행 표")
    with sqlite3.connect(tmp_path / "synthetic-citation.db") as connection:
        records = connection.execute(
            "SELECT payload_json FROM task_execution_events WHERE event_type = 'CitationValidationChecked'"
        ).fetchall()
    payloads = [json.loads(row[0]) for row in records]
    assert max(len(row[0]) for row in records) < 40000
    assert payloads[0]["citation_report"]["claim_count"] > 8
    assert payloads[0]["citation_report"]["details_truncated"]
    assert len(payloads[0]["citation_report"]["claims"]) <= 8
    assert payloads[0]["syntax_error_count"] > 8
    assert len(payloads[0]["syntax_errors"]) <= 8


@pytest.mark.parametrize("code", ["`[citation:unknown]`", "``[citation:known]``", "`value = '[citation:known]'`"])
def test_citation_recovery_preserves_unknown_and_actual_code(code: str) -> None:
    from antigravity_k.engine.citation_table_contract import unwrap_verified_citation_metadata

    assert unwrap_verified_citation_metadata(code, {"known"}) == code
