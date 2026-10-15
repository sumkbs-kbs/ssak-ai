# Prepared launcher: current candidate soak

Status: READY_FOR_PARENT_REVIEW; SOAK_NOT_RUN. Preparation is not execution authority. FRESH3 must finish PASS before the parent invokes the launcher. The old FRESH2 candidate `7360c78544abeea41e38c65faa6eba2610a8a33b` hold remains intact. This packet targets independently reviewed candidate `58d941b340a29a8717dcfbc87348b8542fe0bd77` in frozen WT3; the publication checkout's docs-only `d8a8472e` successor does not replace that candidate.

Run exactly once from this packet with the assigned interpreter:

```sh
/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai/.venv/bin/python -I -B /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-CURRENT-CANDIDATE-SOAK-01/run-20261015T020000Z-codex/start_soak_once.py --launch
```

The helper reuses the FRESH2 sequence with FRESH3-specific guards: complete artifact manifest membership, SHA256 and byte counts; terminal result; every required check strictly true; exactly 23 unique gates and exact manifest commands, each passed with exit 0; official verifier receipt; clean frozen HEAD; current == committed == FRESH3 fingerprints; committed measurement file hashes. It invokes the official gate verifier again and captures its actual exit before the controller can run. Any rejection stops. It claims `soak/` atomically once; an existing directory prevents repetition, including after an interrupted or failed attempt. Do not remove it or blindly retry. Reconcile receipts and actual processes first.

Only essential OS identity, fixed PATH, locale, terminal, temporary directory and Python isolation settings enter the child environment, plus the listed soak configuration. Parent credentials, AGK/full-gate settings, shell startup hooks and custom Git settings are not inherited. `NX10_REPO`, `NX10_PYTHON` and all three output variables are explicit. A new UUID supplies `/tmp/ssak-imp20-soak-58d941b3-*` and both screen IDs. `SOAK_SECONDS=28800` and journal hard cap `8192` MiB are fixed.

Before invoking any controller, `soak/execution-plan.json` records launcher/report/FRESH3 manifest/result hashes, commercial gate manifest hash, four measurement hashes, candidate snapshot, gate checks, exact commands, environment and paths. `run` performs its existing default 60-second SC6 throughput probe, source attribution, disk and machine-wide process checks. No separate preflight call, skips, lowered thresholds or new scheduler are added. On successful `run`, the helper calls the existing `harvest --detach` once. The actual controller invocation exits are in `launch-receipt.json` and `harvest-launch-receipt.json`. The controller's detached harvest return zero only acknowledges its launch request; it is not the detached collector's final exit or eight-hour completion. Verify its screen/process/log evidence after launch and reconcile failures without re-running the soak.

## Later status and collection

Use `soak/execution-plan.json` as the durable source of `cwd`, the complete replacement environment, commands and unique IDs. Run `commands.status` under that environment. Read `soak-exit.txt`, `.soak-run.lock/owner`, `soak-run.log` and `soak-harvest.log` in the same output directory. No automatic launcher retries are authorized by this packet.

After the original run is complete, capture the actual `commands.collect_after_completion` exit/stdout/stderr into new collection artifacts under `soak/`; do not call it while running. Capture `commands.official_final_verify` into `final-verification.stdout.txt`, `final-verification.stderr.txt` and `final-verification.json` with command, cwd, hashes and actual exit. This command combines the original FRESH3 full gate report with this `soak-28800.json`, pinned SHA and `--min-soak-seconds 28800`.

For acceptance, independently reconcile the completed runner block (start/end HEAD58, clean source, identical expected/start/end/current fingerprints and actual exit 0), unchanged four measurement sources and gate artifacts, all six required SC scenarios, actual SC6 duration >= 28,800 seconds, completed operations, errors, throughput, RSS growth, recovery/durability metrics, collector exit 0 and final official verifier exit 0. Preserve the original artifact hashes. A screen session, `run` exit 0, requested duration, partial report or launch receipt is not an eight-hour metric. Nonzero, missing, changed, interrupted or unobserved completion remains FAIL/INCONCLUSIVE as applicable. Do not merge historical soak data.

Scope is real SQLite/journal/process storage concurrency, recovery and load, SC1–SC6. No model-quality, LLM, release/GA or activation claim follows from this preparation or its eventual scoped soak.

## Preparation acceptance

`preparation-evidence.json` records the exact preparation invocation, compile result, current source snapshot, code and measurement hashes, source-contract observations and absence of `soak/`. Validation executes no launcher, controller, tests, model, HTTP, provider or native inference requests. It establishes syntactic readiness and direct read-only source inspection only; runtime guard and eight-hour behavior remain unexecuted.

The launcher owns one guarded launch attempt. JSON values stay local to that boundary and are checked before use; no new orchestration abstraction or scheduler is introduced. No tagged variant dispatch, type suppression or broad exception handling is added. Validation intentionally follows the assignment's compile/read-only restriction.
