# Core live-question boundary review — final 33-file candidate

## Review target and integrity

- HEAD verified as `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- This report is bound to manifest candidate SHA-256 `ef6eb98fb17f3588caf40438d226951c8df2bfdbb8aad9a3ae0057e95b534082`.
- I independently recomputed every SHA-256 in the 33-file `source-manifest.json`; all matched the frozen working tree.
- `code-review-32files.md` and `code-review-pre-tdd.md` preserve the prior reviews. This pass covers only the final accepted-revision/cancellation, request-preservation, and narrow-screen message boundary changes. It does not claim the separate live Q08 model-routing/output residual is fixed, or audit the existing MAX selector prompt truncation.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Boundary assessment

For revision-aware streams, the accepted user snapshot is now emitted before advancing the runtime (`src/antigravity_k/api/routes/chat.py:1235`); the equivalent TDD path does the same (`chat.py:1061`). This lets the client own revision 1 even when the body iterator is closed before generation starts. The request's original user turn was already atomically appended by the authoritative-context path, and cleanup leaves no active stale stream. The real HTTP regression closes after that initial frame, verifies the exact persisted turn, then submits the next turn at the accepted revision and receives revision 3 (`tests/test_chat_stream_output_boundary.py:189`). ChatPage guards every snapshot callback with the current run identity (`dashboard/src/components/Chat/ChatPage.tsx:795`), so this early frame cannot mutate a later session or project.

`_preserve_execution_request` makes the original user instruction authoritative when a refinement or RAG material is added, preserving structured message fields and retaining retry feedback (`src/antigravity_k/engine/orchestrator_execution_handlers.py:54`). Both agent and MAX paths use it, including MAX canonical and fallback execution. The tests cover misleading refinement, explicit QA delegation, retries, MAX task specs, canonical runtime selection, and fallback/error paths (`tests/test_execution_request_preservation.py:107`). The helper only composes request text from established state; it does not affect authorization, access mode, tool policy, or identity binding.

The message wrapping rule is narrowly scoped to user text (`dashboard/src/styles/workspace-chat.css:31`) and limits width without changing assistant markdown or tool output behavior. The supplied 375px evidence records the prior 412px horizontal overflow and the corrected 332px scroll/content width.

## Evidence reviewed

- `core-retry-green.log`: 17 frontend tests passed; `core-retry-chat-suite.log`: 139 frontend tests passed.
- `request-preservation-red.log`: 8 demonstrated pre-fix failures; `request-preservation-green.log`: 11 passed.
- `final-python-regression.log`: 332 passed, 2 skipped.
- `final-frontend-regression.log`: 182 passed; TypeScript check and production Vite build passed.
- `git diff --check` was clean.

## Skill-perspective check

The previously loaded `omo:programming` and `omo:remove-ai-slops` skills were applied again to this final delta. This check ran. The tests assert protocol ordering, cancellation continuity, rendered behavior, and original-instruction preservation; they are not deletion-only, tautological, prompt-prose, or implementation-constant tests. The helper is a small boundary composition rather than a new abstraction layer, and it adds no parsing, untyped escape hatch, or authorization bypass. This diff violates neither skill perspective.

## Decision

`codeQualityStatus`: **CLEAR**  
`recommendation`: **APPROVE**  
`blockers`: None.
