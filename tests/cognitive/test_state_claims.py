"""상태 주장 감사(`scripts/audit_state_claims.py`)의 계약.

이 감사가 **주장하는 것**을 시험으로 고정한다:

  * 산문(펜스 밖)에서만 주장을 뽑는다 — 코드 블록은 그때 돌린 기록이라 주장이 아니다.
  * **test node 를 지목한 문장만** 본다(파일 단위 서술은 조건문과 섞여 기계가 가를 수 없다).
  * 주장과 실제가 다르면 **정정 표기**가 있어야 하고, 없으면 게이트가 실패한다.
  * 정정 표기는 그 줄 뒤 가까이(5줄 안)에 있어야 한다 — 아무 데나 있으면 안 된다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# 이 저장소에서 지금 실제로 통과하는 시험 — 합성 입력이 실재 경로를 가리켜야 재판정을 시험할 수 있다.
PASSING_NODE = "tests/cognitive/test_context.py::test_estimate_tokens_is_deterministic"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_state_claims", REPO_ROOT / "scripts" / "audit_state_claims.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_state_claims"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script()


def write_doc(tmp_path: Path, body: str) -> Path:
    doc = tmp_path / "T99_synthetic.md"
    doc.write_text(body, encoding="utf-8")
    return doc


def gate(audit: Any, claims: list[Any]) -> list[str]:  # noqa: ANN401 - 스크립트 module
    """리뷰가 보는 조건 그대로 게이트를 돌린다 — 탐지력은 실제 증거 문서 기준으로 판정한다."""

    return audit.gate_failures(claims, audit.count_mentions(), audit.self_probe())


# --------------------------------------------------------------------------- 판독


def test_prose_claim_about_a_node_is_extracted(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """산문에서 node 를 지목한 상태 주장을 뽑는다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n")
    claims = audit.extract_claims([doc])

    assert len(claims) == 1
    assert claims[0].node == PASSING_NODE
    assert claims[0].claimed == "fails"


def test_fenced_block_is_a_record_not_a_claim(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """코드 블록 안의 명령·출력은 그때 돌린 기록이다 — 주장으로 세지 않는다."""

    doc = write_doc(
        tmp_path,
        f"기록:\n\n```sh\n.venv/bin/python -m pytest {PASSING_NODE} -q → 1 failed\n```\n",
    )

    assert audit.extract_claims([doc]) == []


def test_file_level_sentence_is_not_a_state_claim(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """파일 단위 서술은 조건문과 섞여 가를 수 없다 — node 를 지목한 문장만 본다."""

    doc = write_doc(tmp_path, "tests/cognitive/test_models.py 는 조건이 바뀌면 실패한다.\n")
    assert audit.extract_claims([doc]) == []


def test_same_node_claimed_twice_in_one_doc_is_judged_once(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """판정은 node 단위다 — 같은 문서의 중복 서술로 실패가 부풀지 않는다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n다시 말해 `{PASSING_NODE}` 는 red 다.\n")
    assert len(audit.extract_claims([doc])) == 1


# --------------------------------------------------------------------------- 판정


def test_claim_that_matches_the_tree_is_ok(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """실제와 맞는 주장은 그대로 통과한다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 통과한다.\n")
    judged = audit.measure([doc])

    assert judged[0].actual == "passes"
    assert judged[0].status == "ok"
    assert judged[0].stale is False
    assert gate(audit, judged) == []


def test_stale_claim_without_a_correction_fails_the_gate(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """지금 통과하는 시험을 “실패한다” 고 적고 정정도 없으면 실패다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n")
    judged = audit.measure([doc])

    assert judged[0].status == "stale"
    problems = gate(audit, judged)
    assert problems and "정정 표기 없음" in problems[0]


def test_nearby_correction_note_resolves_the_claim(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """그 줄 뒤 가까이에 날짜 있는 정정 표기가 있으면 역사로 남긴 것으로 본다."""

    doc = write_doc(
        tmp_path,
        f"`{PASSING_NODE}` 는 실패한다.\n\n> **2026-09-23 정정.** 그 뒤 등록으로 green 이 됐다.\n",
    )
    judged = audit.measure([doc])

    assert judged[0].status == "fixed"
    assert judged[0].stale is False
    assert gate(audit, judged) == []


def test_far_away_correction_does_not_count(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """정정은 그 주장 가까이에 있어야 한다 — 문서 끝의 정정은 이 문장을 덮지 않는다."""

    doc = write_doc(
        tmp_path,
        f"`{PASSING_NODE}` 는 실패한다.\n\n" + "\n" * 12 + "> **2026-09-23 정정.** 문서 끝의 정정.\n",
    )
    judged = audit.measure([doc])

    assert judged[0].status == "stale"


def test_correction_needs_a_date(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """날짜 없는 인용문은 정정 표기로 세지 않는다 — 언제 확인했는지가 없으면 재판정이 아니다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n\n> 정정. green 이 됐다.\n")
    judged = audit.measure([doc])

    assert judged[0].status == "stale"


def test_emit_json_also_reports_failure(
    audit: Any,  # noqa: ANN401
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON 을 내는 실행도 **판정을 종료 코드로** 말한다 — 낡은 주장이 있으면 exit 1.

    예전에는 이 경로가 결과와 무관하게 exit 0 을 냈다. 그래서 읽는 쪽(리뷰·증거 게이트)은 "돌았는데 통과" 와
    "돌았지만 이 감사가 스스로 실패했다" 를 구분할 수 없었고, `returncode != 0` 검사는 죽은 코드였다.
    """

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n")
    stale = audit.measure([doc])
    assert stale and stale[0].status == "stale"
    monkeypatch.setattr(audit, "measure", lambda: stale)
    artifact = tmp_path / "state_claims.json"

    exit_code = audit.main(["--emit-json", "--artifact", str(artifact)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == audit.EXIT_GATE
    assert payload["counts"]["stale"] == 1
    assert audit.main(["--gate", "--artifact", str(artifact)]) == audit.EXIT_GATE


def test_emit_json_reports_counts(audit: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """`--emit-json` 은 리뷰가 읽는 형태(주장별 상태 + 합계)를 낸다."""

    exit_code = audit.main(["--emit-json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert (
        payload["counts"]["claims"]
        == payload["counts"]["ok"]
        + payload["counts"]["fixed"]
        + payload["counts"]["stale"]
        + payload["counts"]["unknown"]
    )
    assert all("status" in claim for claim in payload["claims"])


# --------------------------------------------------------------------------- 감사자 자신의 이빨


def test_self_probe_passes_on_the_real_detector(audit: Any) -> None:  # noqa: ANN401
    """매 실행 자기시험은 실제 감사자에 대해 통과해야 한다 — 재판정 항목이 0건이면 검사하지 않은 것이다."""

    probe = audit.self_probe()

    assert probe.ok, probe.failures
    assert probe.cases >= len(audit._REQUIRED_FAIL_WORDS) + len(audit._REQUIRED_PASS_WORDS)


def test_self_probe_notices_an_emptied_vocabulary(audit: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """어휘를 통째로 비우면 주장 0건이 될 수 있다 — 자기시험이 그 눈먼 상태를 잡아야 한다."""

    monkeypatch.setattr(audit, "_FAILS", ())
    monkeypatch.setattr(audit, "_PASSES", ())

    assert audit.self_probe().ok is False
    assert audit.main(["--self-test"]) == 1


def test_self_probe_notices_a_deleted_word(audit: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """상수를 쓸어보기만 하면 **단어를 지우는** 변경을 놓친다 — 요구 어휘를 따로 고정해 그것도 잡는다."""

    monkeypatch.setattr(audit, "_PASSES", ("통과", "passed"))  # green 삭제
    probe = audit.self_probe()

    assert probe.ok is False
    assert any("green" in failure for failure in probe.failures)


def test_gate_fails_when_no_node_mention_is_found(audit: Any) -> None:  # noqa: ANN401
    """추적할 node 자체가 안 보이면 “주장 0건” 으로 통과하지 않는다 — 탐지력 하한이 실패시킨다."""

    problems = audit.gate_failures([], 0, audit.self_probe())

    assert any("볼 수 없는" in problem for problem in problems)
    assert any("하한" in problem and "근거" in problem for problem in problems)


def test_floors_record_the_reason_they_are_what_they_are(audit: Any) -> None:  # noqa: ANN401
    """하한은 값만으로는 판단할 수 없다 — 관측·여유·근거가 함께 돌아온다."""

    floors = audit.coverage_floors(6, 4)

    assert [floor.label for floor in floors] == ["node 지목 산문", "상태 주장"]
    assert all(floor.why.strip() for floor in floors), "하한 근거가 비었다"
    assert [floor.margin for floor in floors] == [5, 3]
    assert all("2026-09-23 기준 관측" in floor.why for floor in floors)


def test_emit_json_carries_floor_records(audit: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """리뷰가 읽는 JSON 에 하한 기록(값·관측·여유·근거)이 들어 있다."""

    assert audit.main(["--emit-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    floors = payload["floors"]
    assert {floor["label"] for floor in floors} == {"node 지목 산문", "상태 주장"}
    assert all(floor["why"] for floor in floors)
    assert all(floor["margin"] == floor["observed"] - floor["minimum"] for floor in floors)


def test_artifact_records_the_floor_basis(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """감사는 하한 근거와 그때의 관측을 artifact 로 남긴다 — 값이 어디서 왔는지 추적 가능해야 한다."""

    artifact = tmp_path / "state_claims.json"
    assert audit.main(["--artifact", str(artifact)]) == 0
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["floors"] and all(floor["why"] for floor in payload["floors"])
    assert payload["coverage"]["docs"] >= 1


def test_gate_fails_when_the_probe_fails(audit: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401
    """자기시험 실패는 판정과 무관하게 게이트 실패다 — 판독 규칙이 깨진 실행은 증거가 아니다."""

    monkeypatch.setattr(audit, "_FAILS", ())
    problems = audit.gate_failures([], 6, audit.self_probe())

    assert any("자기시험 실패" in problem for problem in problems)


def test_mentions_ignore_fenced_blocks_and_state_words(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """mention 은 상태 어휘가 없어도 세지만, 펜스 안은 세지 않는다(주장의 상한 집합)."""

    fence = "`" * 3
    doc = write_doc(
        tmp_path,
        f"`{PASSING_NODE}` 를 실행한다.\n\n{fence}\n`{PASSING_NODE}` 도 여기 있다.\n{fence}\n",
    )

    assert audit.count_mentions([doc]) == 1
    assert audit.extract_claims([doc]) == []


def test_emit_json_carries_coverage_and_probe(audit: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """리뷰가 읽는 JSON 에 탐지력(문서·mention 수)과 자기시험 결과가 들어 있다."""

    assert audit.main(["--emit-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["coverage"]["docs"] >= 1
    assert payload["coverage"]["mentions"] >= payload["counts"]["claims"]
    assert payload["probe"]["ok"] is True
    assert payload["probe"]["cases"] >= 1


def test_self_test_cli_does_not_run_tests(audit: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """`--self-test` 는 시험을 돌리지 않고 자기시험만 보고한다(오래 걸리지 않는다)."""

    assert audit.main(["--self-test"]) == 0
    out = capsys.readouterr().out

    assert "[self-probe]" in out
    assert "산문" in out
