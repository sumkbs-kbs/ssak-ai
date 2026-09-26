# R16 Evidence — status ↔ durable execution history

## Date
2026-09-26 20:36 KST

## Verdict
PASS (self-review)

## Problem
Status API/CLI built a fresh empty adapter → last_episode / dispatch counts 0 after ACTIVE; static reach confused with runtime ACTIVE.

## Fix summary
- DurableSurfaceHistoryStore (SQLite surface_runs / surface_project_meta)
- CognitiveSurfaceAdapter.history_store; status() prefers durable totals
- API/CLI wire default history at <project_root>/.ssak/surface_history.sqlite
- Active fixtures share history; notes: history_source, actual_active, static-reach disclaimer
- Duplicate-execute test: asserts DUPLICATE_ACTION + no re-dispatch + file unchanged (experience trail may append)

## Tests
- test_r16_a1–a4 in test_surface.py
- test_surface.py + test_active_api.py: 36 passed

## Limits
- Self-review PASS ≠ release GO / CR-14
- Experience flush on DUPLICATE may still append operational records (R11); effect contract preserved
