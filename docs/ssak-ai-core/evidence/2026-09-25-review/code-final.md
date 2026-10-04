---
title: Cognitive core final code review
date: 2026-09-25
verdict: PASS
head: 6be0263d121c1e2a7ade92d3127af226c5e0581f
tags: [cognitive-core, review, code-correctness]
---

# Verdict: PASS (bounded current-tree review)

Reviewed the current uncommitted implementation, not the original HEAD implementation. No additional actionable blocker found in the reviewed changes. This verdict applies only to the exact source manifest below; HEAD alone does not identify the reviewed code.

Graph discovery was attempted first and returned `Transport closed`; current disk source and diff were then inspected. No production state or source files were changed by this reviewer.

## Correctness assessment

- Both previously reproduced duplicate-effect defects are addressed. ACTIVE supplies the shared durable journal to each request-local dispatcher; SQLite commits the unique project/action claim before dispatch. A receipt with an observed effect now refuses replay even when its outcome is FAILED.
- Canonical intent persistence occurs before the external call. Live grant and authenticated session checks repeat after persistence. Journal/storage failures stop execution before that boundary.
- The action record identity matches the execution receipt. Planned records retain independent identities, avoiding a create-only store collision when planning precedes authorization.
- Active HTTP input is restricted to a server-prepared request identifier, digest and reason. Verified JWT ownership, current action digest, project context and session revalidation are checked; request JSON cannot supply its own grant or readiness decision.
- Protected writes evaluate all overlapping protected classes and ancestor targets, bind approval to actual tool arguments, and run before permissive overrides. Workspace changes invalidate approval reuse.
- Extracted modules preserve public imports used by callers. Reviewed lifecycle, context protocol, value contracts and source measurement extraction for integration regressions.

## Validation

Independent reviewer execution:

```text
uv run pytest -q tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py tests/cognitive/test_protection_boundaries.py --disable-warnings
30 passed, 1 warning in 2.13s
```

This covers durable crash/restart admission, concurrent process claims, observed failure replay, failed storage, live authority revocation, real HTTP tool execution with canonical Git persistence, duplicate HTTP submission, invalid identity/ownership/digest and mid-write session revocation. Existing `pytest-boundaries.txt` separately records 150 passed; that broader run was not repeated by this reviewer.

## Scope limits

The journal intentionally never releases claims automatically; recovery/retry after an admitted but unexecuted action requires explicit operational handling. The API remains opt-in server composition and returns unavailable when that service is absent. This review does not assert exhaustive shell-language sandboxing, whole-repository security, or deployment readiness. No constitution changes were requested or made.

## Exact SHA-256 manifest

```text
04f1335de29ff5229a80fc524d54642ebaa5a6a40cb5edc70b59599fb13fab6b  src/antigravity_k/engine/cognitive/action_admission.py
517a7d7eb4a87f6579dcda99117261fcb6286b22be97bc096daeda938359b028  src/antigravity_k/engine/cognitive/action_context.py
d2ccec70d9ade962d7b444df2b490115d387d82e617f4b06d502847b62e9e5d5  src/antigravity_k/engine/cognitive/action_journal.py
e304bd2fe29987f35a764fd98d7a63bd89b299c1ef819f171ceff8041156321d  src/antigravity_k/engine/cognitive/action_lifecycle.py
b947323701780674b3f6cdccde3f0e6f6061e19467f9ccafa443988e9bd71a69  src/antigravity_k/engine/cognitive/action_records.py
d38c3788b0d6f2dafe32d1dcf43c0221da21588d0d9ae3f398f993eae7876b97  src/antigravity_k/engine/cognitive/action_types.py
4caa7f79372e7a69831eed631c7c2d1010620eee0300ddb3ee94c16e48deac42  src/antigravity_k/engine/cognitive/actions.py
1223efbfbfdde20e4ba5dd067d6825d5a0bce53dd4f6890ac5d05c57c9b4eb8f  src/antigravity_k/engine/cognitive/protected_targets.py
e8ef933bff0b98ef6ec4fd439b50d897fd575992246427c5d9b73ccc6fd6865b  src/antigravity_k/engine/cognitive_surface.py
e72fe1bf6be488d44b0f9d27fb6f0f392ef6505e1a91d5aea587b03dde9cb59d  src/antigravity_k/engine/cognitive_surface_measurement.py
20d71760b9b63dc5313f21334a34b4152d0416aff3ac68d7b8a7f08d4d41bb3b  src/antigravity_k/engine/cognitive_surface_types.py
b011f71dfc7f6981d9e855e8d9bfda28ec0f1abd685e84d17372f8eac941883d  src/antigravity_k/tools/permission_gate.py
a9071f70769dabb2f6af46c567ae40c3c040b5c4c902ae939d12b3573bdac7ee  src/antigravity_k/api/routes/cognitive_active_api.py
00651289b141ef3585bf41a5178f2e44b158331eee3c32df8927ec54721ce37b  src/antigravity_k/api/routes/cognitive_surface_api.py
0b174d08b23efabb9e5858e8876cab3a02962d8812c3d3c13e1e94607ed13a51  tests/cognitive/test_action_safety.py
4ddbfcd8365553512ae4b9df29a7dcae4e6c504730449249270cd647fbaa268d  tests/cognitive/test_active_api.py
b3a4490a7d2cfa840553dfd343d157d7447807442fa06b5c687dc852d2254335  tests/cognitive/test_protection.py
a306b5e2ef0989729a2302e94171c27d7ad24e6a72c4a5e43694b8dffa2fa01c  tests/cognitive/test_protection_boundaries.py
796006c5084d0948d01c11735464b922a9c10f32b8309da10bd636132634b3ee  tests/cognitive/test_surface.py
```
