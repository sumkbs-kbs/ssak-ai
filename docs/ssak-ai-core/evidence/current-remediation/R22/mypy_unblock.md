# Follow-up — pre-commit mypy unblock (post-R22)

Date: 2026-09-26 KST

## Problem
Local commit of R00–R23 remediation was blocked by pre-commit mypy (~22–23 errors in non-knowledge files).

## Fix (type-only / Protocol hygiene)
- `action_journal.py`: Protocol `attach_observation` stub only (body belonged on `SqliteActionJournal`); `projection_revision` coerce via `str`
- `brain.py`: annotate budget entry as `dict[str, object]`
- `context.py`: token estimate via `payload.model_dump(mode="json")` (not `to_wire(Record)`)
- `actions.py`: narrow receipt payload with `isinstance(..., ExecutionReceiptPayload)`
- `cognitive_surface_measurement.py`: module-level `import sqlite3`
- `cognitive_surface_api.py`: import `DurableSurfaceHistoryStore`; annotate `section: dict[str, object]`
- `live_pilot.py`: `_as_int` / `_as_float` / `_as_str_bool_map` for `Mapping[str, object]` ledger fields

## Verification
- `uv run --extra dev python -m mypy --ignore-missing-imports --no-strict-optional --exclude "tests/|legacy_|demo/" src/antigravity_k` → **Success: no issues found in 542 source files**
- Related pytest: growth + migration + gbrain + live_pilot → **106 passed**

## Non-claims
Does not change R22 ops NO-GO / CR-14. Architecture digest stale pins unchanged.
