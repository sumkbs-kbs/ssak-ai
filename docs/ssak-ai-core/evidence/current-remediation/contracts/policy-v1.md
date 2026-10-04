# C07 v1 — Versioned policy, pinning and behavior trace

> Publication note (2026-10-04): The raw artifacts marked "local-only archive" are retained in the original local QA workspace and are not included in this public repository. Historical results and hashes describe their recorded revisions. This published summary does not supply the raw evidence or certify today's source.


Producer → consumer: **R13 → R18/R19**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **authoritative learning-integrity boundary has scoped independent goal PASS; registered live experiment remains a separate C08 scope**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

**Tested supported mechanism:** the live experiment uses an operator-prespecified `HUMAN_REQUEST` context-depth hypothesis, then actual TRAIN experience and held-out validation determine whether that operating policy is usable. The generic candidate/validation interfaces below do not imply autonomous semantic hypothesis discovery. Policy/Experience consumption effects are measured by the separately preregistered R19 removal contrasts; this is not a full-factorial interaction study.

A LearningCandidate plus validation report registers a version; registration is not activation. promote and rollback use expected_active_version CAS. Only allowlisted operational targets are eligible; no policy can change protected authority, Human ceilings or historical records. In-flight policy pins retain their chosen version unless explicitly invalidated by authority; current action freshness is checked independently.

BehaviorChangeTrace receives actual shadow_selection and actual_selection from two selectors on the same frozen input, not expected answer IDs assembled by the reporter. Outcome reference can be linked later. Live learning must consume selected TRAIN experience, derive a candidate operating change, validate it before FINAL Mature use, and keep Fresh state separate. A version marker or changed string alone is not measured changed behavior. The learning-integrity boundary has scoped independent goal PASS; live training/experiment outcome is tracked separately and no performance/generalization conclusion is granted by this interface contract. Negative transfer and failed validation remain visible and prevent promotion.

## Refusal and failure behavior

PolicyCasConflict, PromotionRefused, RetiredVersionRefused, AuthorityWideningRefused, AuthorityRevokedError and PolicyNotFoundError.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/policy_store.py

```python
@dataclass(frozen=True, slots=True)
class PolicyVersion:
    policy_id: str
    version: str
    record_id: str
    target: PolicyTarget
    rule: str
    parameters: Mapping[str, ScalarParameter]
    candidate_id: str
    validation_report_id: str
    producer: Producer
    created_at: datetime
    lifecycle: KnowledgeLifecycle = KnowledgeLifecycle.CANDIDATE
    compatibility: str = ''
    def as_mapping(self) -> Mapping[str, object]: ...
    def digest(self) -> str: ...
    def to_record(self, *, project_id: str) -> Record: ...
```

### src/antigravity_k/engine/cognitive/policy_store.py

```python
@dataclass(frozen=True, slots=True)
class BehaviorChangeTrace:
    trace_id: str
    policy_id: str
    policy_version: str
    task_id: str
    shadow_selection: tuple[str, ...]
    actual_selection: tuple[str, ...]
    recorded_at: datetime
    producer: Producer
    outcome_ref: str | None = None
    difference: str = ''
    def as_mapping(self) -> Mapping[str, object]: ...
    def digest(self) -> str: ...
    @property
    def changed(self) -> bool: ...
    def to_record(self, *, project_id: str, policy_record_id: str) -> Record: ...
```

### src/antigravity_k/engine/cognitive/policy_store.py

```python
@dataclass(frozen=True, slots=True)
class PolicyPin:
    episode_id: str
    policy_id: str
    policy_version: str
    pinned_at: datetime
    authority_revision: int | None = None
    revoked_at: datetime | None = None
    revoked_reason: str = ''
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/policy_store.py

```python
class PolicyStore:
    def __init__(self, *, guard: ProtectedWriteGuard | None=None) -> None: ...
    @property
    def records(self) -> tuple[Record, ...]: ...
    def versions(self, policy_id: str) -> tuple[PolicyVersion, ...]: ...
    def version(self, policy_id: str, version: str) -> PolicyVersion: ...
    def active_version(self, policy_id: str) -> str | None: ...
    def active_policy(self, target: PolicyTarget) -> PolicyVersion | None: ...
    def activations(self, policy_id: str) -> tuple[ActivationEvent, ...]: ...
    def retirements(self, policy_id: str) -> tuple[RetirementEvent, ...]: ...
    def traces(self, policy_id: str) -> tuple[BehaviorChangeTrace, ...]: ...
    def pins(self) -> tuple[PolicyPin, ...]: ...
    def pin_of(self, episode_id: str) -> PolicyPin | None: ...
    def register(self, candidate: LearningCandidate, report: ValidationReport, *, version: str, producer: Producer, created_at: datetime, policy_id: str | None=None, compatibility: str='') -> PolicyVersion: ...
    def promote(self, policy_id: str, *, version: str, expected_active_version: str | None, actor: Producer, reason: str, occurred_at: datetime) -> ActivationEvent: ...
    def rollback(self, policy_id: str, *, to_version: str, reason: str, expected_active_version: str | None, actor: Producer, occurred_at: datetime) -> ActivationEvent: ...
    def retire(self, policy_id: str, *, version: str, reason: str, actor: Producer, occurred_at: datetime) -> RetirementEvent: ...
    def pin(self, episode_id: str, policy_id: str, *, pinned_at: datetime, authority_revision: int | None=None) -> PolicyPin: ...
    def resolve(self, pin: PolicyPin) -> PolicyVersion: ...
    def revoke_authority(self, *, reason: str, revoked_at: datetime) -> tuple[PolicyPin, ...]: ...
    def record_behavior_change(self, *, policy_id: str, version: str, task_id: str, shadow_selection: Sequence[str], actual_selection: Sequence[str], producer: Producer, recorded_at: datetime, outcome_ref: str | None=None, difference: str='') -> BehaviorChangeTrace: ...
    def growth_evidence(self, policy_id: str, *, minimum_changed_tasks: int=1) -> GrowthEvidence | None: ...
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "episode_id": "episode-1",
  "policy_id": "policy-1",
  "policy_version": "v1",
  "authority_revision": 3,
  "revoked_at": null,
  "revoked_reason": ""
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_learning.py tests/cognitive/test_live_trial_adapter.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a1_wrong_model_is_real_failure_not_canned`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a2_failed_validation_not_applied_to_final_mature`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a3_fresh_and_mature_roots_independent`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a4_workspace_jail_and_timeout_partial_ledger`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in contract snapshot (local-only archive: `contract-source-manifest.json`, unpublished), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Finalization regression additions

The current fix-specific verification also includes:

- `tests/cognitive/test_learning_experience_binding.py`
  Scenarios: `test_claimed_experience_without_lookup_is_rejected`, `test_unresolved_or_inconsistent_experience_is_rejected`, `test_complete_resolved_experience_remains_mechanically_aggregatable`, `test_raw_comparison_without_experience_claim_needs_no_lookup`, `test_handbuilt_summary_cannot_bypass_candidate_provenance_check`, `test_validator_rechecks_core_provenance_before_issuing_report`, `test_complete_ledger_lookup_binds_aggregation_and_candidate`.
