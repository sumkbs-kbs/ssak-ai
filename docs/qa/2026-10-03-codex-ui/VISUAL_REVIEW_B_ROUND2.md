# Visual QA Pass B — Fidelity and CJK precision

**Verdict: REVISE**  
**Confidence: high**  
**Review type:** focused visual fidelity / CJK precision, read-only product review

## Intent and reference boundary

The intended result is a readable, tidy, current-Codex-like SSAK-AI workspace: a neutral calm dark theme, system sans typography with Korean fallbacks, 14px UI text, 16px chat text with 1.7 body leading, a 248px labelled desktop navigation rail, a 760px conversation/composer measure, a rounded fixed composer, and dismissible modal navigation/inspection on smaller screens. No exact Codex Desktop pixel reference was supplied. `github.com/openai/codex` is a CLI/TUI and is not treated as a pixel target.

The visual contract is therefore `docs/frontend/CODEX_REFERENCE_2026-10-03.md` plus `dashboard/DESIGN.md`, cross-checked against the current DOM/source and the current capture set.

## Evidence identity

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- source manifest: `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- source manifest SHA-256: `855b9221a7bfca549813e226f530fd5b406dbefc800cc53c35e31ad45b84cc20` (41 files)
- built entry: `src/antigravity_k/dashboard_dist/assets/index-BjO0ehSf.js`
- built entry SHA-256: `6f34e2ac4eee4680114937ebeda49a33775b31d7a3843e7103af58a555058121`
- capture manifest: `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json`
- capture manifest SHA-256: `f8e822702abfaed9e4630bb09774f7fdd80e477252cac8da8aa6671773e9b23a`
- capture readiness: `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md` (`READY`)
- capture hygiene: `docs/qa/2026-10-03-codex-ui/CAPTURE_HYGIENE.json`
- browser observations: `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`
- image diff: `docs/qa/2026-10-03-codex-ui/IMAGE_DIFF.json`
- source inspected: `dashboard/DESIGN.md`, `docs/frontend/CODEX_REFERENCE_2026-10-03.md`, `dashboard/src/styles/codex-workspace.css`, `dashboard/src/styles/workspace-shell.css`, `dashboard/src/styles/workspace-chat.css`, `dashboard/src/styles/workspace-inspection.css`, `dashboard/src/styles/workspace-pages.css`, `dashboard/src/pages/NotFoundPage.tsx`, `dashboard/src/pages/dex/ABTestSection.tsx`

## Direct image inspection coverage

I directly opened **all 69/69 current actual screenshots at original resolution** with the image viewer, not a sample. I also directly opened `baseline-768.png` and `actual-768.png` at original resolution.

Current actual IDs opened:

- 375×812 route/state set (29): `settings`, `models`, `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `generation`, `chat-complete`, `copy`, `model-menu`, `history`, `inspection-environment`, `inspection-code`, `inspection-changes`, `command-palette`, `shortcut-guide`, `navigation`, `status`.
- 768×900 route set (17): `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `settings`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `models`.
- 1280×900 route/state set (23): `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `settings`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `models`, `inspection-environment`, `inspection-code`, `inspection-changes`, `output`, `status-details`, `chat-complete`.

The manifest records all 69 as real JPEGs with the requested dimensions and valid signatures. Each capture has `documentWidth == viewport width`, `horizontalOverflowElements == 0`, and the latest `index-BjO0ehSf.js` as its live script. Fonts resolve to `-apple-system, system-ui, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, Malgun Gothic, sans-serif` in the browser observations. No tofu, missing-glyph boxes, descender clipping, black compositor regions, or capture dimension defects were visible.

## Blocking findings

1. **[product] [CJK wrapping] [high] One-character orphan in a primary mobile action.** In `captures/final-375-data-extraction.jpg`, the `A/B 테스트 실행` button wraps the final Korean word as `실` / `행`, leaving a one-character orphan on each line. This is a primary action and the split is immediately visible. It violates `dashboard/DESIGN.md` §5 (`Korean prose uses word-break:keep-all and natural spacing`) and the review requirement of no one-character or semantic-phrase fractures. Concrete fix: keep the action label unbroken (`white-space: nowrap` for this compact button), or stack/reflow the A/B section so the button receives enough inline width at 375px.

2. **[product] [CJK wrapping] [medium] A Korean word is split across lines on the mobile 404 page.** In `captures/final-375-not-found.jpg`, `주소가` is rendered as terminal `주` on one line and `소가` on the next. The source phrase in `dashboard/src/pages/NotFoundPage.tsx` is semantically intact; the rendered break is introduced by the page-wide combination of `word-break: keep-all` and `overflow-wrap: anywhere` in `dashboard/src/styles/workspace-pages.css`. This violates the same `dashboard/DESIGN.md` §5 natural Korean spacing requirement. Concrete fix: apply `overflow-wrap: normal` (or a prose-specific class) to the not-found paragraph while retaining `overflow-wrap:anywhere` only on the path/code token.

No `[evidence]` blocker was found.

## What passed

- The neutral near-black palette, restrained borders, muted secondary text, and lavender/green state accents form a coherent calm workspace across all widths.
- At 1280px the labelled navigation rail is stable and visually close to the intended 248px measure. The chat feed and rounded composer share a narrow centered measure consistent with the 760px contract.
- At 375px navigation becomes a labelled modal drawer; history, command palette, shortcut guide, model menu, status, and inspection states remain bounded and dismissible. No modal leaks past the viewport and no page produces horizontal scrolling.
- The chat composer remains readable and fully visible at 375, 768, and 1280. Tools wrap/redistribute without clipping; Korean placeholder and message copy use the intended larger chat scale.
- The earlier 375px Model Hub and Studio overflow class is visibly resolved. Cards, stepper items, filters, and settings fields stay inside viewport boundaries.
- Korean text generally uses a consistent system fallback with legible weight and leading. Apart from the two blockers above, I found no tofu, clipped glyphs, isolated punctuation, or conspicuous semantic phrase fractures.
- Route content, empty states, cards, controls, headings, and inspection/output panels are live DOM surfaces rather than pasted images. The current captures show no unexpected alpha/black-fill artifact.

## IMAGE_DIFF interpretation and complete hotspot map

`IMAGE_DIFF.json` reports `dimensionsMatch=true`, `totalPixels=691200`, `diffPixels=690971`, `diffRatio=0.9997`, `similarityScore=0`, `alphaChannelIntact=true`, and 64 hotspots. This compares the old SSAK baseline with the redesigned current workspace. It is evidence of the intended full palette/layout/state replacement, not an exact Codex Desktop fidelity score and not a failure by itself.

Every 8×8 hotspot grid cell was mapped after directly opening both images:

- Row `gridY=0`, columns `0,1,2,3,4,5,6,7`: old compact research-group header / narrow app chrome versus the new full-width workspace header and new background palette. Columns `3–7` are additionally old black unused canvas versus populated new header/canvas.
- Row `gridY=1`, columns `0,1,2,3,4,5,6,7`: old icon rail and narrow breadcrumb/user-bubble geometry versus the new workspace header and wide centered user message.
- Row `gridY=2`, columns `0,1,2,3,4,5,6,7`: old narrow assistant identity/message column versus the new open conversation canvas, typography, spacing, and full-width background.
- Row `gridY=3`, columns `0,1,2,3,4,5,6,7`: old token/message region and black unused right canvas versus the new wider conversation canvas; palette and content placement change across the entire row.
- Row `gridY=4`, columns `0,1,2,3,4,5,6,7`: old mostly empty narrow content/black area versus the new uniform elevated canvas and repositioned content.
- Row `gridY=5`, columns `0,1,2,3,4,5,6,7`: old empty narrow main surface/black right side versus the new full-width workspace canvas.
- Row `gridY=6`, columns `0,1,2,3,4,5,6,7`: old composer/context strip begins in the narrow left portion while the new layout keeps open canvas until its wide bottom composer; the remainder changes from black to the new background.
- Row `gridY=7`, columns `0,1,2,3,4,5,6,7`: old cropped composer/black unused region versus the current full-width rounded composer, context footer, and workspace background.

The listed groups cover all 64 hotspot coordinates exactly. The five slightly sub-1.0 regions (`0,0`, `1,0`, `2,0`, `0,1`, `1,1`) and four lower-ranked row-2 regions (`0,2`, `1,2`, `2,2`, `3,2`) share the same causes: both images retain dark pixels and some conversational content there, but use different palette values, geometry, and typography. The remaining listed cells have ratio `1.0` because the redesign changes essentially every pixel in those regions.

## Scope notes

- `Skills` and `Metrics` backend behavior is outside this visual pass; existing `401` behavior is unchanged and no backend pass is claimed.
- Private auth/profile flows were not exercised. The capture operator used the already unlocked root session; no PIN or credential interaction was performed.
- The `Git` route has state variation between widths (`UNKNOWN`/loading versus populated state), but each capture remains structurally bounded and readable. This is not treated as a visual blocker.

## Required revision evidence

After fixing the two CJK wrapping defects, recapture at minimum `final-375-data-extraction.jpg` and `final-375-not-found.jpg` from the same current bundle lineage and re-run capture hygiene. Final approval should still reference the complete current 69-image set, with the two replaced captures newer than the source change.
