"""전량 회귀 원장(결정적 vs seed 민감) 계약.

`scripts/regression_ledger.py` 가 **주장하는 것**을 시험으로 고정한다:

  * junit XML 만 읽는다(로그 문자열 파싱 금지) — 리포트 형태가 바뀌면 여기서 빨개진다.
  * 회차마다 seed 가 **명시적으로** 박힌다(PYTHONHASHSEED 상속에 기대지 않는다).
  * 두 회차에서만 나오는 실패는 `drift`(seed 민감)로, 모든 회차에서 나오는 실패는 `deterministic` 으로 간다.
  * 분류표(`OWNERS`)에 없는 결정적 실패는 **무소유**로 남고, `--gate` 가 그걸 실패로 만든다.
  * 분류표가 가리키는 파일이 사라지면 실패한다(시험 파일 rename 을 조용히 넘기지 않는다).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SPEC = importlib.util.spec_from_file_location("regression_ledger", REPO_ROOT / "scripts" / "regression_ledger.py")
assert _SPEC is not None and _SPEC.loader is not None
ledger_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ledger_module
_SPEC.loader.exec_module(ledger_module)

# pytest 가 실제로 쓰는 형태(2026-09-23 실측: 루트 `<testsuites>` · `<testsuite>` 하나).
_REAL_HEAD = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" '
    'errors="1" failures="1" skipped="1" tests="4" time="1.0">'
)
_REAL_CASES = (
    '<testcase classname="tests.cognitive.test_governance" name="test_approve" time="0.1" />'
    '<testcase classname="tests.cognitive.test_governance" name="test_deny" time="0.1">'
    '<failure message="assert False">trace</failure></testcase>'
    '<testcase classname="tests.test_nx07_doc_consistency" name="test_soak" time="0.1">'
    '<error message="boom">trace</error></testcase>'
    '<testcase classname="tests.cognitive.test_governance" name="test_skip" time="0.1">'
    '<skipped type="pytest.skip" message="reason">skip</skipped></testcase>'
)


def _report(cases: str, *, tests: int | None = None) -> str:
    """합성 junit — 실제 형태 그대로 만든다."""

    head = _REAL_HEAD
    if tests is not None:
        head = head.replace('tests="4"', f'tests="{tests}"')
    return f"{head}{cases}</testsuite></testsuites>"


def _case(path: str, name: str, tag: str = "failure") -> str:
    """실재하는 시험 파일 경로로 testcase 를 만든다(판독이 파일을 찾아야 정규화된다)."""

    assert (REPO_ROOT / path).is_file(), f"합성 입력이 실재 파일을 가리켜야 한다: {path}"
    classname = path[: -len(".py")].replace("/", ".")
    return f'<testcase classname="{classname}" name="{name}" time="0.1"><{tag} message="m">t</{tag}></testcase>'


ALWAYS_RED = "tests/test_model_registry.py::test_always_red"
FLIPS = "tests/cognitive/test_governance.py::test_flips_between_runs"


# --------------------------------------------------------------------------- 판독


def test_real_junit_shape_is_read() -> None:
    """실제 리포트 형태에서 수집·skip·빨강을 읽는다."""

    report = ledger_module.parse_junit(_report(_REAL_CASES), source="fixture")

    assert report.tests == 4
    assert report.skipped == 1
    assert report.aborted is False
    assert report.red == {
        "tests/cognitive/test_governance.py::test_deny",
        "tests/test_nx07_doc_consistency.py::test_soak",
    }


def test_failure_and_error_are_both_red_but_skip_is_not() -> None:
    """`error`(수집 오류·예외)도 빨강이다 — failure 만 세면 조용히 통과한다."""

    report = ledger_module.parse_junit(_report(_REAL_CASES), source="fixture")
    assert len(report.red) == 2, "failure 와 error 를 둘 다 세지 않았다"


def test_pytest_internal_error_marks_the_run_aborted() -> None:
    """pytest 내부 오류 표시는 “중단된 회차”다 — 끝까지 돌지 않은 회차는 증거가 아니다."""

    cases = _case("tests/test_model_registry.py", "test_always_red") + (
        '<testcase classname="pytest" name="internal" time="0.000"><error message="internal error">'
        "traceback</error></testcase>"
    )
    report = ledger_module.parse_junit(_report(cases), source="fixture")

    assert report.aborted is True
    assert "pytest::internal" in report.red


def test_aborted_run_is_excluded_from_judgement() -> None:
    """한 회차가 중단됐으면 그 scope 는 결정적/seed 민감 어느 쪽으로도 세지 않는다."""

    aborted = ledger_module.RunResult(
        scope="chunk",
        seed=202,
        junit="chunk__seed-202.xml",
        tests=100,
        red=frozenset({"pytest::internal"}),
        skipped=0,
        aborted=True,
    )
    ledger = ledger_module.build_ledger([_run(101, frozenset({ALWAYS_RED})), aborted])

    assert ledger.aborted == ("chunk",)
    assert ledger.deterministic == frozenset()
    assert ledger.drift == frozenset()
    problems = ledger_module.gate_failures(ledger, drift_allowance=0)
    assert any("중단된 회차" in problem for problem in problems), problems


def test_class_node_id_keeps_the_class_name() -> None:
    """class 안의 시험은 파일::Class::method 로 남는다(사람이 찾아갈 수 있어야 한다)."""

    node = ledger_module.node_id("tests.cognitive.test_governance.TestThing", "test_x")
    assert node == "tests/cognitive/test_governance.py::TestThing::test_x"


def test_unresolvable_classname_falls_back_not_crashes() -> None:
    """저장소에서 파일을 못 찾으면 dotted 이름을 그대로 남긴다(판독이 멈추지 않는다)."""

    assert ledger_module.node_id("elsewhere.thing", "test_y") == "elsewhere.thing::test_y"


def test_missing_testsuite_raises() -> None:
    """리포트 형태가 바뀌면 조용히 0건으로 읽지 않는다."""

    with pytest.raises(ValueError):
        ledger_module.parse_junit("<html>not a report</html>", source="fixture")


# --------------------------------------------------------------------------- 분리


def _run(seed: int, red: frozenset[str], *, scope: str = "chunk") -> object:
    return ledger_module.RunResult(
        scope=scope, seed=seed, junit=f"{scope}__seed-{seed}.xml", tests=10, red=red, skipped=0
    )


def test_only_one_run_failing_is_drift() -> None:
    """한 회차에서만 나온 실패는 결정적이 아니다(= seed 민감)."""

    ledger = ledger_module.build_ledger([_run(101, frozenset({FLIPS, ALWAYS_RED})), _run(202, frozenset({ALWAYS_RED}))])

    assert ledger.drift == {FLIPS}
    assert ledger.deterministic == {ALWAYS_RED}


def test_scopes_are_judged_separately() -> None:
    """scope 가 다르면 교집합하지 않는다 — 그렇지 않으면 없던 실패가 결정적 실패로 둔갑한다."""

    ledger = ledger_module.build_ledger(
        [
            _run(101, frozenset({ALWAYS_RED}), scope="a"),
            _run(202, frozenset(), scope="a"),
            _run(101, frozenset({FLIPS}), scope="b"),
            _run(202, frozenset({FLIPS}), scope="b"),
        ]
    )

    assert ledger.deterministic == {FLIPS}, "scope b 에서만 결정적이다"
    assert ledger.drift == {ALWAYS_RED}
    assert ledger.incomplete == ()
    assert ledger.scopes == {"a": 2, "b": 2}


def test_single_run_scope_is_incomplete_not_deterministic() -> None:
    """한 회차뿐인 scope 는 판정하지 않는다(결정적과 seed 민감을 구분할 수 없다)."""

    ledger = ledger_module.build_ledger(
        [
            _run(101, frozenset({ALWAYS_RED}), scope="only"),
            _run(101, frozenset(), scope="twice"),
            _run(101, frozenset(), scope="twice"),
        ]
    )

    assert ledger.incomplete == ("only", "twice"), "seed 가 겹치면 두 회차로 보지 않는다"
    assert ledger.deterministic == frozenset()
    assert any("scope" in problem for problem in ledger_module.gate_failures(ledger, drift_allowance=0))


def test_identical_runs_have_no_drift() -> None:
    """두 회차가 같으면 민감 실패 0건 — 이 값이 “우연히 초록” 감시의 기준선이 된다."""

    red = frozenset({ALWAYS_RED})
    ledger = ledger_module.build_ledger([_run(101, red), _run(202, red)])

    assert ledger.drift == frozenset()
    assert len(ledger.deterministic) == 1


def test_no_runs_is_an_error() -> None:
    """회차 0으로 원장을 만들지 않는다."""

    with pytest.raises(ValueError):
        ledger_module.build_ledger([])


# --------------------------------------------------------------------------- 귀속


def test_known_failure_gets_its_owner() -> None:
    """분류표에 있는 파일의 결정적 실패는 오너(레인·사유)와 함께 남는다."""

    node = "tests/test_nx07_doc_consistency.py::test_soak_phases_stay_separated"
    ledger = ledger_module.build_ledger([_run(101, frozenset({node})), _run(202, frozenset({node}))])

    assert ledger.unowned == ()
    assert ledger.owners[node].lane == "release-owner"
    assert "EX-05" in ledger.owners[node].reason


def test_unowned_deterministic_failure_is_reported() -> None:
    """분류표에 없는 결정적 실패는 무소유로 남고 게이트가 실패로 만든다."""

    node = "tests/test_brand_new_thing.py::test_broken"
    ledger = ledger_module.build_ledger([_run(101, frozenset({node})), _run(202, frozenset({node}))])

    assert ledger.unowned == (node,)
    problems = ledger_module.gate_failures(ledger, drift_allowance=0)
    assert any("무소유" in problem for problem in problems), problems


def test_teeth_drift_over_allowance_fails_the_gate() -> None:
    """seed 민감 실패가 허용치를 넘으면 게이트가 문다(이빨)."""

    flaky = frozenset({f"tests/cognitive/test_governance.py::test_flip_{index}" for index in range(3)})
    ledger = ledger_module.build_ledger([_run(101, flaky), _run(202, frozenset())])

    assert len(ledger.drift) == 3
    assert ledger_module.gate_failures(ledger, drift_allowance=0)
    assert not ledger_module.gate_failures(ledger, drift_allowance=3)


def test_owner_registry_points_at_real_files() -> None:
    """분류표의 파일이 사라지면 실패한다 — rename 을 조용히 넘기지 않는다."""

    missing = [path for path, _, _ in ledger_module.OWNERS if not (REPO_ROOT / path).is_file()]
    assert not missing, f"소유자 분류표가 없는 파일을 가리킨다: {missing}"


def test_owner_registry_has_reasons() -> None:
    """레인 이름만 있고 사유가 없으면 다음 사람이 판단할 근거가 없다."""

    for path, lane, reason in ledger_module.OWNERS:
        assert lane and len(lane) > 3, f"{path}: 레인 표기가 비었다"
        assert len(reason) > 20, f"{path}: 소유 사유가 문장이 아니다"


# --------------------------------------------------------------------------- 산출물


def test_load_runs_reads_seed_from_file_name(tmp_path: Path) -> None:
    """`--from-junit` 경로: 재실행 없이 기존 XML 만으로 원장을 다시 만든다."""

    for seed in (101, 202):
        report = _report(_case("tests/test_model_registry.py", "test_always_red"))
        (tmp_path / f"chunk-a__seed-{seed}.xml").write_text(report, encoding="utf-8")

    runs = ledger_module.load_runs(tmp_path)

    assert [run.seed for run in runs] == [101, 202]
    assert {run.scope for run in runs} == {"chunk-a"}
    assert all(run.red == frozenset({ALWAYS_RED}) for run in runs)


def test_load_runs_ignores_files_without_the_name_shape(tmp_path: Path) -> None:
    """이름 규약이 다른 xml 은 조용히 섞지 않는다(scope 를 모르는 산출물은 판정에 쓸 수 없다)."""

    (tmp_path / "stray.xml").write_text(_report(_case("tests/test_model_registry.py", "test_x")), "utf-8")
    (tmp_path / "chunk-a__seed-101.xml").write_text(
        _report(_case("tests/test_model_registry.py", "test_always_red")), encoding="utf-8"
    )

    runs = ledger_module.load_runs(tmp_path)

    assert len(runs) == 1 and runs[0].scope == "chunk-a"


def test_missing_artifacts_is_fatal_not_silent(tmp_path: Path) -> None:
    """junit 이 없으면 0건 원장을 만들지 않고 멈춘다."""

    with pytest.raises(SystemExit):
        ledger_module.load_runs(tmp_path)


def test_run_once_pins_the_hash_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """회차는 seed 를 **명시적으로** 박는다 — 상속된 hash seed 에 기대지 않는다."""

    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        report = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml=")))
        report.write_text(_report(_case("tests/test_model_registry.py", "test_always_red")), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ledger_module.subprocess, "run", fake_run)

    result = ledger_module.run_once(
        scope="chunk-a", seed=303, directory=tmp_path, pattern="not slow", extra=["tests/cognitive"]
    )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PYTHONHASHSEED"] == "303"
    assert result.scope == "chunk-a"
    assert result.junit.endswith("chunk-a__seed-303.xml")
    assert "tests/cognitive" in captured["command"], "scope 선택이 pytest 인자에 실려야 한다"  # type: ignore[operator]
    assert result.red == frozenset({ALWAYS_RED})
    assert "--junitxml=" in " ".join(captured["command"])  # type: ignore[arg-type]


def test_slug_keeps_names_file_safe() -> None:
    """scope 이름이 그대로 파일명이 되므로 구분자·공백을 안전한 문자로 바꿔야 한다."""

    assert ledger_module.slug("flat 001/060") == "flat-001-060"
    assert ledger_module.slug("///") == "scope"


def test_default_seeds_are_distinct_and_positive() -> None:
    """기본 seed 가 겹치면 두 회차가 같은 조건이 되어 drift 가 늘 0으로 보인다."""

    seeds = ledger_module.DEFAULT_SEEDS
    assert len(set(seeds)) == len(seeds)
    assert all(seed > 0 for seed in seeds)
    generated = tuple(seeds[0] + 101 * index for index in range(3))
    assert generated[: len(seeds)] == seeds
