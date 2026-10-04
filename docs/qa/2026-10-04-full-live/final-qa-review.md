---
title: Independent final manual QA review
date: 2026-10-04
tags: [qa, manual, final, isolated-live]
status: complete
---

# Final manual QA review

Verdict: **PASS for the executed isolated API, CLI, and focused regression surfaces.**

Execution was against the frozen candidate identified by HEAD
`8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. The checked manifest was
`docs/qa/2026-10-04-full-live/final-source-manifest.json`, SHA256
`c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`.
The manifest declares 56 source/test files and 12 harness files; all 68 current
hashes matched. The report and four `final-qa-*` receipts are new QA artifacts;
they do not replace or add their counts to the earlier `root-*` receipts.

The first API attempt was stopped before readiness because the ordinary sandbox
could not bind the required ephemeral loopback socket. The exact command was
rerun with the approved local-socket execution permission and completed 118/118.
No private port 8000, browser automation, user home, credentials, logs, or model
backend was used.

## manualQa.surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
| --- | --- | --- | --- | --- | --- |
| api-118 | `API_SCENARIOS.md`: 118-case production HTTP catalog | Real production FastAPI routes over an ephemeral loopback uvicorn socket; real isolated stores; documented search/transcriber/model seams only | `.venv/bin/python docs/qa/2026-10-04-full-live/manual_api_driver.py check --output docs/qa/2026-10-04-full-live/final-qa-api.json > docs/qa/2026-10-04-full-live/final-qa-api.jsonl` | **PASS — 118/118 explicit observations; engine isolation checks present; server exited and temporary auth header was removed** | A1, A2 |
| cli-9 | `API_SCENARIOS.md`: nine actual print-only CLI cases | Fresh child processes invoking the installed Typer CLI with isolated home/config/state and outbound sockets blocked | `.venv/bin/python docs/qa/2026-10-04-full-live/manual_cli_driver.py > docs/qa/2026-10-04-full-live/final-qa-cli.jsonl` | **PASS — 9/9** | A3 |
| regression-12-suites | `root_regression_driver.py`: current focused 12-suite list | Pytest through the repository’s focused regression driver; before-import isolation and outbound socket block | `.venv/bin/python docs/qa/2026-10-04-full-live/root_regression_driver.py > docs/qa/2026-10-04-full-live/final-qa-regression.log 2>&1` | **PASS — 283 passed, 1 deprecation warning, 0 failed** | A4 |
| integrity-freeze | `final-source-manifest.json`: full HEAD and owned-file hashes | Repository and manifest integrity inspection | `git rev-parse HEAD`; `/usr/bin/shasum -a 256 docs/qa/2026-10-04-full-live/final-source-manifest.json`; SHA256 comparison for every manifest entry | **PASS — HEAD and manifest agree; 56 source/test + 12 harness hashes match** | A5 |

The API receipt is not a claim of live external provider, hardware voice, model
generation, startup dispatch, or browser page execution. Its four provider or
compatibility scopes remain visible in the receipt: deterministic external search
provider, synthetic transcriber, unavailable model port, and real route/store
logic around those boundaries.

## manualQa.adversarialCases

Each row below points to explicit case names and observed statuses in A1/A2. The
cases were executed, rather than inferred from source or earlier logs.

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
| --- | --- | --- | --- | --- | --- |
| adv-auth | `auth-required`, `auth-protected`, `auth-verify-missing` | missing or invalid authentication | Public health remains callable; protected routes reject missing credentials with 401; valid isolated bearer succeeds | **PASS** | A1, A2 |
| adv-path-bounds | `vault-bounds`, `filesystem-bounds`, `workspace-context-invalid` | path traversal and out-of-bound workspace | Reject traversal/out-of-bound paths with the explicit 400/403/404 contracts and do not escape the isolated project | **PASS** | A1, A2 |
| adv-validation | `cognitive-limit`, `task-limit`, `decision-invalid`, `extract-invalid`, `voice-blank-speak`, `job-invalid-create` | malformed or over-limit input | Return the documented 400/413/422 validation response without a successful mutation | **PASS** | A1, A2 |
| adv-search-boundary | `extract-unavailable`, `extract-empty`, `search-disabled` | external provider unavailable or empty | Preserve the typed unavailable result; represent an empty result as empty; report disabled search truthfully | **PASS** | A1, A2 |
| adv-voice-boundary | `voice-malformed`, `voice-unsupported`, `voice-overlarge` | malformed, unsupported, and oversized audio | Reject malformed/unsupported WAV and >25 MiB bodies with 422/413; no hardware success is claimed | **PASS** | A1, A2 |
| adv-model-boundary | `messages-model-unavailable`, `responses-model-unavailable`, `integration-capabilities` | unavailable model/backend | Return typed 529/unavailable capability state; do not fabricate generated output | **PASS** | A1, A2 |
| adv-conversation-revision | `conversation-append-invalid-revision`, `conversation-append-invalid-role`, `conversation-fork-invalid-revision`, `conversation-stale-append` | stale, invalid, or conflicting conversation revision | Reject invalid revisions/roles with 422, reject stale append with 409, and preserve the source snapshot | **PASS** | A1, A2 |
| adv-conversation-fork | `conversation-fork`, `conversation-fork-independent-append`, `conversation-originals-preserved` | fork isolation and post-fork mutation | Create the fork, allow independent append, and retain source originals/history | **PASS** | A1, A2 |
| adv-privacy | `vault-redact-invalid-confirmation`, `vault-redact`, `vault-restore`, `memory-retention`, `memory-expired-absent` | invalid confirmation, redaction, restore, and retention | Require confirmation, redact only synthetic vault content, restore the returned snapshot, and remove expired synthetic memory | **PASS** | A1, A2 |
| adv-approval | `browser-approval-unknown-id`, `browser-approval-unresolved`, `browser-approval-always-forbidden`, `browser-approval-owner-mismatch`, `browser-model-self-approval` | unknown, unresolved, forbidden, owner-mismatch, or self-approval | Refuse unsafe grant/resolve/action attempts with the explicit 400/403/404/409 contracts | **PASS** | A1, A2 |
| adv-approval-replay | `browser-approval-once-grant`, `browser-approval-duplicate-grant`, `browser-approval-denied-grant`, `browser-approval-withdraw-once` | duplicate, denied, and one-time approval replay | Permit one isolated grant, reject duplicate or denied reuse, and make withdrawal idempotent | **PASS** | A1, A2 |
| adv-cli-invalid | `manual_cli_driver.py` invalid decision case | invalid CLI input | Exit 2 with the user-facing evaluation error and no traceback | **PASS** | A3 |
| adv-cli-bridge-guard | `manual_cli_driver.py` guarded bridge case | connection-plan injection/default regression | Print the explicitly selected model/base URL, Responses protocol, and guarded token environment reference; omit stale defaults and fake token material | **PASS** | A3 |
| adv-outbound-isolation | `manual_api_fixture.py`, `root_regression_driver.py` network boundary | forbidden outbound socket/model/provider access | Fail closed for server-side outbound connections while allowing the authorized loopback test socket | **PASS** | A1, A2, A4 |

## artifactRefs

| id | kind | description | path |
| --- | --- | --- | --- |
| A1 | structured receipt | Independent API observation JSON; 118 records, all `passed: true`; SHA256 `535cdff86c71dec40c5ed5f1bb5f9c0515a6d06ff4e6f3d38d7e7541f68ff66c` | `docs/qa/2026-10-04-full-live/final-qa-api.json` |
| A2 | transcript | API JSONL transcript and terminal result `RESULT 118/118; server exited; temporary token header removed`; SHA256 `b5fb826b38d2c1e1daae2ff746eaacbcdc9b3ba68f6c4b2753b7eb8446e6cf85` | `docs/qa/2026-10-04-full-live/final-qa-api.jsonl` |
| A3 | transcript | Independent CLI JSONL receipt; nine child observations all `passed: true`, terminal result `RESULT 9/9`; SHA256 `7c623a739ea255b93269751bf869582a48df1f47c74faf1af9834f675e8e946d` | `docs/qa/2026-10-04-full-live/final-qa-cli.jsonl` |
| A4 | transcript | Focused regression output for the current 12-suite driver; `283 passed, 1 warning in 11.78s`; SHA256 `9721a35c824eadf8f381cd3422057725769daadf9fe67e7e2ba589a5b761feb8` | `docs/qa/2026-10-04-full-live/final-qa-regression.log` |
| A5 | integrity record | Current manifest and hash verification: HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, manifest SHA `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`, all 68 owned entries matched | `docs/qa/2026-10-04-full-live/final-source-manifest.json` |

## Actual blockers and limits

There are no unresolved blockers for the executed QA lane. The ordinary sandbox
could not bind the required ephemeral loopback socket on the first API attempt;
the approved normal local-socket execution path resolved that prerequisite and the
same command then passed. Browser saved-localhost denial remains outside this lane,
as does live UI retry, real model loading/generation, live search, hardware audio,
startup lifespan work, OAuth/accounts, publishing, remote relay, and native
install/update/signing. Those surfaces are not counted as PASS by these receipts.
