# Core live-question boundary review — final 37-file candidate

## Review target and integrity

- HEAD verified as `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- This report is bound to manifest candidate SHA-256 `ed99b68b98aa1173936fbfcfd54fcd5b3babfd7eb0533fed37f077a67b858578`.
- I independently recomputed all 37 manifest file hashes; each matched the frozen working tree. The focused new hashes match the manifest: `context_budget_enforcer.py` `8e248e25…555586`, `tool_loop.py` `ba8b9eee…a6c7`, and the three strengthened/new budget test files.
- `omo ulw-loop status --json` reported `ULW_LOOP_PLAN_MISSING`, so the requested QA-directory report path is used. Earlier 32- and 33-file reports remain preserved separately.
- This is a read-only, source/test/log review of the documented live-question boundaries. It does not claim that unrelated live model routing, Markdown, semantic-quality, or MAX-selector residuals are resolved.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Budget-boundary assessment

`fit_final_prompt` treats the complete system text, selected tool schema, latest non-receipt user instruction, all system messages, and an adjacent tool-call/receipt pair as protected (`src/antigravity_k/engine/context_budget_enforcer.py:167`, `:304`). It only shrinks artifacts, memory, skills, and unprotected history; if the protected material cannot fit, it raises `PromptBudgetExceededError` before provider invocation (`:427`, `:443`). This avoids partial system or tool JSON and preserves the original user question through a receipt round. The pair protection includes the mixed-narration call case, where partial compaction would otherwise leave a malformed/orphaned call.

The final enforcement gate runs before `stream_generate`; its typed-error path records a halt and returns (`src/antigravity_k/engine/tool_loop.py:1400`, `:1499`, `:1588`). Fitted optional components are propagated into the loop locals and pinned cache so later rebuilds cannot re-expand a compressed skill block (`:1412`). The strengthened F3 tests exercise a forced rebuild across two provider rounds and verify that systems and selected tools stay whole while fitted skills do not grow again (`tests/test_ctx02_reject_fixes.py:176`).

For direct responses, the budget branch uses the whole serialized direct prompt as an atomic value and fails closed when it exceeds the input limit; it neither normalizes nor truncates arbitrary wrapper/system/tool text (`src/antigravity_k/engine/tool_loop.py:1004`). The exception exits before generation (`:1499`) and therefore before the later quality/format retry paths; the explicit direct-response condition also excludes the format-repair retry (`:2102`). The direct construction selects the final user turn after shaping (`:1201`); the existing shaper retains the most recent non-system turns unchanged, so an oversized current request reaches the final gate intact and is rejected rather than shortened.

The new tests are behavior-focused rather than merely checking implementation constants: they cover optional-skill shrinking, impossible complete essentials, receipt-round preservation, native schema delivery, direct-response zero generation on overflow, and the two F3 re-expansion regressions (`tests/test_final_budget_user_request.py:36`, `:177`, `:223`, `:269`; `tests/test_final_prompt_budget.py:155`; `tests/test_ctx02_reject_fixes.py:176`). They do not pin natural-language prompt prose, delete coverage, or duplicate production algorithms.

## Evidence reviewed

- `final-budget-green.log`: 30 passed.
- `final-budget-ctx02-green.log`: 13 passed.
- `final-budget-regression.log`: 191 passed.
- `final-python-regression-with-budget.log`: 410 passed, 2 environment-disabled skips, and one existing Starlette deprecation warning; exit 0.
- `git diff --check` was clean. Root also reported zero LSP errors for the two production files; this was treated as supplementary, not a substitute for the test logs.

## Skill-perspective check

The `omo:programming` and `omo:remove-ai-slops` skills were loaded and applied before this judgment. This check ran. The reviewed delta violates neither perspective: it has no deletion-only, tautological, prompt-prose, or implementation-mirroring tests; no new untyped escape hatch; and no needless production parsing/normalization or abstraction. The narrow protection helper and typed fail-closed boundary are necessary to prevent a real budget bypass.

## Decision

`codeQualityStatus`: **CLEAR**  
`recommendation`: **APPROVE**  
`blockers`: None.
