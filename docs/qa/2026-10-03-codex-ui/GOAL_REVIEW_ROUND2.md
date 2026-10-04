---
title: Final Codex-inspired UI goal review
tags: [qa, frontend, codex, final-gate]
date: 2026-10-03
---

# Final goal and visual QA review

**recommendation:** REJECT  
**result:** REVISE  
**blockers:**

1. `[product]` `UI-01` / `UI-05`: the 375px data-extraction accuracy row breaks Korean words mid-syllable cluster (`테스/트`, `실/행`), so the required readable CJK and responsive auxiliary-route outcome is not met. Evidence: `captures/final-375-data-extraction.jpg`, accuracy row and primary `A/B 테스트 실행` button. Fix: give the row/button enough intrinsic width or move the action below the label at this breakpoint, and apply `word-break: keep-all` to the Korean control text.
2. `[product]` `UI-01` / `UI-05`: the 375px not-found explanatory sentence breaks `주소가` as `주/소가`, so the required readable CJK outcome is not met. Evidence: `captures/final-375-not-found.jpg`, paragraph directly below `페이지를 찾을 수 없습니다`. Fix: apply the Korean prose wrapping rule (`word-break: keep-all` with normal wrapping) to the not-found copy and recapture at 375px.

## Reviewed binding

- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Source manifest: `SOURCE_MANIFEST.json`
- Source manifest SHA-256: `855b9221a7bfca549813e226f530fd5b406dbefc800cc53c35e31ad45b84cc20`
- Source files: 41; this reviewer recomputed every listed file hash and all matched.
- Capture manifest: `CAPTURE_MANIFEST.json`
- Capture manifest SHA-256: `f8e822702abfaed9e4630bb09774f7fdd80e477252cac8da8aa6671773e9b23a`
- Captures: 69; this reviewer recomputed every listed screenshot hash and all matched.
- Served entry: `/assets/index-BjO0ehSf.js`
- Served entry SHA-256: `6f34e2ac4eee4680114937ebeda49a33775b31d7a3843e7103af58a555058121`
- ULW fallback: `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`, so this report uses the specified non-ULW evidence path.

## Original intent

Replace the crowded, low-readability SSAK-AI dashboard presentation with a calm Codex Desktop-inspired workspace while keeping SSAK-AI's real identity and behavior. The request emphasizes readable Korean/system typography and screen composition rather than an unsupported pixel copy. Core chat behavior, PIN/auth boundaries, project/session CAS behavior, and the selected local 27.3B model must remain real and usable.

## Desired outcome

The shipped UI should provide a neutral conversation-first shell; labelled 248px desktop project/thread navigation; a centered 760px transcript with 16px/1.7 prose; a visually independent 20px-radius composer; concise actual status; collapsible inspection; responsive auxiliary pages at 375, 768, and 1280px; keyboard/focus/modal handoff; reduced-motion support; legible CJK text; and real model/history/generation/copy behavior. It must be a reusable token/component implementation, not a screenshot, static route mock, or copied proprietary Desktop asset.

## User outcome review

REVISE. The complete 69-frame current-build inventory was reviewed as three full montages (29 at 375px, 17 at 768px, and 23 at 1280px), with original-size checks of key conversation and operational pages. All 17 declared routes are represented at all three required widths (51 route frames), plus 18 interaction states. The captures show the intended neutral shell, stable navigation and status hierarchy, open transcript, detached composer, and resolution of the former Round 1 Studio/Model horizontal overflow. Two 375px originals still fail the explicit readable-CJK contract: the data-extraction accuracy row breaks `테스트` and `실행` across lines, and the not-found paragraph breaks `주소가` after its first syllable. These are visible product defects, despite the geometric overflow probe remaining zero.

The implementation is source-backed. `index.css` defines the font, color, spacing, `248px`, `760px`, `16px`, and radius tokens; the workspace styles consume them. `ChatComposer`, `WorkspaceNavigation`, `InspectionFrame`, `ChatHistory`, and `SystemTelemetricsBar` are real components with native controls and semantic labels. `InspectionFrame` switches between a bounded desktop column and a compact modal, uses the shared focus-trap hook, supports Escape and shortcut-guide handoff, and implements keyboard tab movement. Global workspace focus-visible and reduced-motion rules are present. No capture is used by production code, no remote/proprietary font was introduced, and the served page remains actual DOM.

The operator evidence records an actual `qwen3.8:latest (27.3B)` response (`연결 정상입니다.`), completion, clipboard match, Shift+Enter newline without send, two retained history sessions, model menu, status details, navigation, palette, shortcut guide, and compact/docked inspection. DOM observations bind every frame to the current entry script and report zero measured horizontal overflow for all 51 route frames. The reviewer independently reran `pnpm --dir dashboard test --run` (101 files, 980 tests, exit 0) and `pnpm --dir dashboard build` (`tsc -b && vite build`, exit 0). The registry update-check network message was unrelated to either successful command.

## Criteria matrix

| Criterion | Result | Evidence |
| --- | --- | --- |
| `UI-01` calm Codex-inspired composition and readable CJK typography | FAIL | Typography measurements and font stack pass, but `final-375-data-extraction.jpg` and `final-375-not-found.jpg` visibly split Korean words mid-word. |
| `UI-02` reusable design tokens and component tree, no pasted/static fake | PASS | `dashboard/src/styles/index.css`; workspace CSS modules; `ChatComposer.tsx`; `InspectionFrame.tsx`; `WorkspaceNavigation.tsx`; DOM observations and served bundle binding. |
| `UI-03` 248px navigation, 760px transcript, independent 20px composer | PASS | `dashboard/DESIGN.md`; token definitions; `workspace-shell.css`; `workspace-chat.css`; `TYPOGRAPHY_LIVE.json`; completed chat captures. |
| `UI-04` compact actual status and collapsible inspection | PASS | `SystemTelemetricsBar.tsx`; `InspectionFrame.tsx`; `final-375-status.jpg`; `final-1280-status-details.jpg`; six environment/code/changes captures. |
| `UI-05` responsive routes and auxiliary pages | FAIL | Inventory, dimensions, and horizontal-overflow probes pass, but the 375px data-extraction and not-found CJK wrapping defects remain user-visible responsive failures. |
| `UI-06` keyboard, focus, modal handoff, and reduced motion | PASS | `InspectionFrame.tsx`; `Sidebar.test.tsx`; `InspectionFrameHandoff.test.tsx`; `ChatPageComposer.test.tsx`; `codex-workspace.css`; palette/shortcut/navigation/history interaction captures; operator evidence. |
| `FUNC-01` actual 27.3B model send/completion/copy/Shift+Enter/history | PASS | `QA_CAPTURE_READY.md`; `VERIFICATION.json`; completed/generation/copy/model-menu/history captures; independently rerun 980-test suite. |
| `FUNC-02` core/auth/CAS/model contracts preserved | PASS | Protected hashes in `SOURCE_MANIFEST.json` for `chatStore.ts`, `projectStore.ts`, `api/client.ts`, and `accessPinCredential.ts`; `CODE_REVIEW.md`; `SECURITY_REVIEW.md`; passing tests/build. |
| `QUAL-01` programming and anti-slop review | PASS with note | Direct diff/source/test pass plus `CODE_REVIEW.md` explicit skill-perspective section. No deletion-only/removal-pin, tautological, prompt-prose, implementation-mirroring, needless parser/normalizer, static-fake, or slop-animation blocker was found. |

## Direct programming and anti-slop pass

The direct pass covered all 41 manifest-bound source files, the changed tests, the production component/style seams, and the final code-review coverage. Tests added or changed for this UI exercise assert observable behavior such as send/composition handling, copy feedback, history hydration, modal focus/inert state, inspection tab handoff, status disclosure, and route recovery. They do not merely assert that old UI text or deleted markup is absent. Existing rendering/security tests that inspect DOM structure are broader repository tests and do not constitute a failure of a stated visual criterion.

No production screenshot embedding, route-specific screenshot recreation, remote font injection, unnecessary normalization layer, speculative data extractor, or layout animation that contradicts the contract was found. The workspace explicitly disables message animation, restricts current hover behavior, and applies a reduced-motion override. The design remains token-driven across the conversation shell and operational pages.

`ChatPage.tsx` remains approximately 1,191 pure lines and therefore exceeds the anti-slop module-size heuristic. This is a maintenance NOTE: the submitted change already extracts the composer, history, inspection, model selector, navigation, metadata, and copy responsibilities, and no stated success criterion requires a complete controller split. It does not block this user-visible UI goal.

## IMAGE_DIFF interpretation

`IMAGE_DIFF.json` reports matching 768×900 dimensions, `diffRatio: 0.9997`, `similarityScore: 0`, intact alpha, and 64 hot regions. This is expected evidence of a broad before/after redesign, not a Codex fidelity measurement. The old and new frames differ across nearly the entire canvas because the implementation changes the surface palette, removes the busy rail treatment, centers the transcript, separates the composer, replaces decorative telemetry with concise actual status, and contains different live conversation/status content. The result cannot support a pixel-similarity claim and is not used as one.

## Checked artifacts

- `dashboard/DESIGN.md`
- `docs/frontend/CODEX_REFERENCE_2026-10-03.md`
- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_HYGIENE.json`
- `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`
- `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md`
- `docs/qa/2026-10-03-codex-ui/VERIFICATION.json`
- `docs/qa/2026-10-03-codex-ui/TYPOGRAPHY_LIVE.json`
- `docs/qa/2026-10-03-codex-ui/TOKEN_CONTRAST.json`
- `docs/qa/2026-10-03-codex-ui/IMAGE_DIFF.json`
- `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CODE_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/SECURITY_REVIEW.md`
- All 69 files listed by `CAPTURE_MANIFEST.json`, all 41 files listed by `SOURCE_MANIFEST.json`, their current DOM snapshots, and the served entry bundle.

## Evidence gaps and limitations

- No exact Codex Desktop screenshot, stylesheet, or proprietary font was supplied. The evidence supports the explicit adaptive design contract, not pixel-identical Desktop fidelity.
- No browser-injected axe/Lighthouse score or native Electron/physical-device IME automation is present. Focus, keyboard, IME guards, and responsive behavior are supported by source, tests, DOM observations, and the stated operator run.
- Skills and Metrics auxiliary endpoints retain their existing `401` behavior and their page/API source is unchanged. Captures prove their displayed layout/error states only; this review makes no backend-success claim.
- No backend full-suite rerun was performed because the scoped goal and source manifest are frontend-only and the protected auth/API/store hashes are unchanged.
- `React Doctor` retains one accurately documented exit-1 advisory in an ignored, non-shipping mutation fixture. It is absent from the served bundle and is not tied to a stated success criterion.

## Blockers

1. `[product]` `UI-01` / `UI-05` — `captures/final-375-data-extraction.jpg`, accuracy row: `A/B 테스트 실행` and the adjacent label wrap inside Korean words. Make the narrow layout stack or preserve Korean word units, then replace the capture and manifest binding.
2. `[product]` `UI-01` / `UI-05` — `captures/final-375-not-found.jpg`, explanatory paragraph: `주소가` wraps as `주/소가`. Apply the CJK prose wrapping rule, then replace the capture and manifest binding.

No other criterion blocker was found in this binding. Approval requires a fresh source manifest, build, and capture manifest that include the fixes; this report must not be reused for that new binding.
