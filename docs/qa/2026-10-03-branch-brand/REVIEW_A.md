# Reviewer A — footer branch display alias

## Verdict

**PASS** — no blocking product or evidence finding in the stated scope.

## Scope and binding

- Reviewed only the requested chat-footer presentation rule: an actual branch beginning `codex/` is displayed as `ssak-ai/`; the stored value is not changed, and the exact value remains available in the native title.
- Source/evidence binding reproduced: `HEAD=8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; `SOURCE_MANIFEST.json` SHA-256 is `ad74348cdff8d1c1ee95c545f8424b0c762acd9a6f9df292c98fb398082a7327`. Its current hashes match `ChatPage.tsx=8dd7cd8d3e5ea920973b73c2dab2aa65b482f96fbb44b445820e1fcd9fc247fe` and `DESIGN.md=acf4eaf7dc081b467854f5c50c5a0f829d058f93602f896f24666da26a2a24ef`.
- `TASK_DELTA.patch` contains exactly the intended task delta: one DESIGN contract line and one footer JSX line. The JSX uses anchored `replace(/^codex\//, 'ssak-ai/')`, so other prefixes and an interior `codex/` are left alone. The source value remains `workspaceContext.branch`; the title interpolates that unmodified value.
- This remains real reused DOM: the existing `.context-item`, `AppIcon`, and `.item-text.branch` primitives are retained. Existing responsive CSS provides `min-width:0`, nowrap/ellipsis, and bounded branch widths; no raster/mock substitution, one-off style, new parser, normalization layer, extraction, animation, or implementation-mirroring test was added.
- The built artifact manifest is bound to the same source manifest and identifies `ChatPage-B-sPUKRj.js`. Verification records successful `tsc -b` plus Vite build and unchanged protected branch/data files.

## Direct image inventory (13/13 opened at original detail)

Original captures: `before-375.jpg`, `before-768.jpg`, `before-1280.jpg`, `after-375.jpg`, `after-768.jpg`, `after-1280.jpg`, `deliverable.jpg`.

Comparison PNGs: `before-375.png`, `before-768.png`, `before-1280.png`, `after-375.png`, `after-768.png`, `after-1280.png`.

All signatures and dimensions match their extensions/declared viewports and every frame is fully composited. The three before captures are the documented baseline exception. The four after originals are newer than the final source edit and show the final bundle. The six PNGs reproduce their paired JPEG frames as decoded RGB references.

## Visual and responsive result

| Width | Before → after | Bounds / viewport | Verdict |
|---|---|---|---|
| 375×954 | `codex/m1-task-events` → `ssak-ai/m1-task-events` | x=162.98, width=134.84, right=297.83 < 375 | Fits; no clipping, overlap, or horizontal page overflow |
| 768×954 | same | x=174.98, width=134.84, right=309.83 < 768 | Fits; footer hierarchy and composer unchanged |
| 1280×954 | same | x=534.98, width=134.84, right=669.83 < 1280 | Fits; desktop footer remains aligned |
| 757×954 deliverable | final label present | x=174.98, width=134.84, right=309.83 < 757 | Fits; clean final presentation |

The after measurements record `title="실제 Git 브랜치: codex/m1-task-events"` at every width. Thus the user-visible alias is presentation-only and the exact branch remains discoverable. No CJK clipping, orphaning introduced by this label, missing glyph, opaque/black compositor defect, or unexpected alpha issue is visible.

## Complete hotspot accounting

- **375 diff (8/8):** top-row grids `(4,0)`, `(5,0)`, `(6,0)` are the live server clock changing between captures; footer grids `(3,7)`, `(4,7)`, `(5,7)`, `(6,7)` cover the intended longer `ssak-ai/` label and its antialiasing; `(5,2)` is a minute capture-state/raster difference around the narrow-page content/scroll region. Direct before/after inspection shows no structural or content regression there. Dimensions match, alpha is intact, similarity is 99, diff ratio 0.0118.
- **768 diff (3/3):** bottom grids `(1,7)`, `(2,7)`, `(3,7)` span the footer label and adjacent antialiasing only. Dimensions match, alpha is intact, similarity is 100, diff ratio 0.0030.
- **1280 diff (17/17):** left/sidebar state accounts for `(0,0)`, all `(0,1..7)`, and `(1,0..5,7)` listed by the JSON: the before frame retained an older sidebar scroll position while the after reload returned it to the initial position. Footer grids `(3,7)` and `(4,7)` contain the intended label replacement. Direct inspection confirms the main conversation, composer, and footer layout are otherwise stable; the top server clock is also live data. Dimensions match, alpha is intact, similarity is 93, diff ratio 0.0686. These differences are capture state, not a product change from the scoped patch.

## Limitations

This is a deliberately narrow read-only review of the chat footer at the enumerated four after states plus three baselines and six comparison conversions. It does not claim a full-app, Lighthouse, accessibility-suite, OS/IME, hover-tooltip popup, or arbitrary long-branch audit. The native title value is supported by source and DOM measurement metadata rather than a screenshot of the browser tooltip bubble.
