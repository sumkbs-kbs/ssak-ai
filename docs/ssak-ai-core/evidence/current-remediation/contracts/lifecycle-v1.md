# C05 v1 — Durable action and observation publication

Producer → consumer: **R09 → R10/R11/R16**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **scoped independent PASS for corrected observation publication/recovery at the review hashes**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

The SQLite claim/projection plus canonical records form durable evidence; ActionRun is only an in-memory view. Admission records a stable action identity before external execution. A missing receipt after admission is UNKNOWN/pending, never proof of no effect or permission to retry. Timeout/cancellation does not release a claim automatically.

Observation publication uses BEGIN IMMEDIATE with expected receipt/revision/status. Canonical observation/receipt records are appended before authoritative projection settlement; a sink failure leaves the prior pending projection. A crash after canonical append but before SQLite commit may leave immutable records ahead of the projection. Stable identities and original timestamps let an identical restart retry reuse those records and repair projection once. Two conflicting first observations have one accepted winner. Original expected-receipt replay remains idempotent; conflicting stale input refuses. Empty expected_receipt_id is a sentinel only for a receipt-less durable claim, not a general CAS bypass. Late conflicting observations append history without downgrading the settled projection. Neither recovery nor status reads redispatch effects.

## Refusal and failure behavior

PROJECTION_SETTLED, stale receipt/revision, wrong project, unknown action, revoked authority and malformed observation remain explicit refusals. observed=false cannot assert succeeded=true.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/action_types.py

```python
@dataclass(frozen=True, slots=True)
class ActionObservation:
    observed: bool
    succeeded: bool | None = None
    external_ref: str = ''
    detail: str = ''
    status: ObservationStatus = ObservationStatus.COMPLETE
```

### src/antigravity_k/engine/cognitive/action_types.py

```python
@dataclass(frozen=True, slots=True)
class ActionReceipt:
    receipt_id: str
    action_id: str
    action_key: str
    submission_id: str
    dispatch_attempt: int
    status: ReceiptStatus
    started_at: datetime
    finished_at: datetime | None = None
    external_ref: str | None = None
    effects_observed: bool | None = None
    reconciliation: str = ''
    detail: str = ''
    @property
    def settled(self) -> bool: ...
    def to_record(self, *, project_id: str, producer: Producer, created_at: datetime, references: tuple[Reference, ...]=()) -> Record: ...
```

### src/antigravity_k/engine/cognitive/action_types.py

```python
@dataclass(frozen=True, slots=True)
class ActionRun:
    intent: ActionIntent
    status: ActionExecutionStatus
    receipt: ActionReceipt | None = None
    refusal: ActionRefusal | None = None
    reason: str = ''
    reconciliation_required: bool = False
    cancellation_requested: bool = False
    cancellation_note: str = ''
    records: tuple[Record, ...] = ()
    @property
    def refused(self) -> bool: ...
    @property
    def effect_possible(self) -> bool: ...
```

### src/antigravity_k/engine/cognitive/action_types.py

```python
@dataclass(frozen=True, slots=True)
class ObservationSubmission:
    project_id: str
    action_key: str
    expected_receipt_id: str
    observation: ActionObservation
    observed_at: datetime | None = None
```

### src/antigravity_k/engine/cognitive/action_types.py

```python
@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    accepted: bool
    refusal: ActionRefusal | None = None
    reason: str = ''
    receipt_id: str | None = None
    observation_record_id: str | None = None
    projection_revision: int = 0
    records: tuple[Record, ...] = ()
    redispatched: bool = False
```

### src/antigravity_k/engine/cognitive/actions.py

```python
@dataclass(frozen=True, slots=True)
class ActionDispatcher:
    port: ToolDispatchPort | None = None
    record_sink: Callable[[Sequence[Record]], object] | None = None
    clock: Callable[[], datetime] | None = None
    journal: ActionJournal | None = None
    authority_resolver: Callable[[ActionIntent, datetime], AuthorityDecision] | None = None
    freshness_resolver: Callable[[ActionIntent, datetime], FreshnessBinding] | None = None
    _receipts: dict[str, ActionReceipt] = field(default_factory=dict, repr=False)
    _attempts: dict[str, int] = field(default_factory=dict, repr=False)
    _submissions: dict[str, str] = field(default_factory=dict, repr=False)
    _records: list[Record] = field(default_factory=list, repr=False)
    @property
    def records(self) -> tuple[Record, ...]: ...
    def receipt_for(self, action_key: str) -> ActionReceipt | None: ...
    def submission_target(self, submission_id: str) -> str | None: ...
    def pending_reconciliation(self) -> tuple[ActionReceipt, ...]: ...
    def plan(self, intent: ActionIntent, *, project_id: str, producer: Producer) -> tuple[Record, ActionRun]: ...
    def execute(self, intent: ActionIntent, *, project_id: str, producer: Producer, retry_authorized: bool=False, now: datetime | None=None) -> ActionRun: ...
    def reconcile(self, run: ActionRun, observation: ActionObservation, *, project_id: str, producer: Producer, now: datetime | None=None) -> ActionRun: ...
    def cancel(self, run: ActionRun, *, reason: str, now: datetime | None=None) -> ActionRun: ...
    def submit_observation(self, submission: ObservationSubmission, *, producer: Producer, load_record: Callable[[str], Record | None], now: datetime | None=None) -> ReconciliationResult: ...
    def pending_with_reasons(self, project_id: str) -> tuple: ...
    def pending_claims(self, project_id: str): ...
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "observed": true,
  "succeeded": true,
  "external_ref": "receipt-from-observer",
  "detail": "verified effect"
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_observation_atomicity.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_observation_atomicity.py :: test_conflicting_first_observations_have_one_winner`
- `tests/cognitive/test_observation_atomicity.py :: test_failed_observation_append_keeps_claim_pending`
- `tests/cognitive/test_observation_atomicity.py :: test_crash_after_canonical_append_retries_same_ids`
- `tests/cognitive/test_observation_atomicity.py :: test_receiptless_claim_is_recovered_without_dispatch`
- `tests/cognitive/test_observation_atomicity.py :: test_process_crash_after_append_recovers_original_request`
- `tests/cognitive/test_observation_atomicity.py :: test_independent_processes_cannot_publish_conflicting_first_observations`
- `tests/cognitive/test_observation_atomicity.py :: test_late_dispatch_receipt_cannot_replace_observation_projection`
- `tests/cognitive/test_observation_atomicity.py :: test_published_observation_updates_dispatcher_receipt`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in [contract snapshot](contract-source-manifest.json), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Old-wire digest compatibility at final source freeze

`models.to_wire` preserves absent additive fields using `model_fields_set`: Experience episode_reference/evidence_refs, BrainJudgment delta, and ExecutionReceipt detail are omitted only when absent in the original model input. Explicitly supplied new values serialize normally. This prevents new defaults from changing canonical digests of genuine old records and invalidating preissued Context handles. Verification: `tests/cognitive/test_additive_wire_compatibility.py` (10 regression scenarios including real old-wire store reopen/handle resolution); implementer broader 128-test run passed. Independent final model-wire re-review is tracked in finalization evidence.

## Concurrent journal initialization

Multiple processes may initialize the same SQLite action journal concurrently. Schema initialization/migration serializes the inspect-and-ALTER operation so two fresh/opening processes cannot both add the same column. The v5 full-suite duplicate-column failure is preserved as historical evidence; the corrected boundary is covered by `tests/cognitive/test_action_journal_schema.py` and the owner's 37-test targeted validation. Final integrated QA remains separate.
