---
title: Final goal review — Codex-style SSAK-AI UI
tags: [qa, frontend, visual-qa, codex, gate-review]
date: 2026-10-03
---

# Final goal and visual QA review — Pass A

## Recommendation

**REVISE**

Confidence: **high**. The fresh packet proves the intended design direction and resolves the prior Korean wrapping defects, but two current mobile modal states fail the stated readability and foreground-hierarchy contract.

## Reviewed binding

- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Dirty files bound by `SOURCE_MANIFEST.json`: 43
- Source manifest SHA-256: `4abc26596d09679a03b0e5e077bc1fb97f9a72c7148fae59b484bcf95653ef75`
- Main JS: `src/antigravity_k/dashboard_dist/assets/index-CYlhq3Mt.js`; SHA-256 `57732b8b8b74c41b81681724d52ff6b797dbbb635a16c29453e4df4fa1ad86f2`
- Main CSS: `src/antigravity_k/dashboard_dist/assets/index-eFoPJE3Q.css`; SHA-256 `5c177e1f3d82f3549c4b337734c9ecf6355f2781671ad58f2d3074cf25c7b75d`
- Capture manifest SHA-256: `190b37b471006e3e553bb1773ebe884cdd53354bb972998947f8fa9f32b5130c`
- Current captures reviewed: **70/70**: 30 at 375x812, 17 at 768x900, and 23 at 1280x900. This includes all 17 routes at all three widths plus 19 interaction states.
- Manifest hygiene: 70/70 have valid signatures/dimensions, `documentWidth` equals viewport width, measured horizontal overflow is zero, and every capture postdates all source edits.

No ulw-loop plan exists (`ULW_LOOP_PLAN_MISSING`), so this is the requested fallback report path.

## Original intent

Apply the readable, tidy qualities of the current Codex desktop experience to SSAK-AI while preserving core behavior, authentication/CAS boundaries, and 27B model selection. The target is a neutral reusable visual system, system UI typography with Korean fallbacks, 14px interface text, 16px/1.7 chat copy, a 248px desktop rail, centered 760px transcript, detached rounded composer, native project/thread navigation, compact real telemetry, and bounded inspection/navigation modals below their responsive breakpoints.

No exact Codex Desktop screenshot was supplied. The binding contract is `dashboard/DESIGN.md` plus `docs/frontend/CODEX_REFERENCE_2026-10-03.md`; the Codex CLI/TUI is not a pixel reference.

## Desired outcome

Users should receive a calm, readable workspace whose chat, navigation, composer, project/thread context, telemetry, palettes, drawers, and inspection surfaces remain legible and correctly layered at 375px, 768px, and 1280px. Compact overlays must appear as foreground modal surfaces with visible headings and dismissal controls, without background content competing with the active task.

## User outcome review

The broad redesign succeeds. The captures show a coherent neutral shell, system/CJK typography, stable 248px desktop navigation, centered transcript/composer geometry, real DOM content, compact telemetry, responsive 375px navigation and inspection, and no measured horizontal overflow. The prior `A/B 테스트 실행` and `주소가` Korean fractures are visibly fixed in the fresh originals. The completed chat shows `qwen3.8:latest (27.3B)`, the real reply `연결이 정상적으로 활성화되어 있습니다.`, copy affordance, and preserved conversation context.

The outcome is not ready because two frequently used compact overlays fail to establish a clean foreground layer. Both defects are visible in current manifest-bound screenshots and affect readability or dismissal discoverability.

## Criteria review

| Criterion | Result | Evidence |
|---|---|---|
| C1 Neutral reusable tokens and system/CJK typography | PASS | design contract, `TYPOGRAPHY_LIVE.json`, route captures |
| C2 248px desktop rail and centered 760px transcript/composer | PASS | `final-1280-chat-complete.jpg`, `final-1280-inspection-environment.jpg` |
| C3 Independent rounded composer and preserved real chat behavior | PASS | `final-375-chat-complete.jpg`, `final-375-copy.jpg`, `LIVE_CHAT_RESULT.json` |
| C4 Native project/thread navigation and actual compact telemetry | PASS | desktop chat/status captures and current DOM artifacts |
| C5 Inspection modal below 1280 and navigation modal below 1024 | PASS | compact inspection/navigation captures and directed focus evidence |
| C6 Compact overlays have readable foreground hierarchy, visible title, and visible dismissal | **FAIL** | `final-375-history.jpg`, `final-375-command-palette.jpg` |
| C7 Readable Korean wrapping without one-character/semantic fractures | PASS | `final-375-data-extraction.jpg`, `final-375-not-found.jpg` |
| C8 Preserve core/auth/CAS/model-27B boundaries | PASS | protected manifest hashes and current 27B evidence |
| C9 No pasted-image implementation or slop animation | PASS | TSX/CSS/DOM inspection and live route DOM captures |

## Blockers

1. **[product] Mobile history drawer header is obscured.**
   - `violatedCriterion`: **C6 — compact overlays must be readable foreground modal surfaces with visible heading and dismissal control.**
   - Observation: at 375x812, the fixed 48px status strip paints over the history drawer header. Only the bottom of `대화 2개` is visible and the close control is not visible, making the modal identity and primary dismissal affordance unclear.
   - `evidencePointer`: `docs/qa/2026-10-03-codex-ui/captures/final-375-history.jpg`; compare `captures/final-375-navigation.jpg`.

2. **[product] Command palette lacks an opaque foreground reading surface.**
   - `violatedCriterion`: **C6 — compact overlays must foreground the active task and prevent background content from competing with controls/results.**
   - Observation: at 375x812, transcript text and assistant content remain visibly legible through the palette and overlap the search/results region. Search text, underlying transcript, and result labels occupy the same visual plane.
   - `evidencePointer`: `docs/qa/2026-10-03-codex-ui/captures/final-375-command-palette.jpg`.

No `[evidence]` blocker is needed to establish these failures; both are directly visible in fresh, manifest-bound product captures.

## Direct programming and anti-slop pass

I loaded and independently applied `omo:programming` and `omo:remove-ai-slops` to the production/test delta. The implementation uses real React/CSS/DOM surfaces and does not substitute screenshots, canvas replicas, decorative fake telemetry, or gratuitous animation for behavior. The final Korean wrapping correction is narrowly scoped and adds no unnecessary extraction, parsing, normalization, or abstraction.

I found no new deletion-only test, requested-removal-only test, tautological expected value, implementation-mirroring parser/normalizer, or prompt/prose pin introduced by the final correction. Existing UI tests contain text assertions, but none of the reviewed final CSS/class-hook work adds a success-critical overfit test. `CODE_REVIEW.md` explicitly records the same programming and anti-slop perspectives and reports no blocker; it was supporting evidence, not a substitute for this pass.

## Functional and build evidence

- `TESTS_CURRENT.log`: 101 files, 980 tests passed.
- `BUILD_CURRENT.log`: `tsc -b && vite build` passed; only the existing large Monaco/Mermaid chunk advisory remains.
- `QA_DIRECTED_RESULTS_ROUND3.json`: real reload retained selected 27B model/history; mobile navigation focus wrapped and returned; command-palette focus/inert cleanup and draft retention passed mechanically.
- Automated tests cover native IME composition, 503/CAS handling, and late-hydration preservation. These are not described as native-browser executions. The visual goal does not require adding fault-injection fixtures, so this is a note rather than a blocker.

## Checked artifact paths

- `dashboard/DESIGN.md`
- `docs/frontend/CODEX_REFERENCE_2026-10-03.md`
- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json`
- all 70 manifest-listed files under `docs/qa/2026-10-03-codex-ui/captures/`
- `BROWSER_OBSERVATIONS.json`, `QA_DIRECTED_RESULTS_ROUND3.json`, `LIVE_CHAT_RESULT.json`
- `TYPOGRAPHY_LIVE.json`, `TOKEN_CONTRAST.json`, `IMAGE_DIFF.json`
- `TESTS_CURRENT.log`, `BUILD_CURRENT.log`, `CODE_REVIEW.md`, `SECURITY_REVIEW.md`
- current manifest-listed production/test TSX, TS, and CSS sources

## Exact evidence gaps and notes

- `QA_REVIEW.md` predates the 43-file/70-capture binding and still describes the former 41-file/69-capture packet. Newer directed evidence closes model reload, history preservation, drawer focus wrap, palette focus/inert cleanup, and draft retention, but a refreshed aggregate manual-QA report is desirable after recapture.
- Native IME, injected 503/CAS, and deliberately delayed hydration were verified by automated coverage rather than native-browser fault execution. This does not block the stated visual redesign goal.
- `IMAGE_DIFF.json` compares the old 768px SSAK layout with the redesign. Its near-total difference is diagnostic, not Codex Desktop pixel-fidelity evidence.
- Skills/Metrics 401 behavior is unchanged and outside source scope. Private PIN entry was not exercised; the operator used an unlocked tab.

## Required revision evidence

Fix the compact history and command-palette stacking/surface opacity, then regenerate the source/bundle/capture manifests and the complete 70-image packet. Approval requires fresh original-size inspection of both corrected 375px states and a complete inventory check against the new binding.
