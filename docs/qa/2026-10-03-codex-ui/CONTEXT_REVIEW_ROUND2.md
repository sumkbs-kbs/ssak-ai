---
title: Final context and evidence gate — Codex-style SSAK-AI UI
tags: [qa, frontend, context-review, codex]
date: 2026-10-03
---

# Final context and evidence gate

**recommendation:** REJECT

## Evidence identity

- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Dirty-source manifest: `SOURCE_MANIFEST.json`, SHA-256 `855b9221a7bfca549813e226f530fd5b406dbefc800cc53c35e31ad45b84cc20`, 41 files
- Capture manifest: `CAPTURE_MANIFEST.json`, SHA-256 `f8e822702abfaed9e4630bb09774f7fdd80e477252cac8da8aa6671773e9b23a`, 69 JPEGs
- Served entry: `/assets/index-BjO0ehSf.js`, SHA-256 `6f34e2ac4eee4680114937ebeda49a33775b31d7a3843e7103af58a555058121`
- `omo ulw-loop status --json`: no active ulw-loop plan (`ULW_LOOP_PLAN_MISSING`), so this requested project QA path is the report location.

## originalIntent

Adapt the useful typography and screen composition of the current Codex app to SSAK-AI: calm system-sans typography with Korean fallbacks, project/conversation-first navigation, readable 16px conversation prose, a bounded centered transcript and composer, and responsive named navigation and inspection surfaces. Preserve SSAK-AI's files-first, Git-first and typed-metadata architecture plus its PIN, project identity, server conversation revision/CAS, model persistence and real-status semantics. Keep the current dirty workspace, make no commit/PR/auth change, and avoid claiming that the public `openai/codex` CLI/TUI repository or copied proprietary fonts provide an exact Desktop React/pixel reference.

## desiredOutcome

A current production bundle that visibly delivers the documented Codex-inspired hierarchy and typography at 375, 768 and 1280 pixels; renders all 17 declared routes and key interaction states without horizontal overflow, Korean clipping or semantic word fractures; preserves real chat/model/project/status behavior; and is supported by source-bound build, test, browser, visual, code and security evidence. The execution plan's final state requires the independent functional/visual review and final acceptance documentation to pass.

## userOutcomeReview

The major result is present and strongly evidenced: the application uses the intended neutral system-sans composition; measured live values include a 248px desktop sidebar, 760px transcript measure and 16px/27.2px assistant prose; all 51 route frames cover 17 routes at each required viewport; all 69 captures are current-bundle JPEGs with valid signatures/dimensions; the production entry hash matches; and the operator exercised generation, copy, Shift+Enter, navigation, history, inspection, palette, shortcut guide, output and live status. The exact-Desktop/font limitation is stated honestly, existing Skills/Metrics 401 states are not misrepresented as backend success, and the dirty baseline remains uncommitted.

The user-visible result is not ready for final acceptance because the independent visual review found two real Korean wrapping defects in current 375px captures. The independent manual-QA report also records narrower direct-evidence gaps for native IME and post-reload model persistence; automated tests support those contracts, and the plan does not require every preserved boundary to be manually fault-injected, so those gaps are reported below as NOTES rather than additional blockers.

## blockers

### B1 — primary Korean action label fractures at 375px

- **violatedCriterion:** `UI-CJK-NATURAL-WRAP` — `dashboard/DESIGN.md` §4 requires Korean prose to use `word-break: keep-all` and natural spacing, and the execution plan requires no Korean clipping/fracture at 375/768/1280.
- **observation:** The primary `A/B 테스트 실행` action in the 375px data-extraction route breaks `실행` into one-character lines (`실` / `행`). This is a direct current-product defect, not an evidence-only gap.
- **evidencePointer:** `docs/qa/2026-10-03-codex-ui/captures/final-375-data-extraction.jpg`; `docs/qa/2026-10-03-codex-ui/VISUAL_REVIEW_B.md` blocking finding 1.
- **requiredClosure:** Give the compact action enough inline width or keep its label unbroken, rebuild, replace the bound 375px capture, and re-run visual/capture hygiene review.

### B2 — Korean prose word fractures on the 375px NotFound route

- **violatedCriterion:** `UI-CJK-NATURAL-WRAP` — the same natural Korean wrapping criterion and required-width QA checklist.
- **observation:** `주소가` breaks as terminal `주` plus next-line `소가` in the current 375px NotFound screenshot. The visual reviewer traced the rendered break to page-wide wrapping rules rather than a malformed source phrase.
- **evidencePointer:** `docs/qa/2026-10-03-codex-ui/captures/final-375-not-found.jpg`; `docs/qa/2026-10-03-codex-ui/VISUAL_REVIEW_B.md` blocking finding 2; `dashboard/src/pages/NotFoundPage.tsx`; `dashboard/src/styles/workspace-pages.css`.
- **requiredClosure:** Keep ordinary Korean prose on natural word boundaries while retaining aggressive wrapping only for path/code tokens, then rebuild and replace the bound 375px capture.

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
- `docs/qa/2026-10-03-codex-ui/VERIFICATION.json`
- `docs/qa/2026-10-03-codex-ui/TESTS_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/BUILD_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/CODE_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/SECURITY_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/QA_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/VISUAL_REVIEW_B.md`
- Current dashboard diff, changed tests, current served `src/antigravity_k/dashboard_dist/index.html`, and the 69 capture inventory.

## Reproduced evidence

- `git rev-parse HEAD` matched the declared HEAD.
- The SHA-256 of `SOURCE_MANIFEST.json` matched `855b9221...`; all 41 file hashes listed inside it matched current bytes.
- The SHA-256 of `CAPTURE_MANIFEST.json` matched `f8e82270...`.
- The served entry existed and matched `6f34e2ac...`; the served `index.html` matched the bundle manifest.
- `CAPTURE_HYGIENE.json` reports 69 valid current-main-bundle JPEGs and no bad entries. The capture manifest contains 29 frames at 375px, 17 at 768px and 23 at 1280px, including exactly 51 route frames.
- `VERIFICATION.json` is current-bound and reports 101 test files / 980 tests, successful TypeScript/production build, clean scoped whitespace diff and the accurately retained nonshipping React Doctor advisory.
- `git diff --check -- dashboard docs/frontend docs/qa/2026-10-03-codex-ui` passed during this review.

## Direct programming and remove-ai-slops pass

I independently applied the `omo:programming` and `omo:remove-ai-slops` criteria over the current production/test diff. The focused new tests exercise observable behavior for navigation, modal focus/inert boundaries, history selection, metadata refresh and copy/interaction behavior. I found no deletion-only test, test whose only purpose is verifying requested removal, tautological expected value, prompt/prose pin, new test-only parser/normalizer, or needless production extraction that violates a stated acceptance criterion. Existing DOM/class assertions in older broad rendering tests are weak proof for visual acceptance but do not create a criterion failure. Oversized `ChatPage.tsx`, `SettingsPage.tsx`, `EnvironmentPanel.tsx`, `App.tsx`, `chatStore.ts` and `ChatMessage.tsx` remain maintenance debt; this scope did not state module-size refactoring as an acceptance criterion, so they are NOTES rather than blockers.

`CODE_REVIEW.md` explicitly states that it loaded both required skill perspectives and checked untyped escape hatches, brittle prompt assertions, implementation-mirroring/deletion-only/tautological tests, unnecessary normalization and needless extraction. That report's coverage agrees with this direct pass; it does not substitute for it.

## Exact evidence gaps and non-blocking notes

1. Direct current-browser model persistence after reload is missing. The current selector/menu and automated persistence coverage support the preserved contract, but a select/reload/reopen artifact would strengthen final manual evidence. This is a NOTE because the success criteria require persistence to remain functional, not a browser-only proof mechanism.
2. Direct native Korean IME composition behavior is missing. Shift+Enter is directly proven and the composition guard has automated coverage. A native-device sequence would strengthen confidence, but the criterion does not require manual native-device execution, so this is a NOTE.
3. Controlled 503/CAS fault injection and a directly captured late-hydration race are missing from `QA_REVIEW.md`. These are useful follow-up evidence, but the font/layout brief does not require a new browser fault harness; the existing automated contract coverage and unchanged core boundary mean they are NOTES here rather than additional blockers.
4. `SECURITY_REVIEW.md` contains a stale note claiming `VERIFICATION.json` still has round-one bindings. The JSON is now current (`855b9221...`, 101/980). The security report otherwise binds directly to current source/bundle hashes and passes, so this documentation inconsistency is a NOTE.
5. Skills/Metrics requests still return the documented existing 401 state. The route captures prove the displayed state/layout only; no backend-success claim is accepted.
6. No exact Desktop CSS/font/pixel-fidelity claim is supported or made. The public pinned `openai/codex` reference remains CLI/TUI/app-server evidence only.

## Final gate decision

REJECT until B1–B2 close with current source/bundle/capture bindings. The strongest evidence repair from round one is valid: required-width route coverage and current production-bundle binding are no longer blockers. The remaining blocking failures are narrow, visible and concrete.
