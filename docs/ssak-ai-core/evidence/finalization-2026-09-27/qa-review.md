# Independent final QA — R00–R23

**PASS for the frozen source regression scope.** Final run exited0: **1,125 passed,1 intentionally skipped,0 failures,0 errors**, with1 pre-existing warning, in1,240.45seconds(20m40s). XML contains1,126 distinct tests:1,061 cognitive tests(1,060 passed/1 skipped) and65 runtime/CLI tests(all passed). Overlapping earlier runs are not added to this count.

Final source baseline HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, with reviewed working-tree changes. Parent's final1465-file source manifest fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2`. Complete isolated snapshot: `/tmp/ssak-final-v6-D5BiCr`; despite its directory name, final contents include v7 experiment inventory, semantic plan guard, and schema race repair.

## Decisive evidence

| Evidence | Outcome |
| --- | --- |
| `qa-logs/v7-final-full.log`, `.xml`, `.exit` | Final single union run:1,125 passed/1 skipped,exit0 |
| `qa-logs/v7-final-architecture.json`, `.log`, `.exit` | All architecture/evidence checks pass,exit0 |
| `qa-logs/v7-full-pre-hashes.txt` and `v7-full-post-hashes.txt` | Byte-identical tested src/tests/scripts/docs scope |
| `qa-logs/v7-final-source-correspondence.txt` | Only the generated, git-ignored egg-info `SOURCES` packaging list differs between source and snapshot; outside tested manifest; no code/test/script differences |
| `qa-logs/v7-source-tracked.txt` and `v7-snapshot-tracked.txt` | Same legitimately registered task paths before full run |
| `qa-commands.md` | Exact invocations,env,cwd,regeneration and tracking steps |
| `qa-scenarios.md` |20 primary behaviors plus5 boundary scenarios |

Hash of source/test/script hash-list subset: `b6a9ce3a62b86f82dc04ce7d90a63b5a2d45e8e9a0df99041dd3c46729450c2a`. Hash of complete pre-run manifest: `8587997ad0e0c9b201a5a5a9c4bfd774e7faeaa36f694e0f098399e90a0b153e`.

Final command uses existing Python3.13 environment, absolute snapshot PYTHONPATH, PYTHONDONTWRITEBYTECODE=1, and UV_PROJECT_ENVIRONMENT for no-sync CLI subprocesses:

`python -m pytest tests/cognitive tests/test_cognitive_surface_api.py tests/test_cognitive_loop_events.py tests/test_cognitive_recovery.py tests/test_agent_runtime.py tests/test_runtime_benchmark_binding.py tests/test_cli_smoke.py -q -ra --tb=short --durations=10 --junitxml=<qa-logs>/v7-final-full.xml`

## Skip and warning

Exact skipped node: `tests/cognitive/test_harness_self_probes.py::test_every_harness_self_probe_passes[harness_contract]`(line158). Reason: the common harness contract itself has no consumer reading rules (`공통 계약 자신은 소비자의 판독 규칙을 갖지 않는다`). This is an intentionally inapplicable parametrization, not a failed feature or unavailable Docker coverage.

The sole warning is the existing StarletteDeprecationWarning for httpx TestClient, identical to baseline. No new warning type appeared.

## Failure found and verified repair

The prior frozen v5 full run genuinely failed:1,035 passed/1 failed/1 skipped. Two spawned processes simultaneously migrated SQLite action_claims, and one crashed with `duplicate column name: observation_digest`; the parent subsequently timed out reading its queue. This was a real schema initialization race, not an environment-only timeout. The independent58-test repair check and final whole run both pass the original failing node and the new schema regression. Prior failure logs remain `qa-logs/current-full-cognitive.*`.

Later semantic plan/context/provenance changes passed189 focused tests, and schema/action repair passed58 focused tests before legitimate affected-document re-verification. These overlap the final full run and are not additional coverage counts. Earlier651-test and100-test runs and initial baseline910passed/16failed/1skipped remain historical only. A shell bootstrap mistake caused an interrupted run(exit2); `aborted-bootstrap.*` preserves it and it is excluded from verification. Full history is `qa-history.md`.

## Evidence integrity and real surfaces

Metadata was not blindly rewritten to green. Actual current semantic/recovery tests preceded document re-verification. Only authorized digest_reverification.json,digest_drift.json,state_claims.json were copied back to production. Final digest gate:50pins,10 matching,40 reverified,0 stale,0 missing. State claims:4 fixed,0 stale. Actual collection1,061 drove the document marker. Root legitimately intent-registered new task files; snapshot registration mirrors real source. No commit or push was performed by QA.

Actual CLI execution produced expected spec/demo success and explicit live modes NOT_RUN without provider wiring. Final CLI smoke is included in the65 runtime tests. Parent's `manual-active-v7-result.json`, inspected by QA, records real localhost HTTP/process restart/ToolExecutor behavior: anonymous401,first dispatch1,restart DUPLICATE_ACTION with0 dispatches,6 canonical records/6 verified digests/4 Git commits. That fixture explicitly reports `live_brain=false`; it is not evidence of real-model inference or empirical growth.

QA production source stayed read-only except the three authorized generated evidence JSON files. Effects,secrets,and test stores were isolated; unrelated processes/vault/config were not deliberately targeted. Snapshot artifacts remain retained for review. Real local-model pilot/ablation is owned by the parent and is not claimed by this regression verdict. This is scoped automated closure, not a universal safety or generalized growth claim.
