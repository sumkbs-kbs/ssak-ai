# C08 v1 — Registered live trial ledger

> Publication note (2026-10-04): The raw artifacts marked "local-only archive" are retained in the original local QA workspace and are not included in this public repository. Historical results and hashes describe their recorded revisions. This published summary does not supply the raw evidence or certify today's source.


Producer → consumer: **R17 → R18/R19**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **registered live execution and final ledger validation ongoing; scripted contract is not live efficacy**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

Before any provider call, validate corpus/splits/task IDs, order policy, mechanisms, budgets and provider attestation, then freeze the registration. Both arms use the same code/model/hardware/task distribution; only registered learned state differs. ModelTask exposes selected evidence and policy version, not evaluator expected append bytes. Each repetition owns an isolated trial effect target; success scores the registered actual output semantics rather than newline artifacts or residue from earlier repetitions.

Every trial ID has a start and terminal success/failure/timeout/budget entry. Partial ledgers survive incomplete runs. aggregate_from_ledger independently reconstructs arm metrics; analysis unit is task/family, not repeated trial count. Both-arm safety is a gate; unfavorable effects and failed validation are retained. TRAIN and validation may influence Mature only through registered policy/experience changes; FINAL never tunes thresholds. Fixture/scripted artifacts remain labeled separately from live provider output. A model-list probe is not live smoke, smoke is not a registered final experiment, and a complete negative/no-effect experiment is not an efficacy PASS. Live execution currently underway must be reported by its terminal artifact before upgrading status.

## Refusal and failure behavior

GrowthBenchmarkError/invalid input before provider call; LiveTrialTimeout, LiveTrialBudgetExhausted, FixtureLiveMixError; NOT_RUN/NOT_COMPLETE are not completion or efficacy PASS.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass(frozen=True, slots=True)
class ProviderAttestation:
    provider_id: str
    model_id: str
    model_snapshot: str
    decoding: str
    hardware: str
    snapshot_pinned: bool
    reproducibility_limits: tuple[str, ...] = ()
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@runtime_checkable
class LiveTrialPort(Protocol):
    attestation: ProviderAttestation
    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass(frozen=True, slots=True)
class PilotPreRegistration:
    corpus_digest: str
    split: str
    task_ids: tuple[str, ...]
    task_families: Mapping[str, str]
    content_digests: Mapping[str, str]
    seed: int
    arm_order_policy: str
    primary_metric: str
    safety_metric: str
    mechanism_flags: Mapping[str, bool]
    model_digest: str
    code_fingerprint: str
    hardware: str
    budget_calls: int | None
    budget_tokens: int | None
    trials_per_task: int
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass(frozen=True, slots=True)
class TrialLedgerEntry:
    run_id: str
    trial_uid: str
    task_id: str
    arm: str
    repetition: int
    order: str
    status: str
    started_at: str | None
    finished_at: str | None
    outcome: Mapping[str, object] | None
    error_category: str = ''
    policy_version: str | None = None
    mechanism_flags: Mapping[str, bool] = field(default_factory=dict)
    requested_policy_version: str | None = None
    policy_version_reported: bool = False
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass
class RawTrialLedger:
    entries: list[TrialLedgerEntry] = field(default_factory=list)
    def append(self, entry: TrialLedgerEntry) -> None: ...
    def as_mapping(self) -> Mapping[str, object]: ...
    def completed_outcomes(self) -> list[tuple[TrialLedgerEntry, LiveTrialOutcome]]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
def aggregate_from_ledger(ledger_entries: Sequence[TrialLedgerEntry] | Sequence[Mapping[str, object]], *, spec: BenchmarkSpec, plan: LivePilotPlan, tasks: Sequence[GrowthTask], attestation: ProviderAttestation) -> tuple[Mapping[str, LiveArmSummary], LivePilotVerdict | None]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass(frozen=True, slots=True)
class RegisteredExperimentManifest:
    pre_registration: PilotPreRegistration
    independent_task_count: int
    planned_trial_slots: int
    analysis_unit: str
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
def run_registered_live_experiment(harness: LivePilotHarness, port: LiveTrialPort | None, *, attestation_for_freeze: ProviderAttestation | None=None) -> RegisteredExperimentResult: ...
```

### src/antigravity_k/engine/cognitive/live_trial_adapter.py

```python
@dataclass
class LiveTrialAdapter:
    workspace: Path
    model: ModelPort
    executor_factory: Callable[[Path], ToolExecutorPort]
    tasks: Sequence[GrowthTask] = field(default_factory=default_corpus_tasks)
    mechanisms: MechanismSet = field(default_factory=MechanismSet)
    policy_gate: PolicyGateState = field(default_factory=PolicyGateState)
    producer: Producer = field(default_factory=lambda: Producer(kind=ProducerKind.BODY, actor_id='body:live-trial'))
    project_id: str = field(default_factory=lambda: canonical_id('project', 'growth-demo'))
    attestation: ProviderAttestation = field(init=False)
    learning: LiveLearning = field(init=False)
    def arm_root(self, arm: ArmRole | str) -> Path: ...
    def root_digest(self, arm: ArmRole | str) -> str: ...
    def context_limits(self, request: LiveTrialRequest) -> Mapping[str, int]: ...
    def run_train_validation(self, *, force_validation_fail: bool | None=None) -> PolicyGateState: ...
    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome: ...
```

### src/antigravity_k/engine/cognitive/live_trial_types.py

```python
@dataclass(frozen=True, slots=True)
class ModelTask:
    task_id: str
    evidence: tuple[str, ...]
    policy_version: str | None
    context_json: str = ''
```

### src/antigravity_k/engine/cognitive/live_trial_types.py

```python
@dataclass(frozen=True, slots=True)
class ModelChoice:
    append_content: str
    target_name: str | None = None
    expand_missing: bool = False
    detail: str = ''
    tokens: int = 0
    ground_refs: tuple[str, ...] = ()
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "trial_uid": "run:task:fresh:0",
  "status": "timeout",
  "error_category": "provider_timeout"
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_live_pilot.py tests/cognitive/test_live_trial_adapter.py tests/cognitive/test_local_live_model.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_live_pilot.py :: test_r17_a1_invalid_inputs_refuse_before_provider_call`
- `tests/cognitive/test_live_pilot.py :: test_r17_a2_fresh_or_mature_safety_fails_verdict`
- `tests/cognitive/test_live_pilot.py :: test_r17_a3_timeout_keeps_partial_ledger_and_not_complete`
- `tests/cognitive/test_live_pilot.py :: test_r17_a4_independent_aggregator_matches_harness`
- `tests/cognitive/test_live_pilot.py :: test_r19_a1_manifest_frozen_after_final_results`
- `tests/cognitive/test_live_pilot.py :: test_r19_a2_every_trial_id_has_start_and_terminal`
- `tests/cognitive/test_live_pilot.py :: test_r19_a3_arms_share_settings_state_differs`
- `tests/cognitive/test_live_pilot.py :: test_r19_a4_recompute_and_keep_unfavorable`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a1_wrong_model_is_real_failure_not_canned`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a2_failed_validation_not_applied_to_final_mature`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a3_fresh_and_mature_roots_independent`
- `tests/cognitive/test_live_trial_adapter.py :: test_r18_a4_workspace_jail_and_timeout_partial_ledger`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in contract snapshot (local-only archive: `contract-source-manifest.json`, unpublished), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Requested and effective policy ledger (retained in final freeze)

TrialLedgerEntry.requested_policy_version records the requested arm policy. Its policy_version records the actual effective policy only when the adapter reports it; policy_version_reported distinguishes an explicit effective None from an older adapter that did not report a value. Never substitute requested Mature policy for effective None after validation/policy ablation disables it. Outcome carries effective_policy_version and policy_version_reported. Mechanism flags reach actual ArmInputs; disabled policy use and disabled experience use remain distinct observations. Cost/brain-call/token counts come from actual attempts, including refusals, not a hardcoded scripted estimate. `tests/cognitive/test_live_policy_ledger.py` verifies these distinctions.

### src/antigravity_k/engine/cognitive/live_pilot.py

```python
@dataclass(frozen=True, slots=True)
class LiveTrialOutcome:
    success: bool
    retries: int
    tool_calls: int
    brain_calls: int
    tokens: int
    latency_ms: float
    duplicate_dispatch: bool = False
    safety_violation: str = ''
    detail: str = ''
    error_category: str = ''
    effective_policy_version: str | None = None
    policy_version_reported: bool = False
    def as_mapping(self) -> Mapping[str, object]: ...
```

## V7 registration/provenance boundary

The corrected trial implementation passes actual selected Context/Experience payload content to ModelTask, persists actual selector reasons and canonical IDs, and does not fabricate a COMPLETE advisory to prove reuse. Execution assessment follows observed evidence: a failed/no-read path cannot report execution MATCH or claim file.read_text; actual attempts count toward calls/tokens. Registration identity and the whole first-party source-package inventory bind the run. Earlier v5/v6 registrations are historical and cannot be promoted to final acceptance after consumed source changes. The v7 run must complete with unchanged registered source inventory and raw-ledger independent recomputation before a live completion verdict. The bounded synthetic append corpus/context-depth hypothesis does not demonstrate general autonomous semantic discovery.
