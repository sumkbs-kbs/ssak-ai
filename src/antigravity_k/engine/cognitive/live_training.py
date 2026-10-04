"""TRAIN then disjoint VALIDATION orchestration for the live adapter."""

from __future__ import annotations

from antigravity_k.engine.cognitive.growth import ArmRole, SplitRole, tasks_for
from antigravity_k.engine.cognitive.learning import ValidationObservation
from antigravity_k.engine.cognitive.live_pilot import LiveTrialRequest, TrialOrder
from antigravity_k.engine.cognitive.live_trial_types import LiveTrialHost, PolicyGateState


def train_validation(adapter: LiveTrialHost, force_validation_fail: bool | None) -> PolicyGateState:
    """TRAIN 경험 후 VALIDATION. 실패하면 promote하지 않는다 (R18-A2)."""

    if force_validation_fail is not None:
        adapter.policy_gate.force_validation_fail = force_validation_fail
    train = tasks_for(adapter.tasks, SplitRole.TRAIN)
    validation = tasks_for(adapter.tasks, SplitRole.VALIDATION)
    adapter.policy_gate.train_total = 0
    adapter.policy_gate.train_successes = 0
    for index, task in enumerate(train):
        req = LiveTrialRequest(
            task_id=task.task_id,
            split=SplitRole.TRAIN.value,
            arm=ArmRole.MATURE,
            trial_index=index,
            order=TrialOrder.FRESH_FIRST,
            policy_version=None,
            advisory_refs=(),
        )
        out = adapter.run_trial(req)
        adapter.policy_gate.train_total += 1
        adapter.policy_gate.train_successes += int(out.success)
    candidate = adapter.learning.propose()
    validation_observations: list[ValidationObservation] = []
    adapter.policy_gate.validation_total = 0
    adapter.policy_gate.validation_successes = 0
    for index, task in enumerate(validation):
        req = LiveTrialRequest(
            task_id=task.task_id,
            split=SplitRole.VALIDATION.value,
            arm=ArmRole.MATURE,
            trial_index=index,
            order=TrialOrder.FRESH_FIRST,
            policy_version=adapter.policy_gate.candidate_version,
            advisory_refs=(),
        )
        out = adapter.run_trial(req)
        adapter.policy_gate.validation_total += 1
        validation_observations.append(
            ValidationObservation(
                task_id=task.task_id, success=out.success and not adapter.policy_gate.force_validation_fail
            )
        )
        # force fail overrides observed successes for promotion gate
        if not adapter.policy_gate.force_validation_fail and out.success:
            adapter.policy_gate.validation_successes += 1
    adapter.policy_gate.promoted_version = adapter.learning.validate(
        candidate,
        tuple(validation_observations),
        minimum=adapter.policy_gate.validation_minimum,
        store=adapter._seed(adapter.arm_root(ArmRole.MATURE)),
    )
    return adapter.policy_gate
