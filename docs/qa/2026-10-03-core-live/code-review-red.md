# Core live-question boundary review

## Review target

- HEAD verified as `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Candidate is the manifest-declared SHA-256 `c05bf23382a422f16a8ffda73d2a0680851eaddc8a85e1e0fd7fc0d6fe90e952`.
- All 28 manifest file hashes matched the working tree at review time. The candidate is a SHA-256 content identifier, not a Git object; `git cat-file` therefore cannot resolve it.
- Scope is limited to the live-QA boundary files in `source-manifest.json`, excluding the repository's unrelated dirty changes.

## Finding

### HIGH — reconnect can replay only a corrected final while the stream is still active

`chat.py` appends draft chunks to `active_session.history` for reconnect replay, but on a `FinalChunk` replaces that history with a one-element final (`active_session.history[:] = [full_response]` at [chat.py:1224](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:1224)). The reconnect endpoint immediately replays `active_session.history` while `is_active` remains true ([chat.py:453](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:453)). If finalization occurs before the underlying stream has actually closed, a reconnect loses the already-emitted draft prefix and then waits for later chunks that no longer reconstruct that response.

The present regression at [test_chat_stream_output_boundary.py:124](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/tests/test_chat_stream_output_boundary.py:124) only reconnects after the request completes, when `is_active` is false, so it cannot expose this active-stream loss. Preserve the authoritative final separately for persistence/future turn context, or ensure replay history remains complete while the stream is active; add an active reconnect test with draft, final, and a later stream phase.

## Confirmed boundaries

- Fast-search is disabled for the revision protocol and explicit `web_search: false` before the early fast-search return ([chat.py:756](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:756)).
- `ProgressChunk` and `FinalChunk` survive normalizing and direct-task tracking, while final content overrides drafts and the shared-output side channel.
- The event-mode `ContextVar` is set before copying the stream context and reset in `finally`.
- The UI validates status/final SSE channels, guards every callback with run ownership, replaces draft content on a final event, and preserves a copied rejected retry turn across a 409.
- Quality rewrites receive copied, immutable conversation entries. Approval stops the tool loop before postchecks; execution handlers set `COMPLETE`, and final memory sync is skipped. `MemoryRecorder` and `MemoryManager.sync_all` independently prevent writes under the read-only request policy.

## Evidence reviewed

- `docs/qa/2026-10-03-core-live/final-python-regression.log`: 252 passed, 2 skipped.
- `docs/qa/2026-10-03-core-live/core-stream-channels-green.log`: 181 frontend tests passed.
- `docs/qa/2026-10-03-core-live/dashboard-build.log`: production build passed.
- Focused regression logs for search boundary, quality context, direct streams, approval sync, and read-only sync.
- The logs are consistent with the covered tests, but do not cover the active reconnect timing described above.

## Skill-perspective check

Loaded and applied `omo:programming` (Python and TypeScript references) and `omo:remove-ai-slops` before evaluating tests and maintainability. This check ran. Within the reviewed boundary diff, I found no deletion-only tests, prompt-prose tests, tautological assertions, implementation-constant mirrors, needless production parsing/normalization, untyped escape hatches, or unnecessary abstractions. The diff does not violate either skill perspective.

## Decision

`codeQualityStatus`: **BLOCK**  
`recommendation`: **REQUEST_CHANGES**

`blockers`:

1. Fix the active reconnect history loss described above and add a behavioral regression that holds the stream active through the replay.
