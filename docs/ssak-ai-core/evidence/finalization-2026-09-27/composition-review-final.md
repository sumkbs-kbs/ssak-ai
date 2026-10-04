# Independent final ACTIVE composition review

**Scoped final verdict: PASS** for the source hashes below. No remaining blocker found in trusted composition, canonical admission, authenticated HTTP boundaries, structured request binding, durable result forwarding, or late recovery selection.

Read-only review of trusted installation, canonical heads, authenticated HTTP execution, digest binding, and late recovery Experience selection. Base HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; source is dirty and this verdict binds the file hashes below.

## Independently confirmed and fixed during review

P1: canonical Decision `readiness.verdict=NOT_READY`, with a FAIL check and otherwise matching digest/revisions, initially allowed a ready prepared request to dispatch. Real temporary filesystem effect observed: `canonical_verdict NOT_READY http 200 effect True refusal None`. Worker added fail-closed validation of canonical verdict/checks and guarded-readiness compatibility.

Post-fix independent probes:

```
canonical_verdict NOT_READY check FAIL http 409 effect False
canonical_verdict READY check UNKNOWN http 409 effect False
```

The second probe verifies malformed READY metadata cannot bypass a blocking check.

## Independent execution evidence

Installed production-composition auth probe using real canonical heads and real temporary ToolExecutor:

```
missing token / forged token / other owner / injected approver / wrong digest
401 / 401 / 404 / 422 / 409
filesystem effect: absent
```

Selected tests: `test_active_composition.py`, `test_surface_lifecycle.py`, active API authentication/ownership/digest/extra-claims test, and session-revoked-during-canonical-write test: **19 passed in 4.81s**. One pre-existing FastAPI/httpx deprecation warning. A prior run collected the newly added canonical NOT_READY regression during its RED phase and correctly failed it; the subsequent run verifies the fix.

These cover default unconfigured boot OFF, explicit trusted installation, actual executor effect, restart duplicate prevention, committed Decision/state/authority successor drift, missing/ambiguous heads, canonical grant revoke, wrong project root, independent policy version, canonical authorized digest mismatch with unchanged revisions, request-local structured port wiring, recovery Experience single selection on replay, and DEFERRED observations producing no Experience core.

## Reviewed boundaries

- Bootstrap accepts only an already constructed trusted `ProjectActiveConfiguration` from application state and runs in server lifespan; no HTTP route accepts paths, principals, grant bodies, or executors.
- Installed service copies prepared requests, binds canonical Decision lineage, validates prepared owner/project and executor project root, and shares its canonical store and durable action journal across request-local adapters.
- Head resolver reads committed records for one project. Missing roots, ambiguous successors, wrong record kind, repeated/regressed integer revision, unresolved authority ceiling, blocked readiness, or missing digest fail closed.
- Final admission verifies canonical authorized digest equals executed arguments, then checks the readiness binding against returned canonical revisions. This fixes the original intent-digest overwrite.
- HTTP authentication validates signed bearer identity; prepared requests require their owner. Session authorization is rechecked at execution admission. Explicit activation remains required on the HTTP path.
- Recovery selection uses deterministic observation-derived event/core IDs, verifies canonical project Observation, preserves missing-lineage flags, and restores existing cores on replay. It does not silently promote incomplete lineage to complete.

## Nonclaims

This is an opt-in server configuration path, not a default ACTIVE switch. Freshness is a last-admission-check contract: it does not freeze external effects and concurrent canonical writers in one distributed transaction. No multi-host, NFS, operational cutover, or live provider claim is made. Recovery/migration source verdict remains in `code-review-final.md` and is not overwritten by this report.

Additional independent timing probe: patched only the real store sink to publish a canonical state successor (revision 2) immediately after intent persistence, before the second admission check. The installed resolver re-read the store: `HTTP 200 / STALE_READINESS / effect False`. This exercises live canonical mutation during execution admission, not an intent self-comparison or fixture freshness box.

## Final structured path and receipt durability verification

The trusted installation now constructs request-local StructuredSurfaceBrainPort with canonical loaders/sink and the same port for RETHINK. `ActiveRequestBindings` supplies server-owned actions and separate canonical heads for cognitive requests. Unknown action identities cannot inherit the final prepared action's authority; absent bindings or argument-digest mismatch fail closed. Canonical request identity/type/purpose/target/impact are checked against the resolved envelope.

The new real-tool integration initially exposed dropped result text: ActionReceipt.detail was not serialized. The additive `ExecutionReceiptPayload.detail` field (default empty for older records), `ActionReceipt.to_record`, and recovery decoding now preserve that text. The regression retains meaningful content assertions, not only receipt IDs.

Final independently executed selection:

```
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/cognitive/test_active_expansion.py \
  tests/cognitive/test_active_composition.py \
  tests/cognitive/test_surface_lifecycle.py \
  tests/cognitive/test_observation_atomicity.py \
  tests/cognitive/test_active_api.py::test_authentication_ownership_digest_and_extra_claims \
  tests/cognitive/test_active_api.py::test_session_revoked_during_canonical_write_blocks_effect \
  -q -p no:cacheprovider
```

**30 passed in 7.99s**, one FastAPI/httpx deprecation warning. The expansion test runs authenticated HTTP through the production installer, a deterministic structured Primary protocol adapter, an actual ReadFileTool, canonical receipt persistence, and a second Primary call. The receipt body reaching RETHINK contains the actual file contents; reopening the store and reconstructing the receipt retains the same detail. Unbound and digest-mismatched cognitive requests make no tool dispatch. This is deterministic protocol integration, not a live provider claim.

## Final SHA-256 binding

```
a92476d93628bd71b488ada19e925809fb7223d3b037d2f17832052783cbf8c0  src/antigravity_k/engine/cognitive_active_composition.py
6734b842a2540bc46b283bad686d6f53ca399aa478b62b10e9f0ba16eb7840a1  src/antigravity_k/engine/cognitive_active_heads.py
2d66862941a20743168f52ee27fe639de74b9509d2218a990a1b73a4923c69db  src/antigravity_k/engine/cognitive_active_requests.py
98ce540e8557db25d3e3770e9d206a26faf99ac5dd114e9ca992b330f5028e14  src/antigravity_k/engine/cognitive_surface.py
48cd219aedb54d54f9ba8fbfc2fe0c4d0be7faa7398173b23300110b4678f6eb  src/antigravity_k/engine/cognitive_surface_brain.py
9d62e2afd5c52a7edbcf6c0accb358ce71a579f956607f54ef97338c89be783d  src/antigravity_k/engine/cognitive_surface_recovery.py
f46b654bd5088ca72b600ff06f7687118c778522243df9edc6c7bfcbb9e74b39  src/antigravity_k/engine/cognitive/action_admission.py
0a600600ded4597271eb0fe530fb4423c1d9bb3085b1051ada367f573c58e37f  src/antigravity_k/engine/cognitive/models.py
a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7  src/antigravity_k/engine/cognitive/action_types.py
f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c  src/antigravity_k/engine/cognitive/action_recovery_records.py
274a057b06492e9f4ca1c09bbb6da72a48430aa22fdc75f0fcccce47c20e77c0  src/antigravity_k/api/dependencies.py
8cdafc0f69b4a65ceda843d48626e5350c344a622b7aa570c5b804f8b5b03ae3  src/antigravity_k/api/server.py
524496f292b9b1ea56f8f5ec60ae08d1d28d356d6847179e39474e2ab0546046  src/antigravity_k/api/routes/cognitive_active_api.py
b2f1f53af5653140881645107aa1780fa74519ec758e0b567780d911a96b16cd  tests/cognitive/test_active_composition.py
b71d9922cba0dee2b405c33f0d3b450b18b275c254a1aee72222503df2afa90a  tests/cognitive/test_active_expansion.py
bddd77a7f2957947f705c391a7233e590715e89adebd0e64b30e74c780ab1878  tests/cognitive/test_surface_lifecycle.py
00e6ccd76376d7a815c9ef0a24216094c0b368f83ef28023f7ddbf91a5e0c6f3  tests/cognitive/test_observation_atomicity.py
```

## Final compatibility dependency repin (supersedes earlier model hash)

**Scoped PASS reaffirmed** at HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus current dirty dependencies. Independently reviewed targeted absent-additive-field preservation in `to_wire` and all ten dedicated tests. Real pre-upgrade persisted bytes/issued ContextHandle resolve correctly; explicit defaults and nondefault result detail remain intact. Compatibility + recovery + installed composition selection: **38 passed in 11.22s**.

Final `models.py` SHA-256: `afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945`. Dedicated compatibility test SHA-256: `38c31ac70f2854681fcaa16bd3f3b255daebbe451e7802503bf3bcfd18f58fca`. `action_types.py` remains `a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7`; `action_recovery_records.py` remains `f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c`. All other composition source pins remain unchanged. Full method and command: `wire-compatibility-review.md`.
