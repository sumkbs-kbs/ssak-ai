# Response-style code review

## Verdict

- `codeQualityStatus`: **BLOCK**
- `recommendation`: **REQUEST_CHANGES**
- `reportPath`: `docs/qa/2026-10-03-response-style/CODE_REVIEW.md`
- Source binding: `HEAD 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; final `SOURCE_MANIFEST.json` SHA-256 `575fef0f69115a1a526911065a40855e534306dbe59b2e51586c9220379b971a` (56 files). Relevant source hashes in that manifest were recomputed while reviewing.

## Scope reviewed

The response-presentation delta: `ChatMessage.tsx`, `MessageMetadata.tsx`, new `ChatMarkdown.tsx`, `ChatCodeBlock.tsx`, and `responsePresentation.ts`; their new/changed tests; the inherited `formatContent.ts`, `CopyButton.tsx`, and `searchFailure.ts` seams; `dashboard/DESIGN.md` “Assistant Response Typography / Disclosure”; `QA_SCOPE.md`; `TASK_BASELINE.json`; and `TASK_DELTA.patch`.

## Findings

### CRITICAL

None.

### HIGH

1. **A list-continuation HTML fragment can bypass sanitization and retain model-controlled styles.**

   `responsePresentation.ts:31-42` calls every line beginning with four spaces or a tab an indented code block when the prior line is blank. That does not model Markdown containers. For example:

   ```markdown
   - item

       <span style="position:fixed">x</span>
   ```

   has only two spaces beyond this list item's content indentation, so Markdown treats it as list continuation content rather than an indented code block. `codeRanges` nevertheless marks it literal. `formatResponseMarkdown()` at `:102-118` replaces it with a local placeholder before `sanitizeMarkdown()` and restores the original HTML afterwards. `ChatMarkdown.tsx:28-46` permits `style` on `span`, `div`, and the global schema, so the `position:fixed` survives the rendering pipeline.

   This breaks the required Markdown sanitation boundary and permits a response to change layout or obscure controls. The range detector must not decide that container-relative Markdown is literal based on leading whitespace alone. Remove this indented-code placeholder path, or derive literal spans from the Markdown parser; then add a render-level adversarial regression proving the example is sanitized while real top-level indented code remains literal.

### MEDIUM

None.

### LOW

None.

## Test and evidence assessment

- Direct focused re-run: `pnpm exec vitest run src/utils/responsePresentation.test.ts src/components/Chat/__tests__/ChatMessage.presentation.test.tsx` — **29/29 passed**. This validates existing intended boundary examples but does not cover list/container indentation or mount the corresponding sanitation counterexample.
- Inspected `TESTS.log`: final full run records **105 files / 1,030 tests passed** after the sanitation correction. It cannot compensate for the missing adversarial case above.
- Inspected `BUILD.log`: the final build had reached Vite transformation when read; no successful completion line was present in the captured portion. Root-owned build completion was not independently asserted here.
- `git diff --check` was clean. `PROTECTED_CHECK.json` records all four protected files unchanged.
- The final manifest and source hashes are present. Therefore this is not a missing-artifact blocker; the concrete sanitizer defect is the blocker.

## Skill-perspective check

The required check ran: `omo:programming` including its TypeScript reference, and `omo:remove-ai-slops` were read before judging maintainability and tests.

- **Programming perspective:** the handwritten Markdown range parser is unnecessary boundary parsing that cannot correctly represent Markdown container semantics. It creates a security-relevant wrong classification at the sanitization boundary. No new `any`, assertion escape hatch, or brittle prompt test was found in the reviewed delta.
- **Remove-ai-slops perspective:** the focused tests are neither deletion-only nor prose-pinning, and their envelope/copy assertions exercise observable behavior. They are incomplete at the new parser seam: none distinguishes an actual indented code block from list-relative indentation. The bespoke parsing/placeholder complexity is unjustified unless it is parser-correct.

## Blockers

1. Fix the list-continuation sanitizer bypass in `dashboard/src/utils/responsePresentation.ts` and prove it with a render-level adversarial regression before approval.
