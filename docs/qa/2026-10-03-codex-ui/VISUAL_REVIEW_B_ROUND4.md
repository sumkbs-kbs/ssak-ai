# Final visual QA Pass B — fidelity, layout, and CJK precision

**Verdict: REVISE**  
**Confidence: high**  
**Review type:** independent, read-only visual/CJK review

## User intent and reference boundary

The requested outcome is a readable, tidy SSAK-AI workspace inspired by the current Codex app: calm neutral surfaces, system sans typography with Korean fallbacks, a conversation-first composition, labelled desktop navigation, a centered transcript and fixed composer, and usable responsive controls and panels. No exact Codex Desktop screenshot or pixel target was supplied. The public `openai/codex` repository is a CLI/TUI reference, so this review does not claim a proprietary font copy or pixel-identical Desktop clone.

The visual contract is `dashboard/DESIGN.md` and `docs/frontend/CODEX_REFERENCE_2026-10-03.md`: 14px UI, 16px chat with 1.7 leading, a 248px desktop rail, a 760px conversation/composer measure, neutral tokens, system Korean fallbacks, responsive native controls, and real application states.

## Exact evidence binding

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Source manifest: 43 dirty files, declared SHA-256 `4abc26596d09679a03b0e5e077bc1fb97f9a72c7148fae59b484bcf95653ef75`.
- Main bundle: `/assets/index-CYlhq3Mt.js`, SHA-256 `57732b8b8b74c41b81681724d52ff6b797dbbb635a16c29453e4df4fa1ad86f2`.
- Main CSS: `/assets/index-eFoPJE3Q.css`, SHA-256 `5c177e1f3d82f3549c4b337734c9ecf6355f2781671ad58f2d3074cf25c7b75d`.
- Capture manifest: `CAPTURE_MANIFEST.json`, SHA-256 `190b37b471006e3e553bb1773ebe884cdd53354bb972998947f8fa9f32b5130c`.
- `LIVE_STYLE_BINDING.json` directly records the expected JS and CSS loaded by the page.
- `CAPTURE_HYGIENE.json` reports 70 valid JPEGs, exact dimensions, current bundle only, and all frames newer than all bound source edits.
- `TYPOGRAPHY_LIVE.json` measures the expected system/Korean stack, body 14px/21px, assistant 16px/27.2px, sidebar 248px, assistant measure 760px, and composer inner width 726px.

## Direct image review coverage

I directly opened **all 70/70 current screenshots at original resolution**, not a sample, plus `baseline-768.png` and `actual-768.png`.

- 375×812, 30: `model-menu`, `history`, `navigation`, `inspection-environment`, `command-palette`, `inspection-code`, `inspection-changes`, `shortcut-guide`, `status`, `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `settings`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `models`, `empty`, `generation`, `chat-complete`, `copy`.
- 768×900, 17: `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `settings`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `models`.
- 1280×900, 23: `home`, `chat-alias`, `studio`, `start`, `wiki`, `agent`, `settings`, `skills`, `data-extraction`, `git`, `history-page`, `plugins`, `mutation`, `hello-world`, `job-operations`, `not-found`, `models`, `inspection-environment`, `inspection-code`, `inspection-changes`, `output`, `status-details`, `chat-complete`.

This covers 17 routes at three widths and 19 extra states.

## Blocking finding

1. **[product] [responsive modal stacking] [high] Compact history and inspection render underneath the persistent shell header.** In `captures/final-375-history.jpg`, the history panel starts below/behind the 48px status header and its own modal header/close boundary is not visible. The same stacking is visible in `captures/final-375-inspection-environment.jpg`, `final-375-inspection-code.jpg`, and `final-375-inspection-changes.jpg`: the shell status row remains above the compact inspection layer. Source/DOM inspection confirms `.main-content` creates a `z-index:1` stacking context, trapping fixed descendants with local z-index 105/115 below the shell header at z-index 60. This violates `dashboard/DESIGN.md` §§4–5: compact inspection/history must present a labelled, dismissible modal boundary with its header reachable and must not be covered by shell chrome. Concrete fix: remove the unnecessary `.main-content` stacking context (for example `z-index:auto`) or portal the fixed overlays to a root stacking context above the shell header, then recapture all affected compact modal states.

No other `[product]` blocker and no final-state `[evidence]` blocker was found.

## CJK and layout results that passed

The two Round 2 CJK blockers are visibly resolved:

- `captures/final-375-data-extraction.jpg`: `A/B 테스트 실행` remains intact on one line; the row wraps without splitting `실` / `행`.
- `captures/final-375-not-found.jpg`: `주소가` remains intact while `/ui-qa-not-found` retains technical-token wrapping.

The data-extraction explanatory copy also keeps `만원/억원` intact. Across all 70 frames I found no tofu, missing-glyph box, clipped descender, semantic one-character Korean orphan, narrow heading fracture, primary-page horizontal overflow, composer clipping, or control-fit failure. Desktop and tablet composition, typography, neutral palette, centered transcript, fixed composer, operational pages, model cards, and docked inspection states satisfy the documented adaptive design contract.

The command-palette and shortcut-guide screenshots were captured during their 150ms entrance and therefore show transient panel opacity. A subsequent settled DOM measurement records the palette as opaque `rgb(24,24,24)` with opacity 1. This is a capture-timing note, not a product transparency defect and not used to excuse the separate stacking blocker.

`QA_DIRECTED_RESULTS_ROUND3.json` records PASS for reload/model/history restoration, forward/reverse focus wrapping with Escape focus return, and draft preservation during inspection-to-palette handoff. `LIVE_CHAT_RESULT.json` records the actual 27B reply, copy/clipboard match, and Shift+Enter newline. Native IME-device and fault-injection cases remain automated-only limitations; no private auth or PIN interaction is claimed.

## IMAGE_DIFF interpretation and complete hotspot map

`IMAGE_DIFF.json` reports `dimensionsMatch=true`, 768×900 on both sides, `totalPixels=691200`, `diffPixels=690969`, `diffRatio=0.9997`, `similarityScore=0`, `alphaChannelIntact=true`, and 64 cells. This is an old-vs-redesigned layout diagnostic, not a Codex fidelity score. Direct comparison shows the expected replacement of the old narrow terminal surface/black unused canvas with a full-width neutral workspace, wider conversation layout, new header, and fixed rounded composer, plus different live content.

Every 8×8 coordinate is mapped:

- `gridY=0`, `gridX=0–7`: old terminal header/narrow chrome and black right canvas versus the new full-width workspace header and charcoal canvas.
- `gridY=1`, `gridX=0–7`: old icon rail, breadcrumb, and narrow user bubble versus the new compact header and right-aligned user message.
- `gridY=2`, `gridX=0–7`: old narrow assistant column/unused canvas versus the new open transcript, typography, and wider placement.
- `gridY=3`, `gridX=0–7`: old token/message region and black right canvas versus the new transcript surface and relocated response metadata.
- `gridY=4`, `gridX=0–7`: old mostly empty narrow content/black area versus the new uniform workspace canvas.
- `gridY=5`, `gridX=0–7`: old empty narrow main/black right side versus the redesigned full-width canvas.
- `gridY=6`, `gridX=0–7`: old composer/context strip begins at the narrow left while the new layout remains open until its wider bottom composer.
- `gridY=7`, `gridX=0–7`: old cropped composer/unused region versus the current rounded composer, context footer, and workspace background.

These groups enumerate all 64 cells. The sub-1.0 cells `(0,0)`, `(1,0)`, `(2,0)`, `(0,1)`, `(1,1)`, `(0,2)`, `(1,2)`, `(2,2)`, and `(3,2)` retain some dark/conversation pixels in both versions but differ in palette, geometry, and type placement. Every other cell is 1.0 because the redesign changes essentially the whole region.

## Programming and slop perspective

I applied `omo:programming` and `omo:remove-ai-slops`. The completed CJK repair is a narrow class-hook/CSS correction with no parsing, normalization, unnecessary abstraction, duplicated logic, scope drift, or low-value test addition. There is no deletion-only, tautological, request-removal, or implementation-mirroring test. `CODE_REVIEW_ROUND3.md` independently records the same criteria and reports no blocker. The remaining stacking bug is a direct visual contract failure rather than an architecture preference.

## Limitations

- Skills/Metrics auxiliary `401` responses are reviewed only as displayed states; backend success is not claimed.
- Native Electron/IME-device automation, private auth, injected axe/Lighthouse scoring, and fault injection are outside this pass.
- This is an adaptive SSAK-AI review. No proprietary font or exact Desktop stylesheet was copied or claimed.

## Required revision evidence

After correcting the root stacking context, recapture at minimum the four affected 375px states (`history`, `inspection-environment`, `inspection-code`, `inspection-changes`) after the CSS edit and after transition settlement. The final approving round should bind a fresh complete 70-frame set to the new CSS hash and directly re-open all frames.
