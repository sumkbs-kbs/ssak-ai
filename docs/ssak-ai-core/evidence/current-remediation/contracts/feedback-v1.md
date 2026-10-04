# C02 v1 — Request feedback and targeted rethink

Producer → consumer: **R07 → R14/R15**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **supported trusted canonical request expansion, typed receipt feedback and missing-receipt refusal verified; bound to amended frozen source manifest**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

The Primary produces a structured judgment and referenced CognitiveRequest records. The bridge loads each request in the authenticated project and maps typed requests into runtime envelopes. Body owns governance, execution and structural counters; it does not manufacture semantic material change. Explicit Primary MaterialCognitiveDelta governs continuation. A failed or unresolved request cannot become a successful material judgment.

Runtime delivers each RequestFeedback (disposition, execution flag, detail, receipt and observed-effect status) to RethinkPort as well as compatibility feedback IDs. The structured bridge sends these objects in context_delta together with fully resolved canonical execution receipts to the next Primary request and resolves the previous judgment's context. Successful evidence and denials both reach rethink. Repeated normalized signature with unchanged evidence revision is stopped; changed evidence can justify another request only inside total request/round/provider budgets. COMMIT uses the latest integrated plan. A legacy port receiving only IDs does not establish typed-feedback integration; test the actual bridge. Runtime feedback and governance.RequestFeedback are different types and must not be silently interchanged.

## Refusal and failure behavior

RETHINK_CONTEXT_UNRESOLVED, REQUEST_UNRESOLVED, typed BrainFailure, no-delta stop and budget exhaustion remain explicit non-success states.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/runtime.py

```python
@dataclass(frozen=True, slots=True)
class EpisodeDelta:
    judgment: bool = False
    ground: bool = False
    alternative: bool = False
    unknown: bool = False
    risk: bool = False
    action: bool = False
    description: str = ''
    @property
    def material(self) -> bool: ...
```

### src/antigravity_k/engine/cognitive/runtime.py

```python
@dataclass(frozen=True, slots=True)
class ThinkOutcome:
    judgment_ref: str
    requests: tuple[CognitiveRequestEnvelope, ...] = ()
    delta: EpisodeDelta | None = None
    detail: str = ''
    failed: bool = False
    plan: EpisodePlan | None = None
```

### src/antigravity_k/engine/cognitive/runtime.py

```python
@runtime_checkable
class RethinkPort(Protocol):
    def rethink(self, *, previous_judgment_ref: str, feedback_refs: Sequence[str], affected_grounds: Sequence[str], round_index: int, feedback: Sequence[RequestFeedback]=()) -> ThinkOutcome: ...
```

### src/antigravity_k/engine/cognitive/runtime.py

```python
@dataclass(frozen=True, slots=True)
class CognitiveRequestEnvelope:
    request_id: str
    request_type: CognitiveRequestType
    purpose: str
    target: str
    expected_decision_impact: str
    dimension: AuthorityDimension = AuthorityDimension.TOOL_READ
    resource_scope: str = ''
    evidence_revision: str = ''
    action: ActionIntent | None = None
    authority: AuthorityProfile | None = None
    unknowns: tuple[UnknownAssessment, ...] = ()
    advisory_notes: tuple[str, ...] = ()
    risk: RiskProfile = field(default_factory=RiskProfile)
    def signature(self) -> str: ...
    def to_requested_action(self) -> RequestedAction: ...
```

### src/antigravity_k/engine/cognitive/runtime.py

```python
@dataclass(frozen=True, slots=True)
class RequestFeedback:
    request_id: str
    request_signature: str
    disposition: str
    executed: bool
    detail: str = ''
    receipt_ref: str | None = None
    effects_observed: bool | None = None
```

### src/antigravity_k/engine/cognitive/runtime.py

```python
class CognitiveRuntime:
    def __init__(self, *, think: ThinkPort, rethink: RethinkPort | None=None, actions: ActionDispatcher | None=None, governance: GovernanceGate | None=None, readiness: ReadinessGate | None=None, experience: ExperienceLedger | None=None, budget: EpisodeBudget | None=None, project_id: str='', producer: Producer | None=None, clock: Callable[[], datetime] | None=None, record_sink: Callable[[Sequence[Record]], object] | None=None) -> None: ...
    def run(self, request: EpisodeRequest) -> Episode: ...
    def form_experience_core(self, selection: ExperienceSelection, *, trigger: str, experience_id: str | None=None, context_ref: str | None=None, judgment_ref: str | None=None, decision_ref: str | None=None, governance_ref: str | None=None, outcome_ref: str | None=None, action_ref: str | None=None, observation_refs: Sequence[str]=(), evidence_refs: Sequence[str]=(), remaining_unknowns: Sequence[str]=(), future_attention: Sequence[str]=(), missing_references: Sequence[str]=()) -> ExperienceCore: ...
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
  "request_id": "request-1",
  "request_signature": "canonical-signature",
  "disposition": "DENY",
  "executed": false,
  "detail": "authority denied",
  "receipt_ref": null,
  "effects_observed": false
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_episode.py tests/cognitive/test_brain.py tests/cognitive/test_surface.py -q -p no:cacheprovider
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
- `tests/cognitive/test_brain.py :: test_r14_a1_provider_payload_has_goal_state_evidence_text`
- `tests/cognitive/test_brain.py :: test_r14_a2_low_context_window_does_not_hide_required_omissions`
- `tests/cognitive/test_brain.py :: test_r14_a3_malformed_repair_stays_within_budget`
- `tests/cognitive/test_brain.py :: test_r14_a4_two_providers_read_same_fixture_ids`
- `tests/cognitive/test_brain.py :: test_r14_a5_incomplete_context_provider_call_zero`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in [contract snapshot](contract-source-manifest.json), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.

## Finalization regression additions

The current fix-specific verification also includes:

- `tests/cognitive/test_brain_bridge_regressions.py`
  Scenarios: `test_all_selected_layers_reach_provider_without_truncation`, `test_long_required_content_exceeds_window_instead_of_being_shortened`, `test_primary_delta_is_transmitted_and_judgment_persisted`, `test_rethink_transmits_actual_feedback_to_provider`, `test_canonical_request_is_preserved_in_runtime_outcome`, `test_invalid_material_delta_repairs_once_without_crashing`, `test_secondary_request_uses_secondary_authority_dimension`, `test_judgment_digest_must_match_the_context_actually_sent`.
- `tests/cognitive/test_brain_receipt_bridge.py`
  Scenarios: `test_rethink_loads_receipt_and_persists_new_judgment`, `test_rethink_refuses_unloadable_receipt_before_provider`.

## Supported executable request consumer

The trusted `request_resolver` maps a canonical CognitiveRequest to a bound ActionIntent with its own canonical admission anchors. Arbitrary model text never directly manufactures an ActionIntent, grant or final plan. Unsupported/unbound request forms return REQUEST_UNBOUND. The actual authenticated expansion test runs ReadFileTool, commits ExecutionReceiptPayload.detail and supplies its body to Primary rethink; the no-receipt executed feedback case returns EXECUTED_RECEIPT_MISSING before a further provider call. See C09 and `tests/cognitive/test_active_expansion.py`.

## Old-wire digest compatibility at final source freeze

`models.to_wire` preserves absent additive fields using `model_fields_set`: Experience episode_reference/evidence_refs, BrainJudgment delta, and ExecutionReceipt detail are omitted only when absent in the original model input. Explicitly supplied new values serialize normally. This prevents new defaults from changing canonical digests of genuine old records and invalidating preissued Context handles. Verification: `tests/cognitive/test_additive_wire_compatibility.py` (10 regression scenarios including real old-wire store reopen/handle resolution); implementer broader 128-test run passed. Independent final model-wire re-review is tracked in finalization evidence.

### src/antigravity_k/engine/cognitive_active_requests.py

```python
@dataclass(frozen=True, slots=True)
class TrustedCognitiveRequestBinding:
    action: ActionIntent
    anchors: CanonicalHeadAnchors
```

## Material final-plan binding

An initial THINK or RETHINK that reports a material risk/action change must provide an explicit prepared EpisodePlan before a final action can execute. Without it the runtime defers. Ground-only updates may retain the already prepared plan under the explicit tested policy. Governed expansion/read evidence can still be recorded without authorizing a stale final write. Tests: `tests/cognitive/test_episode_plan_binding.py` and the authenticated expansion regression.
