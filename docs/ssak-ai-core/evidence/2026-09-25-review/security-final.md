---
title: Cognitive ACTIVE security boundary final review
date: 2026-09-25
status: PASS-bounded-prepared-action-boundary
reviewer: security_review
source_head: 6be0263d121c1e2a7ade92d3127af226c5e0581f
tags: [cognitive-core, security, review, evidence]
---

Verdict: **PASS for the explicitly composed, server-prepared ACTIVE HTTP action boundary reviewed below.** No remaining reproducible blocker was found in that boundary. This verdict applies to the dirty-tree file hashes below, not to HEAD alone. It is not a claim that the entire agent runtime is migrated or that arbitrary shell programs are contained.

Graph discovery was attempted first and returned `Transport closed`; current disk source was then inspected. No production effects, source edits, or commits were performed by this reviewer. All execution checks used pytest temporary roots or TemporaryDirectory fixtures.

## Observed checks

- `pytest tests/cognitive/test_active_api.py tests/cognitive/test_action_safety.py tests/cognitive/test_protection.py -q`: **41 passed**, one Starlette/httpx deprecation warning, 2.14 seconds.
- `pytest tests/cognitive/test_protection_boundaries.py tests/cognitive/test_surface.py -q`: **39 passed**, 7.56 seconds.
- Additional temporary HTTP fixture checks: another owner's GET returned **404**; prepared-project/adapter-project mismatch returned **409**; absent service returned **503**. No effect file or canonical manifest was created in these three checks.

## Boundary findings

1. **Identity and spoofing — PASS.** `api/routes/cognitive_active_api.py:73` validates the bearer with the real TokenService; `:89` binds both read and execute access to the prepared owner. The request model accepts only request ID, action digest and reason, with extra fields forbidden (`:41`). `:121` compares the server-prepared intent digest; the caller cannot supply tool arguments, readiness, authority or an approver. `engine/auth.py:245` verifies JWT signature/issuer/expiry and the configured session epoch. Forged tokens, absent credentials, another owner, changed digest and an injected approver are covered by the actual HTTP fixture tests.
2. **Session revocation — PASS at the pre-effect boundary.** `cognitive_active_api.py:124` re-verifies the captured bearer, subject and project. `engine/cognitive_surface.py:260` invokes this authorizer on each live authority resolution. `engine/cognitive/actions.py:145` performs a second admission after canonical persistence and before dispatch. Revoking the real TokenService epoch during the canonical sink returns 409 with one durable intent and zero effects. Revocation after a tool has already started cannot undo its effect; that is outside this admission contract.
3. **Project separation — PASS for prepared ownership/context.** `cognitive_active_api.py:134` rejects mismatching adapter project IDs. Request-local adapters capture a request-local authorization closure. SQLite uniqueness is on `(project_id, action_key)` (`action_journal.py:35`). Additional HTTP project-mismatch and cross-owner disclosure checks passed. Actual executor workspace/store routing remains the responsibility of the trusted service factory; this API does not accept those objects from clients.
4. **Replay, concurrent claims and ordering — PASS.** `action_journal.py:29` uses SQLite transactions, a composite primary key and synchronous FULL; the claim commits before its return. `actions.py:142` acquires the claim, then persists intent, then rechecks admission, then invokes the port. Two spawned processes produced one effect. A crash after effect followed by a fresh dispatcher was blocked by the durable claim. Journal failure and canonical sink failure both prevented effects. Claims intentionally remain after uncertainty/failure: replay safety is proven, automatic retry/recovery liveness is not claimed.
5. **Grant freshness — PASS for the reviewed inputs.** `action_admission.py:24` resolves current authority; grant subject, scope, dimension, operation, issuance, expiry and revocation are checked at `:38`. The two admission passes catch expiry/revocation across persistence. The earlier expired-grant bypass is covered by `test_cached_grant_is_checked_at_dispatch`; live revocation during persistence is separately covered.
6. **Protected write regressions — PASS.** `tools/permission_gate.py:186` binds the full actual tool arguments into a digest and scopes registered approvals to the effective root. Protection runs before an ALLOW override. `engine/cognitive/protected_targets.py:339` checks every matching protected root, including ancestors. Tests deny empty digest, changed content, allow-override bypass, ancestor deletion and incomplete class approvals; preserve an injected store guard; and deny approval reuse after workspace changes.

## Bounded limitations

- ACTIVE has no default installed service: an authenticated caller receives 503 until trusted composition supplies prepared actions, a request-local adapter factory, shared durable journal, canonical sink, live authority resolver and executor. This is fail-closed integration scaffolding with a tested real HTTP/tool/store path, not evidence that all default chat/background actions use it.
- A valid authenticated owner explicitly authorizes the prepared action. The factory, prepared-action registry, live resolver and canonical sink are trusted server components. Malicious replacement of those components is not treated as an HTTP-client attack.
- The PermissionGate shell parser is lexical policy, **not an OS sandbox**. The tests establish the named direct/path/ancestor regressions only. Encoded programs, dynamically computed paths, arbitrary plugin internals and unrestricted shell interpreter behavior are not proven contained by this review. Custom canonical-store locations must be registered in the protected guard; default project-document roots cannot discover arbitrary stores.
- Persistent claims prevent replay after process loss, but do not automatically reconstruct the in-memory pending-reconciliation list. Operational recovery must consult durable journal/canonical records; it must not delete claims merely to retry.
- `manual-active-http.json` was inspected as another worker's reported uvicorn/curl/restart evidence (one dispatch, duplicate blocked after restart, two Git-backed canonical records). It was not independently rerun by this reviewer. The independently executed HTTP tests here use FastAPI TestClient, real JWT verification, real ToolExecutor/WriteFileTool, SQLite, and a Git canonical store. No live-brain behavior is certified.

## SHA-256 binding

```text
a9071f70769dabb2f6af46c567ae40c3c040b5c4c902ae939d12b3573bdac7ee  src/antigravity_k/api/routes/cognitive_active_api.py
00651289b141ef3585bf41a5178f2e44b158331eee3c32df8927ec54721ce37b  src/antigravity_k/api/routes/cognitive_surface_api.py
e8ef933bff0b98ef6ec4fd439b50d897fd575992246427c5d9b73ccc6fd6865b  src/antigravity_k/engine/cognitive_surface.py
04f1335de29ff5229a80fc524d54642ebaa5a6a40cb5edc70b59599fb13fab6b  src/antigravity_k/engine/cognitive/action_admission.py
d2ccec70d9ade962d7b444df2b490115d387d82e617f4b06d502847b62e9e5d5  src/antigravity_k/engine/cognitive/action_journal.py
4caa7f79372e7a69831eed631c7c2d1010620eee0300ddb3ee94c16e48deac42  src/antigravity_k/engine/cognitive/actions.py
d38c3788b0d6f2dafe32d1dcf43c0221da21588d0d9ae3f398f993eae7876b97  src/antigravity_k/engine/cognitive/action_types.py
1223efbfbfdde20e4ba5dd067d6825d5a0bce53dd4f6890ac5d05c57c9b4eb8f  src/antigravity_k/engine/cognitive/protected_targets.py
b011f71dfc7f6981d9e855e8d9bfda28ec0f1abd685e84d17372f8eac941883d  src/antigravity_k/tools/permission_gate.py
382cd2d82d64b84c410b387e860e26ea06363d65b85dca4258c8501ecfd89a7f  src/antigravity_k/engine/auth.py
4ddbfcd8365553512ae4b9df29a7dcae4e6c504730449249270cd647fbaa268d  tests/cognitive/test_active_api.py
0b174d08b23efabb9e5858e8876cab3a02962d8812c3d3c13e1e94607ed13a51  tests/cognitive/test_action_safety.py
a306b5e2ef0989729a2302e94171c27d7ad24e6a72c4a5e43694b8dffa2fa01c  tests/cognitive/test_protection_boundaries.py
```
