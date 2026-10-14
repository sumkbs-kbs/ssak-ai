# Remaining baseline failures: bounded follow-up

**17 exact selectors rerun: 14 fail, 3 pass, zero skipped.** No product/test/release-pin edits. Root8000 remained PID46399. All run roots were temporary and removed; no process bearing the soak root remains, screen inventory is empty. This report describes observed pre-fix source; the artifact-contracts owner is now changing five of the failed selectors/artifacts independently.

## Current reproducibility

| Area | Exact result | Interpretation / smallest next action |
|---|---|---|
| Profiler caller tables | PASS, exact historical selector | Historical trace captured a `time.sleep` caller edge with count0; current bounded invocation passes. Do not claim fixed without reproducing the interleaving. |
| Search crash-loop readiness | PASS, exact historical selector | Historical failure was RUNTIME_NOT_READY while state=starting, expected CIRCUIT_OPEN. Current invocation reaches circuit-open and leaves no child PID. No fix proved. |
| Finite soak lifecycle | PASS, 214.92s, exit0 | Existing selftest performs synthetic arm/start/cancel/harvest flows. Saved scheduler logs show stub start, matching expected/start fingerprint1fb93c1772797aeef7fdd244c14ddfaf9c1952441aafdb11fa3fcf11566f1d7c and runner marker. This is not an eight-hour soak certification. |
| Python SBOM | FAIL | Release artifact omits cssselect1.5.0, lxml6.1.1, orjson3.11.9, scrapling0.4.15, tld0.13.2, w3lib2.5.0 present in generated runtime closure. Artifact-contracts owner has exact evidence. |
| Dangerous shell authorization source | FAIL source-only assertion | Permission.DENY assertion succeeds. New cognitive-protection-first branch returns source=cognitive_protection; old test pins permission_gate. No shell command was executed. |
| CSS width literal | FAIL | Actual248px agrees with dashboard/DESIGN.md:64; test pins obsolete240px. All other listed CSS hooks exist. No UI defect demonstrated. |
| README API/default-port check + mutation precondition (2) | FAIL | README:62 has correct Markdown links to8000/docs and8000/openapi.json; line98 names default8000. Test regex accepts former bold-label/standalone numeric-table format only. Update parser's supported structure while retaining wrong-port negative controls. |
| README RP history (1) | FAIL | English README no longer embeds RP-01/RP-12 historical prose; it links dated status/plans at line15. Historical prose pin does not establish a runtime defect. |
| README direct verdict owner pointer (2) | FAIL | Tests demand direct CR14_FINAL_CANDIDATE_VERDICT link/name; current README links docs/20_CURRENT_STATUS instead. Missing direct pointer is real under existing documentation contract; decide/document intended ownership route, never invent a current candidate. |
| README human-axis checks (2) | FAIL | Validator requires Korean human-axis phrases even when README makes no false human-only completion claim. Baseline validator fails before mutation body. Treat as stale language/content-required contract, preserve protection against unscoped completion claims. |
| Release fence/current declared fingerprint (2) | FAIL | Declared historical candidate b6003205365606407cadfd6cbb1c813110beef0f / fingerprint02349a8d... differs from current HEAD02b9cde... / computed186d8165.... Expected release-evidence freshness gap, no gate-pin edit authorized or performed. |
| EX-05 soak status + mutation precondition (2) | FAIL | Ledger row40 says PASS (resoake Decision A), validator requires INCONCLUSIVE and current-status text preserves attribution uncertainty. This is a release-evidence semantics conflict; reconcile against original run/decision evidence, not by changing the test or pin to make it green. |

## Exact actionable selectors

- `tests/test_rel01_clean_build_sbom.py::TestLockSbomConsistency::test_committed_python_sbom_component_set_matches_the_lock`
- `tests/test_tool_contracts.py::test_registry_authorize_returns_permission_gate_denial_for_dangerous_shell_command`
- `tests/test_planning_and_rendering_quality.py::test_dashboard_chat_output_uses_codex_like_reading_style`
- `tests/test_nx07_doc_consistency.py::test_readme_guidance_matches_the_code_default_port`
- `tests/test_nx07_doc_consistency.py::test_teeth_readme_port_drift_is_detected`

These five are assigned to artifact_contracts. All17 exact selectors, elapsed times and current/historical traces are in `backend-recheck-followup-results.json`; no sample stands in for an unrun case. `backend-recheck-followup-excerpts.json` captures line-numbered source evidence for the classifications.

## Invocations, bounds and source

The quick batch invoked existing isolated_entry.py with16 exact selectors, `-vv --tb=short --junitxml`, 360s outer bound, completing in2.81s (exit1). Soak invoked its single exact selector, unchanged600s test timeout and660s outer safety bound, completing in214.92s (exit0). Commands/cwd recorded in `backend-recheck-followup-command.json` and `backend-recheck-soak-command.json`.

Both use isolated Path.home/AGK storage before imports, Python-child home propagation, PYTHON_DOTENV_DISABLED=1, PYTHONDONTWRITEBYTECODE=1 and unique TMPDIR/cwd. Quick cwd includes a dashboard symlink solely for the existing CSS source-read contract. No real user stores, real messages, installs, Git mutation, source edits or release-pin changes. The selftest's own temporary stub scheduler uses a unique path; its built-in cleanup only targets that path.

Quick batch source hashes were unchanged and HEAD02b9cde7fb0e890330ddebfec5ff8ad9ddc50435 stayed stable. Soak command records before/after hashes for existing control/gate/test sources; actual scheduled and start fingerprints match, proving the synthetic launch's source check was satisfied. Other agents may now edit these files; this is timestamped working-tree evidence, not a later clean-commit certification.

## Evidence

- `backend-recheck-followup.txt/.xml`: quick16 raw log and per-selector outcomes.
- `backend-recheck-followup-results.json`: full17-selector outcome mapping and traces.
- `backend-recheck-followup-source-before.json/-source-after.json`: hashes, HEAD, cleanup/root listener.
- `backend-recheck-soak.txt/.xml/-command.json/-cleanup.json`: single finite lifecycle result and cleanup.
- `backend-recheck-soak-snapshots/`: retained scheduler output/start record and nonempty stub marker.
- `backend-recheck-followup-manual-qa.md`: required surfaceEvidence/adversarialCases/artifactRefs matrix. PASS claims are CLI contract results, not manually-operated GUI coverage.
