# R2-05 prompt budget fix

The `qwen3.8:latest` delegate now resolves the registered `qwen3.8` profile, and the final prompt ceiling leaves completion space inside the provider window. The final guard, mandatory prompt preservation, and tool execution policy are unchanged.

## Scope and hypotheses

Production change: `src/antigravity_k/engine/context_budget.py`. New regression module: `tests/test_qwen_repo_prompt_budget.py`. Existing `tests/test_final_prompt_budget.py` is byte-for-byte identical to its captured baseline. QA files carry only repository source contracts, synthetic prompt composition, safe task metadata, counts, and hashes. No live task body, recalled memory, credentials, or raw application logs are exported.

Three hypotheses were tested: (1) mandatory system/tools/request/result actually exceed a valid model window; (2) budget uses the wrong unit or resolves the wrong model capacity; (3) old history or overselected tool documentation causes the failure. The concrete composition is above the erroneous 8,000 input fallback but below the verified provider window; old history compaction cannot solve mandatory payload exceeding that fallback. This confirms model identity/capacity resolution as the cause. Optional tool documentation reduction is unnecessary for this fix.

## Cause and capacity evidence

`ModelRegistry.get_model` resolves both profile name and repo. The budget resolver previously matched only `name`; `qwen3.8:latest` therefore had no declared capacity and fell back to 8,000 input tokens. Current configuration declares `name=qwen3.8`, `repo=qwen3.8:latest`, `context_length=262144`. `OllamaProvider._context_window` uses the shared helper, which caps the provider window at 32,768; root's passive `/api/ps` observation also reported loaded `qwen3.8:latest` context length 32,768. The implementation uses 28,672 input + 4,096 output reserve within 32,768, rather than treating declared 262,144 as the active runtime window.

Both registered identifiers now inherit empirical calibration budgets conservatively. Explicit operator ceilings and unknown-model fallback remain binding. Token counts use the existing weighted estimator (CJK 1.2 tokens/character, other text 0.25); this was not a raw-character limit bug. The shared provider helper is preserved so its `num_ctx` window is not reduced a second time.

## Original live receipt

Exact synthetic R2-05 task `direct_9300b11f775d`, created `2026-10-03T15:50:14.118864+00:00`: first compression event `15:50:24.790133` recorded system116/tools3749/skills815/messages3315, input7995 + reserve4096 = total12091. Step-1 checkpoint `15:50:51.966890` records `read_file` usage; then `context.compress.halted` at `15:50:51.987428` occurred after the file result. The original symptom is a failed final answer after a successful read. The halt event did not persist the protected ledger, and durable snapshots omit transient recalled-memory messages, so the exact full post-result token total is unavailable. Durable post-result message lengths/hashes were inspected in memory only.

## Reproduction and validation

`budget-reproduce.py` extracts real prompt composition functions and builtin schema declarations without constructing the app, store, model manager, or providers. It combines four small synthetic turns, the exact R2-05 instruction, the requested source document, original-request preservation, and the production sanitized tool-result envelope. The fixture contains repository source material and synthetic context only; it is a realistic production-seam reproduction, not an export of the full live prompt.

Baseline alias/canonical/alias toggle: `qwen3.8:latest` halts at 8,000, `qwen3.8` fits, alias halts again. Same complete serialized composition is 8,640 estimated tokens. Candidate alias/canonical/alias all fit unchanged with ledger input8,634 + reserve4,096 = total12,730. New regression tests fail against the isolated baseline (5 failed, 11 passed across the final-budget modules), then pass against the candidate. An in-memory baseline toggle after the edit reproduced the same five failures without reverting the production source.

Final safe leaf suite: **25 passed** (existing final prompt and tool-pairing tests, new alias/capacity/empirical/operator/required-payload regressions, and six pure context-budget tests). Two existing Orchestrator-construction integration cases are excluded because this worker must not initialize against the actual home. `--noconftest` and namespace-only leaf bootstrap prevent shared app/auth/config initialization. Ruff passed; basedpyright passed with 0 errors/warnings/notes via `.venv/bin/python -m basedpyright` (the console script has a stale shebang). No dependencies were installed. Source-size audit identifies an existing oversized module, baseline267 pure LOC → candidate289; unrelated module splitting is outside the approved narrow scope.

## Live retry

Root restarted the existing server and repeated the same R2-05 request. Root verified the UI returned the five correct Markdown fields. Read-only exact-question metadata query matched new task `direct_888c076b6a7f`, created `2026-10-03T16:20:56.775551+00:00`, completed `16:22:06.013818+00:00`, status `done`, target `qwen3.8:latest`. Its final durable snapshot contains one `read_file` tool call; its checkpoint also records exactly one used tool, `read_file`. No compression/halt events were recorded. Successful passes without compaction do not persist a final ledger in current observability, so no exact live ledger is claimed. Safe metadata is in `budget-live-retry-receipt.json`.

Source baseline, source diff, RED/GREEN logs, final tests, static checks, safe retry receipt, and SHA-256 manifest are stored alongside this report. This worker made no provider call, Git operation, installation, real user-data write, or tool-policy/Constitution change.
