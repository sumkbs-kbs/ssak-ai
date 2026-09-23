"""증거 게이트(`scripts/evidence_gate.py`)의 계약 — **돌리지 못한 층을 통과로 세는가**.

여섯 harness 가 각자 게이트를 갖는 것과, 그것을 **도는 자리**는 다르다. 이 도구가 그 자리인데, 도구가 조용히
실패하면(스크립트 이름이 틀려 아무것도 실행되지 않거나, stage 목록이 낡아 한 층이 빠지거나, tier 밖 층이
초록으로 덮이면) 게이트는 형식이 된다. 그래서 여기서는 판정 규칙을 **합성 결과로** 재현한다:

  * 없는 스크립트 · 없는 산출물 · 제한 시간 초과는 `pass` 가 아니라 `unrun` 이고, 문제 문장이 남는다.
  * 실패한 층은 보고서와 문제 문장에 **이름으로** 남는다.
  * tier 밖 층은 통과로 세지 않는다(초록으로 덮지 않고 “보지 않은 층” 으로 적는다).
  * roster 가 줄면 자기시험이 **지워진 이름**을 짚는다(상수 순회로는 지워진 이름이 안 보인다).
  * 카나리아가 아는 harness 는 전부 stage 로 들어 있다(게이트 자신만 재귀 때문에 예외).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gate_under_test", SCRIPTS / "evidence_gate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_gate()


# ------------------------------------------------------------------ 저장소의 실제 상태


def test_fast_tier_runs_every_layer_it_claims(gate: Any) -> None:  # noqa: ANN401
    """fast tier 는 자기가 도는 층을 **전부 실제로 돌리고**, 전부 통과한다(한 층이라도 빨간면 게이트가 빨갛다)."""

    outcomes = gate.run(gate.TIER_FAST, timeout=gate.DEFAULT_TIMEOUT)

    assert {outcome.stage.name for outcome in outcomes} == {stage.name for stage in gate.stages_for(gate.TIER_FAST)}
    for outcome in outcomes:
        assert outcome.ok, f"{outcome.stage.name}: {outcome.kind} exit={outcome.exit_code} {outcome.detail}"
    assert gate.problems(outcomes, gate.coverage_floors()) == []


def test_every_layer_is_rehearsed_or_declared(gate: Any) -> None:  # noqa: ANN401
    """게이트가 도는 층과 카나리아 harness 는 전부 **리허설되거나 이유와 함께 선언**돼 있다.

    “위반 0건” 이 ’다 봤는데 깨끗하다’ 인지 ’한 번도 red 를 낸 적이 없다’ 인지 아무도 묻지 않는 층이 생기는
    순간이 이 회계가 잡으려는 것이다(새 층을 roster 에만 넣으면 여기서 걸린다).
    """

    planted, declared = gate.load_rehearsal_roster()
    names = {stage.name for stage in gate.STAGES} | set(gate.load_canary_harnesses())

    assert gate.SELF_EXEMPT  # 게이트 자신은 재귀 때문에 stage 에서 빠진다
    assert names <= set(planted) | set(declared)
    assert not set(planted) & set(declared)
    assert all(reason.strip() for reason in declared)


def test_the_local_layers_are_named_as_unseen_not_as_pass(gate: Any) -> None:  # noqa: ANN401
    """로컬 회차가 필요한 층(회귀 원장·배포 산출물)은 fast 실행에서 **통과가 아니라 '보지 않은 층'** 이다."""

    outsiders = gate.outsider_outcomes(gate.TIER_FAST)

    assert [outcome.stage.name for outcome in outsiders] == ["release_artifacts", "regression_ledger"]
    assert all(outcome.kind == gate.KIND_OUTSIDE and not outcome.ok for outcome in outsiders)
    report = gate.describe(gate.TIER_FAST, gate.run(gate.TIER_FAST), outsiders)
    assert "이 실행이 보지 않은 층" in report
    assert "regression_ledger" in report


def test_full_tier_covers_every_stage(gate: Any) -> None:  # noqa: ANN401
    """full tier 는 전체 roster 를 돌고, 보지 않은 층이 없다(상위 tier 는 fast 를 포함한다)."""

    assert len(gate.stages_for(gate.TIER_FULL)) == len(gate.STAGES)
    assert gate.tier_outsiders(gate.TIER_FULL) == ()
    assert {stage.name for stage in gate.stages_for(gate.TIER_FAST)} <= {
        stage.name for stage in gate.stages_for(gate.TIER_FULL)
    }


def test_fast_tier_needs_no_uncommitted_artifacts(gate: Any) -> None:  # noqa: ANN401
    """fast tier 는 커밋되지 않는 산출물에 기대지 않는다 — 깨끗한 체크아웃(CI)에서 돌 수 있는 이유다."""

    fast = gate.stages_for(gate.TIER_FAST)

    assert all(stage.requires == () for stage in fast)
    assert not any(".regression-ledger" in arg for stage in fast for arg in stage.args)


def test_the_local_layer_declares_the_artifact_it_needs(gate: Any) -> None:  # noqa: ANN401
    """회귀 원장은 회차 산출물을 `requires` 로 선언한다 — 없으면 조용히 빠지는 대신 `unrun` 으로 실패한다."""

    ledger = next(stage for stage in gate.STAGES if stage.name == "regression_ledger")

    assert ledger.tier == gate.TIER_FULL
    assert ledger.requires, "회차 산출물이 필요한 층은 그 사실을 선언해야 한다"


def test_unknown_tier_is_refused(gate: Any) -> None:  # noqa: ANN401
    """모르는 tier 는 조용히 기본값으로 흘리지 않고 거부한다(오타가 fast 로 실행되면 안 된다)."""

    with pytest.raises(SystemExit):
        gate.stages_for("fullfast")


# ------------------------------------------------------------------ 수치 (한 번의 실행으로 판정 + 수치)


def test_every_layer_hands_back_numbers(gate: Any) -> None:  # noqa: ANN401
    """돌아간 층은 **수치도 함께** 낸다 — 수를 못 읽는 층은 추이에 쓸 수 없다."""

    outcomes = gate.run(gate.TIER_FAST)

    for outcome in outcomes:
        assert outcome.numbers, f"{outcome.stage.name} 이 수치를 내지 않았다"
        assert not outcome.read_detail, f"{outcome.stage.name}: {outcome.read_detail}"


def test_layer_without_readable_numbers_is_a_failure(gate: Any) -> None:  # noqa: ANN401
    """지목한 키에서 수를 못 찾으면 실패한다 — “수가 안 보임” 을 “그대로” 로 쓰지 않는다."""

    stage = replace(gate.STAGES[0], numbers=("no_such_key",))
    outcome = gate.run_stage(stage)

    assert outcome.kind == gate.KIND_PASS
    assert not outcome.numbers
    assert "no_such_key" in outcome.read_detail
    assert any("수치를 읽지 못했다" in problem for problem in gate.problems((outcome,), []))


def test_snapshot_only_holds_layers_that_ran(gate: Any) -> None:  # noqa: ANN401
    """못 돌린 층은 스냅숏에 들어가지 않는다(빈 값을 “그대로” 로 만들지 않는다)."""

    outcomes = gate.run(gate.TIER_FAST)
    kept = gate.snapshot(outcomes)

    assert set(kept) == {outcome.stage.name for outcome in outcomes}
    assert "regression_ledger" not in kept
    assert "regression_ledger" not in gate.snapshot(gate.outsider_outcomes(gate.TIER_FAST))


def test_movements_name_what_moved(gate: Any) -> None:  # noqa: ANN401
    """줄었다·늘었다·새 수·사라진 수·기준 없음을 구분하고, 층과 수치 이름을 함께 낸다."""

    moves = gate.movements(
        {"a": {"x": 1, "y": 5}, "fresh": {"z": 1}},
        {"a": {"x": 3}, "gone": {"q": 1}},
    )
    kinds = {(move.layer, move.key): move.kind for move in moves}

    assert kinds[("a", "x")] == gate.MOVED_DOWN
    assert kinds[("a", "y")] == gate.MOVED_NEW
    assert kinds[("fresh", "")] == gate.MOVED_NONE
    assert kinds[("gone", "")] == gate.MOVED_GONE
    down = next(move for move in moves if (move.layer, move.key) == ("a", "x"))
    assert "a · x 3 → 1" in down.describe()


def test_trend_puts_shrinking_numbers_first(gate: Any) -> None:  # noqa: ANN401
    """추이는 줄어든 수를 먼저 보여 준다 — 늘어난 수부터 보면 얇아진 층이 묻힌다."""

    moves = gate.movements({"a": {"x": 1, "y": 9}}, {"a": {"x": 2, "y": 1}})
    lines = gate.trend_lines(moves, {"path": "b.json", "recorded_on": "2026-01-01"})

    assert "▼" in lines[1]
    assert "▲" in lines[2]


# ------------------------------------------------------------------ 기준 (지난 승인 시점)


def test_repository_baseline_is_recorded_and_covers_the_layers(gate: Any) -> None:  # noqa: ANN401
    """저장소의 기준 파일이 실재하고, 무엇을 보고 승인했는지·언제인지·층 수를 들고 있다."""

    assert gate.BASELINE.exists(), f"{gate.BASELINE} 가 없다 — `--record-baseline --method` 로 만들어야 한다"
    payload = json.loads(gate.BASELINE.read_text(encoding="utf-8"))

    assert str(payload["method"]).strip()
    assert str(payload["recorded_on"]).strip()
    assert len(payload["layers"]) >= 7, payload["layers"].keys()
    assert set(payload["layers"]) == {stage.name for stage in gate.STAGES}


def test_a_file_stage_is_never_run_without_a_place_to_write(gate: Any) -> None:  # noqa: ANN401
    """자리표시자를 그대로 넘기면 그 층이 저장소에 `{report}` 파일을 쓴다 — 실제로 시험 실행이 그걸 남겼다."""

    file_stage = next(stage for stage in gate.STAGES if gate.REPORT_TOKEN in stage.args)

    with pytest.raises(ValueError, match="자리"):
        gate.stage_argv(file_stage, None)

    argv = gate.stage_argv(file_stage, Path("/tmp/here.json"))
    assert gate.REPORT_TOKEN not in " ".join(argv)
    assert "/tmp/here.json" in argv


# ------------------------------------------------------------------ 요약 (CI·리뷰어가 읽는 자리)


def test_summary_names_every_layer_and_the_unseen_ones(gate: Any) -> None:  # noqa: ANN401
    """요약은 층·판정·수치 수를 담고, 보지 않은 층을 "통과가 아니다" 로 적는다."""

    outcomes = gate.run(gate.TIER_FAST)
    outsiders = gate.outsider_outcomes(gate.TIER_FAST)
    summary = gate.summary_markdown(gate.TIER_FAST, outcomes, outsiders, moves=[], baseline={})

    assert "verdict: PASS" in summary
    for outcome in outcomes:
        assert f"`{outcome.stage.name}`" in summary
    assert "이 실행이 보지 않은 층 (통과가 아니다)" in summary
    assert "`regression_ledger`" in summary


def test_summary_still_exists_when_the_gate_is_red(gate: Any) -> None:  # noqa: ANN401
    """빨간 실행도 요약을 남긴다 — 실패한 층의 이름과 이유가 그 안에 있어야 한다."""

    failed = gate.Outcome(gate.STAGES[1], gate.KIND_FAIL, 1, 0.2, "[FAIL] 판독 규칙이 깨졌다")
    problems = gate.problems((failed,), [])
    summary = gate.summary_markdown(gate.TIER_FAST, (failed,), (), moves=[], baseline={}, problems=problems)

    assert "verdict: FAIL" in summary
    assert "## 문제" in summary
    assert gate.STAGES[1].name in summary
    assert "[FAIL] 판독 규칙이 깨졌다" in summary


def test_cli_writes_the_summary_beside_the_json(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """CLI 는 JSON 과 markdown 을 함께 남긴다 — 판정·기계용·사람용이 같은 한 번의 실행에서 나온다."""

    report = tmp_path / "gate.json"
    summary = tmp_path / "gate.md"

    assert (
        gate.main(["--tier", gate.TIER_FAST, "--json", str(report), "--summary", str(summary), "--quiet"])
        == gate.EXIT_OK
    )
    assert report.exists() and summary.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert "# 증거 게이트" in summary.read_text(encoding="utf-8")


# ------------------------------------------------------------------ CI 배선 (실제로 도는 자리)


def test_both_workflows_run_the_gate_and_cover_every_change(gate: Any) -> None:  # noqa: ANN401
    """ci.yml 과 evidence.yml 이 게이트를 돌리고, 둘이 합쳐 모든 변경을 덮는다.

    txt 수준으로 보는 이유: 여기서 확인할 것은 워크플로 문법이 아니라 **배선**이다 — 한쪽이 `docs/**` 를
    무시하므로 다른 쪽이 그 여집합(`docs/**`·`**.md`)을 맡아야 문서만 바꾼 PR 이 게이트를 건너뛰지 않는다.
    """

    code_ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docs_ci = (REPO_ROOT / ".github" / "workflows" / "evidence.yml").read_text(encoding="utf-8")

    assert "scripts/evidence_gate.py" in code_ci
    assert "scripts/evidence_gate.py" in docs_ci
    assert "docs/**" in code_ci and "**.md" in code_ci, "ci.yml 이 문서 변경을 무시하는 전제가 바뀌었다"
    assert "docs/**" in docs_ci and "**.md" in docs_ci, "문서 변경을 맡는 워크플로의 트리거가 바뀌었다"
    assert "--summary" in code_ci and "--summary" in docs_ci
    assert "GITHUB_STEP_SUMMARY" in code_ci and "GITHUB_STEP_SUMMARY" in docs_ci


def test_recording_a_baseline_needs_a_method(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """무엇을 보고 승인했는지 없이는 기준을 기록하지 않는다(그리고 종료 코드로 말한다)."""

    target = tmp_path / "baseline.json"

    assert gate.main(["--record-baseline", "--baseline", str(target), "--quiet"]) == gate.EXIT_GATE
    assert target.exists() is False, "method 없이 기준을 썼다"


def test_a_record_may_not_drop_a_layer_the_gate_still_runs(
    gate: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # noqa: ANN401
    """tier 를 좁혀 기록하면 **보지 않은 층의 승인 수치가 사라진다** — 그 기록을 거부하고 이름을 남긴다.

    실측으로 겪었다: full 전용 둘(regression_ledger·release_artifacts)이 fast 기록으로 기준에서 빠졌다.
    지워진 층은 다음 실행에서 “기준 없음” 으로 나타나 추이가 끊기고, 그 사실은 기록을 만든 실행의 보고에만 남는다.
    """

    target = tmp_path / "baseline.json"
    full_only = [stage.name for stage in gate.STAGES if stage.tier == gate.TIER_FULL]
    assert full_only, "full 전용 stage 가 없으면 이 계약이 공허하다"
    previous = {stage.name: {"n": 1} for stage in gate.STAGES}
    target.write_text(
        json.dumps({"recorded_on": "2026-01-01", "method": "옛 승인", "layers": previous}),
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")

    assert (
        gate.main(
            [
                "--tier",
                gate.TIER_FAST,
                "--record-baseline",
                "--baseline",
                str(target),
                "--method",
                "좁은 tier 로 기록",
                "--quiet",
            ]
        )
        == gate.EXIT_GATE
    )
    captured = capsys.readouterr()
    for layer in full_only:
        assert layer in captured.err, f"사라지는 층을 이름으로 말하지 않았다: {layer}"
    assert target.read_text(encoding="utf-8") == before, "거부한 기록이 기준을 덮어썼다"


def test_a_record_may_drop_a_layer_the_gate_no_longer_knows(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """반대쪽 문도 있다 — stage 목록에서 진짜로 빠진 층은 빼도 된다(그래서 예외 플래그가 필요 없다)."""

    target = tmp_path / "baseline.json"
    seen = [stage.name for stage in gate.STAGES if stage.tier == gate.TIER_FAST]
    previous = {name: {"n": 1} for name in seen}
    previous["층_없음"] = {"n": 9}
    target.write_text(
        json.dumps({"recorded_on": "2026-01-01", "method": "옛 승인", "layers": previous}),
        encoding="utf-8",
    )

    assert (
        gate.main(
            [
                "--tier",
                gate.TIER_FAST,
                "--record-baseline",
                "--baseline",
                str(target),
                "--method",
                "사라진 층을 정리하는 기록",
                "--quiet",
            ]
        )
        == gate.EXIT_OK
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "층_없음" not in payload["layers"], "게이트가 더는 모르는 층을 기준에 남겼다"
    assert set(payload["layers"]) == set(seen)


def test_recording_a_baseline_round_trips(gate: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """기록한 기준으로 바로 다음 실행이 비교한다 — 첫 실행은 전부 '그대로' 다."""

    target = tmp_path / "baseline.json"
    assert (
        gate.main(
            [
                "--tier",
                gate.TIER_FAST,
                "--record-baseline",
                "--baseline",
                str(target),
                "--method",
                "시험용 승인",
                "--quiet",
            ]
        )
        == gate.EXIT_OK
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["method"] == "시험용 승인"
    assert payload["recorded_on"]
    assert set(payload["layers"])

    assert gate.main(["--tier", gate.TIER_FAST, "--baseline", str(target)]) == gate.EXIT_OK
    printed = capsys.readouterr().out
    assert "[추이]" in printed
    assert "기준 없음" not in printed
    assert "그대로" in printed


def test_a_normal_run_does_not_touch_the_baseline(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """게이트는 기준을 **읽기만** 한다 — 돌리는 것만으로 승인 기록이 바뀌면 추이가 거짓말한다."""

    target = tmp_path / "baseline.json"

    assert gate.main(["--tier", gate.TIER_FAST, "--baseline", str(target), "--quiet"]) == gate.EXIT_OK
    assert target.exists() is False


def test_broken_baseline_is_a_failure_not_a_shrug(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """깨진 기준을 “비교 불가” 로 삼키지 않는다 — 그 상태로는 얇아짐을 볼 수 없다."""

    target = tmp_path / "baseline.json"
    target.write_text("{ not json", encoding="utf-8")

    assert gate.main(["--tier", gate.TIER_FAST, "--baseline", str(target), "--quiet"]) == gate.EXIT_GATE


def test_baseline_file_without_layers_is_unusable(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """층 수치가 없는 기준 파일은 기준이 아니다(빈 dict 를 “읽었다” 로 세지 않는다)."""

    target = tmp_path / "baseline.json"
    target.write_text(json.dumps({"method": "m", "recorded_on": "2026-01-01"}), encoding="utf-8")

    snapshot, problem = gate.read_baseline(target)

    assert snapshot == {}
    assert "layers" in problem


# ------------------------------------------------------------------ 판정 규칙 (합성 결과)


def test_missing_script_is_a_failure_not_a_skip(gate: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """스크립트가 없으면 조용히 건너뛰지 않고 `unrun`(실패)으로 남는다."""

    stage = replace(gate.STAGES[0], script="no_such_layer.py")
    outcome = gate.run_stage(stage)

    assert outcome.kind == gate.KIND_UNRUN
    assert not outcome.ok
    assert "스크립트가 없다" in outcome.detail
    assert any(stage.name in problem for problem in gate.problems((outcome,), []))


def test_missing_precondition_names_the_artifact(gate: Any) -> None:  # noqa: ANN401
    """산출물이 없어 돌릴 수 없는 층은 **어떤 산출물이 없는지** 말한다(‘볼 수 없음’ 을 이유로 남긴다)."""

    stage = replace(gate.STAGES[0], requires=("no_such_round_dir",), tier=gate.TIER_FULL)
    outcome = gate.run_stage(stage)

    assert outcome.kind == gate.KIND_UNRUN
    assert "no_such_round_dir" in outcome.detail


def test_timeout_is_not_a_pass(gate: Any) -> None:  # noqa: ANN401
    """중단된 실행은 판정이 아니다 — 제한 시간 안에 안 끝나면 통과가 아니라 실패다."""

    outcome = gate.run_stage(gate.STAGES[0], timeout=0.001)

    assert outcome.kind == gate.KIND_UNRUN
    assert "제한 시간" in outcome.detail
    assert gate.problems((outcome,), [])


def test_failing_layer_is_named_in_report_and_problems(gate: Any) -> None:  # noqa: ANN401
    """빨간 층은 보고서와 문제 문장에 **이름으로** 남는다 — '어딘가 실패했다' 로는 어디가 얇은지 모른다."""

    stage = replace(gate.STAGES[1], args=("--no-such-flag",))
    outcome = gate.run_stage(stage)

    assert outcome.kind == gate.KIND_FAIL
    assert outcome.exit_code not in (0, None)
    report = gate.describe(gate.TIER_FAST, (outcome,), gate.outsider_outcomes(gate.TIER_FAST))
    assert stage.name in report
    assert any(stage.name in problem for problem in gate.problems((outcome,), []))


def test_probe_notices_a_deleted_stage(gate: Any) -> None:  # noqa: ANN401
    """roster 에서 한 층을 지우면 자기시험이 **그 이름을 짚는다**(순회만으로는 지워진 이름이 안 보인다)."""

    kept = tuple(stage for stage in gate.STAGES if stage.name != "audit_enum_identity")
    probe = gate.self_probe(kept)

    assert not probe.ok
    assert any("audit_enum_identity" in failure for failure in probe.failures)


def test_probe_pins_the_floor_and_its_reason(gate: Any) -> None:  # noqa: ANN401
    """하한은 값·관측·근거를 함께 들고, 빈 명단에서는 **문다**(하한 없는 게이트는 형식이다)."""

    floors = gate.coverage_floors()

    assert floors and all(floor.why.strip() for floor in floors)
    assert gate.floor_problems(floors) == []
    assert gate.floor_problems(gate.coverage_floors(()))


def test_probe_follows_the_current_roster(gate: Any) -> None:  # noqa: ANN401
    """하한의 기본값은 상수를 스냅숏하지 않는다 — roster 를 바꾸면 하한이 그 명단을 센다."""

    assert gate.coverage_floors()[0].observed == len(gate.STAGES)
    assert gate.coverage_floors(())[0].observed == 0


def test_self_probe_rejudges_its_own_judgement(gate: Any) -> None:  # noqa: ANN401
    """판정 규칙(종류 구분·tier 필터·roster·근거)은 매 실행 다시 물어본다."""

    probe = gate.self_probe()

    assert probe.ok, probe.failures
    assert probe.cases >= 20


def test_cli_reports_the_missing_layer_in_the_artifact(
    gate: Any,  # noqa: ANN401
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI 는 실패를 exit code 와 **artifact** 양쪽으로 남긴다(읽는 쪽이 진단을 잃지 않는다)."""

    broken = replace(gate.STAGES[0], script="no_such_layer.py")
    monkeypatch.setattr(gate, "STAGES", (broken,))
    target = tmp_path / "evidence-gate.json"

    code = gate.main(["--json", str(target), "--quiet"])

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert code == gate.EXIT_GATE
    assert payload["ok"] is False
    assert payload["stages"][0]["kind"] == gate.KIND_UNRUN
    assert payload["problems"]


def test_cli_self_test_does_not_run_any_layer(gate: Any) -> None:  # noqa: ANN401
    """`--self-test` 는 판정 규칙만 재판정하고 아무 층도 돌리지 않는다(리뷰가 돌릴 수 있어야 한다)."""

    assert gate.main(["--self-test"]) == gate.EXIT_OK


def test_list_shows_the_whole_roster(gate: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """`--list` 는 명단을 그대로 보여준다 — 사람이 '무엇이 도는지' 를 코드 없이 확인하는 자리."""

    assert gate.main(["--list"]) == gate.EXIT_OK
    printed = capsys.readouterr().out
    for stage in gate.STAGES:
        assert stage.name in printed
    assert f"stage {len(gate.STAGES)}개" in printed
