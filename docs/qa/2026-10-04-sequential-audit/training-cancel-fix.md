# Training cancellation verification

Scope: `tests/test_trn02_timeout_resource.py` only. Production controller/supervisor unchanged. No model training, downloads, installs, commits, pushes, user-store access, or use of the root agent's live port 8000. No active ulw attempt exists; canonical captures are under `.omo/evidence/training-cancel/` and copied alongside this report.

## Findings

1. `TestTrainingJobsApi::test_cancel_sets_termination_cancelled` waited for `iter 1` from `python -c 'import time; time.sleep(30)'`, which never emits that line. Its 400 × 50ms polling attempts also include HTTP overhead. If elapsed time exceeds child lifetime, cancellation correctly returns `ok:false` for an already-completed job. Original selectors passed alone (25.76s); a controlled one-second silent child reproduces the exact `assert False is True` failure. The repair makes the finite child emit readiness, waits on an event, asserts the child is alive before cancellation, waits for the training worker's completion event, then reads settled terminal state. No arbitrary settlement delay remains in this selector.
2. Historical 698ms heartbeat gap **was not reproduced**. Original event-loop selector passes in isolation; production cancellation already uses a synchronous FastAPI route. No evidence proves the historical gap was caused by cancellation rather than host/full-suite scheduling. The old test used a fake process, an artificial one-second termination sleep, and did not assert cancellation acceptance. The replacement uses a real child whose SIGTERM handler acknowledges the signal and waits for a release on stdin. While termination is blocked, the loop must complete a concurrent job GET and preserve the 400ms heartbeat bound; only then is the child released. A negative control that dispatches the blocking handler on the event loop fails: child reaches SIGKILL before the concurrent read can prove responsiveness. This strengthens causal coverage without claiming a historical production fix.
3. Existing idempotent-process test now uses `text=True`, matching `terminate_process_group(Popen[str])` and eliminating two existing type errors. No runtime cancellation behavior is altered.

## Scenarios, invocations, observables, artifacts

All commands run from repository root with the existing environment.

| Scenario | Invocation | Binary observable | Artifact |
|---|---|---|---|
| Original two reported failures isolated | `uv run --no-sync pytest tests/test_trn02_timeout_resource.py::TestTrainingJobsApi::test_cancel_sets_termination_cancelled tests/test_trn02_timeout_resource.py::TestCancelDoesNotStallTheEventLoop::test_cancel_keeps_the_loop_responsive -vv --tb=short` | 2 passed, exit 0 | `training-cancel-isolated-before.txt` |
| Original readiness race, finite one-second child | `uv run --no-sync python .omo/evidence/training-cancel/finite_child_repro.py` against archived pre-edit source | 1 failed, `ok:false`, exit 1 | `training-cancel-readiness-red.txt`, `training-cancel-test-before.txt`, `training-cancel-finite_child_repro.py` |
| Repaired readiness, same one-second child lifetime | `uv run --no-sync python .omo/evidence/training-cancel/finite_child_green.py` | 1 passed, child return -15 and worker finished, exit 0 | `training-cancel-readiness-green.txt`, `training-cancel-finite_child_green.py` |
| Deliberately blocking event-loop negative control | `uv run --no-sync python .omo/evidence/training-cancel/blocking_mutation.py` | 1 failed, real child killed before responsive-loop assertion, exit 1 | `training-cancel-blocking-mutation-red.txt`, `training-cancel-blocking_mutation.py` |
| Full focused regressions | `uv run --no-sync pytest tests/test_trn02_timeout_resource.py tests/test_training_jobs_api.py -vv -s --tb=short` | 29 passed in 12.05s, exit 0; includes printed actual PIDs/return codes/heartbeat gap | `training-cancel-full-green.txt` |
| Real loopback HTTP cancellation | `uv run --no-sync python .omo/evidence/training-cancel/live_driver.py` | Actual production router on private ephemeral Uvicorn listener: accepted cancel; GET while child alive/termination waiting in 4.07ms; child return 0; duplicate cancel rejected; exit 0 | `training-cancel-live-driver.txt`, `training-cancel-live_driver.py` |
| Lint and format | `uv run --no-sync ruff check tests/test_trn02_timeout_resource.py`; `uv run --no-sync ruff format --check tests/test_trn02_timeout_resource.py` | both exit 0 | `training-cancel-static.txt` |
| Type errors gate | `uv run --no-sync basedpyright --level error tests/test_trn02_timeout_resource.py` | 0 errors, exit 0 | `training-cancel-types-errors-only.txt` |
| Resource cleanup | PID existence checks from success receipts plus TCP connection check after private-server stop | All owned captured PIDs absent; ephemeral listener closed | `training-cancel-cleanup.txt` |
| Exact inspected sources | SHA256 of edited test and unchanged route/supervisor | hashes recorded | `training-cancel-hashes.txt` |

Limitations: default basedpyright reports 95 warnings and exits 1 (`training-cancel-types.txt`); only the error-level gate is clean. Existing Starlette/httpx deprecation warning persists. No full backend rerun or model/GPU resource release claim is made. The real network driver serves the production training router in an isolated FastAPI app, while the revised regression uses the full application ASGI stack. Historical 698ms cause remains undetermined; the replacement proves termination/loop ordering directly. Existing unrelated changes and other tests' legacy sleeps were preserved.
