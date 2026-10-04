---
title: P07 action durability and freshness regression repair
date: 2026-09-25
tags: [cognitive, action, safety, evidence]
---

# Scope and results

Owned `actions.py`, the focused `action_*` helper modules, and `tests/cognitive/test_action_safety.py`. No production data, external tools, commits, or surface changes were made by this worker.

The original implementation dispatched before calling the canonical sink, accepted cached expired/future/revoked/out-of-scope/operation-incompatible grants, and repeated a non-idempotent action whose FAILED receipt already recorded an observed effect. Seven behavioral regression cases were run against that implementation and failed for these reasons before the implementation changed. A fixture initially omitted required grant revision; that fixture was corrected and all seven genuine behavioral failures were rerun.

Two further failing-first regressions exposed receipt action IDs that did not reference the persisted authorized action and cancellation incorrectly replacing an observed FAILED effect with an effects_observed=False receipt. Both now pass.

# Implementation

- `ActionDispatcher` now persists the authorized canonical intent before calling the executor and persists only the receipt after execution, avoiding a duplicate intent sink write.
- `ActionDispatcher.journal` accepts the `ActionJournal` protocol. `SqliteActionJournal(path)` commits a unique `(project_id, action_key)` claim and serialized intent under SQLite FULL synchronous mode before any effect. Independent processes and restarted dispatchers compete on the same durable claim. Database errors propagate without dispatch.
- Claims deliberately remain held after crashes, sink failures, or outcomes. No automatic retry/release is inferred from absence of a receipt. This prioritizes duplicate prevention; durable retry/reconciliation administration remains an explicit future policy.
- `authority_resolver(intent, moment)` is an optional live authority port. It is consulted during initial admission and again after durable claim/canonical persistence immediately before dispatch. Real grants are rechecked for scope, dimension, allowed operation, issuance time, expiration and revocation. Existing no-grant fixture decisions retain compatibility only on the legacy no-resolver path; the active surface must require an authoritative resolver and shared journal.
- `ActionIntent.operation` defaults to `execute_tool` and is included in its action digest.
- Observed effects block duplicate execution regardless of FAILED status. Cancellation preserves their effect evidence.
- Authorized canonical record IDs now equal the intent action ID passed to the executor and receipt.
- Extracted value objects, admission, journal, canonical record construction, lifecycle and structural helper context preserve the public `actions` imports. Each production action module is at most 250 nonblank/noncomment lines.

# Verification

Command:

```text
.venv/bin/pytest tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q --no-cov
31 passed in 1.21s
```

Coverage includes canonical persistence order, observed FAILED replay, five grant freshness/scope/operation failures, crash after an external file effect then restart, two real spawned OS processes concurrently claiming one action (exactly one file effect), canonical sink failure, SQLite journal failure, live revocation during persistence, canonical action identity and post-effect cancellation.

The process test uses per-test temporary paths, a multiprocessing barrier, bounded waits and process cleanup. It does not rely on sleeps or production storage. The existing real ToolExecutor sandbox tests remain passing.

Ruff check and formatter pass on touched action modules and the regression test. Type checking with `.venv/bin/python -m basedpyright src/antigravity_k/engine/cognitive/action*.py` reports **0 errors, 39 warnings**; warnings concern inherited dynamic executor/value types, shared private helper methods and unused call return values. The basedpyright launcher itself has an existing stale interpreter shebang, so module invocation was used. A transient helper-name shadowing error during extraction was fixed and the full targeted suite rerun successfully.

# Limits

Durability is explicit dependency injection; constructing a dispatcher without a journal retains process-local behavior and is unsuitable for active external effects. Canonical storage is still a separate injected sink (the journal does not replace files/Git). Journal claims are conservative and never auto-released. The grant resolver is the caller's authoritative integration boundary; this worker did not implement or mutate the active surface.
