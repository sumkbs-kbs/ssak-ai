# Concurrent Chroma lifecycle fix

The cold UI failure is a production adapter race, reproduced without the UI or model. Eight simultaneous real `VectorStore` constructors against one new temporary directory opened only one client; seven failed with the same missing `RustBindingsAPI.bindings`, `default_tenant`, and registry `KeyError` seen in `live-final.log`.

Installed Chroma 1.5.9 publishes a shared System in `_identifier_to_system` before starting its components. A second constructor could consume this unfinished System. Separately, both application adapters called `clear_system_cache()` on every close, discarding other live clients' shared systems and reference counts. A saved original GBrain module reproduced the second defect: closing a GBrain in another directory made the live VectorStore's system lookup raise KeyError.

## Smallest common fix

- `engine/chroma_lifecycle.py` supplies one reentrant lock covering client acquisition, collection acquisition, and release in `VectorStore` and `GBrain`. Regular reads, indexing, and queries remain outside the lock.
- Removed both global registry-clear calls. Each adapter closes only its own client; Chroma's native reference counts preserve live peers and release the system after the last owner closes.
- Removed VectorStore's obsolete KeyError → deprecated settings → ephemeral-store fallback. Initialization failure now propagates to the existing caller rather than silently replacing persistence.
- Production GBrain singleton lifetime remains unchanged. `server.py` remains at its prior startup-fix hash. No user store was cleared, dropped, migrated, or indexed; the active QA server was untouched.

## Scenarios, invocations, observables, artifacts

Commands run from `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`. Original evidence is `.omo/evidence/startup-workspace/`; listed text artifacts are mirrored beside this report.

| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Original cold constructor race | `.venv/bin/python docs/qa/2026-10-04-sequential-audit/vector_lifecycle_driver.py` before source fix | Exit 1; `clients_requested=8`, `clients_opened=1`, seven failures matching cold UI exceptions | `vector-lifecycle-race-red.txt` |
| Original GBrain global invalidation | Same driver with `--baseline-gbrain`; loads preserved original `.omo/evidence/startup-workspace/gbrain-before-race.py` in an isolated process | Exit 1; eight fixed VectorStore constructors succeed, but original GBrain close invalidates their system with KeyError | `vector-lifecycle-gbrain-red.txt` |
| Final cold concurrency and persistent readback | `.venv/bin/python docs/qa/2026-10-04-sequential-audit/vector_lifecycle_driver.py` | Exit 0; 8/8 clients open; unrelated GBrain close and seven VectorStore closes preserve the remaining peer; reopened marker/count=1; all owners close; `owned_chroma_systems_remaining=0`; pool joined and temp tree removed | `vector-lifecycle-race-green.txt` |
| Focused regressions, three fresh race processes, production startup | `.venv/bin/python -m pytest tests/test_startup_workspace.py tests/test_gbrain.py::TestGBrainClose tests/test_startup_security.py -q` | Exit 0; **14 passed, no skips** on final driver/source | `vector-lifecycle-tests.txt` |
| Lint | `.venv/bin/ruff check src/antigravity_k/engine/chroma_lifecycle.py src/antigravity_k/engine/vector_store.py src/antigravity_k/engine/gbrain.py tests/test_startup_workspace.py docs/qa/2026-10-04-sequential-audit/vector_lifecycle_driver.py docs/qa/2026-10-04-sequential-audit/startup_workspace_driver.py` | Exit 0; all checks passed | `vector-lifecycle-ruff.txt` |
| Core types | `.venv/bin/basedpyright src/antigravity_k/engine/chroma_lifecycle.py src/antigravity_k/engine/vector_store.py tests/test_startup_workspace.py` | Exit 0; 0 errors, 0 warnings | `vector-lifecycle-core-types.txt` |
| New code audit | `.venv/bin/python /Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/5.1.14/skills/programming/scripts/python/check-no-excuse-rules.py src/antigravity_k/engine/chroma_lifecycle.py tests/test_startup_workspace.py docs/qa/2026-10-04-sequential-audit/vector_lifecycle_driver.py docs/qa/2026-10-04-sequential-audit/startup_workspace_driver.py` | Exit 0; no violations in four files | `vector-lifecycle-new-code-audit.txt` |

The GBrain-inclusive typecheck has 0 errors / 21 warnings and exits 1. The original GBrain source, copied to a disposable non-ignored location and checked under the same `pyproject.toml`, has the identical 21 warning messages. This is not claimed as a clean check. Raw logs and comparison: `vector-lifecycle-types.txt`, `vector-lifecycle-gbrain-types-baseline.txt`, `vector-lifecycle-types-comparison.txt`.

## Harness cleanup correction

The first strengthened cleanup check correctly failed even after all explicit test stores closed. Importing `gbrain.py` creates `global_gbrain` under the fixture's temporary home, separate from the explicit `root/brain` instance. The previous global-clear behavior had hidden that surviving owner.

Both owned drivers now verify this singleton's storage belongs to the temporary root and register its ordinary `close()` on an ExitStack. The race driver explicitly closes it before the unchanged all-owned-registry-empty assertion. No global cache clear, assertion relaxation, process kill, or production singleton change was used. This was a **harness cleanup omission**, not a reason to weaken the production fix.

Failed harness logs and pre-correction driver are retained: `vector-lifecycle-harness-cleanup-failure.txt`, `vector-lifecycle-tests-before-cleanup.txt`, `.omo/evidence/startup-workspace/vector_lifecycle_driver-cleanup-before.py`, and `vector-lifecycle-cleanup-before-hash.txt`. Root's independent failure and later green replay are separately owned by root; this report does not substitute for the upcoming cold UI restart.

## Boundaries and final identity

Actual installed Chroma, persistent databases, eight concurrent constructors, upsert, query, collection counts, peer lifetimes, reopen and close are exercised. The embedding call alone uses deterministic synthetic vectors; outbound sockets are blocked and no embedding model is downloaded. This verifies lifecycle and persistence, not semantic quality. No actual browser/API cold restart was performed by this worker; root owns that integration verification.

`vector-lifecycle-hashes.txt` records all source/driver/test SHA-256 values. Key identities:

- VectorStore: `147cea96911f438fa1c42086924988288651d5fbfa96d21d82b2361e9c194680`
- GBrain: `96a8499c55ad0c2c5ef8f70b3cf8afa1f2ca063a7f7508b6cf1a9cd29b7d1a47`
- Shared lifecycle lock: `538914ab4ace58eaa25257f6dc64771c1b4a298b50689bd2c5873738c441d562`
- Final race driver: `798a1bcd981c4bb053aa3580f3bdb8723718bc29066f76d9a8f9ea0575d1341f`
- Final startup driver: `219b1e7e0f17a47d29593e11f34043db772a251883c3f4e6756d7b1b47ac936a`
