# R15 ENTRY_MATRIX — effect ownership by entry

Generated 2026-09-26 KST from code + `measure_surface_reach`. Self-review; not independent R15-V.

Legend:
- **Owner** = who may produce an external effect for that entry
- **ACTIVE HTTP** = `/api/cognitive/surface/active/*` via `CognitiveActiveService` only
- Static `reaches_core` ≠ actual ACTIVE (see notes on status `actual_active=`)

| Entry | Static reach (legacy/core) | Effect owner | ACTIVE? | Notes |
|---|---|---|---|---|
| CLI (`agk run` / interactive) | yes / yes | legacy ToolExecutor via AgentRuntime | No | Bootstrap `_attach_cognitive_surface` only installs SHADOW observe |
| API server boot | yes / yes | legacy | No | Same attach path; ACTIVE service not installed by default |
| API chat | yes / yes | legacy | No | |
| API agent SSE | yes / yes | legacy + optional SHADOW observe | No | `observe_interaction` runs shadow only |
| EngineContext / cognitive_loop | yes / no | legacy loop | No | |
| tool_loop hook | yes / no | legacy | No | |
| background/durable task | no / no (static) | legacy TaskStore + SHADOW observe wrapper | No | Static graph misses dynamic wiring; code path never calls `run_active` |
| agent runtime | no / yes | attach point for SHADOW | No | ACTIVE only via explicit `run_active` after `activate` |
| CLI `agk cognitive status/surface` | n/a | none (read-only) | No | No episode / no store write |
| HTTP `/api/cognitive/surface` status/reach/stream | n/a | none (read-only) | No | |
| HTTP `/api/cognitive/surface/active/*` | n/a | **CognitiveActiveService** → `run_active` | Yes (opt-in) | Requires app.state install; body cannot inject authority/project_root; unconfigured → 503 |

## Invariants checked in `test_r15_composition.py`

- Unconfigured ACTIVE → 503
- Body inject fields → 422 (`extra: forbid`)
- Boot attach skips `mode=active`
- `observe_interaction` ignores ACTIVE adapters
- Default / `enabled=false` → OFF
- Entry labels present in `measure_surface_reach`
- ACTIVE activate requires freshness_resolver (with other deps)

## Non-claims

- Independent R15-V not claimed
- Ops / CR-14 still NO-GO
- Production must still wire store-backed freshness_resolver when enabling ACTIVE service
