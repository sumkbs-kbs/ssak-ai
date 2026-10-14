from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from antigravity_k.engine.cognitive.growth import GrowthBenchmarkError, default_corpus_tasks, default_spec
from antigravity_k.engine.cognitive.live_pilot import (
    LiveArmSummary,
    LivePilotPlan,
    LivePilotVerdict,
    ProviderAttestation,
    TrialLedgerEntry,
    aggregate_from_ledger,
)


def entry() -> TrialLedgerEntry:
    return TrialLedgerEntry(
        run_id="raw-contract",
        trial_uid="t1",
        task_id="sample",
        arm="fresh",
        repetition=1,
        order="ab",
        status="failed",
        started_at=None,
        finished_at=None,
        outcome=None,
    )


def reduce(
    entries: Sequence[TrialLedgerEntry] | Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, LiveArmSummary], LivePilotVerdict | None]:
    return aggregate_from_ledger(
        entries,
        spec=default_spec(),
        plan=LivePilotPlan(trials_per_task=1),
        tasks=default_corpus_tasks(),
        attestation=ProviderAttestation("fixture", "fixture", "fixture", "fixture", "fixture", True),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("started_at", 17), ("finished_at", []), ("policy_version", False), ("outcome", 9), ("outcome", {1: "invalid"})],
)
def test_raw_ledger_rejects_untyped_metadata_before_summary(field: str, value: object) -> None:
    row = dict(entry().as_mapping())
    row[field] = value
    with pytest.raises(GrowthBenchmarkError, match="ledger"):
        reduce([row])


def test_raw_nullable_ledger_reduction_matches_typed_entry_without_promoting_failure() -> None:
    value = entry()
    assert reduce([dict(value.as_mapping())]) == reduce([value])
