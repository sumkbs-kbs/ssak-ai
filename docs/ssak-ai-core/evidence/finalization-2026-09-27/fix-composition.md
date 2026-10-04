# Trusted ACTIVE composition completion

## Changed

- Added `engine/cognitive_active_composition.py`: `ProjectActiveConfiguration`, `CanonicalHeadAnchors`, `CanonicalCurrentHeads`, `install_cognitive_active`.
- Added `api.dependencies.bootstrap_cognitive_active(app)` and invoked it from the actual API server lifespan before serving. An application owner injects `app.state.cognitive_active_configuration` before boot. No HTTP payload can configure this object. Missing configuration preserves ACTIVE 503; non-ACTIVE settings do not install.
- A single existing `ToolExecutor` is reused by all request-local adapters. Its resolved root must match the trusted project root. Prepared requests must belong to the configured project and authenticated owner. Shared SQLite claims and surface history survive adapter recreation/restart.
- `CanonicalCurrentHeads` reads committed canonical records per project on each authority/freshness check, follows explicit supersedes lineage, and rejects missing, ambiguous, wrong-type, nonadvancing or regressing heads. It never copies request freshness back as authoritative truth.
- Empty expected receipt sentinel is accepted by HTTP schema for receipt-less crash recovery; recovery layer decides its validity. Identical observation retry test now expects idempotent success, per recovery worker contract.

## Producer → consumer contracts

- Trusted application owner produces `ProjectActiveConfiguration`; `bootstrap_cognitive_active` consumes it at real server lifespan boot, and installs `CognitiveActiveService` for existing authenticated ACTIVE endpoints.
- Trusted preparation produces `PreparedCognitiveAction(owner_subject, project_id, request)` plus lineage anchor IDs. HTTP accepts only request ID, reviewed action digest and reason; token verification establishes identity again before execution.
- Canonical `Decision.payload.readiness` produces authorized action digest and decision revision. Canonical `Event.payload.state_revision` produces state revision (there is no ProjectState entity). Canonical `AuthorityProfile.payload.revision` produces authority revision; current grants are evaluated for the trusted execution principal. Optional canonical `Policy.payload.version` produces policy version. `ActionDispatcher` consumes their `FreshnessBinding` immediately before effects.
- Human ceiling references that cannot be resolved are explicitly rejected, not treated as unlimited authority. No grants are fabricated or automatically widened.

## Verification

- RED: initial bootstrap test failed with missing `bootstrap_cognitive_active` attribute before implementation.
- 10 dedicated composition tests pass: trusted boot and actual file effect; durable duplicate after reinstall; real canonical Decision/Event/AuthorityProfile revision changes block effects; missing head; revoked canonical grant; root mismatch; ambiguous branch; policy head version from actual committed successor.
- Tests use isolated temporary canonical Git stores, real ToolExecutor/WriteFileTool, SQLite journal, authenticated HTTP and the same production bootstrap function. No mock freshness callbacks are used in the installed service.
- Dedicated composition + existing active API regression run recorded separately by final test output.

## Scope and limits

Global ACTIVE remains disabled. Production installation requires trusted application-owner configuration because repository defaults do not supply real human grants, a prepared approved action, or authoritative lineage roots. This is an executable production boot seam, not automatic provisioning. Tests exercise the actual bootstrap on an isolated FastAPI app, rather than starting unrelated whole-server network/model/background subsystems. The canonical freshness check is repeated before effects; canonical store publication and external tools are not an atomic cross-resource transaction.

## Surface lifecycle follow-up

- SurfaceEpisodeRequest now forwards explicit Decision/GovernanceDecision/Outcome/Observation/Evidence lineage to EpisodePlan. Trusted composition binds the prepared request to its configured canonical Decision anchor (it does not mislabel AuthorityProfile as GovernanceDecision).
- Experience restoration filters non-Experience entities explicitly, rejects cross-project records, and lets ExperienceContractError surface for contradictory historical cores. Trusted request-local adapters restore existing canonical project cores on construction.
- New `cognitive_surface_recovery.record_recovery_experience` continues accepted late observations through actual Experience selection. Observations without a known outcome stay DEFERRED with no core. Settled recovery creates one deterministic, canonical Experience linked to Action and Observation; Observation already links the current receipt. Missing historical ancestry is explicitly INCOMPLETE. Deterministic selection/core IDs and canonical reads preserve retry/restart idempotency; no effect is redispatched.
- Fixed final review finding in `action_admission._authoritative_freshness`: a resolver-provided authorized digest was incorrectly overwritten by the request digest. It now independently requires the current canonical authorized digest to match actual executed arguments, then compares the unchanged canonical binding to readiness. RED HTTP reproduction previously dispatched a real file write with a different canonical authorized digest and unchanged revisions. GREEN focused regression plus action tests: 22 passed.

## Structured Primary boot contract

`ProjectActiveConfiguration` accepts exactly one of `brain_adapter` (preferred) and an explicitly trusted custom `think` port. The preferred production path is `ProjectActiveConfiguration(..., brain_adapter=primary_adapter)` with `think` left unset. On every request the installer creates `StructuredSurfaceBrainPort(primary_adapter, project_id=settings.project_id, load_context_package=store.read, load_record=store.read, record_sink=store.commit_records)` and installs that same port as both THINK and targeted RETHINK. Thus accepted judgments and cognitive requests use the actual canonical sink, and missing/unresolvable context fails closed. A custom `think` implementation remains an explicit application-owner responsibility for specialized adapters; it is never selected from an HTTP request.

Verification `test_trusted_brain_adapter_boot_persists_canonical_judgment` drives the actual trusted boot factory with canonical context and structured provider response, then checks the accepted BrainJudgment exists in the configured CanonicalStore and THINK/RETHINK share one request-local port.

Canonical authorization also rejects a current Decision with NOT_READY or FAIL/UNKNOWN checks, even when the incoming request independently claims ready and every revision/digest matches. Guarded canonical decisions require guarded request readiness. A second RED HTTP reproduction had previously dispatched this blocked canonical decision; the regression now returns 409 with no file effect.

## Canonical cognitive expansion execution

- Extracted canonical head resolver into `cognitive_active_heads.py` (stable imports re-exported from composition).
- Added `TrustedCognitiveRequestBinding(action, anchors)` in `cognitive_active_requests.py`; `ProjectActiveConfiguration.cognitive_requests` is a trusted mapping keyed by actual canonical CognitiveRequest ID. The binder requires payload.args_digest to equal the bound action digest, preserves canonical purpose/target/type/impact and uses the trusted action dimension/scope. Current canonical AuthorityProfile is loaded at request resolution and independently before tool effect. Unknown action IDs never inherit final-action heads.
- Each expansion action uses its own canonical Decision/State/Authority/Policy anchor binding. The structured port receives the binder through its explicit request_resolver seam; unbound requests fail closed.
- Real authenticated HTTP test `tests/cognitive/test_active_expansion.py::test_structured_request_executes_actual_read_and_rethink_receives_canonical_receipt` executes ReadFileTool through the existing ToolExecutor, persists its canonical receipt, then verifies the actual receipt body reaches the second structured Primary call. The Primary responder is deterministic protocol QA, not a live model claim. Separate tests prove missing binding and mismatched canonical args digest cannot dispatch.
- This E2E exposed ActionReceipt.detail being lost in canonical serialization. Added backward-compatible `ExecutionReceiptPayload.detail` and serializer/restorer wiring. Reopened CanonicalStore receipt preserves actual read content. ToolExecutorPort's existing result bound now marks truncation explicitly instead of silently slicing a result; long output requires further reading rather than claiming completeness.
- Composition + expansion + surface lifecycle validation after these changes: 20 passed, scoped Ruff clean. Broader regression final count is reported to parent separately.
