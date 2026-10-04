"""Live mechanism settings must govern execution or fail closed."""

from dataclasses import replace
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.growth import ArmRole, GrowthBenchmarkError, MechanismSet
from antigravity_k.engine.cognitive.live_pilot import LiveTrialRequest, TrialOrder
from antigravity_k.engine.cognitive.live_trial_adapter import LiveTrialAdapter, ScriptedModelPort
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port


def test_disabled_learning_prevents_active_policy_context(tmp_path: Path) -> None:
    # Given a validated policy, with governance learning then disabled.
    adapter = LiveTrialAdapter(tmp_path, ScriptedModelPort(), fixture_tool_port)
    adapter.run_train_validation()
    adapter.mechanisms = replace(adapter.mechanisms, governance_learning=False)
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.MATURE, 0, TrialOrder.FRESH_FIRST, None, ())
    # When FINAL executes.
    result = adapter.run_trial(request)
    # Then missing evidence still requires expansion, as in Fresh.
    assert result.brain_calls == 2


def test_disabled_rereasoning_prevents_expansion_call(tmp_path: Path) -> None:
    # Given missing context but targeted rereasoning disabled.
    adapter = LiveTrialAdapter(
        tmp_path, ScriptedModelPort(), fixture_tool_port, mechanisms=MechanismSet(targeted_rereasoning=False)
    )
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    # When the model requests expansion.
    result = adapter.run_trial(request)
    # Then no extra model call is made.
    assert result.brain_calls == 1


def test_unsupported_ablation_rejected_before_provider(tmp_path: Path) -> None:
    # Given a mechanism combination the live adapter cannot honor.
    model = ScriptedModelPort()
    # When an adapter is constructed.
    with pytest.raises(GrowthBenchmarkError):
        LiveTrialAdapter(tmp_path, model, fixture_tool_port, mechanisms=MechanismSet(experience=False))
    # Then no inference occurred.
    assert model.calls == 0


def test_drift_task_keeps_baseline_context(tmp_path: Path) -> None:
    # Given an active policy learned on the registered training goal family.
    adapter = LiveTrialAdapter(tmp_path, ScriptedModelPort(), fixture_tool_port)
    adapter.run_train_validation()
    request = LiveTrialRequest("PT-11", "FINAL", ArmRole.MATURE, 0, TrialOrder.FRESH_FIRST, None, ())
    # When a registered negative-transfer task runs.
    result = adapter.run_trial(request)
    # Then it gets baseline context and must request missing evidence.
    assert result.brain_calls == 2


def test_refused_target_preserves_actual_provider_cost(tmp_path: Path) -> None:
    # Given a measured model response asking for expansion then an outside target.
    from antigravity_k.engine.cognitive.live_trial_types import ModelChoice

    class OutsideModel(ScriptedModelPort):
        def choose(self, request, task, *, missing_refs, workspace):
            return ModelChoice("x", str(tmp_path.parent / "outside.txt"), bool(missing_refs), tokens=17)

    adapter = LiveTrialAdapter(tmp_path, OutsideModel(), fixture_tool_port)
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    # When the target is refused after inference.
    result = adapter.run_trial(request)
    # Then actual model work remains in the ledger, with zero dispatched tools.
    assert result.brain_calls == 2
    assert result.tokens == 34
    assert result.tool_calls == 0


def test_every_live_training_experience_comes_from_observed_episode(tmp_path: Path) -> None:
    # Given a live adapter with actual file readback TRAIN observations.
    from antigravity_k.engine.cognitive.models import ExperiencePayload
    from antigravity_k.engine.cognitive.store import CanonicalStore

    adapter = LiveTrialAdapter(tmp_path, ScriptedModelPort(), fixture_tool_port)
    # When TRAIN and validation finish.
    adapter.run_train_validation()
    # Then no additional synthetic COMPLETE advisory core appears in the canonical store.
    records = CanonicalStore(tmp_path / "mature" / "store", git_enabled=False).list_committed()
    experiences = [record for record in records if isinstance(record.payload, ExperiencePayload)]
    actual_ids = {observation.experience_id for observation in adapter.learning.observations}
    assert {record.id for record in experiences} == actual_ids
    assert all(record.payload.episode_reference for record in experiences)


def test_active_policy_reuses_actual_train_cores_for_initial_context(tmp_path: Path) -> None:
    # Given only observed TRAIN cores and a validation-promoted depth policy.
    adapter = LiveTrialAdapter(tmp_path, ScriptedModelPort(), fixture_tool_port)
    adapter.run_train_validation()
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.MATURE, 0, TrialOrder.FRESH_FIRST, None, ())
    # When the held-out task executes.
    result = adapter.run_trial(request)
    # Then real experience links supply initial evidence without a second model call.
    assert result.success
    assert result.brain_calls == 1
    assert result.effective_policy_version == adapter.policy_gate.promoted_version
    assert result.policy_version_reported


def test_failed_dispatch_never_claims_successful_execution_or_file_read(tmp_path: Path) -> None:
    # Given a tool executor that fails without creating a file.
    from antigravity_k.engine.cognitive.actions import ToolExecutorPort
    from antigravity_k.engine.cognitive.models import ObservationPayload, ObservationStatus, OutcomeStatus
    from antigravity_k.engine.cognitive.store import CanonicalStore

    class FailedExecutor:
        def execute(self, tool, arguments):
            return "failure"

    adapter = LiveTrialAdapter(
        tmp_path, ScriptedModelPort(), lambda root: ToolExecutorPort(FailedExecutor(), lambda result: True)
    )
    request = LiveTrialRequest("GT-T1", "TRAIN", ArmRole.MATURE, 0, TrialOrder.FRESH_FIRST, None, ())
    # When execution is evaluated.
    result = adapter.run_trial(request)
    # Then missing output is recorded as unavailable, never successful execution or a completed file read.
    assert not result.success
    assert adapter.learning.observations[0].evaluations.execution.status is not OutcomeStatus.MATCH
    records = CanonicalStore(tmp_path / "mature" / "store", git_enabled=False).list_committed()
    observations = [record.payload for record in records if isinstance(record.payload, ObservationPayload)]
    assert observations and all(item.status is ObservationStatus.UNAVAILABLE for item in observations)


def test_experience_selection_is_durable(tmp_path: Path) -> None:
    # Given an experiment with real TRAIN observations.
    from antigravity_k.engine.cognitive.models import EventPayload
    from antigravity_k.engine.cognitive.store import CanonicalStore

    adapter = LiveTrialAdapter(tmp_path, ScriptedModelPort(), fixture_tool_port)
    # When selection and experience formation complete.
    adapter.run_train_validation()
    # Then a fresh store reader can recover every selection reason/disposition.
    records = CanonicalStore(tmp_path / "mature" / "store", git_enabled=False).list_committed()
    selections = [
        record.payload for record in records if isinstance(record.payload, EventPayload) and record.payload.selection
    ]
    assert {item.episode_id for item in selections} == {item.episode_id for item in adapter.learning.observations}
