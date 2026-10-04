# Functional-upgrade QA preparation

This fixture is ready for a manual browser run of task submit/fork response-loss recovery. It uses the production `TaskExecutionPanel`, `TaskExecutionView`, `useTaskExecutionEvents`, `taskExecutionApi`, `taskOperation`, and task schemas from `dashboard/src/features/task-execution`. The approval queue is replaced only at the fixture boundary because its unrelated diff viewer imports Monaco worker query modules that a standalone bundle cannot resolve; the task execution path itself is production code.

The fake API is a real loopback HTTP server. It commits the task before deliberately closing the first submit or fork response, then returns the committed task for a repeated idempotency key. It serves the current contracts:

- `GET /api/tasks` -> `{status: "ok", data: TaskSummary[]}`.
- `POST /api/tasks/submit` -> `202 {status: "submitted", task_id}`.
- `POST /api/tasks/{task_id}/fork` -> `202 {status: "forked", task_id, source_task_id}`.
- `GET /api/tasks/{task_id}/events` and `/events/stream` -> empty replay plus `stream.end`.
- approval reads/writes return empty, valid responses so the production panel can mount.
- `GET /__fixture/state` exposes request counts and per-key attempt counts for evidence.
- `GET /__fixture/mode` and `POST /__fixture/mode` expose fixture-only first-response modes: `loss`, `503`, or `422` for submit/fork. The browser controls use this endpoint; operation/retry logic stays in the production task components.

## Run and cleanup

From the repository root, run:

```sh
bash docs/qa/2026-10-03-functional-upgrade/fixture/build.sh
env UV_CACHE_DIR=/tmp/ssak-qa-fixture-uv uv run docs/qa/2026-10-03-functional-upgrade/fixture/qa-fixture-server.py
```

The server prints `QA_FIXTURE_URL=http://127.0.0.1:<ephemeral-port>`. The root agent should open that printed URL in its unlocked IAB and use browser screenshots/action logs for the UI evidence. The fixture does not operate the user browser and does not require production credentials. The default port is ephemeral; do not assume the example port in `http-verification.txt` will be reused. To clean up, stop the server with Ctrl-C, then remove the generated `fixture/dist/` directory and the `fixture/node_modules` symlink if the working tree should contain source-only fixture files. No task or vault store is written.

## Primary manual scenarios

Run each scenario with a fresh fixture process unless the scenario explicitly says to continue. Exact surface and invocation are included so the eventual QA matrix can point to screenshots and the state endpoint without inferring behavior.

| ID | Criterion reference | Surface and exact invocation | Expected observation |
| --- | --- | --- | --- |
| FU-S01 | task-submit | Browser IAB at `QA_FIXTURE_URL`; click `작업 제출` after entering `submit-loss` | First response-loss leaves the production panel with the retry banner and no duplicate row yet. |
| FU-S02 | task-submit-idempotency | Same IAB; click `같은 작업 다시 시도` once | The row appears once; `/__fixture/state` reports one submit task and the original key at attempts `2`. |
| FU-S03 | task-submit-idempotency | Same IAB; click `같은 작업 다시 시도` again after recovery | No second task is created; the retry action is no longer offered. |
| FU-S04 | task-fork | Same IAB; click `분기` on seeded `qa-source-ready-for-fork` row | First fork response-loss shows the fork retry banner and does not show a duplicate fork row. |
| FU-S05 | task-fork-idempotency | Same IAB; click `같은 작업 다시 시도` once for the fork | One fork row appears; state reports one fork task and the original key at attempts `2`. |
| FU-S06 | task-fork-idempotency | Same IAB; inspect `/__fixture/state` with `curl -i` | `created_tasks` is `3` after submit plus fork, with no extra task from either retry. |
| FU-S07 | task-stream | Select the seeded row; observe connection badge and event panel | `GET /events` and `stream.end` are consumed; no malformed event error appears. |
| FU-S08 | task-session-isolation | Open two IAB tabs at the printed fixture URL | Each tab has a separate generated session header; each task operation is scoped to its tab. |
| FU-S09 | task-session-isolation | Submit `submit-loss-tab-a` in tab A, then inspect tab B | Tab B does not receive a second locally-created row until its own list refresh. |
| FU-S10 | project-identity | In browser devtools-free UI run; use server log and state endpoint only | The operation carries the fixture project identity headers; no token or cookie is required. |
| FU-S11 | submit-double-click | Enter `double-click-submit`; click submit twice quickly | The production pending guard permits one in-flight operation; the state endpoint shows one key/operation. |
| FU-S12 | submit-key-rotation | Complete one submit, then submit a different prompt | New user intent obtains a new key and creates a new task; the prior key remains unchanged. |
| FU-S13 | fork-key-rotation | Complete one fork, then fork the same source again | New fork intent uses a new key and creates exactly one additional fork. |
| FU-S14 | retry-scope | Trigger response loss, then switch project/session before retry | The stale operation is rejected and its old key is not replayed. This requires the parent app's project switch surface. |
| FU-S15 | retry-auth | Trigger response loss, invalidate the auth context, then retry | Auth/HTTP failure is not presented as a safe ambiguous retry. This requires the parent app's auth surface. |
| FU-S16 | fork-source | Click `분기` on seeded source | The request path contains `task-source-1`; response contains matching `source_task_id`. |
| FU-S17 | fork-replay | Select `task-fork-2` after recovery | Empty event replay keeps `last_sequence=0` and stable selected-task state. |
| FU-S18 | list-refresh | After either retry, watch the task count | The production operation success triggers list refresh and selects the returned task. |
| FU-S19 | reconnect | Keep a selected row while refreshing the page | Initial list and event replay converge without a duplicate task row. |
| FU-S20 | error-recovery | Trigger first loss, leave the banner visible, then use its retry button | The banner is actionable and clears after a successful same-key response. |
| FU-S21 | wire-contract | `curl -i GET /api/tasks` against `QA_FIXTURE_URL` | Response is `200` with `status=ok` and fields accepted by `TaskListResponseSchema`. |
| FU-S22 | wire-contract | `curl -i POST /api/tasks/submit` with a fresh key | First request closes before headers; this is the controlled loss boundary, not a server 5xx. |
| FU-S23 | wire-contract | Repeat the exact submit curl body | Response is `202` with `status=submitted` and the same task id as the committed first attempt. |
| FU-S24 | wire-contract | Repeat the exact fork curl body | Response is `202` with `status=forked`, one fork id, and the original source id. |

## Five edge augmentations

These augment the core narratives and should be run when the parent product surface is available. They are explicitly separate because the fixture proves the wire loss/idempotency boundary; the parent agent must capture any browser verdict.

1. `FU-E01` delayed response after commit: hold the retry click until the banner settles; expected result is still one task for the original key.
2. `FU-E02` repeated retry: press the retry control twice rapidly; expected result is one network retry and one task, with no second operation from the pending guard.
3. `FU-E03` fork source selected late: select a different row while the fork response is lost; expected result is the captured source id and key remain paired.
4. `FU-E04` tab/session boundary: trigger a loss in tab A and click retry in tab B; expected result is a scope rejection rather than replaying A's operation.
5. `FU-E05` clean restart: stop and restart the fixture with a new process; expected result is a fresh seeded source and no carry-over idempotency map, proving the fake state is process-local.

## Artifacts

- `fixture/build.sh`: deterministic Vite build entry.
- `fixture/index.html`: standalone fixture shell and operator cue.
- `fixture/main.tsx`: mounts the production `TaskExecutionPanel`.
- `fixture/qa-fixture-server.py`: ephemeral loopback API/static server with controlled response loss and genuine idempotency maps.
- `fixture/vite.config.ts`: fixture-only build configuration.
- `fixture/ApprovalQueueStub.tsx` and `fixture/ApprovalQueueHookStub.ts`: fixture boundary stubs for unrelated approval UI/API imports.
- `fixture/http-verification.txt`: non-empty build and `curl -i` transcript from the real fixture process.

The fixture imports production `index.css` first and `codex-workspace.css` second, matching `dashboard/src/main.tsx`. The rebuilt CSS emitted no external font URLs or `@font-face` assets; all font references resolve through the production CSS variables and system font stack. The parent agent should add browser screenshots/action logs and the final `manualQa` matrix under the caller's attempt directory. This preparation document records no product verdict.

## Fixture-only controls

The top control strip is explicitly labeled `Fixture-only QA controls`. It imports the production `index.css` and `codex-workspace.css` and mounts the production `TaskExecutionPanel` below it. The controls call the existing `useProjectStore.applyActiveProject` for project A/B and revision changes. `First row` and `Second row` activate the production task queue buttons so selection remains owned by `useTaskExecutionEvents`. The response mode selectors change only the fake server's first submit/fork response: `response loss` closes before headers, `retryable 503` returns HTTP 503, and `confirmed 422` returns HTTP 422.
