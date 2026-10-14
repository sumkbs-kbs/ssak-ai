# Artifact and test contract repair

Date: 2026-10-04. Owner: artifact_contracts. Cwd: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.

## Result and scope

Five directly reproduced failing selectors are repaired. The final relevant run passes **67 tests**, exit 0. No product behavior, styles, auth, release verdict, release candidate, historical digest, or GO pin was edited. No commit or push was made.

The existing SBOM CLI generated `python.cdx.json` and its matching `THIRD_PARTY_NOTICES.txt`: exactly six added lock dependencies (cssselect 1.5.0, lxml 6.1.1, orjson 3.11.9, scrapling 0.4.15, tld 0.13.2, w3lib 2.5.0). Total Python components: 67; dashboard components: 241. Dashboard SBOM bytes are unchanged. Component metadata comes from the existing generator and current environment, not manually assembled data. This is not a new package build or publication certification.

The three test repairs are grounded in current producer evidence:

- README line 62 has linked literal `127.0.0.1:8000/docs` and `/openapi.json` endpoints; line 98 has the combined HOST/PORT row. Parsing no longer requires obsolete bold labels or a separate numeric table cell. All discovered document ports must match the server default. Mutations now use 9999 to avoid passing merely through the separate legacy-8400 prohibition, and assert that each mutation actually changed the input.
- DESIGN.md line 64 owns sidebar width 248px; CSS line 103 matches it. The assertion compares to that documented token and requires CSS consumption of the width variable.
- `PermissionGate.decide` evaluates cognitive protection before the general shell gate. `rm -rf /` returns DENY, `cognitive_protection`, and PATH_ESCAPE. The test preserves all three checks. The command is authorized as data only; it is never executed.

## Criteria, scenarios, observables and artifacts

All relative artifact paths below are under `.omo/evidence/artifact-contracts/`.

| Criterion | Exact scenario / invocation | Binary observable | Artifact |
|---|---|---|---|
| Reproduce drift | Red command below, five selectors | exit 1, exactly 5 failed with the reported mismatch | `red.txt`, `red.xml`, `red.exit` |
| Generate authentic SBOM | `uv run --no-sync python -m antigravity_k.engine.release_sbom generate --project-root . --release-root src/antigravity_k/release` | exit 0, status generated, 67 Python / 241 dashboard components | `generate.txt`, `generate.exit`, `final.patch` |
| SBOM matches lock | `test_rel01_clean_build_sbom.py::TestLockSbomConsistency::test_committed_python_sbom_component_set_matches_the_lock` in green command | passed; exact name/version set equals generated runtime closure, licenses present | `green.xml`, `green.txt` |
| README matches code | `test_nx07_doc_consistency.py::test_readme_guidance_matches_the_code_default_port` | passed | `green.xml` |
| README parser retains rejection | `test_nx07_doc_consistency.py::test_teeth_readme_port_drift_is_detected` | six changed inputs rejected: serve 9999, Swagger 9999, OpenAPI 9999, environment default 9999, removed docs URLs, removed port row | `green.xml`, `final.patch` |
| CSS follows design contract | `test_planning_and_rendering_quality.py::test_dashboard_chat_output_uses_codex_like_reading_style` | passed with documented width and CSS variable consumption | `green.xml` |
| CSS assertion has teeth | `PYTHONPATH=. .venv/bin/python .omo/evidence/artifact-contracts/assertion_probe.py` | width drift, missing token, disconnected consumption all trigger AssertionError | `mutations.txt`, `mutations.exit`, `assertion_probe.py` |
| Dangerous command remains denied with exact provenance | `test_tool_contracts.py::test_registry_authorize_returns_cognitive_protection_denial_for_dangerous_shell_command` | passed, DENY + cognitive_protection + PATH_ESCAPE | `green.xml` |
| Denial assertions have teeth | same assertion_probe command | ALLOW, wrong source, missing reason code all trigger AssertionError | `mutations.txt`, `mutations.exit` |
| Relevant regression suites | green command below | exit 0, 67 passed, no skipped tests | `green.txt`, `green.xml`, `green.exit` |
| Scoped lint and formatting | Ruff commands below | both exit 0 | `lint.txt`, `lint.exit`, `format.txt`, `format.exit` |
| Typing adds no diagnostics | basedpyright and normalized comparison below | 0 errors; same 20 pre-existing warnings; normalized comparison exit 0 | `types-before.json`, `types.json`, `type-warnings-before.json`, `type-warnings-after.json`, `type-comparison.exit` |

## Exact commands

Red:

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_rel01_clean_build_sbom.py::TestLockSbomConsistency::test_committed_python_sbom_component_set_matches_the_lock tests/test_nx07_doc_consistency.py::test_readme_guidance_matches_the_code_default_port tests/test_nx07_doc_consistency.py::test_teeth_readme_port_drift_is_detected tests/test_planning_and_rendering_quality.py::test_dashboard_chat_output_uses_codex_like_reading_style tests/test_tool_contracts.py::test_registry_authorize_returns_permission_gate_denial_for_dangerous_shell_command -q --tb=short --junitxml=.omo/evidence/artifact-contracts/red.xml
```

Green:

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_rel01_clean_build_sbom.py tests/test_release_sbom.py tests/test_nx07_doc_consistency.py::test_readme_guidance_matches_the_code_default_port tests/test_nx07_doc_consistency.py::test_teeth_readme_port_drift_is_detected tests/test_planning_and_rendering_quality.py tests/test_tool_contracts.py tests/cognitive/test_protection.py tests/cognitive/test_protection_boundaries.py -q --tb=short --junitxml=.omo/evidence/artifact-contracts/green.xml
.venv/bin/ruff check tests/test_nx07_doc_consistency.py tests/test_planning_and_rendering_quality.py tests/test_tool_contracts.py
.venv/bin/ruff format --check tests/test_nx07_doc_consistency.py tests/test_planning_and_rendering_quality.py tests/test_tool_contracts.py
.venv/bin/basedpyright tests/test_nx07_doc_consistency.py tests/test_planning_and_rendering_quality.py tests/test_tool_contracts.py --outputjson
```

The existing isolated_entry wrapper redirects home-derived app/auth/storage paths to a temporary directory. Tests needing project-relative CSS paths run from this repository. The mutation probe changes read results and returned decisions in memory and uses a temporary project directory, never product files. Source discovery first attempted the requested graph project; it returned `project not found or not indexed`, so bounded source reads were used. `omo-agent-toolkit ulw-loop status --json` reported ULW_LOOP_PLAN_MISSING; evidence is therefore under `.omo/evidence/` with a copy of this report at the parent-requested docs location.

## Source correspondence and limitations

`before.sha256` and `after.sha256` capture the three test files, generated release files, uv.lock, README, DESIGN, CSS, permission gate and generator inputs. `final.patch` captures exactly this lane's five changed tracked files. Before snapshots in `before/` were taken from HEAD after confirming these test files had no pre-existing diff. Other agents' files were preserved.

Ruff passes. Default basedpyright exits 1 for its **unchanged 20 warning diagnostics**, with zero errors before and after; this is not represented as a warning-free typecheck. Warning identity comparison drops line positions and retains file, severity, message and rule. The evidence-only probe is excluded by the repository typecheck configuration (`filesAnalyzed: 0`), so `probe-types.json` is not claimed as validation; its real execution and Ruff pass are the evidence.

The programming skill checker reports the same 15 legacy findings before and after: 14 existing object annotations and one oversized NX-07 module (301 to 305 pure LOC). Logs: `skill-audit-before.txt`, `skill-audit.txt`; LOC: `loc.txt`. These are explicitly unresolved style findings. Broad refactoring is outside the narrow assignment; no new object annotations or escape hatches were added.

Architectural self-review: each changed assertion keeps its existing responsibility (README guidance consistency, rendering contract, tool authorization); no product trust boundary, tagged variant logic, error handling, logging, destructive operation, parameter list, or new production helper was introduced. Regression-sensitive assertions are exercised by the real focused suite plus forced in-memory failures. The pre-existing module-size issue remains documented rather than silently claimed fixed.

Historical release/candidate/fingerprint/GO and unrelated README status/soak assertions remain untouched and are **not claimed passing**. Their failures from `backend-recheck-followup.xml` remain parent audit work; this lane does not refresh evidence to make old release pins appear current. No full-suite or GUI validation is claimed by this report.
