# C01 v1 — Context and provider budget

> Publication note (2026-10-04): The raw artifacts marked "local-only archive" are retained in the original local QA workspace and are not included in this public repository. Historical results and hashes describe their recorded revisions. This published summary does not supply the raw evidence or certify today's source.


Producer → consumer: **R05/R06 → R07/R14/R15**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **selected-content bridge independently verified (G1); full current integration and final source binding tracked in goal review**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

The authoritative inputs are committed project records loaded by ContextBuilder, a caller-supplied goal and snapshot revision, authenticated ContextPrincipal, and a ContextBudget. The result retains canonical goal_id, state_revision and optional policy_version. Required goal, constraints and selected records must be present in the provider wire, not only reachable via handles. Missing, wrong-project or over-budget required content fails closed; handles and exclusions are bounded metadata with explicit omitted counts.

The revised renderer emits full selected record payloads across constraints/state/history/evidence. `snippet_chars` remains call-compatible but does not authorize truncation. Its UTF-8 accounting is conservative and includes the rendered wire; StructuredBrainClient must separately account for actual request/schema/repair overhead. A renderer-only result does not prove the full provider transport budget. INCOMPLETE/overflow must produce provider call count zero. Context identity and historical policy pins are preserved; new current state requires a rebuild rather than altering an old package.

## Refusal and failure behavior

ContextBuildError; adapter detail CONTEXT_UNRESOLVED, CONTEXT_PROJECT_MISMATCH, CONTEXT_WRONG_TYPE, CONTEXT_INCOMPLETE, CONTEXT_OVERFLOW. These are refusal diagnostics, never successful semantic judgments.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/context.py

```python
@final
class ContextBuilder:
    def __init__(self, store: CanonicalStore, *, clock: Callable[[], datetime] | None=None, handle_ttl: timedelta=DEFAULT_HANDLE_TTL) -> None: ...
    def projection_state(self) -> ProjectionState: ...
    def refresh_projection(self, previous: ProjectionState) -> tuple[ProjectionState, bool]: ...
    def build(self, *, goal_id: str, state_revision: int, principal: ContextPrincipal, budget: ContextBudget, policy_version: str | None=None, brain_capabilities: Sequence[str]=(), l1_limit: int=DEFAULT_L1_LIMIT, l2_limit: int=DEFAULT_L2_LIMIT, l3_limit: int=DEFAULT_L3_LIMIT, requested_disclosure: DisclosureLevel=DisclosureLevel.L1_SUMMARY) -> ContextBuildResult: ...
    def resolve_handle(self, handle: ContextHandleRef, principal: ContextPrincipal, *, max_bytes: int=8000) -> HandleResolution: ...
```

### src/antigravity_k/engine/cognitive/models.py

```python
class ContextBudget(BaseModel):
    token_budget: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    l0_reserved_tokens: int = Field(ge=0)
```

### src/antigravity_k/engine/cognitive/models.py

```python
class ContextPackagePayload(EntityPayloadModel):
    entity_type: Literal['ContextPackage'] = 'ContextPackage'
    goal_id: str = Field(pattern=ID_PATTERN)
    state_revision: int = Field(ge=1)
    policy_version: str | None = None
    l0_constraints: tuple[ContextItem, ...] = ()
    l1_state: tuple[ContextItem, ...] = ()
    l2_history: tuple[ContextItem, ...] = ()
    l3_evidence: tuple[ContextItem, ...] = ()
    handles: tuple[ContextHandleRef, ...] = ()
    budget: ContextBudget
    exclusions: tuple[ContextExclusion, ...] = ()
    integrity: IntegrityStatus = IntegrityStatus.COMPLETE
    missing_ids: tuple[str, ...] = ()
    projection: ProjectionState | None = None
    omitted_handle_count: int = Field(default=0, ge=0)
    omitted_exclusion_count: int = Field(default=0, ge=0)
```

### src/antigravity_k/engine/cognitive/brain_context_render.py

```python
@dataclass(frozen=True, slots=True)
class BrainContextRender:
    wire: Mapping[str, object]
    omitted_required: tuple[str, ...] = ()
    truncated: bool = False
    @property
    def ready_for_provider(self) -> bool: ...
```

### src/antigravity_k/engine/cognitive/brain_context_render.py

```python
def render_context_for_brain(package: ContextPackagePayload, *, project_id: str, context_digest: str, load_record: Callable[[str], Record | None], context_limit: int, snippet_chars: int=400) -> BrainContextRender: ...
```

### src/antigravity_k/engine/cognitive_surface_brain.py

```python
@final
class StructuredSurfaceBrainPort:
    def __init__(self, adapter: BrainAdapter, *, project_id: str, load_context_package: Callable[[str], Record | None], load_record: Callable[[str], Record | None], legacy_observation: Callable[[str], str] | None=None, record_sink: Callable[[Sequence[Record]], CommitReceipt | None] | None=None, request_resolver: Callable[[Record], CognitiveRequestEnvelope | None] | None=None) -> None: ...
    @property
    def provider_calls(self) -> int: ...
    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome: ...
    def rethink(self, *, previous_judgment_ref: str, feedback_refs: Sequence[str], affected_grounds: Sequence[str], round_index: int, feedback: Sequence[RequestFeedback]=()) -> ThinkOutcome: ...
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "entity_type": "ContextPackage",
  "integrity": "INCOMPLETE",
  "missing_ids": [
    "required-record-id"
  ],
  "omitted_handle_count": 3
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_context.py tests/cognitive/test_brain.py tests/cognitive/test_surface.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_context.py :: test_r05_a1_l0_only_budget_without_goal_is_incomplete`
- `tests/cognitive/test_context.py :: test_r05_a2_l1_limit_zero_still_preserves_required_goal`
- `tests/cognitive/test_context.py :: test_r05_a3_stale_revision_and_missing_evidence_are_incomplete`
- `tests/cognitive/test_context.py :: test_r05_a4_normal_minimum_context_is_complete`
- `tests/cognitive/test_context.py :: test_r06_a1_unrelated_evidence_mass_does_not_change_useful_injection`
- `tests/cognitive/test_context.py :: test_r06_a2_superseded_judgment_is_not_current_state`
- `tests/cognitive/test_context.py :: test_r06_a3_serialized_package_stays_within_budget`
- `tests/cognitive/test_context.py :: test_r06_a4_related_evidence_reachable_via_bounded_expansion`
- `tests/cognitive/test_brain.py :: test_r14_a1_provider_payload_has_goal_state_evidence_text`
- `tests/cognitive/test_brain.py :: test_r14_a2_low_context_window_does_not_hide_required_omissions`
- `tests/cognitive/test_brain.py :: test_r14_a3_malformed_repair_stays_within_budget`
- `tests/cognitive/test_brain.py :: test_r14_a4_two_providers_read_same_fixture_ids`
- `tests/cognitive/test_brain.py :: test_r14_a5_incomplete_context_provider_call_zero`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in contract snapshot (local-only archive: `contract-source-manifest.json`, unpublished), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Finalization regression additions

The current fix-specific verification also includes:

- `tests/cognitive/test_brain_bridge_regressions.py`
  Scenarios: `test_all_selected_layers_reach_provider_without_truncation`, `test_long_required_content_exceeds_window_instead_of_being_shortened`, `test_primary_delta_is_transmitted_and_judgment_persisted`, `test_rethink_transmits_actual_feedback_to_provider`, `test_canonical_request_is_preserved_in_runtime_outcome`, `test_invalid_material_delta_repairs_once_without_crashing`, `test_secondary_request_uses_secondary_authority_dimension`, `test_judgment_digest_must_match_the_context_actually_sent`.
- `tests/cognitive/test_brain_receipt_bridge.py`
  Scenarios: `test_rethink_loads_receipt_and_persists_new_judgment`, `test_rethink_refuses_unloadable_receipt_before_provider`.

## Old-wire digest compatibility at final source freeze

`models.to_wire` preserves absent additive fields using `model_fields_set`: Experience episode_reference/evidence_refs, BrainJudgment delta, and ExecutionReceipt detail are omitted only when absent in the original model input. Explicitly supplied new values serialize normally. This prevents new defaults from changing canonical digests of genuine old records and invalidating preissued Context handles. Verification: `tests/cognitive/test_additive_wire_compatibility.py` (10 regression scenarios including real old-wire store reopen/handle resolution); implementer broader 128-test run passed. Independent final model-wire re-review is tracked in finalization evidence.
