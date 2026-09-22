"""T14 최종 Architecture Review harness 시험.

`scripts/architecture_review.py`를 그대로 불러(CLI와 같은 코드 경로) 두 가지를 고정한다.

1. 실제 저장소 상태에서 모든 검사가 통과한다 — 리뷰 문서·매핑·link·증거가 서로 어긋나면 CI가 깨진다.
2. 검사기가 실제로 잡아낸다 — 없는 artifact, 매핑되지 않은 인수 항목, 마커 불일치, 깨진 link를
   통과시키지 않는지 각각 음성 fixture로 확인한다.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "architecture_review.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("architecture_review", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["architecture_review"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def review() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script()


@pytest.fixture(scope="module")
def measurement(review: Any) -> Any:  # noqa: ANN401
    return review.measure()


def test_repository_state_passes_every_check(measurement: Any) -> None:  # noqa: ANN401
    failed = [check.detail for check in measurement.checks if not check.passed]
    assert measurement.passed is True, f"architecture review 검사 실패: {failed}"


def test_source_alignment_counts_match_constitution_and_source(measurement: Any) -> None:
    check = next(c for c in measurement.checks if c.name == "source_alignment")
    assert check.passed is True, check.detail
    assert measurement.measured["principles"] == 24
    assert measurement.measured["source_questions"] == 12
    assert measurement.measured["drift_questions"] == 10


def test_every_principle_has_cards_evidence_tests_and_modules(measurement: Any) -> None:
    for principle in measurement.principles:
        assert principle.cards, f"P{principle.number}: 카드 없음"
        assert principle.evidence, f"P{principle.number}: 증거 없음"
        assert principle.tests, f"P{principle.number}: 시험 없음"
        assert principle.modules, f"P{principle.number}: module 없음"
        assert principle.status in {"covered", "partial", "gap"}
        assert principle.limit.strip(), f"P{principle.number}: 한계 서술 없음"


def test_partial_principles_all_state_a_limit(measurement: Any) -> None:
    partial = [p for p in measurement.principles if p.status != "covered"]
    assert partial, "미완 원칙이 사라졌다면 그 근거를 명시해야 한다"
    assert measurement.measured["principles_gap"] == 0
    assert all(len(p.limit) > 20 for p in partial)


def test_every_source_question_has_a_basis_and_limit(measurement: Any) -> None:
    assert {q.key for q in measurement.source_questions} == {
        "identity",
        "continuity",
        "brain_boundary",
        "context",
        "experience",
        "learning",
        "governance",
        "risk",
        "unknown",
        "history",
        "human",
        "complexity",
    }
    for question in measurement.source_questions:
        assert question.answer in {"yes", "yes_with_limits", "no"}
        assert len(question.basis) > 30, f"{question.key}: 근거가 너무 짧다"
        assert question.limit.strip(), f"{question.key}: 한계 서술 없음"


def test_no_drift_question_is_triggered(measurement: Any) -> None:
    assert measurement.measured["drift_triggered"] == 0
    for drift in measurement.drift_questions:
        assert drift.triggered is False, f"{drift.key}: drift가 감지됐다"
        assert len(drift.basis) > 20, f"{drift.key}: 근거가 너무 짧다"


def test_checklist_entries_are_all_mapped(measurement: Any) -> None:
    check = next(c for c in measurement.checks if c.name == "checklist_coverage")
    assert check.passed is True, check.detail
    assert check.observed == 17


def test_missing_artifact_is_rejected(review: Any, measurement: Any) -> None:  # noqa: ANN401
    broken = (
        dataclasses.replace(measurement.principles[0], evidence=("T99_does_not_exist.md",)),
        *measurement.principles[1:],
    )
    result = review.check_artifacts(broken)
    assert result.passed is False
    assert "T99_does_not_exist.md" in result.detail


def test_unmapped_checklist_entry_is_rejected(review: Any, measurement: Any) -> None:  # noqa: ANN401
    without_t14 = tuple(
        dataclasses.replace(p, cards=tuple(c for c in p.cards if c != "T14")) for p in measurement.principles
    )
    result = review.check_checklist_coverage(without_t14)
    assert result.passed is False
    assert "T14" in result.detail


def test_unknown_card_id_is_rejected(review: Any, measurement: Any) -> None:  # noqa: ANN401
    extra = (
        dataclasses.replace(measurement.principles[0], cards=("T99",)),
        *measurement.principles[1:],
    )
    result = review.check_checklist_coverage(extra)
    assert result.passed is False
    assert "T99" in result.detail


def test_marker_mismatch_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = tmp_path / "REVIEW.md"
    document.write_text("<!-- measured:principles=99 -->\n", encoding="utf-8")
    monkeypatch.setattr(review, "REVIEW_DOC", document)
    result = review.check_measured_markers({"principles": 24})
    assert result.passed is False
    assert "≠ 실제 24" in result.detail


def test_missing_marker_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = tmp_path / "REVIEW.md"
    document.write_text("# 리뷰\n", encoding="utf-8")
    monkeypatch.setattr(review, "REVIEW_DOC", document)
    result = review.check_measured_markers({"principles": 24})
    assert result.passed is False
    assert "principles 마커가 없다" in result.detail


def test_unverified_marker_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = tmp_path / "REVIEW.md"
    document.write_text("<!-- measured:made_up=7 -->\n", encoding="utf-8")
    monkeypatch.setattr(review, "REVIEW_DOC", document)
    result = review.check_measured_markers({})
    assert result.passed is False
    assert "검사되지 않은 값" in result.detail


def test_review_document_requires_every_principle(
    review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, measurement: Any
) -> None:
    document = tmp_path / "REVIEW.md"
    document.write_text("**P1** 만 있는 문서\n", encoding="utf-8")
    monkeypatch.setattr(review, "REVIEW_DOC", document)
    result = review.check_review_document(measurement.principles)
    assert result.passed is False
    assert "P24" in result.detail
    assert "Q-identity" in result.detail


def test_broken_doc_link_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs_root = tmp_path / "ssak-ai-core"
    docs_root.mkdir()
    (docs_root / "A.md").write_text("[없는 문서](B.md)\n[정상](../ssak-ai-core/A.md)\n", encoding="utf-8")
    monkeypatch.setattr(review, "DOCS_ROOT", docs_root)
    result = review.check_doc_links()
    assert result.passed is False
    assert "B.md" in result.detail


def test_orphan_evidence_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "T99_orphan.md").write_text("고아 증거\n", encoding="utf-8")
    docs_root = tmp_path / "ssak-ai-core"
    docs_root.mkdir()
    (docs_root / "CHECKLIST.md").write_text("증거 없음\n", encoding="utf-8")
    monkeypatch.setattr(review, "DOCS_ROOT", docs_root)
    monkeypatch.setattr(review, "EVIDENCE_DIR", evidence_dir)
    result = review.check_evidence_referenced(())
    assert result.passed is False
    assert "T99_orphan.md" in result.detail


def test_cli_writes_artifact_and_reports_verdict(
    review: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "review.json"
    exit_code = review.main(["--output", str(output)])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.out
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["failures"] == []
    assert len(payload["principles"]) == 24
    assert len(payload["source_questions"]) == 12
    assert len(payload["drift_questions"]) == 10
    assert "verdict passed=True" in captured.out


def test_missing_regression_ledger_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """원장 artifact 가 없으면 리뷰가 실패한다 — 회귀 수치의 출처 없이 수치를 쓰지 않는다."""

    monkeypatch.setattr(review, "REGRESSION_LEDGER", tmp_path / "absent.json")
    result = review.check_regression_ledger(review.read_regression_ledger())
    assert result.passed is False
    assert "없거나" in result.detail


def test_incomplete_scope_is_rejected(review: Any) -> None:  # noqa: ANN401
    """한 회차짜리 scope 는 “결정적”과 “seed 민감”을 구분하지 못하므로 통과시키지 않는다."""

    ledger = {
        "runs": [{"scope": "chunk", "seed": 101}],
        "scopes": {"chunk": 1},
        "incomplete_scopes": ["chunk"],
        "deterministic": [],
        "owners": {},
        "unowned": [],
        "drift": [],
    }
    result = review.check_regression_ledger(ledger)
    assert result.passed is False
    assert "두 회차" in result.detail


def test_scopeless_ledger_is_rejected(review: Any) -> None:  # noqa: ANN401
    """scope 이름이 없는 원장은 “무엇을 쟀는가”가 없으므로 인용할 수 없다."""

    ledger = {
        "runs": [{"seed": 101}, {"seed": 202}],
        "scopes": {},
        "incomplete_scopes": [],
        "deterministic": [],
        "owners": {},
        "unowned": [],
        "drift": [],
    }
    result = review.check_regression_ledger(ledger)
    assert result.passed is False
    assert "scope 가 없다" in result.detail


def test_duplicate_seed_scope_is_reported_by_the_ledger(review: Any) -> None:  # noqa: ANN401
    """두 회차가 같은 seed 면 같은 조건을 두 번 잰 것이라 drift 가 늘 0으로 보인다."""

    ledger = {
        "runs": [{"scope": "chunk", "seed": 101}, {"scope": "chunk", "seed": 101}],
        "scopes": {"chunk": 2},
        "incomplete_scopes": ["chunk"],
        "deterministic": [],
        "owners": {},
        "unowned": [],
        "drift": [],
    }
    result = review.check_regression_ledger(ledger)
    assert result.passed is False
    assert "두 회차" in result.detail


def test_unowned_deterministic_failure_is_rejected(review: Any) -> None:  # noqa: ANN401
    """소유자 없는 결정적 실패를 리뷰가 넘기지 않는다."""

    node = "tests/test_new_thing.py::test_broken"
    ledger = {
        "runs": [{"scope": "chunk", "seed": 101}, {"scope": "chunk", "seed": 202}],
        "scopes": {"chunk": 2},
        "incomplete_scopes": [],
        "deterministic": [node],
        "owners": {},
        "unowned": [node],
        "drift": [],
    }
    result = review.check_regression_ledger(ledger)
    assert result.passed is False
    assert "소유자 없는 결정적 실패 1건" in result.detail
    assert node in result.detail


def test_regression_measured_reads_the_five_slots(review: Any) -> None:  # noqa: ANN401
    """마커로 고정할 다섯 값을 원장에서 센다."""

    ledger = {
        "runs": [{"seed": 101}, {"seed": 202}, {"seed": 303}],
        "scopes": {"a": 2, "b": 1},
        "deterministic": ["x", "y"],
        "owners": {"x": {}, "y": {}},
        "unowned": [],
        "drift": ["z"],
    }
    assert review.regression_measured(ledger) == {
        "regression_scopes": 2,
        "regression_runs": 3,
        "regression_deterministic": 2,
        "regression_drift": 1,
        "regression_unowned": 0,
    }


def test_repository_regression_ledger_has_two_seeded_runs(review: Any) -> None:  # noqa: ANN401
    """저장소의 원장 artifact 가 실제로 두 회차·복수 scope 를 담고 있는지(리뷰가 인용하는 수치의 출처)."""

    ledger = review.read_regression_ledger()
    assert ledger is not None, f"{review.REGRESSION_LEDGER} 가 없다 — `scripts/regression_ledger.py` 로 만들어야 한다"
    result = review.check_regression_ledger(ledger)
    assert result.passed is True, result.detail
    seeds = [run["seed"] for run in ledger["runs"]]
    assert len(set(seeds)) >= 2, "두 회차가 같은 seed 면 drift 가 늘 0으로 보인다"
    assert ledger["incomplete_scopes"] == []
    assert all(count >= 2 for count in ledger["scopes"].values()), ledger["scopes"]
    assert len(ledger["scopes"]) >= 2, "전량 회귀를 한 scope 로만 쟀다"


def test_collected_test_count_matches_document_marker(review: Any) -> None:
    """문서의 cognitive_tests 마커가 실제 수집 개수와 일치해야 한다(시험 추가 시 갱신 강제)."""

    count = review.collect_test_count(review.REPO_ROOT / "tests" / "cognitive")
    assert count is not None and count > 0
    text = review.REVIEW_DOC.read_text(encoding="utf-8")
    markers = dict(review._MARKER_PATTERN.findall(text))
    assert markers.get("cognitive_tests") == str(count), (
        "tests/cognitive 수집 개수가 바뀌었다 — ARCHITECTURE_REVIEW.md의 cognitive_tests 마커를 갱신해야 한다"
    )
