# CI repair verification

Published baseline: `0b1aca2d990e08235c784c94f94585ec0c688ac5`. These observations describe the scoped repair; remote results will be recorded separately.

## Workflow causes and checks

- Dashboard verifier originally returned `BUNDLE-STATUS: INFRA_ERROR — uv 가 필요합니다`. The dashboard job now installs uv. Running the real wheel verifier in a clean source export passed: 106 source/packaged files, fingerprints `b0defc2bbbdb2070`, zero missing/extra/content mismatches. This checks the exported committed bundle; the new remote dashboard job must check its freshly rebuilt bundle.
- Container job failed before checkout because `aquasecurity/trivy-action@0.28.0` does not exist. The official tags API lists `v0.28.0` at `915b19bbe73b92a6cf82a1bc12b087c9a19a5fe2`; the workflow now pins that SHA. Scanning still rejects HIGH/CRITICAL findings.
- E2E readiness failed with exit 7 on its first curl. Executing the exact extracted loop under `bash -e -o pipefail` with a first connection failure then HTTP 200 produced old exit 7 and repaired exit 0. Continuous connection failure produces exit 1 after the bounded deadline. The loop also rejects an exited server process.
- Gitleaks checkout and unsupported Bandit SARIF reporting were corrected without changing secret/vulnerability detection thresholds. Security findings that were previously unreachable are recorded in SECURITY.md; the job is not claimed green.
- Executing the repaired Bandit JSON command in the Python 3.12 export returned exit 1 and produced valid JSON with 33 findings (32 MEDIUM, one HIGH). The report is now available while the hard gate still rejects its findings.
- Workflow YAML and bash syntax checks passed for 56 CI run steps and seven benchmark run steps. The YAML language server is absent by an existing user preference; no installation was attempted.
- Existing release/bootstrap contracts: 19 tests passed in 10.93 seconds.
- Independent final review approved the bounded patch after 69 focused tests passed. Its benchmark test-discovery correction was adopted; this approval excludes existing security findings and full benchmark acceptance.
- The new symbol extraction performance regression is included in both benchmark invocations, and extractor/test changes trigger that PR workflow. The benchmark workflow has no main push trigger; a main push alone does not validate its 500ms criterion.

## Current surface reverification

The root export `/tmp/ssak-ci-snapshot.IvGI3A` was produced with `git archive HEAD`, then given an actual shallow Git reference/index to the published commit. `uv sync --locked --no-editable --extra dev --python 3.12` installed the project in its own environment. No private raw evidence was copied.

Under `PYTHON_DOTENV_DISABLED=1`, the existing isolated launcher patches the home and state paths before project imports. Python 3.12.13 ran:

```sh
.venv/bin/python -B docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/cognitive/test_surface.py tests/test_cognitive_surface_api.py tests/cognitive/test_feature_off_regression.py tests/test_cli_smoke.py tests/test_decision_evaluation_surfaces.py tests/test_decision_diagnostic_surfaces.py -q
```

Observed: **104 passed**, 12 warnings, 48.10 seconds. The warnings are Starlette's httpx deprecation and existing duplicate OpenAPI operation IDs.

The same Python 3.12 export also passed strict `mypy src/` across 573 source files and the existing financial/growth suite: **40 passed** in 11.18 seconds. The performance lane's separate focused checks and its remaining strict threshold failure are recorded in BENCHMARK.md.

Personally executed production CLI commands through that launcher:

- `cognitive status --json`: exit 0, `enabled=false`, `mode=off`, `source=legacy`, dispatched actions 0.
- `cognitive surface`: exit 0, static import reach legacy 7/9 and core 5/9. Static reach is not runtime activation; historical 2026-09-22 counts were not rewritten.
- `cognitive --help`: exit 0, both status/surface commands discoverable.
- `cognitive unsupported-command`: exit 2 with a concrete invalid-command error.

A separate isolated server on port 18151 returned HTTP 200 for `/health` and authenticated `/api/cognitive/surface/status`. The cognitive status preserved OFF/legacy and `actual_active=false`; the test token was local and synthetic, and is not included in this document.

Initial archive-only test run had one failure because Git source_head was absent; after adding the real Git context the same test passed. This was a reproduction setup issue, not a product source fix. An attempted test command used two nonexistent decision test filenames and collected no tests; the corrected actual surface test filenames are recorded above.

Only the changed CLI/router and growth pins are renewed, with their measured bytes and scoped methods. Historical raw logs remain local, and this repair does not certify live model quality or all product features.

The public export's final fast evidence gate passed **9 stages**, with zero failed or unrun stages. Two local-only layers, release artifacts and the full regression ledger, were outside this tier and are not counted as passes. The digest inventory contains 50 pins: 8 matching original bytes and 42 with scoped reverification, with zero drift, stale records, or missing files. No baseline, floor, security severity, or latency threshold was reduced.

## Local environment recovery

One root sync command was accidentally launched in the shared checkout instead of the export and temporarily rebuilt its environment as Python 3.12/dev-only. It was restored to Python 3.13.12 with all locked extras and editable project installation. MLX, mlx_lm, and pydantic imports passed; the existing application at port 8000 remained healthy with qwen3.8 loaded. Subsequent CI reproduction uses the separate export environment. No user PIN or application configuration was changed.
