"""증거 digest drift 측정(`scripts/digest_drift.py`)의 계약.

이 스크립트가 **주장하는 것**을 시험으로 고정한다:

  * 증거 문서가 파일에 못 박은 sha256 을 실제로 읽어낸다(관행 형태를 놓치지 않는다).
  * pin 을 셋으로만 가른다 — 그대로 / 움직임(그 뒤에 파일이 바뀜) / 깨짐(파일이 없음).
  * digest 를 현재 값으로 **갱신하지 않는다** — 갱신은 재확인 주장이라 사람의 몫이다.
  * 저장본(artifact)이 낡았거나 파일 없는 pin 이 있으면 `--gate` 가 실패한다.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 실제 파일 — 합성 입력이 실재 경로를 가리켜야 해석 단계를 시험할 수 있다.
REAL_FILE = "tests/cognitive/test_surface.py"
SHORTHAND = "tools/ssak_bundle_store.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("digest_drift", REPO_ROOT / "scripts" / "digest_drift.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["digest_drift"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drift() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script()


def digest_of(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def write_pin(tmp_path: Path, citation: str, recorded: str) -> Path:
    """pin 한 줄만 담은 가짜 증거 문서를 만든다."""

    docs = tmp_path / "ssak-ai-core"
    docs.mkdir(exist_ok=True)
    (docs / "T99_synthetic.md").write_text(f"  - {citation} (sha256 {recorded}…)\n", encoding="utf-8")
    return docs


# --------------------------------------------------------------------------- 판독


def test_pin_is_read_from_the_repository_wording(drift: Any) -> None:  # noqa: ANN401
    """관행 형태(`경로 (sha256 앞자리…)`)에서 경로와 digest 를 함께 읽는다."""

    docs = REPO_ROOT / "docs" / "ssak-ai-core" / "evidence"
    text = (docs / "T01a_typed_model.md").read_text(encoding="utf-8")
    pairs = drift._PIN_PATTERN.findall(text)

    assert pairs, "증거 문서에서 pin 을 하나도 읽지 못했다"
    paths = {path for path, _ in pairs}
    assert "src/antigravity_k/engine/cognitive/models.py" in paths
    assert all(len(prefix) >= 8 for _, prefix in pairs)


def test_only_sha256_hex_digits_count(drift: Any, tmp_path: Path) -> None:
    """digest 자리에 hex 가 없으면 pin 이 아니다(`sha256 를 통과한 뒤` 같은 산문)."""

    docs = tmp_path / "ssak-ai-core"
    docs.mkdir()
    (docs / "Z.md").write_text(
        f"- {REAL_FILE} 를 sha256 통과 뒤에만 실행한다\n- {SHORTHAND} (sha256 abcdef12…)\n",
        encoding="utf-8",
    )
    result = drift.measure(docs)

    assert [pin.path for pin in result.pins] == [SHORTHAND], "산문의 `sha256` 을 pin 으로 셌다"


# --------------------------------------------------------------------------- 판정


def test_matching_pin_is_recorded_as_match(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """그대로인 pin 은 match 로만 남고 파일 내용은 건드리지 않는다."""

    docs = write_pin(tmp_path, REAL_FILE, digest_of(REAL_FILE)[:16])
    before = (REPO_ROOT / REAL_FILE).read_bytes()
    result = drift.measure(docs)

    assert result.counts[drift.STATUS_MATCH] == 1
    assert result.counts[drift.STATUS_DRIFT] == 0
    assert (REPO_ROOT / REAL_FILE).read_bytes() == before, "측정이 파일을 건드렸다"


def test_changed_file_is_reported_as_drift_not_rewritten(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """파일이 바뀌면 drift 로 보고한다 — digest 를 현재 값으로 갱신하지 않는다."""

    docs = write_pin(tmp_path, REAL_FILE, "0000000000000000")
    result = drift.measure(docs)
    pin = next(iter(result.pins))

    assert pin.status == drift.STATUS_DRIFT
    assert pin.recorded == "0000000000000000", "기록된 digest 를 덮어썼다"
    assert pin.actual == digest_of(REAL_FILE)
    assert "T99_synthetic.md" in drift.describe(result)


def test_missing_file_is_reported_as_broken(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """파일이 없는데 digest 를 못 박았으면 깨진 pin 이다(움직임과 구분한다)."""

    docs = write_pin(tmp_path, "tests/test_t99_absent.py", "abcdef1234567890")
    result = drift.measure(docs)

    assert result.counts[drift.STATUS_MISSING] == 1
    assert next(iter(result.pins)).actual == ""


def test_shorthand_citation_is_resolved(drift: Any) -> None:  # noqa: ANN401
    """`tools/x.py` 축약 표기를 `src/antigravity_k/tools/x.py` 로 해석한다."""

    assert drift.resolve_citation(SHORTHAND) == REPO_ROOT / "src" / "antigravity_k" / SHORTHAND
    assert drift.resolve_citation("tests/test_t99_absent.py") is None


def test_measurement_is_deterministic(drift: Any) -> None:  # noqa: ANN401
    """두 번 재면 같은 값이다(artifact 최신성 비교가 흔들리지 않게)."""

    first = drift.measure()
    second = drift.measure()

    assert first.compared() == second.compared()
    assert first.pins == second.pins
    assert first.counts == second.counts


def test_repository_pins_are_all_resolvable(drift: Any) -> None:  # noqa: ANN401
    """이 저장소에는 파일이 없는 pin 이 없어야 한다(있으면 그 증거가 가리키는 것이 없다)."""

    result = drift.measure()

    assert result.counts[drift.STATUS_MISSING] == 0, [pin.path for pin in result.pins if pin.actual == ""]
    assert len(result.pins) > 0


# --------------------------------------------------------------------------- 산출물·게이트


def test_reverification_record_turns_drift_into_reverified(drift: Any, tmp_path: Path) -> None:
    """재확인 기록이 있고 그 뒤 파일이 그대로면 `reverified` 다 — `drift` 와 구분한다."""

    record = tmp_path / "reverification.json"
    docs = write_pin(tmp_path, REAL_FILE, "0000000000000000")
    drifted = drift.measure(docs, reverifications=record)
    assert next(iter(drifted.pins)).status == drift.STATUS_DRIFT, "기록 전에는 drift 다"

    recorded = drift.Reverification(
        doc="T99_synthetic.md",
        path=REAL_FILE,
        verified_digest=digest_of(REAL_FILE),
        verified_on="2026-09-23",
        method="시험용",
    )
    record.write_text(json.dumps({"entries": [recorded.as_mapping()]}), encoding="utf-8")
    reverified = drift.measure(docs, reverifications=record)
    pin = next(iter(reverified.pins))

    assert pin.status == drift.STATUS_REVERIFIED
    assert pin.reverified_on == "2026-09-23"
    assert reverified.counts[drift.STATUS_DRIFT] == 0


def test_reverification_goes_stale_when_the_file_moves_again(drift: Any, tmp_path: Path) -> None:
    """재확인은 면죄부가 아니다 — 그 뒤에 파일이 또 바뀌면 무효이고 게이트가 실패한다."""

    record = tmp_path / "reverification.json"
    docs = write_pin(tmp_path, REAL_FILE, "0000000000000000")
    recorded = drift.Reverification(
        doc="T99_synthetic.md",
        path=REAL_FILE,
        verified_digest="1" * 64,
        verified_on="2026-09-23",
        method="시험용",
    )
    record.write_text(json.dumps({"entries": [recorded.as_mapping()]}), encoding="utf-8")

    result = drift.measure(docs, reverifications=record)
    assert next(iter(result.pins)).status == drift.STATUS_STALE

    artifact = tmp_path / "digest_drift.json"
    artifact.write_text(json.dumps(result.as_mapping(), ensure_ascii=False), encoding="utf-8")
    problems = drift.gate_failures(result, artifact)
    assert any("무효" in problem for problem in problems)


def test_record_writes_only_the_pins_that_moved_along_with_a_method(
    drift: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--record` 는 움직인 pin 만 박고 방법 문장을 함께 남긴다(낡은·과장된 재확인을 만들지 않는다)."""

    record = tmp_path / "reverification.json"
    docs = write_pin(tmp_path, REAL_FILE, "0000000000000000")
    measured = drift.measure(docs, reverifications=record)

    exit_code, message = drift.write_reverification(
        "T99_synthetic.md", measured, method="계약 시험 재실행 후 확인", on="2026-09-23", path=record
    )
    payload = json.loads(record.read_text(encoding="utf-8"))

    assert exit_code == 0, message
    assert len(payload["entries"]) == 1, "움직인 pin 만 기록해야 한다"
    entry = payload["entries"][0]
    assert entry["verified_digest"] == digest_of(REAL_FILE)
    assert entry["verified_on"] == "2026-09-23"
    assert entry["method"] == "계약 시험 재실행 후 확인"
    _ = capsys


def test_record_does_nothing_when_no_pin_moved(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """이미 기록과 같은 pin 뿐이면 기록하지 않는다 — 낡은 재확인을 만들지 않는다."""

    record = tmp_path / "reverification.json"
    docs = write_pin(tmp_path, REAL_FILE, digest_of(REAL_FILE)[:16])
    measured = drift.measure(docs, reverifications=record)

    exit_code, message = drift.write_reverification(
        "T99_synthetic.md", measured, method="시험용", on="2026-09-23", path=record
    )

    assert exit_code == 0
    assert "기록할 것이 없다" in message
    assert record.exists() is False


def test_record_refuses_without_a_method(drift: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """무엇을 확인했는지 없이는 재확인이 아니다 — 기록을 거부한다."""

    record = tmp_path / "reverification.json"
    exit_code = drift.main(["--record", "T01a_typed_model.md", "--reverification", str(record)])

    assert exit_code == 1
    assert record.exists() is False
    assert "--method" in capsys.readouterr().err


def test_gate_requires_a_current_artifact(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """artifact 가 없으면 `--gate` 는 실패한다 — 측정 없이 수치를 인용하지 않는다."""

    problems = drift.gate_failures(drift.measure(), tmp_path / "absent.json")
    assert problems and "없거나" in problems[0]


def test_stale_artifact_fails_the_gate(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """저장본이 저장 뒤 바뀐 측정과 다르면 실패한다 — 썩은 수치를 통과시키지 않는다."""

    artifact = tmp_path / "digest_drift.json"
    stored = drift.measure().as_mapping()
    stored["counts"]["match"] = 0  # 저장 뒤에 파일이 바뀐 상황을 흠내낸다
    artifact.write_text(json.dumps(stored), encoding="utf-8")

    problems = drift.gate_failures(drift.measure(), artifact)
    assert problems and "최신이 아니다" in problems[0]


def test_gate_passes_with_a_current_artifact_and_no_broken_pins(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """최신 본이 있고 파일 없는 pin 이 없으면 통과한다(움직임 자체는 실패가 아니다)."""

    artifact = tmp_path / "digest_drift.json"
    # artifact 는 `compared()` 로 비교되는 부분을 그대로 담아야 한다(여기에는 하한 기록도 포함된다).
    artifact.write_text(json.dumps(drift.measure().compared(), ensure_ascii=False), encoding="utf-8")

    assert drift.gate_failures(drift.measure(), artifact) == []


def test_removing_the_floor_basis_makes_the_artifact_stale(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """하한의 근거를 바꾸고 artifact 를 다시 만들지 않으면 게이트가 실패한다."""

    original = drift.coverage_floors

    def without_reason(_drift: object) -> list[Any]:
        return [
            floor.__class__(floor.label, floor.observed, floor.minimum, why="") for floor in original(drift.measure())
        ]

    artifact = tmp_path / "digest_drift.json"
    stored = {**drift.measure().compared(), "floors": drift.floor_records(original(drift.measure()))}
    artifact.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    if hasattr(drift, "coverage_floors"):
        drift.coverage_floors = without_reason  # type: ignore[attr-defined]
    try:
        problems = drift.gate_failures(drift.measure(), artifact)
    finally:
        drift.coverage_floors = original  # type: ignore[attr-defined]

    assert any("최신이 아니다" in problem for problem in problems)


def test_broken_pin_fails_the_gate_even_with_a_current_artifact(drift: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """파일 없는 pin 은 통과시키지 않는다 — 가리키는 것이 없는 주장이다."""

    artifact = tmp_path / "digest_drift.json"
    artifact.write_text(json.dumps(drift.measure().as_mapping(), ensure_ascii=False), encoding="utf-8")
    stored = json.loads(artifact.read_text(encoding="utf-8"))
    stored["counts"]["missing"] = 1
    stored["pins"].append(
        {"doc": "Z.md", "path": "tests/test_t99_absent.py", "recorded": "abc", "actual": "", "status": "missing"}
    )
    artifact.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    problems = drift.gate_failures(drift.measure(), artifact)
    assert any("최신이 아니다" in problem for problem in problems)


def test_emit_json_writes_nothing_to_the_artifact(
    drift: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--emit-json` 은 stdout 만 쓴다 — 리뷰 검사가 artifact 를 건드리지 않고 잴 수 있게."""

    artifact = tmp_path / "digest_drift.json"
    exit_code = drift.main(["--emit-json", "--artifact", str(artifact)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert artifact.exists() is False, "--emit-json 이 artifact 를 썼다"
    assert set(payload["counts"]) == {
        "match",
        "reverified",
        "drift",
        "stale_reverification",
        "missing",
    }
    assert payload["source_head"]


def test_repository_artifact_is_current(drift: Any) -> None:  # noqa: ANN401
    """이 저장소의 artifact 는 최신이다 — 파일을 고쳤으면 다시 재야 한다."""

    problems = drift.gate_failures(
        drift.measure(), REPO_ROOT / "docs" / "ssak-ai-core" / "evidence" / "digest_drift.json"
    )
    assert problems == [], problems
