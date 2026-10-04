"""R18 — LiveTrialAdapter acceptance."""

from __future__ import annotations

from pathlib import Path

from antigravity_k.engine.cognitive.growth import (
    ArmRole,
    BenchmarkSpec,
    RunKind,
    SplitRole,
    default_corpus_tasks,
    default_spec,
)
from antigravity_k.engine.cognitive.live_pilot import (
    LivePilotHarness,
    LivePilotPlan,
    LivePilotStatus,
    LiveTrialRequest,
    TrialEventStatus,
    TrialOrder,
)
from antigravity_k.engine.cognitive.live_trial_adapter import LiveTrialAdapter, ScriptedModelPort
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port


def live_spec() -> BenchmarkSpec:
    return default_spec(experiment_id="growth-live-pilot-v1", run_kind=RunKind.LIVE_PILOT)


def _final_task():
    return next(t for t in default_corpus_tasks() if t.split is SplitRole.FINAL)


def test_r18_a1_wrong_model_is_real_failure_not_canned(tmp_path: Path) -> None:
    task = _final_task()
    adapter = LiveTrialAdapter(
        executor_factory=fixture_tool_port, workspace=tmp_path / "ws", model=ScriptedModelPort(mode="wrong")
    )
    req = LiveTrialRequest(
        task_id=task.task_id,
        split=SplitRole.FINAL.value,
        arm=ArmRole.FRESH,
        trial_index=0,
        order=TrialOrder.FRESH_FIRST,
        policy_version=None,
        advisory_refs=(),
    )
    out = adapter.run_trial(req)
    assert out.success is False
    target = tmp_path / "ws" / "fresh" / "trials" / "FINAL" / task.task_id / "0" / f"{task.task_id}.txt"
    assert target.exists()
    assert target.read_text(encoding="utf-8") != task.append_content
    assert "WRONG:" in target.read_text(encoding="utf-8")


def test_r18_a2_failed_validation_not_applied_to_final_mature(tmp_path: Path) -> None:
    adapter = LiveTrialAdapter(
        executor_factory=fixture_tool_port,
        workspace=tmp_path / "ws",
        model=ScriptedModelPort(mode="correct"),
    )
    gate = adapter.run_train_validation(force_validation_fail=True)
    assert gate.promoted_version is None
    assert gate.validation_passed is False

    final = _final_task()
    req = LiveTrialRequest(
        task_id=final.task_id,
        split=SplitRole.FINAL.value,
        arm=ArmRole.MATURE,
        trial_index=0,
        order=TrialOrder.FRESH_FIRST,
        policy_version="should-not-apply",
        advisory_refs=(),
    )
    out = adapter.run_trial(req)
    policy_dir = tmp_path / "ws" / "mature" / "policy"
    assert not policy_dir.exists() or not any(policy_dir.glob("*-promoted.json"))
    assert "policy=None" in out.detail


def test_r18_a3_fresh_and_mature_roots_independent(tmp_path: Path) -> None:
    adapter = LiveTrialAdapter(
        executor_factory=fixture_tool_port, workspace=tmp_path / "ws", model=ScriptedModelPort(mode="correct")
    )
    adapter.run_train_validation(force_validation_fail=False)
    if adapter.policy_gate.promoted_version is None:
        adapter.policy_gate.promoted_version = "forced-promoted-for-digest"
    final = _final_task()
    fresh_req = LiveTrialRequest(
        task_id=final.task_id,
        split=SplitRole.FINAL.value,
        arm=ArmRole.FRESH,
        trial_index=0,
        order=TrialOrder.FRESH_FIRST,
        policy_version=None,
        advisory_refs=(),
    )
    mature_req = LiveTrialRequest(
        task_id=final.task_id,
        split=SplitRole.FINAL.value,
        arm=ArmRole.MATURE,
        trial_index=0,
        order=TrialOrder.FRESH_FIRST,
        policy_version=adapter.policy_gate.promoted_version,
        advisory_refs=(),
    )
    adapter.run_trial(fresh_req)
    adapter.run_trial(mature_req)
    assert adapter.root_digest(ArmRole.FRESH) != adapter.root_digest(ArmRole.MATURE)
    assert not (tmp_path / "ws" / "fresh" / "policy").exists()
    assert (
        adapter.learning.policies.active_policy(
            __import__("antigravity_k.engine.cognitive.models", fromlist=["PolicyTarget"]).PolicyTarget.CONTEXT_DEPTH
        )
        is not None
    )


def test_r18_a4_workspace_jail_and_timeout_partial_ledger(tmp_path: Path) -> None:
    task = _final_task()
    outside = LiveTrialAdapter(
        executor_factory=fixture_tool_port, workspace=tmp_path / "ws", model=ScriptedModelPort(mode="outside")
    )
    req = LiveTrialRequest(
        task_id=task.task_id,
        split=SplitRole.FINAL.value,
        arm=ArmRole.FRESH,
        trial_index=0,
        order=TrialOrder.FRESH_FIRST,
        policy_version=None,
        advisory_refs=(),
    )
    out = outside.run_trial(req)
    assert out.success is False
    assert out.tool_calls == 0
    assert out.error_category == "WORKSPACE_JAIL"
    assert not (tmp_path / "OUTSIDE_JAIL.txt").exists()

    timeout_adapter = LiveTrialAdapter(
        executor_factory=fixture_tool_port,
        workspace=tmp_path / "ws2",
        model=ScriptedModelPort(mode="timeout"),
    )
    harness = LivePilotHarness(
        live_spec(),
        LivePilotPlan(trials_per_task=3),
        tasks=default_corpus_tasks(),
    )
    report = harness.run(timeout_adapter)
    assert report.status is LivePilotStatus.NOT_COMPLETE
    assert any(e.status == TrialEventStatus.TIMEOUT.value for e in report.ledger)
    assert any(e.status == TrialEventStatus.STARTED.value for e in report.ledger)


def test_model_boundary_excludes_private_answer(tmp_path: Path) -> None:
    # Given a model that inspects its actual input boundary.
    from dataclasses import replace

    from antigravity_k.engine.cognitive.live_trial_adapter import ModelChoice

    class InspectingModel(ScriptedModelPort):
        def choose(self, request, task, *, missing_refs, workspace):
            assert not hasattr(task, "append_content")
            assert not hasattr(task, "expected_outcome")
            assert hasattr(task, "evidence")
            return ModelChoice(append_content="model-output")

    task = replace(_final_task(), append_content="private-oracle-value")
    adapter = LiveTrialAdapter(
        executor_factory=fixture_tool_port, workspace=tmp_path, model=InspectingModel(), tasks=(task,)
    )
    request = LiveTrialRequest(task.task_id, "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    # When the trial passes input to the model.
    result = adapter.run_trial(request)
    # Then the private evaluator answer never crossed the model boundary.
    assert not result.success


def test_repeated_trials_have_independent_effect_files(tmp_path: Path) -> None:
    # Given identical requests distinguished by trial index.
    from dataclasses import replace

    task = _final_task()
    adapter = LiveTrialAdapter(executor_factory=fixture_tool_port, workspace=tmp_path, model=ScriptedModelPort())
    request = LiveTrialRequest(task.task_id, "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    adapter.run_trial(request)
    # When a second trial executes.
    result = adapter.run_trial(replace(request, trial_index=1))
    # Then the previous append does not contaminate the measurement.
    assert result.success


def test_train_experience_has_real_canonical_lineage_and_active_policy(tmp_path: Path) -> None:
    # Given a model port with explicit grounds and isolated real file tools.
    from antigravity_k.engine.cognitive.models import PolicyTarget
    from antigravity_k.engine.cognitive.store import CanonicalStore

    adapter = LiveTrialAdapter(executor_factory=fixture_tool_port, workspace=tmp_path, model=ScriptedModelPort())
    # When TRAIN and disjoint validation finish.
    gate = adapter.run_train_validation()
    # Then promotion is backed by complete, resolvable observed experience.
    assert gate.promoted_version
    store = CanonicalStore(tmp_path / "mature" / "store", git_enabled=False)
    assert adapter.learning.policies.active_policy(PolicyTarget.CONTEXT_DEPTH)
    for observation in adapter.learning.observations:
        core = adapter.learning.ledger.core(observation.experience_id)
        assert core and not core.missing_references
        for ref in (
            core.context_ref,
            core.judgment_ref,
            core.decision_ref,
            core.action_ref,
            core.outcome_ref,
            *core.observation_refs,
        ):
            assert ref and store.read(ref)
