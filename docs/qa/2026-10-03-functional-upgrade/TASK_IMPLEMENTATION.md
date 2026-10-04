---
title: Task idempotent retry implementation evidence
date: 2026-10-03
tags: [qa, task-execution, idempotency, dashboard]
---

# Task submit and fork retry

## Scope

- `taskOperation.ts` captures one submit or fork intent: a fresh random key, exact prompt or source task, project/session identity, and an in-memory owner fingerprint plus authorization header.
- `taskExecutionApi.ts` sends that captured body and headers. It does not read current project identity while replaying an operation.
- `useTaskExecutionEvents.ts` blocks repeated pending actions synchronously, checks scope again after asynchronous capture, retains only ambiguous network outcomes for explicit retry, and selects the server-returned task after a successful retry.
- `TaskQueuePanel.tsx` keeps submit text after a failed request and exposes a native `같은 작업 다시 시도` control. A confirmed submit clears only the exact submitted input generation; an edit made during a failed request is retained even if its text later matches. Fork completion never clears the submit input. Submit, fork, cancel, and resume controls are disabled during submit/fork ownership.
- The operation fingerprint and captured authorization header stay only in in-memory React operation state; they are not rendered, logged, or persisted.

## Red evidence

Before implementation, the new hook scenarios did not type-check because `TaskExecutionState` had no `failedTaskOperation` or `retryTaskOperation`; `submitTask` accepted only a prompt and `forkTask` only a task id. The initial LSP result named those missing properties in `useTaskExecutionEvents.test.ts`.

## Green evidence

Invocation:

```sh
cd dashboard
./node_modules/.bin/vitest run \
  src/features/task-execution/taskOperation.test.ts \
  src/features/task-execution/taskExecutionApiFailure.test.ts \
  src/features/task-execution/TaskQueuePanel.test.tsx \
  src/features/task-execution/TaskExecutionView.test.tsx \
  src/features/task-execution/useTaskExecutionEvents.test.ts
./node_modules/.bin/tsc -b --pretty false
```

Binary result: Vitest exited `0` with `5` files and `27` tests passing; TypeScript exited `0`.

The focused tests verify these user-visible and wire-level scenarios:

1. A submit POST whose response is lost is explicitly retried with the same operation object/key, then selects the one server task.
2. A fork response loss reuses the original source task and key.
3. A later user intent receives a fresh key; repeated pending clicks cause one request.
4. A project switch after failure discards the retry target, and a switch during scope capture sends no POST.
5. Owner credential changes invalidate retry; the API preserves the captured project/session/authorization headers and idempotency body rather than substituting live identity.
6. The retry notice is a named native control. The form clears after a confirmed initial submit or retry only when its exact input generation is still current; newer edits remain, including an edit back to identical text. Fork success does not clear the form.
7. Scope is compared again after the asynchronous owner fingerprint completes, so either a project switch or authenticated-owner change during that boundary prevents a POST; HTTP `5xx` outcomes retain the operation for safe idempotent retry while `4xx` outcomes do not.

`git diff --check` on all listed task-execution files exited `0`.

## Files

- `dashboard/src/features/task-execution/taskOperation.ts`
- `dashboard/src/features/task-execution/taskExecutionApi.ts`
- `dashboard/src/features/task-execution/useTaskExecutionEvents.ts`
- `dashboard/src/features/task-execution/TaskQueuePanel.tsx`
- `dashboard/src/features/task-execution/TaskExecutionView.tsx`
- `dashboard/src/features/task-execution/TaskExecutionPanel.tsx`
- focused tests beside those modules

## Manual surface handoff

The root integration owner must perform the live browser scenario against the running dashboard: submit a harmless task, force or simulate the response-loss boundary, activate `같은 작업 다시 시도`, and verify one task row is selected. This worker does not own the shared authenticated browser surface.
