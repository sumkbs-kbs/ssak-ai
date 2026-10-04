---
title: Functional upgrade manual QA review
date: 2026-10-03
tags: [qa, manual-qa, functional-upgrade]
---

# Verdict: FAIL — browser interaction coverage is incomplete

This is an independent QA execution against the latest dirty tree. The production
source scope is pinned to `HEAD 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` and
`source_hash c042ab34d8b264078583f13ae76adef3360bec052e281ccd20c524d5d1a87309`.
All 308 source-manifest entries match the current files. The focused dashboard run
passes 13 files and 102 tests; the supplied full-suite log reports 109 files and
1,088 tests passed; current TypeScript exits 0; and the supplied production and
fixture builds exit 0.

The fixture response-loss UI has fresh browser captures at 375/768/1280 plus a
post-retry success capture, and its state artifact shows one submit and one fork
idempotency key at attempt 2 with three created tasks.
The remaining browser interaction claims are not accepted from static screenshots or
source/tests. No browser action log was supplied for fork-loss UI, two-tab/session
isolation, double-click UI, delayed retry, late fork-source selection, tab crossover,
or clean browser restart. The static chat captures show the rendered controls at
375/768/1280, but do not prove SSE, Stop/new-send, conversation navigation, fork,
command-palette, or scroll interactions.

## Invocation catalog

`VITEST_CURRENT` (automated dashboard surface):

```sh
cd /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard
./node_modules/.bin/vitest run src/components/Chat/__tests__/ChatPageFork.test.tsx src/components/Chat/__tests__/ChatPageRunOwnership.test.tsx src/components/Chat/__tests__/ChatPageComposer.test.tsx src/components/Chat/__tests__/ChatPageHydration.test.tsx src/components/Chat/__tests__/QueuedMessagesCard.test.tsx src/hooks/useConversationFork.test.tsx src/api/client.test.ts src/stores/__tests__/chatStore.revision.test.ts src/features/task-execution/taskOperation.test.ts src/features/task-execution/taskExecutionApiFailure.test.ts src/features/task-execution/TaskQueuePanel.test.tsx src/features/task-execution/TaskExecutionView.test.tsx src/features/task-execution/useTaskExecutionEvents.test.ts
```

`TSC_CURRENT` (automated dashboard surface):

```sh
cd /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard
./node_modules/.bin/tsc -b --pretty false
```

`IAB_TASK_LOSS` (browser fixture surface): open the printed `QA_FIXTURE_URL` in
the root agent's IAB, select `response loss` for first submit, enter
`submit-loss`, click `작업 제출`, and observe the retry banner. Then click
`같은 작업 다시 시도` once, inspect `GET /__fixture/state`, and repeat the retry
control once to verify no second task.

`IAB_FORK_LOSS` (browser fixture surface): with seeded
`qa-source-ready-for-fork` selected, click `분기` while first fork response is
`response loss`; observe the fork retry banner, click `같은 작업 다시 시도`,
then inspect `GET /__fixture/state`.

`CURL_READ_STATE` (read-only fixture HTTP surface):

```sh
curl -i --max-time 5 http://127.0.0.1:50084/__fixture/state
curl -i --max-time 5 http://127.0.0.1:50084/__fixture/mode
curl -i --max-time 5 http://127.0.0.1:50084/api/tasks
curl -i --max-time 5 http://127.0.0.1:50084/api/tasks/task-source-1/events
curl -i --max-time 5 http://127.0.0.1:50084/api/tasks/task-source-1/events/stream
```

`CURL_WIRE_PRIOR` is the exact `curl -i` submit/fork sequence recorded in
`fixture/http-verification.txt`, including the first empty reply, repeated 202,
state, and event-stream requests. It is prior real fixture evidence, reviewed
read-only; this executor did not POST or change fixture counts.

## surfaceEvidence

| Scenario | Criterion reference | Surface | Exact invocation | Verdict | Result; artifactRefs |
|---|---|---|---|---|---|
| FU-S01 | task-submit | Browser IAB fixture | `IAB_TASK_LOSS` submit step | PASS | `task-loss-375/768/1280` captures show the production task panel, network-loss error, retained prompt, and named retry at all three widths; artifactRefs: A10, A14 |
| FU-S01 | task-submit | Automated dashboard | `VITEST_CURRENT` | PASS | Current hook/panel tests pass response-loss rendering path; A03 |
| FU-S02 | task-submit-idempotency | Fixture state from browser run | `IAB_TASK_LOSS` retry once, then `GET /__fixture/state` | PASS | `submit_attempts` is 2; `task-success-1280` shows the retry notice cleared and a second session row; artifactRefs: A09, A14 |
| FU-S03 | task-submit-idempotency | Fixture state from browser run | `IAB_TASK_LOSS` retry again, then `GET /__fixture/state` | PASS | `created_tasks` remains 3 and the success capture has no retry notice or duplicate submit row; artifactRefs: A09, A14 |
| FU-S04 | task-fork | Browser IAB fixture | `IAB_FORK_LOSS` fork step | FAIL | No fork-loss browser screenshot/action log was supplied; the HTTP boundary is covered by A07 and automated behavior by A03 |
| FU-S04 | task-fork | Automated dashboard | `VITEST_CURRENT` | PASS | Fork loss path is green in `useTaskExecutionEvents` tests; A03 |
| FU-S05 | task-fork-idempotency | Fixture state from browser run | `IAB_FORK_LOSS` retry once, then `GET /__fixture/state` | PASS | `fork_attempts` is 2 and the state contains one fork task; A09 |
| FU-S06 | task-fork-idempotency | Fixture HTTP | `CURL_WIRE_PRIOR` repeated fork body and state read | PASS | Prior real transcript reports `created_tasks=3`, fork attempts 2, and one `source_task_id`; A07 |
| FU-S07 | task-stream | Fixture HTTP + automated dashboard | `CURL_WIRE_PRIOR`; `VITEST_CURRENT` | PASS | Empty replay and `stream.end` are recorded; reconnection/event tests pass; A07, A03 |
| FU-S08 | task-session-isolation | Browser IAB | Open two IAB tabs at `QA_FIXTURE_URL` and compare session-scoped task views | FAIL | No two-tab screenshot or action log; missing prerequisite is a fresh two-tab browser run |
| FU-S09 | task-session-isolation | Browser IAB | Submit `submit-loss-tab-a` in tab A, inspect tab B | FAIL | No tab-A/tab-B action log or screenshots; missing prerequisite is a fresh two-tab browser run |
| FU-S10 | project-identity | Automated dashboard | `VITEST_CURRENT` | PASS | API/operation tests verify captured project/session identity and replay headers; A03 |
| FU-S11 | submit-double-click | Automated dashboard | `VITEST_CURRENT` | PASS | Pending guard and one-operation behavior pass in task event tests; A03 |
| FU-S11 | submit-double-click | Browser IAB | `IAB_TASK_LOSS` with two rapid submit clicks | FAIL | No double-click browser action log or state artifact; missing prerequisite is a fresh browser run |
| FU-S12 | submit-key-rotation | Automated dashboard | `VITEST_CURRENT` | PASS | Later submit intent receives a fresh operation key in task operation tests; A03 |
| FU-S13 | fork-key-rotation | Automated dashboard | `VITEST_CURRENT` | PASS | Fork operation creation and repeated pending behavior pass; A03 |
| FU-S14 | retry-scope | Automated dashboard | `VITEST_CURRENT` | PASS | Project-switch retry invalidation passes in task event tests; A03 |
| FU-S15 | retry-auth | Automated dashboard | `VITEST_CURRENT` | PASS | Auth-owner change invalidates retry; A03 |
| FU-S16 | fork-source | Fixture HTTP + automated dashboard | `CURL_WIRE_PRIOR`; `VITEST_CURRENT` | PASS | Transcript returns `source_task_id=task-source-1`; operation tests preserve source id; A07, A03 |
| FU-S17 | fork-replay | Fixture HTTP + automated dashboard | `CURL_WIRE_PRIOR`; `VITEST_CURRENT` | PASS | Replay has `last_sequence=0`, `has_more=false`; A07, A03 |
| FU-S18 | list-refresh | Automated dashboard | `VITEST_CURRENT` | PASS | Successful task operation refresh/select path is green; A03 |
| FU-S19 | reconnect | Automated dashboard | `VITEST_CURRENT` | PASS | Reconnect refresh and stale-list error tests pass; A03 |
| FU-S20 | error-recovery | Browser IAB fixture + automated dashboard | `IAB_TASK_LOSS`; `VITEST_CURRENT` | PASS | Loss captures show the named retry; success capture shows it cleared after recovery; panel retry tests pass; artifactRefs: A10, A14, A03 |
| FU-S21 | wire-contract | Fixture HTTP | `CURL_WIRE_PRIOR` GET `/api/tasks` | PASS | Prior `curl -i` transcript: HTTP 200, `status=ok`, seeded task; A07 |
| FU-S22 | wire-contract | Fixture HTTP | `CURL_WIRE_PRIOR` first submit POST with fresh key | PASS | Prior real transcript: intentional empty reply after commit; A07 |
| FU-S23 | wire-contract | Fixture HTTP | `CURL_WIRE_PRIOR` repeated exact submit body | PASS | Prior real transcript: HTTP 202, `status=submitted`, same task id; A07 |
| FU-S24 | wire-contract | Fixture HTTP | `CURL_WIRE_PRIOR` repeated exact fork body | PASS | Prior real transcript: HTTP 202, `status=forked`, one fork id and source id; A07 |

The current browser fixture server was offline when `CURL_READ_STATE` was run; each
read returned curl exit 7. That read-only result is recorded in A12. The prior
fixture transcript is retained as real evidence for the HTTP-shaped scenarios and
is not presented as a fresh current browser interaction.

## adversarialCases

| Scenario | Criterion reference | Adversarial class | Expected behavior | Verdict | ArtifactRefs |
|---|---|---|---|---|---|
| FU-E01 | task-submit-idempotency | delayed response after commit | A settled response-loss banner remains retryable; same key yields one task | FAIL | No delayed-response browser action log; A12 records missing live prerequisite |
| FU-E02 | task-submit-idempotency | repeated rapid retry | Pending guard permits one network retry and one task | PASS (automated); FAIL (browser) | `VITEST_CURRENT` passes guard; no rapid-click browser log; A03, A12 |
| FU-E03 | task-fork | late source selection | Captured source id remains paired with the captured fork key | FAIL | No late-selection browser action log; automated source capture is only supporting evidence; A03, A12 |
| FU-E04 | task-session-isolation | tab/session crossover | Tab B cannot replay tab A's unresolved operation | FAIL | No two-tab crossover evidence; missing prerequisite is a two-tab browser run; A12 |
| FU-E05 | wire-contract | clean fixture restart | New process has fresh seed/idempotency map and no carry-over count | PASS (fixture transcript); FAIL (browser) | Prior transcript documents process-local restart; no browser restart action log; A07, A12 |

## artifactRefs

| ID | Kind | Description | Path |
|---|---|---|---|
| A01 | source-manifest | Current HEAD/source hash and 308-file manifest | `docs/qa/2026-10-03-functional-upgrade/source-manifest.json` |
| A02 | scope | Baseline diff and changed-file scope | `docs/qa/2026-10-03-functional-upgrade/task.diff`, `changed-files.json` |
| A03 | automated-test | Fresh current-tree dashboard Vitest result, 13 files/102 tests, plus tsc exit 0 | `docs/qa/2026-10-03-functional-upgrade/review-focused-vitest.txt` |
| A04 | automated-test-log | Supplied full dashboard result, 109 files/1,088 tests passed | `docs/qa/2026-10-03-functional-upgrade/dashboard-tests.log` |
| A05 | build-log | Supplied production dashboard build exit 0 | `docs/qa/2026-10-03-functional-upgrade/dashboard-build.log` |
| A06 | build-log | Supplied standalone fixture build exit 0 | `docs/qa/2026-10-03-functional-upgrade/fixture-final-build.log` |
| A07 | fixture-http | Prior real `curl -i` fixture transcript for submit/fork loss, retry, state, and stream | `docs/qa/2026-10-03-functional-upgrade/fixture/http-verification.txt` |
| A08 | fixture-source | Fixture preparation and exact 24+5 scenario contract | `docs/qa/2026-10-03-functional-upgrade/QA_PREPARE.md` |
| A09 | fixture-state | Browser-run fixture state: requests 17, created tasks 3, submit/fork attempts 2 | `docs/qa/2026-10-03-functional-upgrade/task-browser-first-state.json` |
| A10 | browser-screenshot | Fresh 375x900 fixture UI after submit response loss with named retry | `docs/qa/2026-10-03-functional-upgrade/captures/task-loss-375.jpg` |
| A11 | browser-capture | Static chat screenshots/accessibility trees at 375/768/1280 | `docs/qa/2026-10-03-functional-upgrade/captures/after-chat-375.jpg`, `after-chat-768.jpg`, `after-chat-1280.jpg` and matching `.txt` |
| A12 | fixture-read | Fresh read-only GET attempts and explicit offline blocker | `docs/qa/2026-10-03-functional-upgrade/review-fixture-readonly.txt` |
| A13 | integrity | Fresh source-manifest hash verification, 0/308 mismatches | `docs/qa/2026-10-03-functional-upgrade/review-source-integrity.txt` |
| A14 | browser-capture | Fixture loss and post-retry task UI at 375/768/1280, with accessibility trees and button-state JSON | `docs/qa/2026-10-03-functional-upgrade/captures/task-loss-375/768/1280.*`, `task-success-1280.*` |

The manual QA verdict remains FAIL until the missing browser action logs/screenshots
cover the required interaction boundaries. This report intentionally does not infer
browser behavior from passing unit tests, static screenshots, source inspection, or
the prior fixture transcript.
