---
title: Final context and evidence review — Codex-inspired SSAK-AI UI
tags: [qa, frontend, context-review, codex, final-gate]
date: 2026-10-03
---

# Final context and evidence review

**recommendation:** REJECT

## blockers

### B1 — compact history and inspection overlays render below the global status layer

- **violatedCriterion:** `UI-04` / `UI-06` — compact inspection/history must behave as foreground, dismissible modal surfaces with correct focus/modal handoff; the execution plan also requires panel and history behavior to remain usable at the required widths.
- **observation:** `.main-content` is `position: relative; z-index: 1`, which creates a stacking context. Compact history (`z-index: 115`) and inspection (`z-index: 105`) are descendants of that context, so their fixed headers and backdrop cannot rise above the global status layer (`z-index: 60`) outside the context. Root DOM/manual QA reproduced the compact overlay header underneath the status bar. The numeric child z-index values do not escape the parent stacking context.
- **evidencePointer:** `dashboard/src/styles/index.css:646`; `dashboard/src/styles/workspace-inspection.css:23`; `dashboard/src/styles/workspace-history.css`; current compact history/inspection DOM inspection in IAB `browser2/tab1`.
- **requiredClosure:** Remove the unintended `.main-content` stacking context (or portal the compact overlays to the intended top-level modal layer), rebuild, regenerate the source/bundle/capture binding, and manually verify history and inspection headers/backdrops above status at 375px and 768px.

## Evidence identity

- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Dirty source manifest: `SOURCE_MANIFEST.json`, SHA-256 `4abc26596d09679a03b0e5e077bc1fb97f9a72c7148fae59b484bcf95653ef75`, 43 files
- Production entry: `/assets/index-CYlhq3Mt.js`, SHA-256 `57732b8b8b74c41b81681724d52ff6b797dbbb635a16c29453e4df4fa1ad86f2`
- Production CSS: `/assets/index-eFoPJE3Q.css`, SHA-256 `5c177e1f3d82f3549c4b337734c9ecf6355f2781671ad58f2d3074cf25c7b75d`
- Capture manifest: `CAPTURE_MANIFEST.json`, SHA-256 `190b37b471006e3e553bb1773ebe884cdd53354bb972998947f8fa9f32b5130c`
- Capture inventory: 70 fresh screenshots; 51 route frames covering 17 routes at 375×812, 768×900 and 1280×900, plus 19 interaction states
- ULW status: `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`; this project QA path is therefore the required fallback report location.

## originalIntent

Adapt the useful typography, hierarchy and screen composition of the current Codex experience to SSAK-AI while preserving SSAK-AI's real product behavior. The requested result is a calmer, more readable system-sans workspace with Korean fallbacks, project/conversation-first navigation, a centered conversation canvas, an independent composer and usable responsive layouts. The implementation must preserve chat, project identity, model selection, PIN/authentication, server revision/CAS, sanitization/approval and actual-status behavior, including the local Qwen 3.8 27.3B default and the explicit 125B option. The current dirty workspace and existing histories must be retained without a commit, PR, worktree, credential read or external message.

The reference boundary is correctly documented: public `openai/codex` at commit `604061ce51d194a3aa6aad3b3170240d096e1725` supplies CLI/TUI and app-server interaction ideas, not proprietary Codex Desktop React/CSS or exact font metrics. No exact-pixel Desktop claim, copied font, copied dependency or screenshot-backed production fake is accepted.

## desiredOutcome

A source-bound production bundle that provides the documented Codex-inspired typography and composition at 375, 768 and 1280 pixels; renders all declared routes and key interaction states without horizontal overflow, Korean clipping or unnatural word fracture; keeps genuine model, history, generation, copy, navigation, inspection and status behavior; and is backed by current build, test, security, code, browser and visual evidence.

## userOutcomeReview

REJECT for the current binding. Most of the requested user-visible outcome is present: live measurements bind the 14px system-sans UI, 16px/27.2px assistant prose, 248px desktop navigation and 760px conversation measure. All 51 required-width route frames are present, hash-valid, postdate the last source edit and report bounded document width. The 19 interaction frames cover the responsive navigation, history, model menu, generation/completion/copy, inspection tabs, command palette, shortcut guide, output and live-status surfaces. However, direct compact-surface QA found that history and inspection are not reliably foreground modal surfaces because their fixed layers are trapped in `.main-content`'s lower stacking context. This violates the panel/history/modal behavior criteria and blocks acceptance of this source/bundle/capture lineage.

The two defects from the prior review are closed in the current binding. Direct original-resolution inspection of `captures/final-375-data-extraction.jpg` shows the primary `A/B 테스트 실행` label intact, and `captures/final-375-not-found.jpg` shows `주소가` intact on one line. The current CSS and class hooks are narrowly scoped, the fresh captures postdate those edits, and the current code/security reports bind all 43 source hashes and the served `CYlhq3Mt` bundle.

Real-surface evidence records a completed `qwen3.8:latest27.3B` response, matching clipboard content, Shift+Enter newline behavior, reload with the selected 27B model still pressed, preservation of both original histories, creation of a third synthetic QA chat without deletion, bidirectional navigation focus wrapping, Escape focus return, inspection-to-palette handoff and preservation of an unsent draft. Existing Skills/Metrics 401 responses are accurately limited to displayed route-state evidence and are not represented as backend success.

## Criteria review

| Criterion | Result | Evidence |
|---|---|---|
| `REF-01` honest Codex reference boundary | PASS | `CODEX_REFERENCE_2026-10-03.md` pins `604061ce…`, distinguishes public CLI/TUI/app-server code from Desktop React/CSS and rejects copied proprietary assets. |
| `UI-01` calm, readable system-sans/CJK composition | PASS | `dashboard/DESIGN.md`, `TYPOGRAPHY_LIVE.json`, current route/state captures; direct review of both corrected 375px CJK frames. |
| `UI-02` reusable tokens/components rather than a pasted screenshot | PASS | Tokenized workspace CSS and real `ChatComposer`, `WorkspaceNavigation`, `InspectionFrame`, `ChatHistory` and `SystemTelemetricsBar` components; live DOM/capture binding. |
| `UI-03` 248px navigation, 760px transcript, 16px conversation prose and independent composer | PASS | `TYPOGRAPHY_LIVE.json`, workspace styles and 375/768/1280 captures. |
| `UI-04` compact actual status and responsive inspection | **FAIL** | Compact history/inspection fixed layers are trapped under the global status layer by `.main-content { position: relative; z-index: 1; }`. |
| `UI-05` 17 routes at 375/768/1280 without overflow or CJK fracture | PASS | `CAPTURE_MANIFEST.json` and `CAPTURE_HYGIENE.json`; 51/51 route frames; direct post-fix CJK inspection. |
| `UI-06` keyboard, focus, modal handoff and reduced motion | **FAIL** | Focus tests pass, but the compact modal's visible stacking order is wrong in direct DOM/manual QA; a foreground modal criterion requires both focus ownership and correct visual layering. |
| `FUNC-01` actual model/send/completion/copy/history behavior | PASS | `LIVE_CHAT_RESULT.json`, `QA_DIRECTED_RESULTS.json`, `VERIFICATION.json` and current interaction captures. |
| `FUNC-02` core chat/project/auth/CAS/sanitization/approval contracts preserved | PASS | Current protected hashes, `CODE_REVIEW.md`, `SECURITY_REVIEW.md`, 980 passing tests and successful typecheck/build. |
| `MODEL-01` 27.3B preference persists and 125B remains available | PASS | Real reload/pressed-state result, current model-menu evidence and preserved model-store contract. |
| `QUAL-01` build/test/code/security quality | PASS | 101 test files / 980 tests, successful `tsc -b && vite build`, current code/security reports and direct programming/anti-slop pass. |
| `BIND-01` reviewed source, bundle, CSS and captures are traceable | PASS | Source `4abc2659…`, JS `57732b8b…`, CSS `5c177e1f…`, capture manifest `190b37b4…`, `LIVE_STYLE_BINDING.json`; all 70 capture hashes reproduced with no missing/stale entry. |

## Direct programming and remove-ai-slops pass

I directly applied the `omo:programming` and `omo:remove-ai-slops` criteria to the production/test diff and final CSS delta. The focused tests assert observable behavior: IME/composition and Shift+Enter submission boundaries, late-hydration preservation, model preference, copy outcomes, focus/inert ownership, modal handoff, route recovery and telemetry disclosure. They are not deletion-only tests, requested-removal tests, prompt/prose pins, tautological projections or tests of a parser/normalizer created only for the test. The two final CJK fixes appropriately have real-surface evidence instead of brittle tests that assert literal CSS declarations.

No screenshot is embedded in production, no static route recreation or unnecessary parsing/normalization layer was introduced, and no new dependency or proprietary font asset was added. Existing large modules such as `ChatPage.tsx`, `SettingsPage.tsx`, `EnvironmentPanel.tsx`, `App.tsx`, `chatStore.ts` and `ChatMessage.tsx` remain maintenance debt, but module-size refactoring is not a stated success criterion and no demonstrated user outcome fails because of it. Existing older DOM/class assertions are weak visual proof and were not used as acceptance evidence.

`CODE_REVIEW.md` explicitly records its own programming and anti-slop check, including deletion-only, removal-pin, tautological, prose/prompt, implementation-mirroring, unnecessary normalization and needless extraction categories. Its coverage agrees with this direct pass and does not replace it.

## Checked artifact paths

- `AGENTS.md`
- `docs/frontend/EXECUTION_PLAN_2026-10-03.md`
- `docs/frontend/CODEX_REFERENCE_2026-10-03.md`
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-03-codex-ui/BASELINE.json`
- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_HYGIENE.json`
- `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`
- `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md`
- `docs/qa/2026-10-03-codex-ui/QA_DIRECTED_RESULTS.json`
- `docs/qa/2026-10-03-codex-ui/LIVE_CHAT_RESULT.json`
- `docs/qa/2026-10-03-codex-ui/LIVE_STYLE_BINDING.json`
- `docs/qa/2026-10-03-codex-ui/TYPOGRAPHY_LIVE.json`
- `docs/qa/2026-10-03-codex-ui/VERIFICATION.json`
- `docs/qa/2026-10-03-codex-ui/TESTS_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/BUILD_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/CODE_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/SECURITY_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/QA_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/GOAL_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/VISUAL_REVIEW_B.md`
- All 70 files listed by the current capture manifest and all 43 files listed by the current source manifest.

## Exact evidence gaps and non-blocking notes

1. `QA_REVIEW.md`, `GOAL_REVIEW.md` and `VISUAL_REVIEW_B.md` remain bound to the superseded 41-file / `index-BjO0ehSf.js` / 69-capture revision. Their two product blockers describe the pre-fix screenshots and are closed by the current source/bundle/capture lineage and direct gate inspection. They must not be cited as current approvals. Current direct QA results, code/security reviews and this final gate supply the current-bound coverage.
2. Native device/Electron IME composition, controlled 503/CAS fault injection and the late-project-hydration race were not manually injected in the browser. The execution plan requires those behavior boundaries, not a browser-only proof mechanism; meaningful automated behavior tests cover them, so this is a limitation rather than a failed criterion.
3. No browser-injected axe/Lighthouse score is present. Focus behavior, semantic controls, contrast tokens and responsive layout have narrower evidence; no criterion requires an axe/Lighthouse score.
4. React Doctor retains one accurately documented exit-1 advisory in a pre-existing ignored, non-shipping mutation fixture. It is outside the 43-file manifest and served bundle and does not violate a stated success criterion.
5. The execution-plan status remains phase 4 `in_progress` and phase 5 `pending` while gates are running. That status is procedurally accurate during review; the artifact evidence required for this context gate is complete.
6. The command-palette opacity seen in some screenshots was captured during its transition. Direct settled-style inspection reports the intended opaque `rgb(24, 24, 24)` surface at opacity 1; this is not a blocker. Fresh post-repair captures should be taken after transition settling to avoid ambiguous visual evidence.

## Final decision

REJECT. The current binding closes the prior CJK defects but fails the compact foreground modal requirement because history and inspection render inside a lower stacking context. Approval requires the stacking repair plus a new source/bundle/capture binding and direct compact overlay verification.
