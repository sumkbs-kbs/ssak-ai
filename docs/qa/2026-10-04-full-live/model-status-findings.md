---
title: Model runtime status validation
date: 2026-10-04
tags: [qa, models, runtime]
---

HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` (shared working tree; no Git mutation).

## Scope and hypotheses

1. Installed Ollama catalog is mistaken for running processes. Confirmed source: `_discover_ollama` obtains `/api/tags` and unconditionally assigns `running`.
2. Frontend converts an installed status into running. Refuted source: ModelHub counts the backend `status` field directly.
3. Running daemon catalog is stale or has all six models resident. Root's passive actual `/api/ps` observation reports one running Qwen model, while the actual browser displays six.

The corrected contract uses `/api/tags` for installed inventory and `/api/ps` for running status. A valid empty process list means installed; an unavailable or malformed process response means runtime status unknown. Selected chat model remains a separate state.

## Planned artifacts and isolation

- Permanent focused test and minimal source changes (owned files only).
- Permanent `model-status-red.txt`, `model-status-green.txt`, `model-status-driver.txt`, checks and source hashes.
- Temporary unique test home/cwd/config/task/data/cache paths are managed by `TemporaryDirectory`; `Path.home` is patched before every project/pytest import. `HOME` and `CODEX_HOME` are preserved.
- No daemon load/unload, user credentials, logs, private memory, model installation or training. Root owns actual browser retest after build/restart.
- Temporary toggle of only this agent's three ModelHub status edits, then restoration: needed because the first asynchronous frontend run compiled after the fix and could not supply RED evidence.
- Permanent `model_status_driver.py` uses production discovery against the actual local Ollama read-only catalogs. It scans no filesystem/cache inventory and retains only model IDs and status. Its unique temporary home/cwd is automatically removed.

## Plan

1. Source discovery and cause: complete.
2. Failing focused tests: complete (initial eight Python failures; UI one failure/one pass; malformed-identity boundary one failure/nine passes).
3. Minimal source fix and regression: complete (44 Python cases, 12 UI cases).
4. Driver evidence, checks and handoff: complete. Actual browser and final shared build/restart remain owned by root.

## Final behavior and evidence

- Ollama `/api/tags` establishes installed inventory. A separately parsed `/api/ps` snapshot establishes exact running names. Empty valid processes yield installed status; HTTP failure, missing/malformed payload or blank identity yields unknown status while preserving the installed catalog.
- ModelHub shows installed, cached and unknown states distinctly, never counting the selected model as resident merely because it is selected. Its selected label now says `선택된 모델`; readiness text describes the observed inventory/runtime fact.
- New parser is an immutable Pydantic boundary value. Existing loopback-only URL policy, two-second timeout, discovery deduplication and model-selection/load behavior remain in place.
- Initial RED: `model-status-red.txt`, eight failures showing installed models falsely running.
- UI toggle RED: `model-status-ui-red.txt`, one failure/one pass. The selected unknown model displayed cache and ready status. The initial asynchronous frontend attempt compiled after the fix and was not used as RED evidence.
- Boundary RED: `model-status-boundary-red.txt`, one failure/nine passes for whitespace-only process identity. Final parser strips and rejects empty identities.
- Final related Python regression: `model-status-green.txt`, **44 passed**, one pre-existing Starlette deprecation warning.
- Final UI regression: `model-status-ui-green.txt`, **12 passed** across existing ModelHub tests and the new status tests.
- TypeScript typecheck and scoped ESLint exited zero. Absolute-path LSP calls for both changed UI files and both backend production files found no error diagnostics. The automatic hook used a duplicated `dashboard/dashboard` path; it does not describe a source error.
- Python basedpyright reports **zero errors and eight pre-existing warnings** in the untouched Hugging Face metadata branch of `local_model_discovery.py`. Its configured warning policy makes the exit code one. New parser, tests and driver have no diagnostics; no warnings were hidden or suppressed.
- Ruff check passed. Formatting changed only the added long status expression and new driver layout.
- `model-status-driver.txt` records production discovery calling the actual local Ollama read-only endpoints: **one running** (`qwen3.8:latest`), **five installed**, **zero unknown**. No models were loaded, unloaded or selected.

## Independent review binding

`/root/model_runtime_status_fix/model_status_review` returned **APPROVE / CLEAR, no blockers**, then re-read the final parser, tests, 44-case green result and verified the current source manifest. The review is bound to the task HEAD recorded above plus exact file hashes in `model-status-source-hashes.txt`; the reviewer did not independently execute Git.

The five reviewed source/test hashes are:

- Discovery: `1023e489d4eb0460e330736c5b70f4a3ffb2af3ae4f2b500e28d9d8d259ea818`
- Process parser: `45137a8920e649b01b866fff6fa19c0fd5d57e5ebb5c05f0cda6e902872d3db8`
- ModelHub: `787705754d1d979d1d708aa9e73d4150b9251bc12a669b45a6031766f87d8417`
- Python status test: `002bfcf6c01c496a3e1a85cecb3d6dd4cf60d1ce9c11d5173f934a96bca38039`
- UI status test: `281b24108c9365b8c300f1a605daed2714c2719b4e31bb4e2f00037c3f299fc9`

## Boundaries and cleanup

The old discovery module and ModelHub page exceed 250 pure lines before this task. This focused correction does not perform a broad shared-tree refactor; the new parser, driver and focused tests each remain below that ceiling. Existing non-Ollama model servers were covered by unchanged regression fixtures, not real deployed runtime proof. The actual browser retest and responsive captures must be recorded by root after the shared final build.

All temporary test/driver homes and cwd overrides have been cleaned by their context managers. The temporary UI toggle was restored; no debugger, debug logging, daemon mutation, credential artifact or additional process remains. Reports and test/driver outputs are deliberately retained as sanitized task evidence.
