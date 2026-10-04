# Conversation view residual closure — 2026-10-03

Scope: preserve the existing F2 implementation and user changes, close deferred-view safety defects. No staging, commits, production activation or vault mutation.

## Baseline and investigation

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; this report binds to working-file hashes below, not HEAD alone.
- Graph discovery succeeded for `ConversationStore`; a later query lost the project index, so a fast nonpersistent reindex was completed.
- Existing `tests/test_view_freshness_contract.py`: **5 failed, 6 passed**, reproduced with `uv run --no-sync pytest -q tests/test_view_freshness_contract.py` before this worker's patch.
- Hypotheses tested: stale cached flush bypasses process serialization; dirty-work removal before persist loses retry; get-or-create skips the public-read convergence contract. Existing failures and inspected paths confirmed all three.
- The finite-window failure also exposed a test assumption: a deferred first view need not exist yet. The original journal has the committed event; the view is only a derived cache.

## Changes

- `flush_views()` takes the existing process and thread locks, checks storage readiness, and refreshes each pending identity against its current journal before flushing.
- Refresh recognizes durable deletion markers and committed delete tails, invalidating local pending/cached state instead of resurrecting a deleted view.
- A missing view can reuse the same writer's journal-current cache; it does not require journal replay on every deferred turn.
- Deferred work is removed only after successful persistence, including explicit flush, public-read flush and bounded-window flush.
- `get_or_create()` converges deferred views like other public reads.
- Existing untracked test helper `_view_sequence()` now counts an absent derived view as sequence zero. No assertions were deleted or relaxed: bounded lag, final convergence, deletion safety, peer-turn retention and failure retry remain required. This matches the historical F2 fixture, which uses `(_view_seq(store) or 0)` for absent views.
- Added two regression tests for failed public-read and full-window persistence followed by explicit retry. Formatted only the owned test file.

## Verification

| Surface | Result | Artifact |
| --- | --- | --- |
| New residual contracts | 13 passed, 0.35s | `view-worker-contracts.txt` |
| Related conversation/API/identity/multiprocess tests, including residual contracts | 68 passed, 1 warning, 9.80s | `view-worker-related.txt` |
| Historical F2 ten contracts | 10 passed, 0.26s | `view-worker-f2.txt` |
| Real library driver | Peer append survives stale-writer flush; peer deletion leaves no view and read returns None | `view_worker_driver.py`, `view-worker-manual.txt` |
| Ruff, three owned Python files | All checks passed | Command below |
| Basedpyright, three owned Python files | 0 errors, 0 warnings, 0 notes | Command below |

Related command:

```sh
uv run --no-sync pytest -q tests/test_view_freshness_contract.py tests/test_conversation_store_ctx01.py tests/test_val02_conversation_multiprocess.py tests/test_fr05_conversation_authoritative_reads.py tests/test_cr01_conversation_identity.py tests/test_conversation_api_ctx01.py
uv run --no-sync pytest -q docs/qa/2026-09-16-followup/nx10/fsync2/test_view_freshness_contract.py
uv run --no-sync python docs/qa/2026-10-03-residual-close/view_worker_driver.py
uv run --no-sync ruff check src/antigravity_k/engine/conversation_store.py tests/test_view_freshness_contract.py docs/qa/2026-10-03-residual-close/view_worker_driver.py
uv run --no-sync basedpyright --level error src/antigravity_k/engine/conversation_store.py tests/test_view_freshness_contract.py docs/qa/2026-10-03-residual-close/view_worker_driver.py
```

An initial combined command used `--import-mode=importlib` to avoid the two same-named contract modules. This broke macOS spawn imports (`ModuleNotFoundError: No module named 'tests'`), leading to a queue timeout. It was interrupted after **1 failed, 22 passed**, exit 2, and preserved as `view-worker-tests.txt`. The corrected independent invocations above passed; the interrupted attempt is not counted as product validation. The one remaining warning is the existing Starlette/httpx deprecation.

## Source correspondence

| File | SHA-256 |
| --- | --- |
| `src/antigravity_k/engine/conversation_store.py` | `7763f0a1cd80a751da13dcefae5f228c21d6a4e999448e17373beca59f310fbf` |
| `tests/test_view_freshness_contract.py` | `fb538d46279988b62e8e5a65551bd96a9a6860cb2f8c1fb6f340b542c0c5e80a` |
| `docs/qa/2026-10-03-residual-close/view_worker_driver.py` | `3a5283252e54583791c516a84588b6acdba74c617d54f7e15407d2ec7e097116` |

Manual stores were created with `TemporaryDirectory` and removed. No instrumentation remains in production code; no listeners were started. Existing user journal and unrelated changes were preserved. This is bounded conversation-store validation, not a full repository test or live rollout claim.
