# R16 report — status bound to durable execution history

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R16-V not claimed.

## Before

`GET /api/cognitive/surface/status` and `cognitive status` built a fresh empty `CognitiveSurfaceAdapter`, so after a real ACTIVE execute the status showed no last_episode and dispatch 0. Static import reach could be confused with runtime ACTIVE evidence.

## After

- `DurableSurfaceHistoryStore` (SQLite) records episode_id / termination / dispatch counts on `_remember`.
- Fresh adapters with the same store project durable last episode and totals.
- Status payload separates configured mode, `actual_active` (activation-backed only), and `history_source`; notes state that static import reach is not runtime evidence.
- Status reads do not mutate projection revision (side effect 0). Other project_ids do not see foreign history.

## Acceptance

| ID | Result |
|----|--------|
| R16-A1 | PASS — after ACTIVE execute, status shows same episode_id and dispatch 1 |
| R16-A2 | PASS — new store handle (process replacement) keeps history |
| R16-A3 | PASS — reaches_core does not set actual_active |
| R16-A4 | PASS — other project hidden; status read does not bump revision |
| R16-E | PASS — this evidence tree |
| R16-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_surface.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/cognitive/test_active_api.py -q -p no:cacheprovider -k r16
```

## Limits

- Self-review ≠ release GO / CR-14.
- Default history path is `<project_root>/.ssak/surface_history.sqlite` when configured.

## Regression note (duplicate execute)

`test_authenticated_actual_tool_and_durable_duplicate` previously required unchanged `committed_manifests()` after DUPLICATE_ACTION. R11 experience flush may append operational records on the refused episode. Asserts updated to: refusal=DUPLICATE_ACTION, dispatched_actions=0, external file effect unchanged. Suites: test_surface + test_active_api → 36 passed (2026-09-26 evening close).
