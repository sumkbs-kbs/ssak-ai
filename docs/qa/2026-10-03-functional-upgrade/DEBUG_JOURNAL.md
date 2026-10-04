---
title: Functional upgrade runtime evidence and cleanup journal
date: 2026-10-03
tags: [qa, debugging, runtime-evidence]
---

Scope: same-project conversation ownership, progressive output, canonical conversation fork/compact, and task submit/fork retry. No production auth, home environment, Constitution or persisted user history is altered for test isolation.

Hypotheses checked by read-only audits and failing-first regressions: (1) project-only guards permit cross-session writes; (2) abort resolution permits stale finalization after a new run starts; (3) stream buffer has no rendering consumer; (4) queue text and shared attachment bytes have different ownership; (5) supported request DTOs reject an injected project_revision; (6) uncertain task POST failures discard the idempotent operation.

## Journaled artifacts

| Artifact | Purpose | Cleanup rule |
|---|---|---|
| baseline/dashboard-before.tar | exact source before this task | retain as review evidence |
| captures/*, test/build logs, source/bundle manifests, reports | durable scoped QA evidence | retain; no credentials or auth headers |
| /tmp/ssak-functional-isolation-20261003-root/sitecustomize.py and test-home | isolated Python import/spawn test state; reuse prior proven helper | remove only this temporary helper/home after tests; never inject into running API |
| fixture/* and isolated QA server | controlled HTTP response-loss verification | preserve fixture source/results; stop only its process at closeout |

## Runtime observations

Initial optional backend contract test attempt: collection failed because module import tries the user's GBrain lock outside the sandbox. The failed output is retained as backend-contract-tests.log. Follow-up uses the already established test-only Path.home patch via SSAK_QA_HOME and PYTHONPATH so both parent and spawn imports stay isolated. System HOME is unchanged; no approval escalation to the real user store.

Further runtime results and final cleanup are recorded in REPORT.md and the evidence ledger.
