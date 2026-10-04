---
title: Final conversation append compact fork validation evidence
date: 2026-10-04
tags: [qa, core, conversation, validation]
---

Completed: compact boundary diagnosis/fix, actual append/fork failure confirmation,
failing-first regressions, typed-boundary fixes, related regression, actual curl
verification, independent final review, and owned server/header cleanup.
Parent-provided HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
This report supersedes the source/review hash in `compact-validation-report.md`;
its original RED and live receipts remain historical evidence and are retained.
No Git commands or mutations were used. Existing shared edits were preserved.

## Result

The existing models already reject negative revisions, invalid roles, and
out-of-range retained tails. All three HTTP handlers manually parsed JSON and
called their Pydantic models inside handler execution, so model validation errors
reached the generic HTTP500 `internal_error` handler.

Append, compact, and fork now receive typed FastAPI body parameters. Invalid
requests reach the existing HTTP422 `validation_error` boundary before any
handler/store access. Compact's `/compact` alias uses the same handler.
Only request parsing and the now-unused `MissingExecutionContextError` import
changed. No models, constraints, store algorithm, project/session/auth binding,
Constitution, model generation, or CAS policy changed.

`model_dump(mode="json", exclude_none=True)` preserves every accepted body field
because all models forbid extras and declare the binding inputs. Header session
resolution remains unchanged. Canonical `conversation_revision` is still built
from the parsed `expected_revision`. Optional/default role, project, retained
tail, target conversation, and fork revision values keep their existing behavior.
No direct Python callers of these three handlers exist under current src/tests;
the framework routes provide the parsed model argument.

## Runtime diagnosis and failing-first evidence

`compact-validation-red.txt`: four HTTP500-vs422 failures and six valid passes.
Compact size constraints were already present; changing dispatch to typed-body
validation made the same invalid sizes return422 without touching stored bytes.

After root authorized the sibling check, actual production curl reproduced:

| Request | Input | Before fix | After fix |
| --- | --- | --- | --- |
| POST `/v1/conversations/append` | expected_revision=-1 | 500 internal_error | 422 validation_error |
| POST `/v1/conversations/append` | role=moderator, current revision4 | 500 internal_error | 422 validation_error |
| POST `/v1/conversations/fork` | expected_revision=-1 | 500 internal_error | 422 validation_error |

Both actual curl runs used project `default`, conversation
`qa-conversation-source`, and the existing isolated production fixture. All
conversation-store file hashes and the source snapshot/messages remained
identical after the three rejected requests; revision remained4.
The before-fix receipt is `conversation-validation-baseline-live.json`.

`conversation-validation-red.txt`: **3 failed, 3 passed**, exit1. The three
failures were exactly500 rather than expected422; valid append/fork cases passed.
These clean RED runs, followed by the same requests returning422, distinguish
the exception boundary from absent constraints or a broken/stale store.

## Final tests and static checks

`conversation-validation-green.txt`: **26 passed, 1 warning**, exit0. Includes
the sixteen new compact/append/fork boundary cases and the existing conversation
API and store suites. New tests use real HTTP routes and a real persisted store.
Invalid input leaves all journal/view bytes unchanged. Valid requests verify
CAS/count/retention, persisted appended roles/content, explicit fork identity,
and all copied roles/content against independent synthetic fixture inputs.
The single warning is the installed Starlette/httpx deprecation.

Before pytest/project imports, the runner enters `manual_api_fixture.isolated_home()`:
`Path.home` is patched, cwd and explicit AGK config/data/task/project/cache/auth
paths are isolated, and `HOME`/`CODEX_HOME` are preserved. It additionally sets
`AGK_CONVERSATION_STORE_DIR` to that root and `--basetemp` below that root.
Both route and binding getters use the same real temporary conversation store.
Use the command in `compact-validation-report.md`, adding
`tests/test_conversation_request_validation.py` to the listed suites.

- Ruff: exit0, `All checks passed!` (`conversation-validation-ruff.txt`).
- Basedpyright: exit0, `0 errors, 0 warnings, 0 notes`
  (`conversation-validation-types.txt`).
- LSP: no error diagnostics on the source or either new test.
- Strict no-excuse: one existing route-size violation remains,272 pure LOC
  versus reconstructed baseline284. New tests are93 and92 pure LOC with no violation. The
  narrow fix reduces the existing module rather than broadening into a route
  refactor. Evidence: `conversation-validation-no-excuse.txt`.

An initial bare sibling-test import failed collection and was corrected to the
package-relative import before the clean RED run. It is not a product failure.
Earlier compact harness isolation/precondition corrections are documented in
the retained compact report; no denied or misconfigured run is counted as green.

## Actual final HTTP/curl verification

`conversation-validation-live.json` contains nine actual curl observations
through production FastAPI middleware/routes on an ephemeral loopback server:

- Three exact invalid append/fork inputs now return422; storage is unchanged.
- Valid append with omitted role uses the default user role, returns200 and
  revision5, and persists `QA_ACCEPTED_APPEND`.
- Valid explicit fork returns200, target `qa-valid-fork`, revision0 and five
  copied turns; the original source stays at revision5.
- GET confirms the persisted source role and the fork's five messages.

The unchanged compact behavior was also driven with fifteen real curl requests
in the earlier compact candidate: invalid tails return422, tail0 yields one
summary message, and tail2 yields three view messages. It passes the final
candidate's regression suite; root's final full API protocol covers it again.

The final owned server PID29436 exited0; its synthetic0600 bearer-header file
and temporary root were removed. Baseline server PID26130 also exited0 and
cleaned its root/header. No actual user credentials, histories, model/provider
calls, training, debugger, instrumentation, or raw app logs were used.
The worker did not restart the user's actual8000 application.

## Independent final review and exact hashes

Read-only agent `compact_boundary_review`: **PASS, no findings**, bound to all
three final hashes below. It verified all three request boundaries, unchanged
binding/default/forwarding behavior, meaningful persisted-byte rejection tests,
and the strengthened persisted role/content and copied-content assertions.
It did not execute tests, import the project, use Git/network, or edit files.

```text
src/antigravity_k/api/routes/conversation_api.py
2f78dae05b39f192e37cec047e5fb88a7f08bf77b451314b04f5a5af60889a69
tests/test_conversation_compact_validation.py
2d2242c3dc54b7e5ff339715cd64e9d98008372c5b51aebd204f3df4d63ea01f
tests/test_conversation_request_validation.py
b639122c2ebc740ba58dc83d7c6c0dfd4ce2d0b4754571239a0117fd02df8758
src/antigravity_k/api/contracts/conversation.py (unchanged)
7c380ce882cc9b3c99c83f863096639a57864ea90bfc9edc697585bedf38d56c
```

Architectural review: the source retains the existing conversation HTTP surface;
untrusted input is now parsed once at the framework boundary. No new helper,
variant dispatch, log, broad catch, or type escape was introduced. Tests reuse
the existing focused real-store fixture and assert user-visible persisted data.
