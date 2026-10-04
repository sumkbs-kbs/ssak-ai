# C03 v1 — Authoritative current heads and admission

Producer → consumer: **R08 → R09/R13/R15**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **trusted canonical-head composition and governed expansion independently verified; bound to amended frozen source manifest**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

FreshnessBinding owns decision_revision, action_digest, state_revision, authority_revision and policy_version. Trusted composition anchors current records independently of ActionIntent. CanonicalCurrentHeads follows committed supersedes lineage within one project: Decision readiness supplies the decision/digest, Event supplies state revision, AuthorityProfile supplies grants/revision, and optional Policy supplies version. There is no ProjectState entity to invent.

Missing, ambiguous, wrong-type, nonadvancing or regressing heads must refuse execution. Current grants and their ancestor attenuation are evaluated at execution time. A new policy cannot silently mutate an existing reasoning pin. The dispatcher checks admission and repeats current binding immediately before the tool call. Shared journal claim prevents duplicate local execution. Canonical publication and an external tool are not one cross-resource atomic transaction: the documented ordering is a final read/check before dispatch, not a claim to stop a revoke that occurs after effect starts. No client body field serves as authoritative current state. Human-ceiling references that cannot be resolved refuse rather than grant unlimited capability.

## Refusal and failure behavior

STALE_READINESS, NOT_AUTHORIZED and duplicate-action refusal. Missing/current-head lookup exceptions must fail closed; exact serialized route response is covered by active API tests.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/readiness.py

```python
@dataclass(frozen=True, slots=True)
class FreshnessBinding:
    decision_revision: int
    action_digest: str
    state_revision: int
    authority_revision: int | None = None
    policy_version: str | None = None
    def changed_fields(self, current: FreshnessBinding) -> tuple[str, ...]: ...
    def is_fresh(self, current: FreshnessBinding) -> bool: ...
    def digest(self) -> str: ...
    def as_mapping(self) -> Mapping[str, object]: ...
```

### src/antigravity_k/engine/cognitive/action_admission.py

```python
def preconditions(self: ActionContext, intent: ActionIntent, *, retry_authorized: bool, now: datetime, subject: str) -> ActionRun | None: ...
```

### src/antigravity_k/engine/cognitive_active_heads.py

```python
@dataclass(frozen=True, slots=True)
class CanonicalHeadAnchors:
    decision_id: str
    state_event_id: str
    authority_id: str
    policy_id: str | None = None
```

### src/antigravity_k/engine/cognitive_active_heads.py

```python
@dataclass(frozen=True, slots=True)
class CanonicalCurrentHeads:
    store: CanonicalStore
    project_id: str
    principal: str
    anchors: CanonicalHeadAnchors
    def authority(self, intent: ActionIntent, now: datetime) -> AuthorityDecision: ...
    def freshness(self, intent: ActionIntent, now: datetime) -> FreshnessBinding: ...
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "decision_revision": 2,
  "action_digest": "sha256:reviewed-action",
  "state_revision": 4,
  "authority_revision": 3,
  "policy_version": "v1"
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_composition.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_final_authority_boundaries.py -q -p no:cacheprovider
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
