from pathlib import Path

from scripts.architecture_review import check_citation_tracking


def test_explicit_planning_citation_is_reported_separately_from_existing_code(tmp_path: Path) -> None:
    document = tmp_path / "plan.md"
    document.write_text(
        "---\nplanning_only: true\n---\n"
        "<!-- proposed-path: src/not_implemented.py -->\n"
        "Proposed ownership: `src/not_implemented.py`.\n"
    )
    result = check_citation_tracking(tmp_path)
    assert result.passed
    assert "미구현 제안 1건" in result.detail


def test_proposal_marker_cannot_hide_a_missing_implementation_claim(tmp_path: Path) -> None:
    document = tmp_path / "implemented.md"
    document.write_text("<!-- proposed-path: src/not_implemented.py -->\nImplemented in `src/not_implemented.py`.\n")
    result = check_citation_tracking(tmp_path)
    assert not result.passed
    assert "src/not_implemented.py" in result.detail


def test_planning_document_still_rejects_unmarked_missing_references(tmp_path: Path) -> None:
    document = tmp_path / "plan.md"
    document.write_text("---\nplanning_only: true\n---\nRead `src/missing_dependency.py`.\n")
    result = check_citation_tracking(tmp_path)
    assert not result.passed
    assert "src/missing_dependency.py" in result.detail
