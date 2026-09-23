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
import subprocess
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


def _drift_report(
    *,
    reverified: int = 0,
    missing: int = 0,
    stale: int = 0,
    pins: int = 1,
    probe_present: bool = True,
    probe_ok: bool = True,
    exit_code: int | None = 0,
) -> dict[str, object]:
    """digest 측정 artifact 의 최소 형태 — 판정에 쓰는 키만 담는다."""

    entries: list[dict[str, str]] = [
        {
            "doc": "T01a.md",
            "path": "src/antigravity_k/engine/cognitive/models.py",
            "recorded": "a",
            "actual": "a",
            "status": "match",
            "reverified_on": "",
        }
        for _ in range(max(pins, 0))
    ]
    counts = {
        "match": len(entries),
        "reverified": reverified,
        "drift": 0,
        "stale_reverification": stale,
        "missing": missing,
    }
    report: dict[str, object] = {
        "counts": counts,
        "docs": {"T01a.md": dict(counts)} if entries else {},
        "pins": entries,
        "coverage": {"pins": len(entries), "docs": 1 if entries else 0, "min_pins": 1},
        "floors": [
            {
                "label": "pin",
                "observed": len(entries),
                "minimum": 1,
                "margin": len(entries) - 1,
                "why": "2026-09-23 기준 관측: pin " + str(len(entries)),
            },
            {
                "label": "pin 을 박은 문서",
                "observed": 1 if entries else 0,
                "minimum": 1,
                "margin": (1 if entries else 0) - 1,
                "why": "2026-09-23 기준 관측: 문서 1개",
            },
        ],
    }
    if probe_present:
        report["probe"] = {"cases": 9, "failures": [] if probe_ok else ["경로+digest 판독: 0 ≠ 1"], "ok": probe_ok}
    if exit_code is not None:
        report["exit_code"] = exit_code
    return report


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


def test_digest_report_without_a_self_probe_is_rejected(review: Any) -> None:  # noqa: ANN401
    """자기시험 결과가 없는 측정 artifact 는 통과하지 않는다 — 판독력을 확인하지 않은 수치다."""

    report = _drift_report(probe_present=False)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "자기시험" in result.detail


def test_digest_report_with_a_failed_self_probe_is_rejected(review: Any) -> None:  # noqa: ANN401
    """자기시험이 실패한 측정은 실패다 — pin 50개를 셌어도 판독 규칙이 깨졌으면 증거가 아니다."""

    report = _drift_report(probe_ok=False)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "자기시험 실패" in result.detail


def test_digest_report_without_a_floor_basis_is_rejected(review: Any) -> None:  # noqa: ANN401
    """하한 근거가 기록되지 않은 측정은 실패한다 — 나중에 그 값을 내려도 되는지 판단할 수 없다."""

    report = _drift_report(reverified=3)
    report["floors"] = [dict(item) for item in report["floors"]]
    report["floors"][0]["why"] = ""  # type: ignore[index]
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "근거(`why`)가 비었다" in result.detail


def test_blind_digest_measurement_is_rejected(review: Any) -> None:  # noqa: ANN401
    """pin 을 하나도 못 본 측정은 “움직임 0” 이 아니라 실패다(탐지력 하한)."""

    report = _drift_report(pins=0)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "볼 수 없는" in result.detail


def test_citation_floor_applies_to_the_repository_corpus(
    review: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: ANN401
    """저장소 전체에서 인용이 하나도 안 보이면 읽지 못한 것일 수 있다 — 하한이 그것을 잡는다.

    하한은 **기본 범위**(저장소)에만 걸린다: 부분 범위를 넘기면 그 범위를 정한 호출자가 하한을 소유한다.
    """

    empty_root = tmp_path / "ssak-ai-core"
    empty_root.mkdir(exist_ok=True)
    monkeypatch.setattr(review, "DOCS_ROOT", empty_root)
    result = review.check_citation_tracking()

    assert result.passed is False
    assert "하한" in result.detail


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


def _state_claim_report(
    *,
    ok: int = 0,
    fixed: int = 0,
    stale: int = 0,
    unknown: int = 0,
    mentions: int = 6,
    probe_present: bool = True,
    probe_ok: bool = True,
    exit_code: int | None = 0,
) -> dict[str, object]:
    """상태 주장 감사 JSON 의 최소 형태."""

    claims: list[dict[str, object]] = []
    for index in range(ok):
        claims.append({"doc": "T01a.md", "line": index + 1, "status": "ok"})
    for index in range(fixed):
        claims.append({"doc": "T01b.md", "line": index + 1, "status": "fixed"})
    for index in range(stale):
        claims.append({"doc": "T03.md", "line": index + 1, "status": "stale"})
    report: dict[str, object] = {
        "claims": claims,
        "coverage": {"docs": 16, "mentions": mentions, "min_mentions": 1},
        "floors": [
            {"label": "node 지목 산문", "observed": mentions, "minimum": 1, "margin": mentions - 1, "why": "기준 관측"},
            {"label": "상태 주장", "observed": ok + fixed + stale, "minimum": 1, "margin": 0, "why": "기준 관측"},
        ],
        "counts": {"claims": ok + fixed + stale, "ok": ok, "fixed": fixed, "stale": stale, "unknown": unknown},
    }
    if probe_present:
        report["probe"] = {
            "cases": 17,
            "failures": [] if probe_ok else ["통과 어휘가 사라졌다: ['green']"],
            "ok": probe_ok,
        }
    if exit_code is not None:
        report["exit_code"] = exit_code
    return report


def test_state_claims_need_a_recorded_floor_basis(review: Any) -> None:  # noqa: ANN401
    """하한 근거를 기록한 artifact 가 없으면 통과하지 않는다 — 값 없는 하한은 판단 근거가 아니다."""

    result = review.check_state_claims(None, _state_claim_report(fixed=4))

    assert result.passed is False
    assert "하한 근거를 기록하지 않은" in result.detail


def test_state_claims_artifact_must_be_current(review: Any) -> None:  # noqa: ANN401
    """기록된 하한·관측이 새 측정과 다르면 실패한다 — 저장본을 그대로 두고 새 수치를 인용하지 않는다."""

    result = review.check_state_claims(_state_claim_report(fixed=4), _state_claim_report(fixed=4, mentions=7))

    assert result.passed is False
    assert "최신이 아니다" in result.detail


def test_state_claim_floor_without_a_reason_is_rejected(review: Any) -> None:  # noqa: ANN401
    """하한에 근거(`why`)가 비어 있으면 실패한다 — 나중에 내려도 되는지 판단할 수 없는 값이기 때문이다."""

    report = _state_claim_report(fixed=4)
    floors = [dict(item) for item in report["floors"]]  # type: ignore[union-attr]
    floors[0]["why"] = ""
    report["floors"] = floors
    result = review.check_state_claims(report, report)

    assert result.passed is False
    assert "근거(`why`) 없는 하한" in result.detail


def test_state_claim_report_without_floors_is_rejected(review: Any) -> None:  # noqa: ANN401
    """하한이 아예 없는 측정은 통과하지 않는다(주장 0건으로 조용히 통과할 수 있는 상태)."""

    report = _state_claim_report(fixed=4)
    del report["floors"]
    result = review.check_state_claims(report, report)

    assert result.passed is False
    assert "탐지력 하한이 artifact 에 없다" in result.detail


def test_stale_state_claim_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """지금 트리와 어긋나는 상태 주장이 정정 없이 남으면 리뷰가 실패한다."""

    report = _state_claim_report(stale=1)
    result = review.check_state_claims(report, report)
    assert result.passed is False
    assert "어긋나는 상태 주장" in result.detail
    assert "T03.md" in result.detail


def test_corrected_state_claim_passes_and_is_counted(review: Any) -> None:  # noqa: ANN401
    """정정 표기가 붙은 주장은 통과하고, 몇 건인지 수치로 남는다."""

    report = _state_claim_report(fixed=4)
    result = review.check_state_claims(report, report)
    assert result.passed is True
    assert result.observed == 4
    assert "정정 붙임 4" in result.detail


def test_unjudgeable_state_claim_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """상태를 판정하지 못한 주장은 통과시키지 않는다 — 확인 불가를 통과로 쓰지 않는다."""

    report = _state_claim_report(unknown=2)
    result = review.check_state_claims(report, report)
    assert result.passed is False
    assert "판정하지 못한" in result.detail


def test_review_rejects_a_failed_self_probe(review: Any) -> None:  # noqa: ANN401
    """감사자 자기시험이 실패하면 리뷰가 실패한다 — 판독 규칙이 깨진 실행은 증거가 아니다."""

    report = _state_claim_report(probe_ok=False)
    result = review.check_state_claims(report, report)
    assert result.passed is False
    assert "자기시험" in result.detail


def test_review_rejects_a_missing_self_probe(review: Any) -> None:  # noqa: ANN401
    """자기시험 결과가 아예 없으면 통과시키지 않는다 — 확인하지 않은 판독력을 인정하지 않는다."""

    report = _state_claim_report(probe_present=False)
    result = review.check_state_claims(report, report)
    assert result.passed is False
    assert "자기시험 결과가 없다" in result.detail


def test_review_rejects_a_blind_audit(review: Any) -> None:  # noqa: ANN401
    """node 를 지목한 산문이 하나도 안 보이면 리뷰가 실패한다(주장 0건으로 조용히 통과하지 않는다)."""

    report = _state_claim_report(mentions=0)
    result = review.check_state_claims(report, report)
    assert result.passed is False
    assert "볼 수 없는" in result.detail


def test_repository_state_claims_are_judged(measurement: Any) -> None:  # noqa: ANN401
    """이 저장소의 상태 주장은 전부 판정돼 있고 낡은 채로 남은 것이 없다."""

    check = next(c for c in measurement.checks if c.name == "state_claims")
    assert check.passed is True, check.detail
    assert measurement.measured["state_claims_stale"] == 0
    assert measurement.measured["state_claims"] >= 1


def test_repository_audit_proves_its_own_sight(measurement: Any) -> None:  # noqa: ANN401
    """감사가 이 저장소에서 실제로 보고 있다 — mention 이 주장을 덮고, 자기시험이 돌아 있다."""

    assert measurement.measured["state_claim_mentions"] >= measurement.measured["state_claims"]
    assert measurement.measured["state_claim_probe_cases"] >= 1


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


def _canary_report(
    *,
    harnesses: int = 6,
    blind: str | None = None,
    unjustified: str | None = None,
    unhealthy: str | None = None,
    exit_code: int | None = 0,
    counted_ok: int | None = None,
) -> dict[str, object]:
    """카나리아 JSON 의 최소 형태 — 이름만 바꿔 네 가지 결함을 각각 재현한다."""

    names = [
        "digest_drift",
        "regression_ledger",
        "audit_state_claims",
        "audit_enum_identity",
        "audit_test_namespace_purge",
        "measure_cognitive_surface",
    ]
    items: list[dict[str, object]] = []
    for name in names[:harnesses]:
        items.append(
            {
                "name": name,
                "healthy": not (unhealthy == name),
                "bites": not (blind == name),
                "carries_reason": not (unjustified == name),
            }
        )
    ok = sum(1 for item in items if item["healthy"] and item["bites"] and item["carries_reason"])
    report: dict[str, object] = {
        "harnesses": items,
        "counts": {"harnesses": len(items), "ok": ok if counted_ok is None else counted_ok},
    }
    if exit_code is not None:
        report["exit_code"] = exit_code
    return report


def test_harness_canary_missing_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """카나리아를 돌리지 못한 실행은 통과하지 않는다 — 하한이 무는지 확인하지 않았다."""

    result = review.check_harness_canary(None)

    assert result.passed is False
    assert "돌리지 못했다" in result.detail


def test_decorative_floor_is_rejected_by_the_review(review: Any) -> None:  # noqa: ANN401
    """눈멀게 한 사본을 막지 못하는 하한은 장식이라 실패한다."""

    result = review.check_harness_canary(_canary_report(blind="regression_ledger"))

    assert result.passed is False
    assert "장식이다" in result.detail
    assert "regression_ledger" in result.detail


def test_floor_without_recorded_basis_is_rejected_by_the_review(review: Any) -> None:  # noqa: ANN401
    """차단 문장에 하한 근거를 싣지 않으면 실패한다 — 왜 막았는지 말하지 않는 차단은 판정이 아니다."""

    result = review.check_harness_canary(_canary_report(unjustified="audit_enum_identity"))

    assert result.passed is False
    assert "근거를 싣지 않은" in result.detail
    assert "audit_enum_identity" in result.detail


def test_floor_that_blocks_healthy_measurement_is_rejected(review: Any) -> None:  # noqa: ANN401
    """정상 측정까지 막는 하한은 탐지력이 아니라 오탐이라 실패한다(카나리아 자신이 실제로 이 버그를 냈다)."""

    result = review.check_harness_canary(_canary_report(unhealthy="regression_ledger"))

    assert result.passed is False
    assert "정상 측정을 막은" in result.detail


def test_canary_seeing_no_harness_is_rejected(review: Any) -> None:  # noqa: ANN401
    """harness 를 하나도 보지 않은 카나리아는 통과하지 않는다."""

    result = review.check_harness_canary({"harnesses": [], "counts": {"harnesses": 0, "ok": 0}})

    assert result.passed is False
    assert "하나도 보지 않았다" in result.detail


def test_canary_report_without_an_exit_code_is_rejected(review: Any) -> None:  # noqa: ANN401
    """종료 코드 없는 보고는 통과하지 않는다 — 스스로 실패했는지 알 수 없는 보고는 판정이 아니다."""

    result = review.check_harness_canary(_canary_report(exit_code=None))

    assert result.passed is False
    assert "종료 코드 없이 온 보고" in result.detail


def test_canary_exit_code_contradicting_its_own_report_is_rejected(review: Any) -> None:  # noqa: ANN401
    """보고는 전부 통과라는데 카나리아는 실패했다고 하면 모순이라 실패한다."""

    result = review.check_harness_canary(_canary_report(exit_code=1))

    assert result.passed is False
    assert "모순" in result.detail
    assert "exit 1" in result.detail


def test_blind_floor_keeps_its_diagnosis_through_the_seam(review: Any) -> None:  # noqa: ANN401
    """카나리아가 exit 1 로 끝나도 **어느 harness 가 못 물었는지**가 판정 문장에 남는다(진단을 뭉개지 않는다)."""

    result = review.check_harness_canary(_canary_report(exit_code=1, blind="digest_drift"))

    assert result.passed is False
    assert "장식이다" in result.detail
    assert "digest_drift" in result.detail
    assert "카나리아 exit 1" in result.detail


def test_canary_total_disagreeing_with_its_items_is_rejected(review: Any) -> None:  # noqa: ANN401
    """합계가 항목과 다르면 실패한다 — 보고의 수치를 그대로 믿을 수 없다."""

    result = review.check_harness_canary(_canary_report(counted_ok=6, blind="digest_drift"))

    assert result.passed is False
    assert "합계가 항목과 다르다" in result.detail


def test_measure_canary_keeps_the_report_when_the_run_fails(review: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """카나리아가 exit 1 이어도 JSON 이 읽히면 그대로 쓴다(진단과 판정이 만나는 이음매에서 정보를 잃지 않는다)."""

    payload = json.dumps(_canary_report(exit_code=1, blind="regression_ledger"))

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=payload, stderr="")

    monkeypatch.setattr(review.subprocess, "run", fake_run)
    report = review.measure_canary()

    assert report is not None
    assert report["exit_code"] == 1
    result = review.check_harness_canary(report)
    assert result.passed is False
    assert "regression_ledger" in result.detail


def test_measure_canary_returns_nothing_when_the_output_is_not_json(
    review: Any, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN401
    """JSON 이 아니면(예: import 오류) None 이다 — 읽을 수 없는 출력을 통과로 쓰지 않는다."""

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="Traceback...", stderr="boom")

    monkeypatch.setattr(review.subprocess, "run", fake_run)

    assert review.measure_canary() is None


def test_canary_markers_come_from_the_report(review: Any) -> None:  # noqa: ANN401
    """마커로 고정할 두 값(harness 수·문 수)을 카나리아 보고에서 센다."""

    assert review.canary_measured(_canary_report()) == {"canary_harnesses": 6, "canary_ok": 6}
    assert review.canary_measured(_canary_report(blind="digest_drift")) == {
        "canary_harnesses": 6,
        "canary_ok": 5,
    }


def test_repository_canary_bites_on_every_harness(review: Any) -> None:  # noqa: ANN401
    """저장소의 카나리아가 여섯 harness 전부에서 실제로 무는지(리뷰가 인용하는 수치의 출처)."""

    report = review.measure_canary()
    assert report is not None, f"{review.CANARY_SCRIPT} 를 돌리지 못했다"
    result = review.check_harness_canary(report)
    assert result.passed is True, result.detail
    assert result.observed >= 6, result.detail


def _rehearsal_layer(name: str, **defects: object) -> dict[str, object]:
    """리허설 한 층의 최소 보고 — 이름만 바꾸지 않고 **결함별 변형**을 만든다."""

    item: dict[str, object] = {
        "layer": name,
        "planted": f"probe/{name}.py",
        "dirty_exit": 1,
        "seen": 1,
        "named": True,
        "spoken": True,
        "clean_exit": 0,
        "blind_exit": 1,
        "crashed": False,
    }
    item.update(defects)
    item["ok"] = (
        item["dirty_exit"] == 1
        and item["seen"] >= 1
        and bool(item["named"])
        and bool(item["spoken"])
        and item["clean_exit"] == 0
        and item["blind_exit"] != 0
        and not item["crashed"]
    )
    item["problems"] = [] if item["ok"] else ["probe"]
    return item


def _rehearsal_report(
    *,
    layers: list[dict[str, object]] | None = None,
    exit_code: int | None = 0,
    counted_ok: int | None = None,
    declared: dict[str, str] | None = None,
    floors: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """red 리허설 JSON 의 최소 형태 — 한 층을 결함 상태로 바꾸어 판정 규칙을 재현한다."""

    items = layers if layers is not None else [_rehearsal_layer("audit_enum_identity")]
    ok = sum(1 for item in items if item.get("ok"))
    report: dict[str, object] = {
        "layers": items,
        "counts": {"layers": len(items), "ok": ok if counted_ok is None else counted_ok},
        "declared": declared if declared is not None else {"review": "리허설을 읽고 판정하는 층이다"},
        "floors": floors
        if floors is not None
        else [{"label": "리허설 대상", "observed": 2, "minimum": 2, "why": "근거"}],
        "probe": {"cases": 19, "failures": [], "ok": True},
    }
    if exit_code is not None:
        report["exit_code"] = exit_code
    return report


def test_red_rehearsal_missing_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """리허설을 돌리지 못한 실행은 통과하지 않는다 — 심어 보지 않은 ‘위반 0건’ 은 관찰이 아니다."""

    result = review.check_red_rehearsal(None)

    assert result.passed is False
    assert "돌리지 못했다" in result.detail


def test_a_layer_that_never_saw_the_planted_violation_is_rejected(review: Any) -> None:  # noqa: ANN401
    """심은 위반을 한 건도 못 본 층은 실패다 — green 이 ‘못 봐서’ 일 수 있다."""

    result = review.check_red_rehearsal(
        _rehearsal_report(layers=[_rehearsal_layer("audit_enum_identity", seen=0, named=False, spoken=False)])
    )

    assert result.passed is False
    assert "한 건도 보지 못한" in result.detail
    assert "audit_enum_identity" in result.detail


def test_a_layer_that_does_not_go_red_is_rejected(review: Any) -> None:  # noqa: ANN401
    """심은 위반을 보고도 exit 0 이면 실패다(리뷰 자신의 검사도 결함 상태로 확인한다)."""

    result = review.check_red_rehearsal(
        _rehearsal_report(layers=[_rehearsal_layer("audit_enum_identity", dirty_exit=0)])
    )

    assert result.passed is False
    assert "red 를 내지 못한" in result.detail


def test_a_false_positive_control_is_rejected(review: Any) -> None:  # noqa: ANN401
    """허용 형태를 위반으로 보는 층은 실패다 — 그 리허설은 심은 위반이 아니라 트리 모양을 본 것이다."""

    result = review.check_red_rehearsal(
        _rehearsal_report(layers=[_rehearsal_layer("audit_test_namespace_purge", clean_exit=1)])
    )

    assert result.passed is False
    assert "오탐" in result.detail
    assert "audit_test_namespace_purge" in result.detail


def test_a_layer_that_passes_an_empty_tree_is_rejected(review: Any) -> None:  # noqa: ANN401
    """빈 트리를 통과시키는 층은 ‘위반 0건’ 과 ‘못 봄’ 을 구분하지 못한다 — 실패다."""

    result = review.check_red_rehearsal(
        _rehearsal_report(layers=[_rehearsal_layer("audit_enum_identity", blind_exit=0)])
    )

    assert result.passed is False
    assert "아무것도 없는 트리를 통과시킨" in result.detail


def test_rehearsal_exit_code_contract_matches_the_canary(review: Any) -> None:  # noqa: ANN401
    """종료 코드 없는 보고·모순·합계 불일치는 카나리아와 **같은 규칙**으로 실패다."""

    missing = review.check_red_rehearsal(_rehearsal_report(exit_code=None))
    assert missing.passed is False
    assert "종료 코드 없이" in missing.detail

    contradiction = review.check_red_rehearsal(_rehearsal_report(exit_code=1))
    assert contradiction.passed is False
    assert "모순" in contradiction.detail

    mismatch = review.check_red_rehearsal(_rehearsal_report(counted_ok=0))
    assert mismatch.passed is False
    assert "합계가 항목과 다르다" in mismatch.detail


def test_rehearsal_without_reasons_is_rejected(review: Any) -> None:  # noqa: ANN401
    """이유 없는 생략(선언 없음·하한 근거 없음·자기시험 없음)은 실패다."""

    no_declared = review.check_red_rehearsal(_rehearsal_report(declared={}))
    assert no_declared.passed is False
    assert "이유" in no_declared.detail

    no_why = review.check_red_rehearsal(
        _rehearsal_report(floors=[{"label": "리허설 대상", "observed": 2, "minimum": 2, "why": ""}])
    )
    assert no_why.passed is False
    assert "근거" in no_why.detail


def test_rehearsal_markers_come_from_the_report(review: Any) -> None:  # noqa: ANN401
    """마커로 고정할 두 값(리허설 층 수·red 를 낸 층 수)을 보고에서 센다."""

    assert review.rehearsal_measured(_rehearsal_report()) == {"rehearsal_layers": 1, "rehearsal_ok": 1}
    assert review.rehearsal_measured(
        _rehearsal_report(layers=[_rehearsal_layer("audit_enum_identity", dirty_exit=0)])
    ) == {"rehearsal_layers": 1, "rehearsal_ok": 0}


def test_repository_rehearsal_goes_red_for_every_planted_layer(review: Any) -> None:  # noqa: ANN401
    """저장소의 리허설이 심는 층 전부에서 실제로 red 를 내는지(리뷰가 인용하는 수치의 출처)."""

    report = review.measure_red_rehearsal()
    assert report is not None, f"{review.REHEARSAL_SCRIPT} 를 돌리지 못했다"
    result = review.check_red_rehearsal(report)
    assert result.passed is True, result.detail
    assert result.observed >= 2, result.detail


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


def _gate_report(review: Any, **changes: object) -> dict[str, object]:  # noqa: ANN401
    """저장소 증거 게이트의 실제 명세 — `**changes` 로 한 자리씩 결함을 재현한다."""

    report = review.measure_evidence_gate(review.load_evidence_gate())
    assert report is not None
    merged = dict(report)
    merged.update(changes)
    return merged


def test_repository_evidence_gate_binds_every_layer(review: Any) -> None:  # noqa: ANN401
    """저장소의 게이트가 여섯 층을 실제로 묶고 있는지(리뷰가 인용하는 수치의 출처)."""

    report = _gate_report(review)
    result = review.check_evidence_gate(report)

    assert result.passed is True, result.detail
    assert report["probe"]["ok"] is True, report["probe"]
    assert report["fast"], "fast tier 가 비어 있다 — 기본 실행이 아무 층도 돌지 않는다"
    for floor in report["floors"]:
        assert str(floor["why"]).strip(), f"하한 {floor['label']} 에 근거가 없다"


def test_every_layer_is_a_stage_of_the_gate(review: Any) -> None:  # noqa: ANN401
    """카나리아가 아는 층은 전부 게이트의 stage 다 — 게이트 자신만 재귀 때문에 빠진다."""

    report = _gate_report(review)
    names = set(report["names"])
    canary = review.measure_canary()
    assert canary is not None
    known = {item["name"] for item in canary["harnesses"]}

    assert known - names == {"evidence_gate"}
    assert {"review", "canary"} <= names


def test_missing_gate_fails_the_review(review: Any) -> None:  # noqa: ANN401
    """게이트를 불러오지 못하면 통과하지 않는다 — 층마다 있는 게이트를 도는 명령이 없다면 기억으로만 돌아간다."""

    result = review.check_evidence_gate(None)

    assert result.passed is False
    assert "불려오지 않는다" in result.detail


def test_gate_without_stages_is_rejected(review: Any) -> None:  # noqa: ANN401
    """stage 가 비면 실패한다 — '볼 것이 없음' 은 '문제 없음' 이 아니다."""

    result = review.check_evidence_gate(_gate_report(review, stages=[], names=[]))

    assert result.passed is False
    assert "stage 가 하나도 없다" in result.detail


def test_gate_stage_with_missing_script_is_rejected(review: Any) -> None:  # noqa: ANN401
    """stage 가 없는 스크립트를 가리키면 실패한다(그 층은 영영 돌지 않는다)."""

    result = review.check_evidence_gate(
        _gate_report(review, stages=[{"name": "ghost", "tier": "fast", "script": "ghost_layer.py", "args": []}])
    )

    assert result.passed is False
    assert "스크립트가 없다" in result.detail


def test_gate_without_self_probe_is_rejected(review: Any) -> None:  # noqa: ANN401
    """자기시험이 없으면 실패한다 — 판정 규칙을 확인하지 않은 게이트는 명단일 뿐이다."""

    result = review.check_evidence_gate(_gate_report(review, probe={}))

    assert result.passed is False
    assert "자기시험 결과가 없다" in result.detail


def test_gate_with_failing_self_probe_is_rejected(review: Any) -> None:  # noqa: ANN401
    """자기시험이 실패하면 실패한다 — 판정 규칙이 깨졌다는 사실이 이유와 함께 남는다."""

    result = review.check_evidence_gate(
        _gate_report(review, probe={"cases": 3, "failures": ["pass 는 통과다"], "ok": False})
    )

    assert result.passed is False
    assert "자기시험 실패" in result.detail
    assert "pass 는 통과다" in result.detail


def test_gate_floor_without_basis_is_rejected(review: Any) -> None:  # noqa: ANN401
    """하한에 근거가 없으면 실패한다 — 값만 남으면 나중에 내려도 되는지 판단할 수 없다."""

    result = review.check_evidence_gate(
        _gate_report(review, floors=[{"label": "stage", "observed": 8, "minimum": 8, "why": "  "}])
    )

    assert result.passed is False
    assert "근거" in result.detail


def test_gate_with_unknown_tier_is_rejected(review: Any) -> None:  # noqa: ANN401
    """모르는 tier 를 쓰는 stage 는 실패한다 — 그 층은 어느 실행에서도 돌지 않는다."""

    result = review.check_evidence_gate(_gate_report(review, tiers=["fast"]))

    assert result.passed is False
    assert "모르는 tier" in result.detail


def test_gate_with_empty_fast_tier_is_rejected(review: Any) -> None:  # noqa: ANN401
    """기본 실행이 아무 층도 돌지 않으면 실패한다."""

    result = review.check_evidence_gate(_gate_report(review, fast=[]))

    assert result.passed is False
    assert "fast tier 가 비어 있다" in result.detail


def test_repository_gate_baseline_is_recorded(review: Any) -> None:  # noqa: ANN401
    """저장소의 기준 파일이 기록돼 있다 — 기준 없는 게이트는 추이를 말할 수 없다."""

    baseline = _gate_report(review)["baseline"]

    assert baseline["exists"] is True, baseline
    assert baseline["readable"] is True, baseline
    assert str(baseline["method"]).strip()
    assert str(baseline["recorded_on"]).strip()
    assert baseline["layers"] >= 7


def test_gate_without_a_baseline_is_rejected(review: Any) -> None:  # noqa: ANN401
    """기준 파일이 없으면 실패한다 — 그 상태의 추이는 매번 '기준 없음' 이다."""

    report = _gate_report(review, baseline={"path": "b.json", "exists": False, "readable": False, "layers": 0})
    result = review.check_evidence_gate(report)

    assert result.passed is False
    assert "기준 파일이 없다" in result.detail


def test_gate_with_an_unreadable_baseline_is_rejected(review: Any) -> None:  # noqa: ANN401
    """깨진 기준을 “기준 없음” 으로 삼키지 않는다."""

    report = _gate_report(review, baseline={"path": "b.json", "exists": True, "readable": False, "layers": 0})
    result = review.check_evidence_gate(report)

    assert result.passed is False
    assert "읽지 못한다" in result.detail


def test_gate_baseline_without_a_method_is_rejected(review: Any) -> None:  # noqa: ANN401
    """무엇을 보고 승인했는지 없는 기준은 근거가 아니다."""

    report = _gate_report(
        review,
        baseline={
            "path": "b.json",
            "exists": True,
            "readable": True,
            "layers": 8,
            "method": "  ",
            "recorded_on": "2026-01-01",
        },
    )
    result = review.check_evidence_gate(report)

    assert result.passed is False
    assert "method" in result.detail


def test_gate_baseline_without_a_date_is_rejected(review: Any) -> None:  # noqa: ANN401
    """언제 승인한 상태인지 모르는 기준도 실패한다."""

    report = _gate_report(
        review,
        baseline={"path": "b.json", "exists": True, "readable": True, "layers": 8, "method": "m", "recorded_on": ""},
    )
    result = review.check_evidence_gate(report)

    assert result.passed is False
    assert "recorded_on" in result.detail


def test_gate_stage_count_is_a_marker(review: Any) -> None:  # noqa: ANN401
    """stage 수는 measured 마커로 고정된다 — 명단이 줄면 문서 마커가 어긋난다."""

    report = _gate_report(review)

    assert review.evidence_gate_measured(report) == {"evidence_gate_stages": len(report["stages"])}
    assert review.evidence_gate_measured(None) == {}


def test_failure_lines_name_each_failing_check_with_its_reason(review: Any) -> None:  # noqa: ANN401
    """실패 문장은 검사 이름과 이유를 담는다 — 게이트가 이 출력에서 어느 층이 얕은지 읽는다."""

    measurement = review.ReviewMeasurement(
        principles=(),
        source_questions=(),
        drift_questions=(),
        checks=(
            review.CheckResult(name="doc_links_resolve", passed=True, detail="ok"),
            review.CheckResult(name="citation_tracking", passed=False, detail="추적되지 않는 인용 1건"),
        ),
    )

    assert review.failure_lines(measurement) == ["[FAIL] citation_tracking: 추적되지 않는 인용 1건"]


def test_digest_report_without_an_exit_code_is_rejected(review: Any) -> None:  # noqa: ANN401
    """종료 코드 없는 보고는 판정이 아니다 — 스스로 실패했는지 알 수 없는 수치를 쓰지 않는다."""

    report = _drift_report(exit_code=None)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "종료 코드가 없다" in result.detail


def test_digest_report_contradicting_its_own_exit_code_is_rejected(review: Any) -> None:  # noqa: ANN401
    """보고서는 문제 없다는데 실행이 스스로 실패했다면 둘 중 하나는 거짓이라 실패한다."""

    report = _drift_report(exit_code=1)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "모순" in result.detail


def test_state_claims_contradicting_its_own_exit_code_is_rejected(review: Any) -> None:  # noqa: ANN401
    """같은 규칙을 상태 주장 감사에도 적용한다(보고는 통과인데 스스로 실패했다고 말함)."""

    report = _state_claim_report(fixed=4, exit_code=1)
    result = review.check_state_claims(report, report)

    assert result.passed is False
    assert "모순" in result.detail


def test_state_claims_without_an_exit_code_is_rejected(review: Any) -> None:  # noqa: ANN401
    """종료 코드를 싣지 않은 보고도 통과시키지 않는다."""

    report = _state_claim_report(fixed=4, exit_code=None)
    result = review.check_state_claims(report, report)

    assert result.passed is False
    assert "종료 코드가 없다" in result.detail


def test_exit_code_check_does_not_double_count_a_real_defect(review: Any) -> None:  # noqa: ANN401
    """이미 지목된 결함은 모순으로 다시 세지 않는다 — 같은 사실을 두 번 적으면 판정이 흐려진다."""

    report = _drift_report(missing=1, exit_code=1)
    result = review.check_digest_report(report, report)

    assert result.passed is False
    assert "모순" not in result.detail
    assert "파일이 없는데 digest 를 못 박은 항목" in result.detail


def test_measure_digest_drift_keeps_the_report_when_the_run_fails(review: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """exit 1 이어도 JSON 이 읽히면 그대로 쓴다 — 진단을 이음매에서 뭉개지 않는다."""

    payload = json.dumps(_drift_report(missing=1))

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=payload, stderr="[FAIL] 파일이 없다")

    monkeypatch.setattr(review.subprocess, "run", fake_run)
    report = review.measure_digest_drift()

    assert report is not None
    assert report["exit_code"] == 1
    assert review.check_digest_report(report, report).passed is False


def test_measure_state_claims_returns_nothing_when_the_output_is_not_json(
    review: Any, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN401
    """읽을 수 없는 출력은 통과로 쓰지 않는다(import 오류·traceback)."""

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="Traceback...", stderr="boom")

    monkeypatch.setattr(review.subprocess, "run", fake_run)

    assert review.measure_state_claims() is None


def test_quiet_run_still_says_which_check_failed(
    review: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # noqa: ANN401
    """`--quiet` 는 표만 숨긴다 — 실패 이유를 숨기면 그 층을 다시 돌려야 어디가 얕은지 안다."""

    measurement = review.ReviewMeasurement(
        principles=(),
        source_questions=(),
        drift_questions=(),
        checks=(review.CheckResult(name="measured_markers", passed=False, detail="evidence_gate_stages 마커가 없다"),),
    )
    monkeypatch.setattr(review, "measure", lambda: measurement)

    code = review.main(["--quiet"])
    captured = capsys.readouterr()

    assert code == review.EXIT_FAILED
    assert captured.out == ""
    assert "[FAIL] measured_markers: evidence_gate_stages 마커가 없다" in captured.err
