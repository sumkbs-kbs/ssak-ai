# Core live-question boundary review — TDD access and hydration follow-up

## Review target and integrity

- HEAD verified as `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- This report is bound to manifest candidate SHA-256 `66084760af1fe96c98cceaab19adb5dd8184863140ccb2b9919c4e4ffc8ceaf3`.
- I independently recomputed every SHA-256 in the 32-file `source-manifest.json`; all matched the frozen working tree.
- The preceding 30-file review is preserved as `code-review-pre-tdd.md`. This pass covers only the new TDD access/revision and canonical-history hydration boundaries; it does not claim a complete audit of read-only profile learning or other unrelated dirty changes.

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

`chat.py` snapshots `AccessMode` before intent classification at `src/antigravity_k/api/routes/chat.py:662`, then clears TDD mode before the TDD branch whenever the request is read-only or carries an explicit false `code_mode` (`chat.py:762`). This covers both explicit mode and automatic keyword/classifier selection without constructing `OmniTDDEngine`; the ordinary runtime receives the request-local tool policy, including `safe_only` from that same snapshot (`chat.py:1202`).

For an allowed revision-aware TDD request, `tdd_event_generator` emits typed status/final channels (`chat.py:1046`), appends the terminal assistant turn through the shared CAS helper, emits the resulting conversation revision, then emits `[DONE]` (`chat.py:1086`). A stale CAS result is sent as the typed conflict channel and does not overwrite the concurrent answer (`chat.py:1105`). The regression tests exercise code-off values `false`, `0`, and `"false"`; explicit and automatic paths; read-only with omitted/enabled code; both TDD report outcomes; next-turn revision continuity; and concurrent CAS conflict (`tests/test_chat_tdd_boundary.py:127`).

The history hydration projection now uses the server-provided message IDs and, only for pre-hydration local records, a session-and-index fallback key (`dashboard/src/components/Chat/ChatPage.tsx:1410`). This distinguishes two equal-content assistant answers until canonical IDs arrive. The delayed-project-hydration test verifies exact ordered canonical history, both duplicate answers rendered, and preservation of an unsent composer draft (`dashboard/src/components/Chat/__tests__/ChatPageHistoryHydration.test.tsx:64`).

## Evidence reviewed

- `tdd-boundary-red.log`: 12 demonstrated pre-fix failures, covering forbidden engine entry and missing assistant persistence.
- `tdd-boundary-green.log`: 15 passed.
- `history-hydration-green.log`: 19 frontend files / 182 tests passed.
- Existing final regression evidence remains 262 Python passed, 2 skipped; frontend 181 passed for the prior 30-file candidate.
- `git diff --check` was clean.

## Skill-perspective check

The earlier loaded `omo:programming` (including Python and TypeScript references) and `omo:remove-ai-slops` perspectives were applied again to this follow-up before assessing tests and maintainability. This check ran. The new tests assert externally observable access, persistence, conflict, and rendering outcomes; they are neither deletion-only nor implementation-constant mirrors. The minimal request-local snapshot and React key fallback add no untyped escape hatch, needless parsing, or unnecessary abstraction. The reviewed change violates neither skill perspective.

## Decision

`codeQualityStatus`: **CLEAR**  
`recommendation`: **APPROVE**  
`blockers`: None.
