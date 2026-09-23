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
    assert audit.gate_failures(judged) == []


def test_stale_claim_without_a_correction_fails_the_gate(audit: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """지금 통과하는 시험을 “실패한다” 고 적고 정정도 없으면 실패다."""

    doc = write_doc(tmp_path, f"`{PASSING_NODE}` 는 실패한다.\n")
    judged = audit.measure([doc])

    assert judged[0].status == "stale"
    problems = audit.gate_failures(judged)
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
    assert audit.gate_failures(judged) == []


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
