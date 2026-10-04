---
title: Job Operations zero completed runs display
tags: [qa, dashboard, job-operations, boundary]
date: 2026-10-04
---

# Job Operations zero completed runs display

The success-rate summary previously showed `100%` when the server returned its nominal `success_rate: 1` with `completed_runs: 0`. That empty denominator does not establish a measured success rate.

`JobOperationsPage.tsx` now projects the displayed rate to `null` for the zero-completed-run window. The summary renders `—` with `No completed runs`. An unhealthy scheduler with no completed runs also renders `No completed runs` in the policy alert. The scheduler badge still uses the server's `healthy` boolean. Nonempty windows retain the server's rounded percentage, including a measured `0%`.

The change uses the existing summary tile, alert, and design tokens. No CSS, API contract, job data, scheduler state, or provider execution changed.

## Automated verification

- Red: local Vitest before the production change had **2 failures / 5 passes**. Both new zero-window cases failed because the rendered summary still showed `100%` and lacked the unmeasured marker.
- Green: `node node_modules/vitest/vitest.mjs run src/features/job-operations/JobOperationsPage.test.tsx` passed **7 / 7**. Coverage includes zero completed runs for healthy and unhealthy schedulers, measured `0%`, `75%`, and `100%`, plus existing retry and initial-error behavior.
- `node node_modules/typescript/bin/tsc --noEmit --pretty false -p tsconfig.json`: exit **0**.
- `node node_modules/eslint/bin/eslint.js src/features/job-operations/JobOperationsPage.tsx src/features/job-operations/JobOperationsPage.test.tsx`: exit **0**.
- Independent read-only boundary review: **no blockers**. It confirmed the zero denominator differs from measured `0%`, both rate locations share the same projection, the badge remains controlled by `health.healthy`, and retry handling does not depend on the rate display.

The first `pnpm exec` invocation triggered pnpm's implicit dependency status/install path and aborted before removing modules because no TTY was available; its registry check also failed under restricted networking. All successful checks used the already installed local Node tools directly, with no dependency installation.

## Discovery and scope

Read the root `AGENTS.md`, Programming TypeScript reference, Frontend design/perfection guidance, and `dashboard/DESIGN.md`. No nested dashboard/docs `AGENTS.md` was found.

Graph-first discovery: one `index_repository(mode="fast", persistence=false)` reported indexed; `search_graph` returned the exact page symbol and feature path. The next `get_code_snippet` returned `symbol not found`, and a narrowed feature search returned zero matches. Discovery therefore fell back to bounded reads of `dashboard/src/features/job-operations/` and config/design files.

Owned source paths:

- `dashboard/src/features/job-operations/JobOperationsPage.tsx`
- `dashboard/src/features/job-operations/JobOperationsPage.test.tsx`

Source is frozen. Root's fresh live-fixture observation of `/history` → 예약작업 after this change is the remaining rendered-surface evidence; this report does not substitute component tests for real browser QA.
