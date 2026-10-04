# Brain bridge completion evidence — 2026-09-27

Repository: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.

## Changes

- Extracted renderer into `cognitive/brain_context_render.py`; stable exports remain in brain.py.
- Selected L0 constraints, L1 state, L2 history, L3 evidence, full payload fields, and package metadata now reach the provider. `snippet_chars` remains accepted for compatibility but never shortens selected content. Full UTF-8 serialization is conservatively budgeted; oversized or unresolved selected content fails closed.
- Extracted StructuredSurfaceBrainPort and counting wrapper into cognitive_surface_brain.py; public import remains stable.
- Added optional Primary-authored MaterialCognitiveDelta to BrainJudgmentPayload; exact fields map to EpisodeDelta. No semantic change is inferred by Body.
- Canonical request references resolve to runtime request envelopes; unresolved/wrong-type/wrong-project requests fail closed. Requests require an explicit trusted request_resolver binding. Missing bindings and changed canonical request identity/type/purpose/target/decision-impact fail closed; action arguments, authority and dimension come unchanged from the trusted composition binder. No execution binding is invented.
- Optional record_sink persists every validated judgment. Rethink preserves prior judgment, creates a superseding judgment, and sends actual typed feedback plus fully loaded canonical receipts. Missing or wrong-project/type receipts fail before the next provider call, including executed=True feedback with receipt_ref=None.
- Provider responses must match the actual supplied context_digest; malformed schema or mismatched digest has a single repair allowance. Missing input digest fails before a provider call. Updated successful fixtures to bind their actual context digest.
- Provider call count reflects real respond invocations, including repair calls.

## Red → green observations

Command (repository cwd):
`.venv/bin/python -m pytest tests/cognitive/test_brain_bridge_regressions.py -q`

Before fixes, observed failures included: 800-character goal reduced to 400; 20,000-character required goal incorrectly accepted within 1,000 budget; record_sink unsupported; rethink missing; invalid delta schema escaped as ValidationError; unbound Secondary Brain request incorrectly reported as adapted; mismatched digest accepted as BrainJudgment.

Receipt tests first failed because context_delta lacked receipts and an unloadable receipt still resulted in a second provider call.

Final command:
`.venv/bin/python -m pytest tests/cognitive/test_brain.py tests/cognitive/test_brain_bridge_regressions.py tests/cognitive/test_brain_receipt_bridge.py -q`

Result: **42 passed**.

Ruff check for the three owned implementation modules and three Brain test modules: **all checks passed**.

`.venv/bin/python -m basedpyright src/antigravity_k/engine/cognitive/brain_context_render.py src/antigravity_k/engine/cognitive_surface_brain.py`

Result: **0 errors, 0 warnings**. The direct basedpyright launcher has an existing stale interpreter path; running via the repository Python works.

## Actual local provider-contract driver

`PYTHONPATH=src:. .venv/bin/python /Users/mr.k/Documents/Codex/2026-09-22/referenced-chatgpt-conversation-this-is-an/work/finalize-2026-09-27/brain_contract_driver.py`

Result:
```
PASS: ContextPackage -> structured provider contract -> durable judgment -> typed feedback -> new judgment
provider_calls=2; external_provider_calls=0; paid_calls=0; canonical_judgments=2
```

This runs the production port, structured client, renderer, and canonical store against a local deterministic implementation of the provider protocol. It is not a live hosted-model quality claim. No global configuration was modified and no commit was created.

## Broader-suite boundary

A duplicate tests/cognitive run was stopped at the parent's request because the final QA worker owns that lane. Interrupted result: 293 passed, 11 failed; failures included existing artifact digest/count gates, enum audits, R10 HTTP, and evidence gate. The enum audit independently identified only live_pilot.py:1238/:1256 and live_trial_adapter.py:156, outside these changes; parent was notified. Do not treat the interrupted broad run as full-suite verification.

## Scope review and hashes

Renderer owns lossless context serialization; port owns structured runtime adaptation. Inputs are validated through canonical models; Primary retains materiality and action semantics. New modules stay below 250 nonblank/noncomment lines, with the port in the warning band. Existing brain.py/models.py and original tests are already oversized; this change extracts the renderer and port without a broad unrelated rewrite. Shared-file hashes are point-in-time because other authorized workers also edit models.py/surface.py. No before-file hashes were captured; the before behavior is recorded by the observed failing commands above.

| File | Nonblank/noncomment lines | SHA-256 after |
| --- | ---: | --- |
| `src/antigravity_k/engine/cognitive/brain.py` | 550 | `422cb28624be5c166c130f4a6705d81dc4b3c0a989da3d1f44578dc1fea2e393` |
| `src/antigravity_k/engine/cognitive/brain_context_render.py` | 71 | `bb3e1d677ece3580228091a0b682bbf4fb58cb4f3c64e8088e50fa701e59c4c1` |
| `src/antigravity_k/engine/cognitive_surface_brain.py` | 235 | `48cd219aedb54d54f9ba8fbfc2fe0c4d0be7faa7398173b23300110b4678f6eb` |
| `src/antigravity_k/engine/cognitive/models.py` | 879 | `ca25fe36564cc9917169d2f61247db2cc71a3be9e241c6b4c4eb0933b5e6838a` |
| `tests/cognitive/test_brain.py` | 562 | `544e3104813aa282dea796390b089cef0131db4c606535c088501713d16b6def` |
| `tests/cognitive/test_brain_bridge_regressions.py` | 214 | `6440cc146f6f7f5fc4b87720df11fb67e1a387d1194dd10fd34ee4de95dd0bd4` |
| `tests/cognitive/test_brain_receipt_bridge.py` | 99 | `d813ab7d494a5a789ca19720a10491945eb8fa4974df9e1e5a04d88f69470c10` |

## Final counterexample closure

The independent final review exposed executed=True feedback with no receipt reference. The added parametrized regression first failed (provider_calls=2), then passed after explicit EXECUTED_RECEIPT_MISSING failclosure (provider_calls stays 1). Denied/unexecuted feedback without a receipt remains valid.

The serialization-only request adaptation was replaced by optional `request_resolver: Callable[[Record], CognitiveRequestEnvelope | None]`. Absent/missing binding fails as REQUEST_UNBOUND; mismatched canonical metadata fails as REQUEST_BINDING_MISMATCH. Successful envelopes come unchanged from the trusted composition binder. Dedicated red→green tests cover exact, missing, mismatched and default-unbound Secondary cases. The composition worker owns separate trusted per-request action/authority/args-digest/current-head binding and full model-request→real tool→receipt→rethink integration proof; the local driver above alone does not claim full autonomous request execution.

## Final import-cycle closure

Moved the existing SurfaceBrainPort class unchanged into cognitive_surface_legacy_brain.py; cognitive_surface.py re-exports it and cognitive_surface_brain.py imports the dedicated module directly. This removes the new surface→structured-port→surface cycle without changing cognitive/* dependencies or legacy behavior.

Verification: 69 Brain + surface tests passed; Ruff clean; basedpyright over the three modules reports 0 errors and 0 import-cycle diagnostics (31 existing warnings). Raw output: brain-cycle-types.json.

- `src/antigravity_k/engine/cognitive_surface.py` SHA-256 `dde8864726956390483008334bc7463a5668ac7e2b115fc047c417daf2218cef`
- `src/antigravity_k/engine/cognitive_surface_brain.py` SHA-256 `54d0fff11a328608014c7fbbfd41e8d770f9b792bc4c2c1b44aa6ec81663a2f9`
- `src/antigravity_k/engine/cognitive_surface_legacy_brain.py` SHA-256 `454e4c5f0f96d8e42fb3c04c139617887fd751021bb41052c22830a2d2109b34`

## Final typed plan invalidation closure

Independent HTTP counterexample: a second Primary judgment changed both risk/action but supplied no new EpisodePlan; runtime retained the old prepared final write and created effect.txt. Added a 12-case unit matrix (initial/rethink × risk/action/ground × absent/explicit plan) and three actual HTTP expansion cases. Red: 7 failed, 11 passed; four unit paths dispatched and three HTTP paths wrote the stale final effect.

Runtime now DEFERs on any typed action/risk delta without an explicit prepared plan, on both initial THINK and RETHINK. This occurs before final dispatch and preserves actual prior request feedback/receipt records. No prose parsing or Body-authored replacement plan. Ground-only updates explicitly retain the prepared plan; the matrix covers that policy. An explicit plan remains subject to existing readiness/authority/freshness checks.

FixtureThink now receives the actual prebuilt scoped EpisodePlan and explicitly returns/reaffirms it, preserving its original risk/action delta flags. The existing safe-alternative test likewise explicitly provides its actual prepared plan. Live owner separately updates ModelDrivenThink to provide its actual choice-based prepared plan.

Commands:
- `.venv/bin/python -m pytest tests/cognitive/test_episode_plan_binding.py tests/cognitive/test_active_expansion.py tests/cognitive/test_episode.py -q`: **55 passed**.
- `.venv/bin/python -m pytest tests/cognitive/test_growth.py -q`: **25 passed**.
- Ruff over these implementation/test paths: clean.
- Exact independent HTTP probe rerun: `goal-risk-probe-fixed.txt`: HTTP200, action_status null, dispatched_actions0, effect_exists false; read action/receipt still canonical.
- Typecheck runtime+growth: no runtime errors; two pre-existing growth errors (possibly unbound corrected; optional policy_version), raw brain-plan-types.json. Root owns broader baseline classification.

Point-in-time final plan-guard hashes (growth.py has concurrent live-owner plan_readiness-only work):
- `src/antigravity_k/engine/cognitive/runtime.py` SHA-256 `0ff93d8ee9e32b1f0b01dca53069c166baf2569a39545faca2674adfc4ee2683`
- `src/antigravity_k/engine/cognitive/growth.py` SHA-256 `c472511c2dfe4436f79f80b7dbd1fa354cf024d3b72d32eb1756384ebe689816`
- `tests/cognitive/test_episode.py` SHA-256 `71c4f7d7887bec8bfb2d74bb89df356118fc51c971fec103e996c9abb512b732`
- `tests/cognitive/test_episode_plan_binding.py` SHA-256 `8046fd840fd527d88a0a8703393a46be610a21c09dd97b6071d8f418570484cf`
- `tests/cognitive/test_active_expansion.py` SHA-256 `b2e1bcaed628c849874b27897724365b08250d011fa5b09972fcc6ede9740c8c`
