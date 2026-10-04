---
title: Durable task single-runner claim evidence
tags: [qa, task-runner, concurrency, sqlite, paperclip]
date: 2026-10-03
---

## Outcome

Every background execution now claims the durable row from its expected start state before worktree, snapshot, orchestrator, tool, or model work begins. A pending start claims `pending -> running`; a resume claims `resuming -> running`. A runner that loses this SQLite CAS reads the authoritative state and exits without invoking the orchestrator or recording a competing outcome. Pre-start cancellation uses the same expected-state boundary, so a stale duplicate cannot cancel the active winner.

## RED

Scenario: one runner held a shared pending task inside orchestration while a second runner started the same durable task from another `BackgroundTaskRunner` instance and SQLite connection.

Invocation: `.venv/bin/pytest -q tests/test_task_runner_claim.py`

Binary observable: exit `1`; the losing runner invoked its orchestrator once (`second_orchestrator.calls == 1`) before the fix.

Artifact: `task-claim-red.log`

## GREEN

Scenario 1: the same deterministic two-runner race after the claim boundary. Observable: exactly one orchestrator invocation, one step-10 checkpoint, one successful outcome, and durable terminal status `done`.

Scenario 2: two runners concurrently resumed one paused durable task. Observable: resume results were exactly `[False, True]`, with one orchestrator invocation and one successful outcome.

Invocation: `.venv/bin/pytest -q tests/test_task_runner_claim.py`

Binary observable: exit `0`; `2 passed`.

Artifact: `task-claim-green.log`

## Related regression

The regression invocation patched `Path.home()` before pytest collection to `/tmp/ssak-task-claim-home-01a101d0`, keeping user GBrain, memory, authentication, and task databases untouched. It covered task state, resume, outcomes, process restart, cancellation ownership, and terminal CAS behavior.

Binary observable: exit `0`; `58 passed`.

Artifact: `task-claim-regression.log`

## Static verification

- Ruff: exit `0`, `All checks passed!` in `task-claim-ruff.log`.
- Ruff format check: exit `0`, both files already formatted in `task-claim-format.log`.
- Basedpyright error gate: exit `0`, `0 errors, 0 warnings, 0 notes` in `task-claim-types-errors.log`.
- The all-severity type report has `0 errors`; its existing production-file warnings and two test-only private-boundary warnings are retained in `task-claim-types.log`. It reports no `Any` annotation or argument warning for the final test.
- LSP error diagnostics: clean for both changed files in `task-claim-lsp.md`.
- `git diff --check`: exit `0`.

## Changed source

- `src/antigravity_k/engine/task_runner.py`: `5cf8c52389295e52d97888dcd4ddde38c8adcbe6f1751f1586add9276c2c79e1`
- `tests/test_task_runner_claim.py`: `4031fc7512626fd7c0c54a5071d4d9a833d8fec69f4751336c39aa1fb85a2868`

The production file was already above the local 250-line guideline before this bounded change. No unrelated split or migration was attempted.
