"""Actual policy reporting is distinct from requested policy and legacy unknowns."""

from antigravity_k.engine.cognitive.growth import RunKind, default_corpus_tasks, default_spec
from antigravity_k.engine.cognitive.live_pilot import LivePilotHarness, LivePilotPlan, LiveTrialOutcome
from antigravity_k.engine.cognitive.live_trial_types import ScriptedModelPort


def test_terminal_policy_uses_actual_report_including_explicit_none() -> None:
    # Given requested policy differs from actual policy, with explicit drift refusal.
    tasks = tuple(task for task in default_corpus_tasks() if task.task_id in {"PT-01", "PT-11"})

    class Port:
        attestation = ScriptedModelPort().attestation

        def run_trial(self, request):
            actual = "validated-v1" if request.task_id == "PT-01" and request.arm.value == "MATURE" else None
            return LiveTrialOutcome(
                True, 0, 1, 1, 7, 1.0, effective_policy_version=actual, policy_version_reported=True
            )

    harness = LivePilotHarness(
        default_spec(tasks=tasks, run_kind=RunKind.LIVE_PILOT),
        LivePilotPlan(3, policy_version="requested-v0"),
        tasks=tasks,
    )
    # When terminal entries are emitted.
    report = harness.run(Port())
    terminal = [entry for entry in report.ledger if entry.status == "COMPLETED"]
    # Then effective policy is recorded and explicit None never falls back to the request.
    assert len(terminal) == 12
    for entry in terminal:
        expected = "validated-v1" if entry.task_id == "PT-01" and entry.arm == "MATURE" else None
        assert entry.policy_version == expected
        assert entry.policy_version_reported
        assert entry.requested_policy_version == ("requested-v0" if entry.arm == "MATURE" else None)


def test_legacy_outcome_does_not_claim_effective_policy_reporting() -> None:
    # Given an old port without effective policy metadata.
    result = LiveTrialOutcome(True, 0, 1, 1, 7, 1.0)
    # When serialized.
    payload = result.as_mapping()
    # Then unreported and explicitly no-policy remain distinguishable.
    assert payload["policy_version_reported"] is False
