"""측정 harness 들이 **자기 눈을 확인하는가** — 공통 계약(`scripts/harness_contract.py`)의 이빨.

각 harness 는 두 가지를 스스로 해야 한다: 자기 판독 규칙을 매 실행 재판정하고(self-probe),
자기가 봐야 할 대상이 하한보다 적으면 실패한다(coverage floor). “찾은 것이 없다” 와 “볼 수 없다” 를
구분하지 못하는 harness 는 초록으로 보이지만 그 초록은 증거가 아니다.

이 시험은 그 구분을 **양방향**으로 고정한다 — 정상일 때 통과하고, 판독력을 망가뜨리면 실패한다.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

# harness 이름 → 실행 파일. 각자 자기 판독 규칙과 하한을 들고 있다.
HARNESSES = (
    "harness_contract",
    "digest_drift",
    "regression_ledger",
    "audit_state_claims",
    "audit_enum_identity",
    "audit_test_namespace_purge",
    "measure_cognitive_surface",
)


if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"harness_probe_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contract() -> Any:  # noqa: ANN401 - 스크립트 module
    return load("harness_contract")


# --------------------------------------------------------------------- 공통 계약 자체


def test_probe_without_cases_is_not_ok(contract: Any) -> None:  # noqa: ANN401
    """검사 항목이 0건이면 통과가 아니다 — 검사하지 않은 것을 통과로 세면 자기시험이 장식이 된다."""

    assert contract.Probe(cases=0, failures=()).ok is False
    assert contract.Probe(cases=3, failures=("무언가",)).ok is False
    assert contract.Probe(cases=3, failures=()).ok is True


def test_probe_problems_distinguishes_absence_and_failure(contract: Any) -> None:  # noqa: ANN401
    """자기시험 부재·항목 0건·실패를 각각 다른 문장으로 실패시킨다."""

    assert "결과가 없다" in contract.probe_problems(None, name="x")[0]
    assert "항목 0건" in contract.probe_problems(contract.Probe(cases=0, failures=()), name="x")[0]
    failed = contract.probe_problems(contract.Probe(cases=2, failures=("깨짐",)), name="x")[0]
    assert "자기시험 실패" in failed and "깨짐" in failed


def test_cases_builder_reports_missing_items_it_was_never_iterating(contract: Any) -> None:  # noqa: ANN401
    """**지워진 항목**은 순회로 안 보인다 — 요구 목록을 따로 넘겨 그 부재를 잡는다."""

    cases = contract.Cases()
    cases.covers("어휘", ("red", "green"), ("red",))
    cases.equal("값", 1, 2)
    probe = cases.probe()

    assert probe.cases == 2
    assert any("green" in failure for failure in probe.failures)
    assert any("1 ≠ 2" in failure for failure in probe.failures)


def test_floor_distinguishes_nothing_found_from_nothing_seen(contract: Any) -> None:  # noqa: ANN401
    """하한 미달은 “찾은 것이 없다” 가 아니라 “볼 수 없는 상태” 로 보고된다."""

    assert contract.Floor("pin", 3, 1).problem() is None
    problem = contract.Floor("pin", 0, 1).problem()

    assert problem is not None and "하한 1" in problem and "볼 수 없는" in problem
    assert len(contract.floor_problems([contract.Floor("pin", 0, 1), contract.Floor("회차", 2, 1)])) == 1


def test_self_test_line_reports_failures(contract: Any) -> None:  # noqa: ANN401
    """사람이 읽는 한 줄 — 항목 수와 실패 이유가 함께 보인다."""

    assert "3건 재판정 — 통과" in contract.describe_self_test("x", contract.Probe(cases=3, failures=()))
    assert "실패: 깨짐" in contract.describe_self_test("x", contract.Probe(cases=3, failures=("깨짐",)))


# --------------------------------------------------------------------- 각 harness 의 자기시험


@pytest.mark.parametrize("name", HARNESSES)
def test_every_harness_self_probe_passes(name: str) -> None:
    """모든 harness 가 실제 저장소에서 자기 판독력을 통과한다 — 항목이 0건이면 검사하지 않은 것이다."""

    module = load(name)
    if name == "harness_contract":
        pytest.skip("공통 계약 자신은 소비자의 판독 규칙을 갖지 않는다")
    probe = module.self_probe()

    assert probe.ok, probe.failures
    assert probe.cases >= 5, f"{name} 자기시험 항목이 너무 적다: {probe.cases}"


def test_digest_drift_probe_notices_a_broken_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    """경로+digest 패턴이 망가지면 그 실행이 실패한다(움직임 0건으로 조용히 통과하지 않는다)."""

    module = load("digest_drift")
    monkeypatch.setattr(module, "_PIN_PATTERN", __import__("re").compile(r"절대_안_맞는_패턴"))

    assert module.self_probe().ok is False


def test_digest_drift_rejects_an_empty_measurement() -> None:
    """pin 을 하나도 못 본 측정은 “움직임 0” 이 아니라 게이트 실패다."""

    module = load("digest_drift")
    empty = module.Drift(pins=(), source_head="probe")

    problems = module.gate_failures(empty, Path("/tmp/no-such-artifact.json"))
    assert any("볼 수 없는" in problem for problem in problems)


def test_regression_ledger_rejects_an_empty_ledger() -> None:
    """회차 0개·scope 0개인 원장은 “결정적 0 · drift 0” 이 아니라 게이트 실패다."""

    module = load("regression_ledger")
    empty = module.Ledger()

    problems = module.gate_failures(empty, drift_allowance=0)
    assert sum(1 for problem in problems if "볼 수 없는" in problem) == 2


def test_state_claims_rejects_a_blind_audit() -> None:
    """node 를 지목한 산문이 안 보이면 상태 주장 감사가 스스로 눈이 멀었음을 보고한다."""

    module = load("audit_state_claims")

    problems = module.gate_failures([], 0, module.self_probe())
    assert any("눈이 멀었을 수 있다" in problem for problem in problems)


def test_enum_audit_probe_notices_a_broken_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """판독기가 위반을 못 찾게 되면(빈 결과) 자기시험이 잡는다 — 그리고 CLI 가 실패한다."""

    module = load("audit_enum_identity")
    assert module.self_probe().ok is True

    monkeypatch.setattr(module, "scan_source", lambda source, *, file: ())
    assert module.self_probe().ok is False
    assert module.main(["--quiet"]) == module.EXIT_VIOLATION


def test_namespace_audit_probe_notices_a_broken_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """purge 판독이 무뎌지면(아무것도 위반으로 안 봄) 자기시험이 잡고 CLI 가 실패한다."""

    module = load("audit_test_namespace_purge")
    assert module.self_probe().ok is True

    monkeypatch.setattr(module, "scan_source", lambda source, *, file: ())
    assert module.self_probe().ok is False
    assert module.main([]) == 1


def test_surface_harness_rejects_an_empty_entrypoint_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """표면 표가 비면 “legacy 도달 0/0” 이 아니라 실패다 — 실측 harness 가 빈 표를 증거로 내지 않는다."""

    module = load("measure_cognitive_surface")
    empty = module.measure_surface_reach(entrypoints=())

    floors = module.coverage_floors(empty)
    assert sum(1 for floor in floors if floor.problem() is not None) == 2

    monkeypatch.setattr(module, "measure_surface_reach", lambda **_kwargs: empty)
    assert module.main([]) == module.EXIT_FAIL


def test_surface_harness_probe_notices_a_broken_reach_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """도달 판독이 죽으면(항상 False) 자기시험이 잡는다 — 표면 실측도 자기 눈을 확인한다."""

    module = load("measure_cognitive_surface")
    assert module.self_probe().ok is True

    original = module.measure_surface_reach

    def never_reaches(**kwargs: object) -> object:
        """실재 모듈은 알아보지만 도달은 항상 False 인 판독기 — `legacy_via`/`core_via` 를 비운다."""

        measurement = original(**kwargs)  # type: ignore[arg-type]
        return replace(
            measurement,
            entrypoints=tuple(
                replace(item, reaches_legacy=False, reaches_core=False, legacy_via=(), core_via=())
                for item in measurement.entrypoints
            ),
        )

    monkeypatch.setattr(module, "measure_surface_reach", never_reaches)
    probe = module.self_probe()

    assert probe.ok is False
    assert any("core 도달" in failure for failure in probe.failures)


def test_namespace_audit_probe_notices_an_all_violating_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """반대 방향도 잡는다 — 허용 형태(트리 override·실행 시점)를 위반으로 세면 자기시험이 실패한다."""

    module = load("audit_test_namespace_purge")

    def always_violation(source: str, *, file: str) -> tuple[Any, ...]:
        return (module.Violation(file=file, line=1, kind="unguarded_purge", expression="probe"),)

    monkeypatch.setattr(module, "scan_source", always_violation)
    assert module.self_probe().ok is False
