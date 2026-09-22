"""T13 — 성장 평가·ablation 시험 (P10).

검증 범위:
- spec은 실행 전에 등록되고, 결과를 보고 기준을 바꿀 수 없다(digest 변화).
- 같은 brain/code/corpus로 fresh와 mature를 분리 root에서 실행하고, mature만 축적 경험 + 검증된 policy를 쓴다.
- EXPERIENCE → POLICY CHANGE → FUTURE BEHAVIOR CHANGE가 실제 selection·retry 변화로 이어진다.
- 6 ablation은 mechanism 하나만 바꾸고, 쓰이지 않은 mechanism 비교는 NOT_RUN으로 남긴다.
- 권한·헌법 보호는 ablation 대상이 아니며, CLI는 잘못된 입력을 조용히 통과시키지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.growth import (
    BASELINE_CONTEXT_LIMITS,
    METRIC_CONTEXT_TOKENS,
    METRIC_EXPERIENCE_REUSE,
    METRIC_GUARDED_SUCCESS,
    METRIC_TASK_SUCCESS,
    METRIC_TOTAL_RETRIES,
    METRIC_TOTAL_TOOL_CALLS,
    AblationStatus,
    ArmInputs,
    ArmRole,
    FixtureCategory,
    GrowthBenchmarkError,
    GrowthRunner,
    GrowthTask,
    Mechanism,
    MechanismSet,
    RunKind,
    SplitRole,
    corpus_digest,
    default_corpus_tasks,
    default_metrics,
    default_spec,
    split_ids,
    tasks_for,
)
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_cognitive_growth.py"


def load_cli() -> object:
    spec = importlib.util.spec_from_file_location("growth_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["growth_cli"] = module
    spec.loader.exec_module(module)
    return module


def reduced_corpus() -> tuple[GrowthTask, ...]:
    """시험용 축소 corpus. train 2 / validation 2 / final 4(guard 1, negative transfer 1)."""

    rows = (
        ("RT-T1", SplitRole.TRAIN, FixtureCategory.RECOVERY, ("cfg-alpha",), (), False, False),
        ("RT-T2", SplitRole.TRAIN, FixtureCategory.RECOVERY, ("cfg-beta",), (), False, False),
        ("RT-V1", SplitRole.VALIDATION, FixtureCategory.NORMAL, ("cfg-alpha",), (), False, False),
        ("RT-V2", SplitRole.VALIDATION, FixtureCategory.NORMAL, ("cfg-beta",), ("noise-1",), False, False),
        ("RT-F1", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-alpha",), (), False, False),
        ("RT-F2", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-gamma",), ("noise-2",), False, False),
        ("RT-F3", SplitRole.FINAL, FixtureCategory.AUTHORITY_RESHAPE, ("cfg-beta",), (), True, False),
        ("RT-F4", SplitRole.FINAL, FixtureCategory.DRIFT_NEGATIVE_TRANSFER, ("cfg-beta",), (), False, True),
    )
    tasks: list[GrowthTask] = []
    for task_id, split, category, required, irrelevant, guarded, negative in rows:
        tasks.append(
            GrowthTask(
                task_id=task_id,
                split=split,
                category=category,
                goal_name=f"goal-{task_id.lower()}",
                required_items=required,
                store_items=tuple(dict.fromkeys((*required, *irrelevant))),
                irrelevant_items=irrelevant,
                append_content=f"{task_id} appended",
                expected_outcome=f"{task_id} appended",
                requires_guarded_reshape=guarded,
                negative_transfer=negative,
            )
        )
    return tuple(tasks)


@pytest.fixture()
def runner(tmp_path: Path) -> GrowthRunner:
    corpus = reduced_corpus()
    spec = default_spec(tasks=corpus, experiment_id="growth-demo-test", registered_at=default_spec().registered_at)
    return GrowthRunner(
        tmp_path / "growth", spec, tasks=corpus, source_head="test-head", executor_factory=fixture_tool_port
    )


# ─── spec 사전 등록 ─────────────────────────────────────────────────


def test_default_spec_roundtrips_with_same_digest() -> None:
    spec = default_spec()
    restored = type(spec).from_json(spec.to_json())
    assert restored.digest() == spec.digest()
    assert restored.split_ids == spec.split_ids
    assert restored.primary_improvement_metric == METRIC_TOTAL_RETRIES
    assert restored.negative_transfer_max_success_decrease == 0
    assert restored.run_kind is RunKind.DETERMINISTIC_FIXTURE
    assert restored.metric(METRIC_CONTEXT_TOKENS).denominator == "FINAL split tasks"
    assert {metric.direction for metric in default_metrics()} == {"higher_better", "lower_better", "report_only"}


def test_changing_the_gate_requires_a_new_experiment_id() -> None:
    spec = default_spec()
    relaxed = replace(spec, success_noninferiority_margin=0.5)
    assert relaxed.digest() != spec.digest()
    stricter = replace(spec, validation_minimum_success=0.9)
    assert stricter.digest() != spec.digest()
    another = replace(spec, experiment_id="growth-demo-v2")
    assert another.digest() != spec.digest()


def test_corpus_splits_are_disjoint_and_cover_required_categories() -> None:
    tasks = default_corpus_tasks()
    ids = [task.task_id for task in tasks]
    assert len(ids) == len(set(ids))
    for role in SplitRole:
        assert tasks_for(tasks, role), f"{role} split이 비었다"
    final = tasks_for(tasks, SplitRole.FINAL)
    assert len(tasks_for(tasks, SplitRole.TRAIN)) >= 2
    assert len(tasks_for(tasks, SplitRole.VALIDATION)) >= 4
    assert len(final) >= 12

    # 원문 권고의 고정 fixture 12개: 정상 4, unknown/conflict 2, authority/reshape 2, recovery 2, drift 2
    fixtures = tuple(task for task in tasks if task.task_id.startswith("PT-"))
    assert len(fixtures) == 12
    counts = {category: sum(1 for task in fixtures if task.category is category) for category in FixtureCategory}
    assert counts[FixtureCategory.NORMAL] == 4
    assert counts[FixtureCategory.UNKNOWN_CONFLICT] == 2
    assert counts[FixtureCategory.AUTHORITY_RESHAPE] == 2
    assert counts[FixtureCategory.RECOVERY] == 2
    assert counts[FixtureCategory.DRIFT_NEGATIVE_TRANSFER] == 2

    # growth held-out: train 2 / validation 4 / final 6, task ID 중복 0
    growth = tuple(task for task in tasks if task.task_id.startswith("GT-"))
    assert len(growth) == 12
    assert len(tasks_for(growth, SplitRole.TRAIN)) == 2
    assert len(tasks_for(growth, SplitRole.VALIDATION)) == 4
    assert len(tasks_for(growth, SplitRole.FINAL)) == 6
    assert sum(1 for task in final if task.negative_transfer) == 3
    assert split_ids(tasks)["FINAL"] == tuple(task.task_id for task in final)
    assert corpus_digest(tasks) == default_spec(tasks=tasks).corpus_digest


def test_runner_refuses_unregistered_corpus_and_live_pilot(tmp_path: Path) -> None:
    corpus = reduced_corpus()
    spec = default_spec(tasks=corpus)
    with pytest.raises(GrowthBenchmarkError):
        GrowthRunner(tmp_path / "a", spec, tasks=corpus[:4], executor_factory=fixture_tool_port)
    with pytest.raises(GrowthBenchmarkError):
        GrowthRunner(
            tmp_path / "b",
            replace(spec, run_kind=RunKind.LIVE_PILOT),
            tasks=corpus,
            executor_factory=fixture_tool_port,
        )


def test_mechanism_set_disables_one_at_a_time_and_keeps_authority() -> None:
    full = MechanismSet()
    assert full.disabled() == ()
    assert full.authority_boundaries_unchanged is True
    for mechanism in Mechanism:
        ablated = full.without(mechanism)
        assert ablated.disabled() == (mechanism,)
        assert ablated.enabled(mechanism) is False
        assert ablated.as_mapping()[mechanism.value] is False
        assert ablated.authority_boundaries_unchanged is True
        assert sum(1 for value in ablated.as_mapping().values() if value is False) == 1


# ─── 성장 사슬 ─────────────────────────────────────────────────────


def test_growth_phase_links_experience_validation_activation_and_trace(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    assert phase.validation_passed is True
    assert phase.independent_episode_count >= 2
    assert phase.policy_id.startswith("policy:")
    assert phase.activation_id.startswith("policy_activation:")
    assert phase.behavior_trace_ids
    assert phase.candidate_parameters == dict(runner.spec.policy_parameters)
    assert phase.train_task_ids == tuple(task.task_id for task in tasks_for(runner.tasks, SplitRole.TRAIN))
    records = {record.id for record in phase.commit_records}
    assert phase.validation_report_id in records
    assert phase.activation_id in records
    assert all(trace_id in records for trace_id in phase.behavior_trace_ids)
    assert len({record.entity_type.value for record in phase.commit_records}) >= 4


def test_fresh_vs_mature_run_changes_future_selection(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    fresh = runner.run_fresh()
    mature = runner.run_mature(phase)
    comparison = runner.compare(fresh, mature, phase)

    assert fresh.manifest.arm is ArmRole.FRESH
    assert mature.manifest.arm is ArmRole.MATURE
    # 같은 brain/code/corpus이고 저장 root만 다르다.
    assert fresh.manifest.brain_version == mature.manifest.brain_version
    assert fresh.manifest.corpus_digest == mature.manifest.corpus_digest
    assert fresh.store_root != mature.store_root
    assert mature.manifest.policy_version == phase.policy_version

    # 실제 선택이 달라졌다: mature는 필요한 evidence를 미리 열고(주입 token이 늘 수 있다),
    # 사전 지정 metric(retry)과 tool call은 줄어든다. "더 많이 계산했다"는 성장 근거가 아니다.
    assert (mature.metrics.value(METRIC_CONTEXT_TOKENS) or 0) != (fresh.metrics.value(METRIC_CONTEXT_TOKENS) or 0)
    assert (mature.metrics.value(METRIC_TOTAL_RETRIES) or 0) < (fresh.metrics.value(METRIC_TOTAL_RETRIES) or 0)
    assert (mature.metrics.value(METRIC_TOTAL_TOOL_CALLS) or 0) < (fresh.metrics.value(METRIC_TOTAL_TOOL_CALLS) or 0)
    assert (mature.metrics.value(METRIC_EXPERIENCE_REUSE) or 0) > 0

    # success 비열등 + negative transfer 0 + safety clean + 중복 dispatch 0
    assert comparison.success_mature >= comparison.success_fresh
    assert comparison.negative_transfer_delta <= runner.spec.negative_transfer_max_success_decrease
    assert mature.safety_violations == ()
    assert mature.duplicate_dispatches == 0
    assert comparison.verdict.passed is True, comparison.verdict.reasons
    assert comparison.meta.validation_report_id == phase.validation_report_id


def test_baseline_limits_do_not_include_evidence_and_mature_limits_do(runner: GrowthRunner) -> None:
    fresh_inputs = ArmInputs(role=ArmRole.FRESH)
    mature_inputs = ArmInputs(role=ArmRole.MATURE, policy_version="growth-demo-test-v1", advisory_refs=("evidence:x",))
    assert fresh_inputs.effective_limits() == dict(BASELINE_CONTEXT_LIMITS)
    assert fresh_inputs.effective_limits()["l3_limit"] == 0
    assert mature_inputs.effective_limits()["l3_limit"] > 0
    # policy 없이 advisory만 있으면 깊이를 열지 않는다.
    advisory_only = replace(mature_inputs, policy_version=None)
    assert advisory_only.effective_limits() == dict(BASELINE_CONTEXT_LIMITS)


def test_context_builder_is_required_before_action(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    inputs = ArmInputs(
        role=ArmRole.ABLATION,
        mechanisms=MechanismSet().without(Mechanism.CONTEXT_BUILDER),
        policy_version=phase.policy_version,
        advisory_refs=phase.advisory_refs,
        disabled_mechanism=Mechanism.CONTEXT_BUILDER,
    )
    arm = runner.run_arm(inputs, extra_records=phase.commit_records, arm_label="ablation-context")
    assert arm.success_count == 0
    assert all(outcome.termination == "BLOCKED_CONTEXT" for outcome in arm.outcomes)
    assert arm.metrics.value(METRIC_TOTAL_TOOL_CALLS) == 0


# ─── ablation ──────────────────────────────────────────────────────


def test_all_six_ablations_are_measured_with_one_mechanism_off(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    mature = runner.run_mature(phase)
    results = {mechanism: runner.run_ablation(mechanism, phase=phase, baseline=mature) for mechanism in Mechanism}

    assert set(results) == set(Mechanism)
    for mechanism, result in results.items():
        assert result.status is AblationStatus.MEASURED, f"{mechanism}가 MEASURED가 아니다"
        assert result.arm is not None
        manifest = result.arm.manifest
        assert manifest.disabled_mechanisms == (mechanism.value,)
        assert sum(1 for value in manifest.mechanisms.values() if value is False) == 1
        assert manifest.policy_version == mature.manifest.policy_version
        assert manifest.task_ids == mature.manifest.task_ids
        assert manifest.brain_version == mature.manifest.brain_version
        assert all(
            record.mechanisms[Mechanism.RISK_SHAPING.value] is True or mechanism is Mechanism.RISK_SHAPING
            for record in [manifest]
        )
        # 권한·헌법 보호는 어떤 ablation에서도 그대로다.
        assert MechanismSet(
            **{key.lower(): value for key, value in manifest.mechanisms.items()}
        ).authority_boundaries_unchanged

    # mechanism별로 관측된 효과가 서로 다르다.
    assert results[Mechanism.CONTEXT_BUILDER].delta_success < 0
    assert (results[Mechanism.GOVERNANCE_LEARNING].delta_primary or 0) > 0
    assert (results[Mechanism.EXPERIENCE_ADVISORY].delta_primary or 0) > 0
    assert results[Mechanism.TARGETED_REREASONING].delta_success < 0
    assert results[Mechanism.RISK_SHAPING].delta_success < 0


def test_ablation_cascades_are_recorded(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    mature = runner.run_mature(phase)
    experience = runner.run_ablation(Mechanism.EXPERIENCE, phase=phase, baseline=mature)
    assert experience.status is AblationStatus.MEASURED
    assert Mechanism.EXPERIENCE_ADVISORY in experience.dependent_mechanisms
    assert experience.arm is not None
    assert experience.arm.metrics.value(METRIC_EXPERIENCE_REUSE) == 0

    context = runner.run_ablation(Mechanism.CONTEXT_BUILDER, phase=phase, baseline=mature)
    assert Mechanism.EXPERIENCE_ADVISORY in context.dependent_mechanisms
    assert Mechanism.TARGETED_REREASONING in context.dependent_mechanisms


def test_unused_mechanism_ablation_is_not_run(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    fresh = runner.run_fresh()
    # fresh에는 검증된 policy도 advisory도 없다 → 두 mechanism은 사용되지 않았다.
    governance = runner.run_ablation(Mechanism.GOVERNANCE_LEARNING, phase=phase, baseline=fresh)
    assert governance.status is AblationStatus.NOT_RUN
    assert "no-op" in governance.reason
    assert governance.arm is None and governance.delta_primary is None
    advisory = runner.run_ablation(Mechanism.EXPERIENCE_ADVISORY, phase=phase, baseline=fresh)
    assert advisory.status is AblationStatus.NOT_RUN


def test_risk_shaping_ablation_keeps_basic_authority_checks(runner: GrowthRunner) -> None:
    phase = runner.growth_phase()
    mature = runner.run_mature(phase)
    guarded = [outcome for outcome in mature.outcomes if outcome.guarded_success]
    assert guarded, "guarded fixture가 mature에서 guard를 실제로 쓰지 않았다"
    assert (mature.metrics.value(METRIC_GUARDED_SUCCESS) or 0) > 0

    ablated = runner.run_ablation(Mechanism.RISK_SHAPING, phase=phase, baseline=mature)
    assert ablated.arm is not None
    assert (ablated.arm.metrics.value(METRIC_GUARDED_SUCCESS) or 0) == 0
    # 기본 권한·readiness 경계는 그대로 남는다(실행은 guard 없이 거부되고, context/authority는 유지).
    assert ablated.arm.metrics.value(METRIC_CONTEXT_TOKENS) == mature.metrics.value(METRIC_CONTEXT_TOKENS)
    assert ablated.arm.safety_violations == ()


# ─── CLI 계약 ──────────────────────────────────────────────────────


def test_cli_print_spec_registers_digest(tmp_path: Path) -> None:
    cli = load_cli()
    output = tmp_path / "spec.json"
    assert cli.main(["--print-spec", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["spec_digest"].startswith("sha256:")
    assert payload["spec"]["experiment_id"] == "growth-demo-v1"


def test_cli_rejects_unsupported_mode_and_missing_mechanism(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli = load_cli()
    assert cli.main(["--mode", "live-pilot"]) == 2
    assert "NOT_RUN" in capsys.readouterr().err
    assert cli.main(["--mode", "ablation", "--store-root", str(tmp_path / "run")]) == 2
    assert "--mechanism" in capsys.readouterr().err


def test_cli_rejects_tampered_spec(tmp_path: Path) -> None:
    cli = load_cli()
    spec_path = tmp_path / "spec.json"
    assert cli.main(["--print-spec", "--output", str(spec_path)]) == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["spec"]["success_noninferiority_margin"] = 0.9
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    assert cli.main(["--mode", "fresh", "--manifest", str(tampered), "--store-root", str(tmp_path / "run")]) == 2


def test_cli_runs_fresh_arm_with_registered_spec(tmp_path: Path) -> None:
    cli = load_cli()
    spec_path = tmp_path / "spec.json"
    assert cli.main(["--print-spec", "--output", str(spec_path)]) == 0
    output = tmp_path / "fresh.json"
    code = cli.main(
        [
            "--mode",
            "fresh",
            "--manifest",
            str(spec_path),
            "--store-root",
            str(tmp_path / "run"),
            "--output",
            str(output),
            "--source-head",
            "test-head",
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manifest"]["arm"] == "FRESH"
    assert payload["manifest"]["source_head"] == "test-head"
    assert payload["manifest"]["spec_digest"].startswith("sha256:")
    assert payload["metrics"]["values"][METRIC_TASK_SUCCESS] > 0
