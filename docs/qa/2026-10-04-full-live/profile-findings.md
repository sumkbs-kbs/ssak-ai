---
title: READ_ONLY user profile persistence evidence
tags: [qa, read-only, user-profile]
date: 2026-10-04
---

# READ_ONLY user profile persistence

Scope: `src/antigravity_k/engine/user_model.py` and focused regression test only.

## Artifact ledger (recorded before creation)

- Temporary `ssak-profile-repro-*` directory under `/private/tmp`, including isolated project/profile JSON and graph-only GBrain snapshots/locks: automatically removed by `TemporaryDirectory` teardown. Historical driver runs redirected child HOME; final reruns preserve inherited HOME/CODEX_HOME and patch `Path.home()` before project imports.
- Temporary `ssak-profile-policy-*` directory in the OS temporary directory for each subprocess regression scenario: automatically removed by `TemporaryDirectory` teardown. The final test uses the platform default, preserves inherited HOME/CODEX_HOME, and patches `Path.home()` to the temporary CWD before project imports.
- Temporary `ssak-profile-regression-*` directory under `/private/tmp` for the existing preference-precedence tests, including isolated CWD/project store and pytest basetemp: automatically removed by `TemporaryDirectory` teardown. Final reruns preserve inherited HOME/CODEX_HOME and patch `Path.home()` before project imports.
- Retained `tests/test_user_model_request_policy.py`: focused subprocess regression test.
- Retained this report: concise RED/GREEN, source fingerprints and validation evidence; no private data or raw logs.
- Bytecode disabled and pytest cache provider disabled. No model, daemon, server, network, auth or Constitution operations.

The root agent owns the shared task journal. Artifacts and hypotheses were sent to the root before runtime or file creation.

## Hypotheses and distinguishing observations

1. `_save_profile()` ignores active READ_ONLY policy. Distinguishing observation: observation five writes both profile and graph while `request_allows_side_effects()` is false. **Confirmed.**
2. GBrain already blocks READ_ONLY writes downstream. Distinguishing observation: graph file/node/reward tick remain absent/zero despite profile file creation. **Refuted:** graph snapshot and `user_profile_main` node appeared, reward tick became one.
3. The request policy context is lost before `observe()`. Distinguishing observation: shared predicate is true at observation five despite READ_ONLY setup. **Refuted:** predicate remained false.

Synthetic pristine roots also distinguish delayed persistence from an import-time existing profile: after observations one through four there was no profile file or graph snapshot; observation five created both.

## Isolation and runtime evidence

Historical baseline repro and initial RED/GREEN tests redirected child HOME to a temporary directory. That harness setup was corrected after review: final tests and driver reruns preserve inherited HOME/CODEX_HOME and patch `pathlib.Path.home()` to the isolated temporary CWD before every project import. GBrain uses `Path.home()` at `gbrain.py:209`; a bounded source audit of `user_model`, `gbrain`, `tool_policy`, `preference_memory`, `memory_contracts`, `secret_scanner`, `secret_scanner_patterns` and `base_tool` found no `expanduser`, HOME/CODEX_HOME or environment-based home consumers. The final setup also asserts GBrain's store equals the temporary CWD's `.antigravity/gbrain` before any observations.

Package shells point at repository leaf source and bypass `engine/__init__.py` model imports. Real ToolPolicy is bound before importing `user_model`. Real `UserIntentModeler` and graph-only GBrain execute; optional ChromaDB is unavailable in the child to prevent embedding/model/network calls. GBrain import-time store directories are initialization baseline, not counted as profile observation writes. Test claims cover JSON and GraphML persistence, not the optional vector projection or the full HTTP stack.

Baseline runtime before source edit:

| Observation | Policy permits effects | Profile JSON | Graph snapshot | Profile node | Reward tick | In-memory English count |
| --- | --- | --- | --- | --- | --- | --- |
| First four | false | absent | absent | absent | 0 | 4 |
| Fifth READ_ONLY | false | created | created | present | 1 | 5 |

The existing shared predicate is `tool_policy.request_allows_side_effects()`, which permits absent policy and `safe_only=False`. `memory_provider` and `memory_recorder` already use it for durable memory writes. Guarding the beginning of `_save_profile()` preserves observation-driven in-memory learning while preventing directory creation, `updated_at` mutation, GBrain synchronization and JSON overwrite under READ_ONLY.

## Validation

RED command before source edit:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest --noconftest -p no:cacheprovider -q tests/test_user_model_request_policy.py
```

Observed result: **3 failed, 2 passed in 1.21s**. The first failure ended with `AssertionError: READ_ONLY created profile JSON`; direct `_save_profile()` failed the absent-directory check; the existing-profile scenario failed the unchanged-bytes check. Explicit permitted policy and absent policy both passed, including real GraphML reload.

Production fix: import the existing `request_allows_side_effects` predicate and return at the beginning of `_save_profile()` when false. The production diff is one import plus a two-line early return. No caller, policy, frontend, auth or Constitution changes.

GREEN with the same focused command: **5 passed in 1.31s**. The test covers the first-four/fifth observation cadence, explicit permitted and absent policies, direct-save denial, byte-preservation of existing JSON and GraphML, continued in-memory explicit preference learning, and count 15 saved at the next permitted interval.

Final test portability correction uses the platform's default temporary directory. Revalidation: **5 passed in 1.01s**; lint/format and module-based type checks remained clean. No production source changed during this correction.

Final HOME-preservation correction replaces child HOME redirection with an early `unittest.mock.patch.object(Path, "home", return_value=Path.cwd())`. Final revalidation: **5 passed in 1.27s**, **2 existing preference tests passed in 0.19s**, lint and format passed, and type checks reported **0 errors, 0 warnings, 0 notes**. Manual driver and existing-regression driver asserted inherited HOME/CODEX_HOME values remained unchanged and GBrain's store resolved under the isolated CWD. Production source remained unchanged.

Final manual re-run of the synthetic fifth-observation driver after the guard, with inherited HOME/CODEX_HOME and an early `Path.home()` patch:

```json
{"before_fifth": {"graph_exists": false, "profile_exists": false, "reward_tick": 0}, "read_only_fifth": {"graph_exists": false, "in_memory_count": 5, "node_exists": false, "policy_allows_writes": false, "profile_exists": false, "reward_tick": 0}}
```

Existing preference-precedence regression: an isolated Python driver bound permitted ToolPolicy before leaf imports, then ran `pytest.main(["--noconftest", "-p", "no:cacheprovider", "-q", absolute_test_path, "--basetemp", isolated_pytest_path])` against `tests/test_user_profile_preference_precedence.py`. Historical result: **2 passed in 0.17s** with redirected child HOME. Final revalidation: **2 passed in 0.19s**, using temporary CWD, patched `Path.home()`, inherited HOME/CODEX_HOME, package shells, blocked optional ChromaDB and automatic cleanup. Full app/HTTP/model and full repository suite were intentionally outside this agent's isolated boundary scope.

```sh
.venv/bin/ruff check --no-cache src/antigravity_k/engine/user_model.py tests/test_user_model_request_policy.py
.venv/bin/ruff format --check --no-cache src/antigravity_k/engine/user_model.py tests/test_user_model_request_policy.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m basedpyright --level error src/antigravity_k/engine/user_model.py tests/test_user_model_request_policy.py
```

Results: **All checks passed; 2 files already formatted; 0 errors, 0 warnings, 0 notes**. The `.venv/bin/basedpyright` entry script initially failed because its shebang names an old checkout; invoking the same installed module through the repository interpreter resolved this without modifying the environment.

Post-write review: profile persistence remains the source module's single responsibility. New code adds one Boolean guard, no API/type/variant changes, no escape hatches, logging, error catches or abstractions. Regression tests fail without the guard. Approximate nonblank/non-comment counts: source **207**, test **141**; source is within the skill's warning band, so future growth should consider splitting before approaching 250. Existing unrelated source style is preserved.

Independent static policy/source/test review: **PASS**, no material defect or false-green gap. No private data, logs or full app execution involved.

## Source fingerprints and cleanup

SHA-256:

| Artifact | Hash |
| --- | --- |
| Baseline `src/antigravity_k/engine/user_model.py` | `d10f724d25ce102a37a6471b702726716dac741b6b5bb9a4d8c2a1b54b1fb9bc` |
| Fixed `src/antigravity_k/engine/user_model.py` | `ecfb1629dc4ad9e586c2c32ba7c1b2ada60c12960b824d1488ee74e6a43110ee` |
| `tests/test_user_model_request_policy.py` | `6f4ab1cdd55f1a568545c9ef5e881b4097144ff2ab2167b8f5a48ed821b6157a` |

All manually created transient artifacts used automatic TemporaryDirectory teardown. No retained debug edits, bytecode, pytest/lint caches, background processes, ports, shell environment changes or Git mutations. Read-only `git diff` confirmed only the three-line production guard in the touched source; new test and this report are retained task artifacts. Other agents' working tree changes are preserved.
