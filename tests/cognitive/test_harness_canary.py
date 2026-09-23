"""하한 카나리아(`scripts/harness_canary.py`)의 계약 — **장식인 하한을 잡는가**.

카나리아는 “하한이 무는가” 를 묻는 도구이므로, 카나리아 자신이 눈이 멀면 마지막 구멍이 남는다.
그래서 여기서는 세 가지를 고정한다:

  * 정상 저장소에서 여섯 harness 가 모두 문다(정상 통과 · 눈멀게 한 사본 차단 · 근거 동봉).
  * 하한이 **없는** harness 는 통과가 아니라 실패로 보고된다(빈 목록을 “문제 없음” 으로 읽지 않는다).
  * `minimum=0` 처럼 **영원히 안 무는** 하한은 장식으로 잡힌다 — 이 경우가 없으면 카나리아는 형식이 된다.
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
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_canary() -> ModuleType:
    spec = importlib.util.spec_from_file_location("canary_under_test", SCRIPTS / "harness_canary.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def canary() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_canary()


# --------------------------------------------------------------------- 저장소의 실제 상태


def test_every_harness_floor_bites(canary: Any) -> None:  # noqa: ANN401
    """모든 harness 의 하한이 지금 저장소에서 실제로 문다 — 하나라도 안 물면 카나리아가 문제를 낸다."""

    results = canary.run()

    assert len(results) == len(canary.HARNESSES) == 7
    for result in results:
        assert result.ok, f"{result.name}: {result.problems}"
    assert all(result.floors >= 1 for result in results)


def test_canary_reads_recorded_floors_where_they_exist(canary: Any) -> None:  # noqa: ANN401
    """기록 artifact 가 있는 harness 는 **저장본**의 하한으로 판정한다(빈 원장으로 만든 기준은 오탐이 된다)."""

    assert set(canary.ARTIFACT_FLOORS) == {"digest_drift", "regression_ledger", "audit_state_claims"}
    for name, relative in canary.ARTIFACT_FLOORS.items():
        floors = canary.artifact_floors(name)
        assert floors, f"{name} 저장본에 floors 가 없다"
        assert all(floor.why.strip() for floor in floors)
        assert (REPO_ROOT / relative).exists()


def test_recorded_and_measured_floors_agree(canary: Any) -> None:  # noqa: ANN401
    """저장본의 관측값이 실제 측정과 같다 — 다르면 카나리아가 옛 기준을 시험하게 된다."""

    digest = canary.artifact_floors("digest_drift")
    module = canary.load_harness("digest_drift")
    live = module.coverage_floors(module.measure())

    assert [floor.observed for floor in digest] == [floor.observed for floor in live]
    assert [floor.minimum for floor in digest] == [floor.minimum for floor in live]


# --------------------------------------------------------------------- 카나리아 자신의 이빨


def test_a_harness_without_floors_is_reported_not_passed(canary: Any) -> None:  # noqa: ANN401
    """하한이 없는 harness 는 “막을 것이 없다” 가 아니라 실패다 — 빈 목록을 통과로 읽지 않는다."""

    module = canary.load_harness("audit_enum_identity")
    original = canary.harness_floors

    canary.harness_floors = lambda name, mod: []  # type: ignore[assignment]
    try:
        result = canary.inspect("audit_enum_identity", module)
    finally:
        canary.harness_floors = original  # type: ignore[assignment]

    assert result.ok is False
    assert any("하한이 없다" in problem for problem in result.problems)


def test_a_floor_that_never_bites_is_caught(canary: Any) -> None:  # noqa: ANN401
    """`minimum=0` 하한은 눈멀게 한 사본도 통과시킨다 — 카나리아가 그것을 장식으로 잡아야 한다."""

    module = canary.load_harness("audit_enum_identity")
    original = canary.harness_floors

    def decorative(name: str, mod: ModuleType) -> list[Any]:
        return [canary.Floor("스캔한 파일", 21, 0, why="2026-09-23 기준 관측: 21개")]

    canary.harness_floors = decorative  # type: ignore[assignment]
    try:
        result = canary.inspect("audit_enum_identity", module)
    finally:
        canary.harness_floors = original  # type: ignore[assignment]

    assert result.ok is False
    assert any("장식이다" in problem for problem in result.problems)


def test_a_floor_blocking_a_healthy_measurement_is_caught(canary: Any) -> None:  # noqa: ANN401
    """정상 측정을 막는 하한도 고장이다 — 하한이 난폭하면 게이트가 늘 빨개져 무시된다."""

    module = canary.load_harness("audit_enum_identity")

    def too_high(name: str, mod: ModuleType) -> list[Any]:
        return [canary.Floor("스캔한 파일", 21, 999, why="2026-09-23 기준 관측: 21개")]

    original = canary.harness_floors
    canary.harness_floors = too_high  # type: ignore[assignment]
    try:
        result = canary.inspect("audit_enum_identity", module)
    finally:
        canary.harness_floors = original  # type: ignore[assignment]

    assert result.healthy is False
    assert any("정상 측정을 막는다" in problem for problem in result.problems)


def test_a_floor_without_a_reason_is_caught(canary: Any) -> None:  # noqa: ANN401
    """근거 없는 하한은 기록이 없으므로 카나리아가 잡는다."""

    module = canary.load_harness("audit_enum_identity")
    original = canary.harness_floors

    def without_reason(name: str, mod: ModuleType) -> list[Any]:
        return [canary.Floor("스캔한 파일", 21, 1, why="")]

    canary.harness_floors = without_reason  # type: ignore[assignment]
    try:
        result = canary.inspect("audit_enum_identity", module)
    finally:
        canary.harness_floors = original  # type: ignore[assignment]

    assert result.ok is False
    assert any("근거가 없다" in problem for problem in result.problems)


def test_a_harness_that_raises_is_a_finding_not_a_crash(canary: Any) -> None:  # noqa: ANN401
    """harness 불러오기가 예외로 죽어도 카나리아는 그것을 판정으로 내놓는다(한 번에 다 보고한다)."""

    def explode(name: str) -> ModuleType:
        raise RuntimeError("harness 를 읽을 수 없다")

    original = canary.load_harness
    canary.load_harness = explode  # type: ignore[assignment]
    try:
        results = canary.run(("audit_enum_identity",))
    finally:
        canary.load_harness = original  # type: ignore[assignment]

    assert len(results) == 1
    assert results[0].ok is False
    assert any("예외로 죽었다" in problem for problem in results[0].problems)


# --------------------------------------------------------------------- CLI 계약


def test_gate_fails_when_a_floor_is_decorative(
    canary: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # noqa: ANN401, E501
    """장식 하한이 하나라도 있으면 `--gate` 가 exit 1 로 막는다."""

    def decorative() -> tuple[Any, ...]:
        return (
            canary.CanaryResult(
                name="probe",
                floors=1,
                healthy=True,
                bites=False,
                carries_reason=True,
                problems=("probe 의 하한이 눈멀게 한 사본을 막지 못한다(장식이다)",),
            ),
        )

    monkeypatch.setattr(canary, "run", decorative)
    assert canary.main(["--gate"]) == 1
    assert "[FAIL]" in capsys.readouterr().err


def test_emit_json_reports_every_harness(canary: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """`--emit-json` 은 리뷰가 읽는 형태(harness 별 판정 + 합계)를 낸다."""

    assert canary.main(["--emit-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["counts"]["harnesses"] == 7
    assert payload["counts"]["ok"] == 7
    assert payload["counts"]["blind"] == 0
    assert {item["name"] for item in payload["harnesses"]} == set(canary.HARNESSES)


def test_emit_json_also_fails_when_a_floor_is_decorative(
    canary: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # noqa: ANN401, E501
    """JSON 을 내는 실행도 판정을 종료 코드로 말한다 — 아니면 읽는 쪽은 “통과” 로 오해한다.

    진단은 stdout 에 그대로 남아야 한다(리뷰가 어느 harness 가 못 물었는지 읽는다).
    """

    def decorative() -> tuple[Any, ...]:
        return (
            canary.CanaryResult(
                name="probe",
                floors=1,
                healthy=True,
                bites=False,
                carries_reason=True,
                problems=("probe 의 하한이 눈멀게 한 사본을 막지 못한다(장식이다)",),
            ),
        )

    monkeypatch.setattr(canary, "run", decorative)
    assert canary.main(["--emit-json"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["counts"]["blind"] == 1
    assert payload["harnesses"][0]["bites"] is False
    assert "장식이다" in payload["harnesses"][0]["problems"][0]
