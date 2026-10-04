# C06 v1 — Experience lineage, replay and assessment

Producer → consumer: **R11/R12 → R13/R18**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **runtime formation/replay and learning-integrity boundary independently verified in their scoped final goal review; bound to amended frozen source manifest**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

Every episode may produce an operational trail. SelectionDisposition distinguishes OPERATIONAL_ONLY, DEFERRED and EXPERIENCE; routine matching execution need not become learning. Body may measure observed outcome/execution, while semantic decision quality requires sourced Primary/Human assessment and otherwise stays UNKNOWN. Readiness is not semantic correctness.

ExperiencePayload adds optional episode_reference and evidence_refs without breaking old records. ExperienceCore includes context/judgment/governance/decision/action/observations/outcome/evidence and unknowns. Serialization preserves all lineage and typed evidence relations. material_digest excludes only a newly proposed experience ID; callers must use the core returned by form_experience, because a material-identical retry reuses the committed identity. Changed material is a distinct append, never replacement of history. Ingested committed cores are readable but already sunk, so replay does not republish them. A legacy core with unknown episode remains INCOMPLETE instead of guessing context as episode; conflicting supplied metadata or same-ID changed material raises. Interpretation and later assessment remain separate appended records.

## Refusal and failure behavior

ExperienceContractError for conflicting identity/metadata or invalid selection. UNKNOWN/UNEVALUATED and DEFERRED must not be projected as success.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/experience.py

```python
@dataclass(frozen=True, slots=True)
class ExperienceCore:
    experience_id: str
    episode_reference: str
    trigger: str
    context_ref: str | None = None
    judgment_ref: str | None = None
    governance_ref: str | None = None
    decision_ref: str | None = None
    action_ref: str | None = None
    observation_refs: tuple[str, ...] = ()
    outcome_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    remaining_unknowns: tuple[str, ...] = ()
    future_attention: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_references: tuple[str, ...] = ()
    def as_mapping(self) -> Mapping[str, object]: ...
    def digest(self) -> str: ...
    def material_digest(self) -> str: ...
    def to_record(self, *, project_id: str, producer: Producer, created_at: datetime) -> Record: ...
```

### src/antigravity_k/engine/cognitive/experience.py

```python
@dataclass(frozen=True, slots=True)
class DecisionAssessment:
    status: OutcomeStatus
    available_at_decision: bool
    reason: str
    evidence_refs: tuple[str, ...] = ()
```

### src/antigravity_k/engine/cognitive/experience.py

```python
def evaluate_decision(comparison: OutcomeComparison, *, available_at_decision: bool | None=None, reason: str='', evidence_refs: Sequence[str]=(), assessed_status: OutcomeStatus | None=None, assessment: DecisionAssessment | None=None) -> DecisionEvaluation: ...
```

### src/antigravity_k/engine/cognitive/experience.py

```python
def evaluate_execution(*, succeeded: bool | None, receipt_ref: str | None=None, reason: str='') -> ExecutionEvaluation: ...
```

### src/antigravity_k/engine/cognitive/experience.py

```python
class ExperienceLedger:
    def __init__(self) -> None: ...
    @property
    def operational_records(self) -> tuple[OperationalRecord, ...]: ...
    @property
    def selections(self) -> tuple[ExperienceSelection, ...]: ...
    @property
    def records(self) -> tuple[Record, ...]: ...
    def pending_sink_records(self) -> tuple[Record, ...]: ...
    def mark_sunk(self, count: int) -> None: ...
    def core(self, experience_id: str) -> ExperienceCore | None: ...
    def core_digest_history(self, experience_id: str) -> tuple[str, ...]: ...
    def interpretations(self, experience_id: str) -> tuple[Interpretation, ...]: ...
    def supplements(self, experience_id: str) -> tuple[ExperienceSupplement, ...]: ...
    def record_operational(self, record: OperationalRecord, *, project_id: str='', producer: Producer | None=None, created_at: datetime | None=None) -> OperationalRecord: ...
    def select(self, record: OperationalRecord, *, comparison: OutcomeComparison, signals: EpisodeSignals, producer: Producer, recorded_at: datetime, evidence_refs: Sequence[str]=(), policy_version: str | None=None, note: str='') -> ExperienceSelection: ...
    def form_experience(self, selection: ExperienceSelection, core: ExperienceCore, *, project_id: str, producer: Producer, created_at: datetime) -> ExperienceCore: ...
    def cores_for_episode(self, episode_reference: str) -> tuple[ExperienceCore, ...]: ...
    def ingest_core_record(self, record: Record, *, episode_reference: str='') -> ExperienceCore: ...
    def interpret(self, experience_id: str, *, author: Producer, meaning: str, confidence_profile: ConfidenceProfile, applicability_profile: ApplicabilityProfile | None=None, evidence_ids: Sequence[str]=(), recorded_at: datetime, project_id: str='', created_at: datetime | None=None) -> Interpretation: ...
    def supplement(self, experience_id: str, *, observation: Record, note: str, recorded_at: datetime) -> ExperienceSupplement: ...
```

### src/antigravity_k/engine/cognitive/models.py

```python
class ExperiencePayload(EntityPayloadModel):
    entity_type: Literal['Experience'] = 'Experience'
    episode_reference: str | None = None
    evidence_refs: tuple[str, ...] = ()
    trigger: str = Field(min_length=1)
    historical_refs: tuple[str, ...] = ()
    remaining_unknowns: tuple[str, ...] = ()
    future_attention: tuple[str, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_references: tuple[str, ...] = ()
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "entity_type": "Experience",
  "episode_reference": null,
  "evidence_refs": [],
  "trigger": "legacy-replay",
  "integrity": "INCOMPLETE",
  "missing_references": [
    "episode_reference"
  ]
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_episode.py tests/cognitive/test_experience_roundtrip.py tests/cognitive/test_models.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_episode.py :: test_r07_a1_successful_evidence_updates_plan_before_commit`
- `tests/cognitive/test_episode.py :: test_r07_a2_deny_then_safe_alternative_runs_next_round`
- `tests/cognitive/test_episode.py :: test_r07_a3_repeat_signature_stops_but_new_evidence_revision_retries`
- `tests/cognitive/test_episode.py :: test_r07_a4_total_request_budget_caps_large_initial_batch`
- `tests/cognitive/test_episode.py :: test_r07_a5_simple_and_no_delta_stop_without_extra_secondary`
- `tests/cognitive/test_episode.py :: test_r11_a1_stopped_no_delta_has_operational_trail_without_experience`
- `tests/cognitive/test_episode.py :: test_r11_a2_deviation_core_survives_restart_via_canonical_records`
- `tests/cognitive/test_episode.py :: test_r11_a3_routine_match_stays_operational_only`
- `tests/cognitive/test_episode.py :: test_r11_a4_provider_neutral_core_reader`
- `tests/cognitive/test_episode.py :: test_r11_a5_deferred_then_late_interpretation_leaves_core_bytes`
- `tests/cognitive/test_episode.py :: test_r11_a6_selected_core_idempotent_on_replay`
- `tests/cognitive/test_episode.py :: test_r12_a1_good_outcome_poor_decision_are_separate_axes`
- `tests/cognitive/test_episode.py :: test_r12_a2_bad_outcome_sound_contemporaneous_decision`
- `tests/cognitive/test_episode.py :: test_r12_a3_no_assessment_means_decision_unknown_despite_readiness`
- `tests/cognitive/test_experience_roundtrip.py :: test_roundtrip_preserves_full_core_and_typed_evidence`
- `tests/cognitive/test_experience_roundtrip.py :: test_regenerated_selection_returns_original_core_after_restart`
- `tests/cognitive/test_experience_roundtrip.py :: test_ingestion_preserves_pending_new_records_without_republishing_history`
- `tests/cognitive/test_experience_roundtrip.py :: test_legacy_record_marks_unknown_episode_instead_of_guessing_context`
- `tests/cognitive/test_experience_roundtrip.py :: test_conflicting_ingestion_cannot_replace_committed_core`
- `tests/cognitive/test_experience_roundtrip.py :: test_revised_history_is_appended_without_overwriting_original`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in [contract snapshot](contract-source-manifest.json), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Finalization regression additions

The current fix-specific verification also includes:

- `tests/cognitive/test_runtime_experience_lineage.py`
  Scenarios: `test_rethought_plan_supplies_selected_core_lineage`, `test_performed_phase_missing_reference_is_incomplete`, `test_simple_episode_does_not_require_expansion_governance_reference`, `test_observed_result_without_supplied_record_gets_canonical_lineage`, `test_governed_episode_without_governance_record_is_incomplete`.

## Old-wire digest compatibility at final source freeze

`models.to_wire` preserves absent additive fields using `model_fields_set`: Experience episode_reference/evidence_refs, BrainJudgment delta, and ExecutionReceipt detail are omitted only when absent in the original model input. Explicitly supplied new values serialize normally. This prevents new defaults from changing canonical digests of genuine old records and invalidating preissued Context handles. Verification: `tests/cognitive/test_additive_wire_compatibility.py` (10 regression scenarios including real old-wire store reopen/handle resolution); implementer broader 128-test run passed. Independent final model-wire re-review is tracked in finalization evidence.
