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


def _citation_docs(review: Any, tmp_path: Path, body: str) -> Path:
    """인용 한 줄만 담은 가짜 문서 디렉터리 — 검사기에 그 문장만 보이게 한다."""

    docs_root = tmp_path / "ssak-ai-core"
    docs_root.mkdir(exist_ok=True)
    (docs_root / "A.md").write_text(body + "\n", encoding="utf-8")
    return docs_root


def test_citation_of_a_missing_file_is_rejected(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """실재하지 않는 경로를 문장으로 인용하면 실패한다 — 등록 없이는 통과하지 않는다."""

    docs_root = _citation_docs(review, tmp_path, "근거: tests/test_t99_not_here.py (없는 파일)")
    monkeypatch.setattr(review, "_CITATION_EXCEPTIONS", ())
    result = review.check_citation_tracking(docs_root)
    assert result.passed is False
    assert "tests/test_t99_not_here.py" in result.detail


def test_citation_of_an_untracked_file_is_rejected(
    review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실재해도 **추적되지 않으면** 실패다 — 이 체크아웃을 잃으면 사라지는 근거를 통과시키지 않는다."""

    docs_root = _citation_docs(review, tmp_path, "근거: tests/cognitive/test_surface.py (추적되는 파일)")
    monkeypatch.setattr(review, "_CITATION_EXCEPTIONS", ())
    monkeypatch.setattr(review, "_tracked_paths", lambda: set())
    result = review.check_citation_tracking(docs_root)
    assert result.passed is False
    assert "추적되지 않는 인용" in result.detail


def test_registered_citation_is_allowed_but_a_stale_registration_is_rejected(
    review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """등록은 통과를 주지만 면죄부는 아니다 — 추적되는 경로를 등록해 두면 낡은 등록으로 실패한다."""

    docs_root = _citation_docs(review, tmp_path, "근거: tests/cognitive/test_surface.py")
    registered = (
        review.CitationException(
            path="tests/cognitive/test_surface.py",
            owner="cognitive-core",
            reason="시험용 등록",
            review_by="2026-12-31",
        ),
    )
    monkeypatch.setattr(review, "_CITATION_EXCEPTIONS", registered)
    result = review.check_citation_tracking(docs_root, on="2026-09-23")
    assert result.passed is False, "낡은 등록을 통과시켰다"
    assert "낡은 등록" in result.detail


def test_overdue_citation_registration_is_rejected(
    review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """재검토 기한이 지난 등록은 실패한다 — 미추적 인용을 영원히 두지 않는다."""

    docs_root = _citation_docs(review, tmp_path, "근거: tests/test_t99_not_here.py")
    registered = (
        review.CitationException(
            path="tests/test_t99_not_here.py",
            owner="cognitive-core",
            reason="시험용 등록",
            review_by="2026-01-01",
        ),
    )
    monkeypatch.setattr(review, "_CITATION_EXCEPTIONS", registered)
    result = review.check_citation_tracking(docs_root, on="2026-09-23")
    assert result.passed is False
    assert "재검토 기한이 지난 등록" in result.detail


def test_citation_resolves_the_repository_shorthand(review: Any) -> None:  # noqa: ANN401
    """`tools/x.py` 같은 축약 인용을 실제 경로로 해석한다 — 좋은 문서가 오탐으로 깨지지 않게."""

    assert review._resolve_citation("tools/ssak_bundle_store.py") is not None
    assert review._resolve_citation("tests/test_t99_not_here.py") is None
    assert review._resolve_citation("docs/ssak-ai-core/architecture_review.py") is None


def test_glob_and_elided_citations_are_not_judged(review: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """glob·생략 표기는 파일이 아니라 패턴이다 — 없는 파일로 세지 않는다."""

    docs_root = _citation_docs(review, tmp_path, "대상: tests/test_cr14_*.py · docs/qa/.../probe_view.py · src/**/*.py")
    monkeypatch.setattr(review, "_CITATION_EXCEPTIONS", ())
    result = review.check_citation_tracking(docs_root)
    assert result.passed is True, result.detail
    assert result.observed == 0, "패턴을 인용으로 셌다"


def _drift_report(*, reverified: int = 0, missing: int = 0, stale: int = 0) -> dict[str, object]:
    """digest 측정 artifact 의 최소 형태 — 판정에 쓰는 키만 담는다."""

    pins = [
        {
            "doc": "T01a.md",
            "path": "src/antigravity_k/engine/cognitive/models.py",
            "recorded": "a",
            "actual": "a",
            "status": "match",
            "reverified_on": "",
        }
    ]
    counts = {
        "match": len(pins),
        "reverified": reverified,
        "drift": 0,
        "stale_reverification": stale,
        "missing": missing,
    }
    return {
        "counts": counts,
        "docs": {"T01a.md": dict(counts)},
        "pins": pins,
    }


def test_stale_digest_report_is_rejected(review: Any) -> None:  # noqa: ANN401
    """저장본이 방금 잰 값과 다르면 실패한다 — 파일이 바뀐 뒤 낡은 수치를 인용하지 않는다."""

    result = review.check_digest_report(_drift_report(), _drift_report(reverified=3))
    assert result.passed is False
    assert "최신이 아니다" in result.detail


def test_missing_digest_report_is_rejected(review: Any) -> None:  # noqa: ANN401
    """측정 artifact 가 없으면 실패한다 — 증거의 digest 가 아직 그 파일인지 알 길이 없다."""

    result = review.check_digest_report(None, _drift_report())
    assert result.passed is False
    assert "없거나" in result.detail


def test_broken_digest_pin_is_rejected(review: Any) -> None:  # noqa: ANN401
    """파일이 없는데 digest 를 못 박은 항목은 실패다(가리키는 것이 없는 주장)."""

    report = _drift_report(missing=1)
    result = review.check_digest_report(report, report)
    assert result.passed is False
    assert "파일이 없는데" in result.detail


def test_reverified_digests_pass_and_are_counted(review: Any) -> None:  # noqa: ANN401
    """재확인된 pin 은 통과하고 수치로 남는다 — 재확인 사실이 사라지면 그것도 드러나야 한다."""

    report = _drift_report(reverified=21)
    result = review.check_digest_report(report, report)
    assert result.passed is True
    assert result.observed == 21
    assert "재확인 21" in result.detail


def test_invalidated_reverification_fails_the_check(review: Any) -> None:  # noqa: ANN401
    """재확인 뒤에 파일이 또 바뀌면 그 재확인은 무효다 — 통과시키지 않는다."""

    report = _drift_report(stale=2)
    result = review.check_digest_report(report, report)
    assert result.passed is False
    assert "무효" in result.detail


def test_repository_digest_report_is_current_and_counted(measurement: Any) -> None:  # noqa: ANN401
    """이 저장소의 digest 측정은 최신이고, 마커로 고정된 값과 같다."""

    check = next(c for c in measurement.checks if c.name == "digest_report")
    assert check.passed is True, check.detail
    assert measurement.measured["digest_pinned"] > 0
    assert measurement.measured["digest_missing"] == 0
    assert measurement.measured["digest_drifted"] >= 0


def _state_claim_report(*, ok: int = 0, fixed: int = 0, stale: int = 0, unknown: int = 0) -> dict[str, object]:
    """상태 주장 감사 JSON 의 최소 형태."""

    claims: list[dict[str, object]] = []
    for index in range(ok):
        claims.append({"doc": "T01a.md", "line": index + 1, "status": "ok"})
    for index in range(fixed):
        claims.append({"doc": "T01b.md", "line": index + 1, "status": "fixed"})
    for index in range(stale):
        claims.append({"doc": "T03.md", "line": index + 1, "status": "stale"})
    return {
        "claims": claims,
        "counts": {"claims": ok + fixed + stale, "ok": ok, "fixed": fixed, "stale": stale, "unknown": unknown},
    }


def test_stale_state_claim_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """지금 트리와 어긋나는 상태 주장이 정정 없이 남으면 리뷰가 실패한다."""

    result = review.check_state_claims(_state_claim_report(stale=1))
    assert result.passed is False
    assert "어긋나는 상태 주장" in result.detail
    assert "T03.md" in result.detail


def test_corrected_state_claim_passes_and_is_counted(review: Any) -> None:  # noqa: ANN401
    """정정 표기가 붙은 주장은 통과하고, 몇 건인지 수치로 남는다."""

    result = review.check_state_claims(_state_claim_report(fixed=4))
    assert result.passed is True
    assert result.observed == 4
    assert "정정 붙임 4" in result.detail


def test_unjudgeable_state_claim_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """상태를 판정하지 못한 주장은 통과시키지 않는다 — 확인 불가를 통과로 쓰지 않는다."""

    result = review.check_state_claims(_state_claim_report(unknown=2))
    assert result.passed is False
    assert "판정하지 못한" in result.detail


def test_repository_state_claims_are_judged(measurement: Any) -> None:  # noqa: ANN401
    """이 저장소의 상태 주장은 전부 판정돼 있고 낡은 채로 남은 것이 없다."""

    check = next(c for c in measurement.checks if c.name == "state_claims")
    assert check.passed is True, check.detail
    assert measurement.measured["state_claims_stale"] == 0
    assert measurement.measured["state_claims"] >= 1


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
