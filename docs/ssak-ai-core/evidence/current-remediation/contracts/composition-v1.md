# C09 v1 — Trusted ACTIVE composition and durable status

Producer → consumer: **R15/R16 → R22**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **trusted composition, HTTP refusals and structured canonical expansion independently verified; bound to amended frozen source manifest**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

Trusted application ownership injects ProjectActiveConfiguration into app.state before the real server lifespan calls bootstrap_cognitive_active. No HTTP body may supply authority, an executor or freshness callback. Absent configuration leaves ACTIVE unavailable (503); OFF/SHADOW remains the default. Installing the seam is distinct from supplying real Human grants or globally enabling ACTIVE.

Configuration binds project/store/root, authenticated owner, execution principal, existing ToolExecutor, Think port, canonical head anchors and prepared requests. Executor root must match the trusted root. HTTP submits prepared request ID, reviewed action digest and reason, then verifies token ownership. One selected executor owns each effect; no simultaneous legacy/canonical dispatch. Shared journal/history survives adapter recreation and restart. Status distinguishes configured mode, actual activation, actual effect and durable episode history. Static import reach does not mean supported runtime entry. Read-only status must not call Brain/learn/act.

Dedicated tests call the production bootstrap on isolated FastAPI instances with real tools and canonical stores. They do not start unrelated full-server subsystems or certify deployment. Rollback disables the new executor/keeps OFF, restores the last valid versioned policy, and preserves receipts/history; an external side effect is not reversed merely by turning the switch off.

## Refusal and failure behavior

Missing trusted service: HTTP503; unauthenticated:401; mismatched owner/project/digest and missing/ambiguous heads refuse; durable duplicate returns no new dispatch.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive_active_heads.py

```python
@dataclass(frozen=True, slots=True)
class CanonicalHeadAnchors:
    decision_id: str
    state_event_id: str
    authority_id: str
    policy_id: str | None = None
```

### src/antigravity_k/engine/cognitive_active_composition.py

```python
@dataclass(frozen=True, slots=True)
class ProjectActiveConfiguration:
    settings: CognitiveCoreSettings
    project_root: Path
    runtime_root: Path
    owner_subject: str
    principal: str
    store: CanonicalStore
    executor: ToolExecutor
    anchors: CanonicalHeadAnchors
    prepared: Mapping[str, 'PreparedCognitiveAction']
    think: ThinkLike | None = None
    brain_adapter: BrainAdapter | None = None
    cognitive_requests: Mapping[str, TrustedCognitiveRequestBinding] = field(default_factory=dict)
```

### src/antigravity_k/engine/cognitive_active_composition.py

```python
def install_cognitive_active(app: 'FastAPI', configuration: ProjectActiveConfiguration) -> None: ...
```

### src/antigravity_k/engine/cognitive_surface.py

```python
class CognitiveSurfaceAdapter:
    def __init__(self, settings: CognitiveCoreSettings | None=None, *, think: ThinkLike | None=None, rethink: RethinkPort | None=None, governance: GovernanceGate | None=None, dispatch_port: ToolDispatchPort | None=None, journal: ActionJournal | None=None, record_sink: Callable[[Sequence[Record]], CommitReceipt | None] | None=None, authority_resolver: Callable[[ActionIntent, datetime], AuthorityDecision] | None=None, freshness_resolver: Callable[[ActionIntent, datetime], FreshnessBinding] | None=None, activation_authorizer: Callable[[str, str, datetime], bool] | None=None, producer: Producer | None=None, clock: Callable[[], datetime] | None=None, history_store: DurableSurfaceHistoryStore | None=None) -> None: ...
    @property
    def source(self) -> SurfaceSource: ...
    def status(self) -> SurfaceStatus: ...
    def activate(self, *, approver: str, reason: str, now: datetime | None=None) -> ActivationRecord: ...
    def run_shadow(self, request: SurfaceEpisodeRequest) -> ShadowRun: ...
    def run_active(self, request: SurfaceEpisodeRequest) -> ShadowRun: ...
    def restore_experience_records(self, records: Sequence[Record], *, episode_reference: str='') -> int: ...
    @property
    def experience(self) -> ExperienceLedger: ...
    def list_pending_actions(self): ...
    def submit_observation(self, *, action_key: str, expected_receipt_id: str, observed: bool, succeeded: bool | None, detail: str='', external_ref: str='', load_record, now=None) -> ReconciliationResult: ...
```

### src/antigravity_k/engine/cognitive_surface_measurement.py

```python
class DurableSurfaceHistoryStore:
    def __init__(self, path: str | Path) -> None: ...
    def record_run(self, *, project_id: str, episode_id: str, termination: str | None, dispatched_actions: int, refused_actions: int, observed_at: str | None=None) -> DurableSurfaceHistory: ...
    def latest(self, project_id: str) -> DurableSurfaceHistory | None: ...
    def totals(self, project_id: str) -> tuple[int, int]: ...
```

### src/antigravity_k/api/dependencies.py

```python
def bootstrap_cognitive_active(app: 'FastAPI') -> None: ...
```

### src/antigravity_k/api/routes/cognitive_active_api.py

```python
@dataclass(frozen=True)
class PreparedCognitiveAction:
    owner_subject: str
    project_id: str
    request: SurfaceEpisodeRequest
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "configured_mode": "OFF",
  "actual_active": false,
  "reaches_core": false
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_active_composition.py tests/cognitive/test_active_api.py tests/cognitive/test_r15_composition.py tests/cognitive/test_surface_lifecycle.py tests/cognitive/test_feature_off_regression.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_active_composition.py :: test_boot_without_trusted_configuration_leaves_active_uninstalled`
- `tests/cognitive/test_active_composition.py :: test_trusted_boot_executes_once_and_restart_keeps_durable_claim`
- `tests/cognitive/test_active_composition.py :: test_actual_canonical_revision_change_blocks_effect`
- `tests/cognitive/test_active_composition.py :: test_missing_canonical_head_fails_closed`
- `tests/cognitive/test_active_composition.py :: test_revoked_canonical_grant_blocks_effect`
- `tests/cognitive/test_active_composition.py :: test_trusted_root_mismatch_rejected_at_boot`
- `tests/cognitive/test_active_composition.py :: test_ambiguous_head_rejected_without_effect`
- `tests/cognitive/test_active_composition.py :: test_canonical_policy_head_version_is_loaded_independently`
- `tests/cognitive/test_active_composition.py :: test_canonical_authorized_digest_mismatch_blocks_unchanged_revisions`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in [contract snapshot](contract-source-manifest.json), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Frozen trusted expansion composition

`CanonicalCurrentHeads` and `CanonicalHeadAnchors` now live in `cognitive_active_heads.py` with stable composition re-exports. `TrustedCognitiveRequestBinding(action, anchors)` lives in `cognitive_active_requests.py`; `ProjectActiveConfiguration.cognitive_requests` maps canonical CognitiveRequest IDs to trusted prepared actions and per-expansion head anchors. The preferred `brain_adapter` constructs one request-local StructuredSurfaceBrainPort for THINK and RETHINK. A custom `think` port remains explicitly trusted configuration. The two alternatives are mutually exclusive.

The binder matches canonical args_digest to actual action arguments and preserves request identity/type/purpose/target/impact. Unbound or mismatched requests refuse. Expansions receive their own Decision/state/authority/policy heads; they never borrow final-action authority. Actual ReadFileTool execution stores canonical receipt.detail and that persisted body reaches Primary rethink, including after canonical reopen. Truncated executor output is explicitly labeled. This supported path is tested by `tests/cognitive/test_active_expansion.py`, including missing binding and mismatched digest refusals.

### src/antigravity_k/engine/cognitive_active_requests.py

```python
@dataclass(frozen=True, slots=True)
class TrustedCognitiveRequestBinding:
    action: ActionIntent
    anchors: CanonicalHeadAnchors
```
