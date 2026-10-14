# Runtime and registry recheck

Status: SCOPED_RUNTIME_RECHECK_PASS; independent review PENDING. Base candidate 481a634195bd3924ed601f1b881958c75e5e6892. Only config.yaml and tests/test_cli_smoke.py were edited in the candidate. ROOT source/index were not edited. No commit made.

## Changes and acceptance

- Default configuration parity: original existing byte-identity test failed. config.yaml now contains exactly the 17 disabled search.ssak/browser_task_memory lines already shipped in the package default. repaired/launch.json invokes the same parity selector and CLI selector, repaired/junit.xml reports 2 pass, receipt exit 0.
- CLI discovered-model contract: replace only local_model_discovery.safe_urlopen with in-memory metadata transport. Actual CliRunner -> model_list -> registry refresh -> discovery normalization/merge/render remains exercised. The fixture supplies llava:latest and the test requires an /api/tags request, the model output, and placement after the Vision Models heading. Existing subprocess smoke cases remain unchanged.
- User configuration priority: precedence/launch.json invokes tests/test_model_registry_config_precedence.py; precedence/junit.xml 4 pass, exit 0. Explicit path wins over environment; environment wins over default; absent/empty environment uses default.
- Child interpreter/runtime: runtime/launch.json selects CLI, project-registry atomicity, key migration, config identity, TargetResolution and local discovery cases. Original runtime/junit.xml: 40 pass, 2 fail, 0 skipped. trace records 27 Python starts, every executable is the candidate .venv/bin/python; 18 socket attempts were denied, 0 allowed. All five TargetResolution cases passed with auto-discovery enabled and provider sockets blocked; prior disabled-discovery environment would prevent mocked refresh.
- Real API: api-corrected-guard/launch.json invokes tests/test_e2e_smoke.py; JUnit 9 pass, exit 0, 3 candidate Python starts, one owned ephemeral listener, 14 allowed owned HTTP connections and 26 denied provider/external socket attempts. UVICORN_LOOP=asyncio is explicit. This verifies health, auth boundaries, headers and lifecycle of the owned server; no live provider/inference quality claim.
- Static: checks.json names exact commands and stdout/stderr files; Ruff lint, Ruff format, in-memory compile and git diff --check all exit 0.
- task-only.patch reconstructs both owned paths from preimage byte-identically; patch-reconstruction.json records true/true. Source hashes are in per-phase source-binding.json and source-binding-final.json.

## Preserved failed attempts and limitations

First runtime run retained 2 failures: missing llava installation assumption and 17-line config drift. Only these two repaired selectors were rerun. The other 40 successes are retained evidence, not a fresh all-42 pass. Four precedence cases and nine API cases are separately reported; no full-suite/GA claim.

Initial API attempt has 9 setup errors. The guard did not observe uvloop's native listen, so it denied readiness connections. First attempt raw logs/receipts remain under api/. Changing only the owned probe to select asyncio allowed Python socket-listen observation. Current proof does not establish uvloop behavior.

Initial patch replay was invoked within an enclosing Git repository and applied no owned paths; initial-result.json and initial-patch-reconstruction.json preserve false results. correct_reconstruction.py confines Git discovery with GIT_CEILING_DIRECTORIES and its new replay proves byte equality. Initial status was superseded; no ROOT patch was applied. No test rerun was needed for this artifact-only repair.

artifact-manifest.json is the original pre-closeout inventory. final-artifact-manifest.json is authoritative after corrections/handoff; it excludes private-runtime directories and itself. private-runtime contains disposable test secrets/storage and must not be published. Python-start and socket trace files contain no credential values. Existing helper-derived probes copied no caller environment credentials.

Graph discovery reported project not indexed. Parent had already timed out indexing, so exact known source paths were read directly. Parent owns unrelated candidate work; no other files were reverted or edited.
