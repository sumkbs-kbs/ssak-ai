# Visual QA pass A — design-system and functional integrity

## Verdict

- **VERDICT: PASS**
- **CONFIDENCE: HIGH**
- **Review type:** fresh read-only design-system and functional-integrity pass
- **Blocking findings:** none
- **Product source reviewed:** `HEAD 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- **Evidence binding:** `SOURCE_MANIFEST.json` SHA-256 `83be9b42fb18a0a4a9d09e040e5e2133888f08da0e9ace723aaeb67827941c72`
- **Binding reproduction:** `git rev-parse HEAD` and `sha256sum SOURCE_MANIFEST.json` matched those values. Every one of the manifest's 62 file hashes was recomputed against the current workspace with zero mismatches.

The shipped surface satisfies the response-style brief: assistant answers use the documented system sans-serif stack and a coherent token-driven Markdown hierarchy, while code alone uses the mono stack. The response remains a live semantic DOM with working native disclosures, copy controls, preserved raw text, parser-bound sanitation, scoped horizontal overflow, and responsive layout at 375/768/1280px. The baseline is used only to disclose the intentional presentation change; it is not treated as a Codex Desktop pixel target.

## Intent and design-system assessment

The requested outcome is a Codex-compatible *response typography and Markdown treatment*, not a copy of proprietary Codex Desktop pixels or fonts. `dashboard/DESIGN.md` states that boundary explicitly and defines the assistant-response contract: 16px/1.7 system-sans prose, 18px headings, 13px mono fenced code, 14px tables, token spacing, native response details, bounded raw source, semantic Markdown, and internal overflow for code/tables.

The implementation is a reusable system rather than a screenshot or one-off mock:

- `src/styles/index.css` owns the canonical system font, type, spacing, color, radius, focus, and state tokens.
- `src/styles/workspace-response.css` scopes answer typography to `.workspace-chat` and consumes semantic variables. `STYLE_TOKEN_CHECK.json` found all 29 referenced tokens and no missing token.
- `ChatMessage.tsx`, `ChatMarkdown.tsx`, `ChatCodeBlock.tsx`, `MessageMetadata.tsx`, and `CopyButton.tsx` compose semantic articles, parsed Markdown, code primitives, native details, and announced copy states. No raster/background image stands in for response content.
- The same component path handles ordinary answers, streaming, fenced/unlabelled code, tables, blockquotes, links, failure/action content, and metadata. The images confirm reuse across the saved greeting and a real generated response.
- No added decorative motion exists. Streaming screenshots represent a real `Working` state and restored send/stop control rather than ornamental animation.

Fresh live-DOM measurements in `TYPOGRAPHY.json` reproduce the contract rather than inferring it from CSS: H1 is 18px/27px at weight 600; prose is 16px/27.2px at weight 400; inline/fenced code is 13px/22.1px in the mono stack; table headings are 14px/21px at weight 600; response summaries are 13px/19.5px. The measured long TypeScript `pre` is 707px wide with 1441px scroll width, directly confirming internal code overflow.

## Direct image review — complete inventory

I opened every file below with `view_image` at **original** detail. `CAPTURE_CHECK.json` independently records JPEG signatures, exact requested dimensions, SHA-256 values, viewport matches, and freshness against final source for all 26 manifest captures. The three baseline captures have the declared baseline exception; all 23 final/interaction/deliverable captures are post-final-source. No capture has a black compositor region, missing primary surface, wrong extension, or wrong viewport.

### 26 `CAPTURE_MANIFEST.json` originals

1. `before-greeting-1280.jpg` — baseline response decoration exposed in-body.
2. `before-greeting-768.jpg` — same baseline at tablet width.
3. `before-greeting-375.jpg` — same baseline at mobile width.
4. `after-greeting-1280.jpg` — open answer prose; metadata collapsed.
5. `after-info-1280.jpg` — native response information expanded.
6. `after-original-1280.jpg` — raw original nested disclosure expanded.
7. `after-greeting-768.jpg` — open answer prose at tablet width.
8. `after-info-768.jpg` — expanded metadata, readable two-column definition list.
9. `after-original-768.jpg` — bounded raw source at tablet width.
10. `after-greeting-375.jpg` — Korean prose wraps naturally; actions fit.
11. `after-info-375.jpg` — metadata reflows without page overflow.
12. `after-original-375.jpg` — raw source wraps within the bounded `pre`.
13. `stream-start-1280.jpg` — real Working 0s state and stop affordance.
14. `stream-progress-1280.jpg` — same run at 27s; stable layout.
15. `after-rich-top-1280.jpg` — preserved tool/artifact trace plus heading/body/list region.
16. `after-rich-code-1280.jpg` — labelled and unlabelled code, table, quote, link.
17. `after-rich-tail-1280.jpg` — tail controls and disclosure remain reachable.
18. `copy-typescript-1280.jpg` — actual copied state plus pasted TypeScript text.
19. `copy-unlabelled-1280.jpg` — actual copied state plus pasted unlabelled code.
20. `after-rich-top-768.jpg` — rich response reflows at tablet width.
21. `after-rich-code-768.jpg` — code owns horizontal scrolling; table fits.
22. `after-rich-tail-768.jpg` — quote/link/actions reachable at tail.
23. `after-rich-top-375.jpg` — narrow response uses full content width; code remains contained.
24. `after-rich-code-375.jpg` — table, quote, link, and actions remain readable.
25. `after-rich-tail-375.jpg` — tail state remains reachable above fixed composer.
26. `deliverable.jpg` — restored 757x954 default-window final state.

The manifest's `pageWidth` equals viewport width in all 26 records. Rich/code captures intentionally contain block-level code whose `scrollWidth` exceeds its `clientWidth`; the screenshots and CSS show that overflow belongs to the inner `pre`, while the page width remains fixed. This is the required overflow behavior, not primary-page clipping.

### Six comparison PNGs

All six were directly opened at original resolution: `comparisons/{before,after}-greeting-{375,768,1280}.png`. They are RGB conversions of the matching greeting captures. They show the intended transformation from in-body producer decoration and token pill to open answer prose with `응답 정보` disclosure. They do not suggest a pixel-match target. The live-status age also changes between the before/after moments and is legitimate dynamic content.

## All 55 image-diff hotspots mapped

The three diff files report matching dimensions and intact alpha. Similarities are 97/100 (1280), 95/100 (768), and 90/100 (375). Those scores are descriptive only. Every hotspot maps to intentional response hierarchy/removal/reflow or the live header age; none maps to an unexplained rendered defect.

| Width | Hotspots | Exact grid/region mapping | Interpretation |
|---:|---:|---|---|
| 1280 | 1–5 | `2,2 320,238 160x119 .3850`; `3,2 480,238 160x119 .3282`; `3,3 480,357 160x120 .2491`; `2,3 320,357 160x120 .2311`; `4,2 640,238 160x119 .1639` | Main response body/action zone: producer badge, quality line and token pill removed from prose; answer/action/disclosure compacted upward. |
| 1280 | 6–7,9,11 | `3,1 480,119 160x119 .1422`; `4,1 640,119 160x119 .1144`; `2,1 320,119 160x119 .0881`; `5,1 800,119 160x119 .0020` | User/answer vertical alignment and glyph anti-aliasing caused by the shorter response composition. |
| 1280 | 8,10 | `7,0 1120,0 160x119 .1045`; `6,0 960,0 160x119 .0293` | Dynamic `LIVE · now/age` header text between capture times. |
| 768 | 1–6,8,14 | `0,2 0,238 96x119 .5437`; `1,2 96,238 96x119 .5032`; `0,3 0,357 96x120 .2897`; `1,3 96,357 96x120 .2857`; `3,2 288,238 96x119 .2314`; `2,2 192,238 96x119 .1993`; `2,3 192,357 96x120 .1422`; `4,2 384,238 96x119 .0497` | Tablet response body/action zone: decoration removal, open prose, and compact footer reflow. |
| 768 | 7,9–10,12,16 | `3,1 288,119 96x119 .1493`; `1,1 96,119 96x119 .1219`; `2,1 192,119 96x119 .1214`; `0,1 0,119 96x119 .0929`; `4,1 384,119 96x119 .0086` | User/assistant vertical alignment and expected text anti-aliasing/reflow. |
| 768 | 11,13 | `6,0 576,0 96x119 .1193`; `7,0 672,0 96x119 .0826` | Dynamic server live-age text. |
| 768 | 15 | `0,6 0,715 96x119 .0483` | Composer caret/edge capture-time difference; composer geometry remains unchanged and in bounds. |
| 375 | 1–11,15,24,26 | `1,3 46,357 47x120 .6224`; `1,2 46,238 47x119 .6192`; `2,2 93,238 47x119 .6079`; `0,2 0,238 46x119 .5657`; `2,3 93,357 47x120 .5303`; `3,3 140,357 47x120 .4734`; `0,3 0,357 46x120 .4574`; `3,2 140,238 47x119 .3901`; `4,3 187,357 47x120 .3583`; `4,2 187,238 47x119 .2589`; `5,2 234,238 47x119 .2466`; `6,2 281,238 47x119 .0928`; `7,2 328,238 47x119 .0201`; `5,3 234,357 47x120 .0163` | Mobile response body/action zone. The narrower grid spreads the intended removal and vertical compaction across more cells; rendered answer and actions are fully readable. |
| 375 | 17–23,25 | `3,1 140,119 47x119 .0581`; `4,1 187,119 47x119 .0579`; `5,1 234,119 47x119 .0578`; `6,1 281,119 47x119 .0570`; `2,1 93,119 47x119 .0558`; `1,1 46,119 47x119 .0556`; `0,1 0,119 46x119 .0386`; `7,1 328,119 47x119 .0172` | User bubble and assistant position/glyph reflow from the reduced answer envelope. |
| 375 | 12–13,16 | `5,0 234,0 47x119 .1450`; `4,0 187,0 47x119 .1234`; `6,0 281,0 47x119 .0672` | Dynamic live-age/header text. |
| 375 | 14,27–28 | `0,6 0,715 46x119 .0987`; `0,4 0,477 46x119 .0080`; `1,4 46,477 47x119 .0078` | Composer caret/left edge and low-ratio downstream anti-aliasing caused by response height change; no horizontal page overflow. |

Count check: 11 + 16 + 28 = **55 mapped hotspots**.

## Functional integrity and semantic behavior

- **Native keyboard disclosure:** `MessageMetadata.tsx` uses nested native `<details>/<summary>` elements. The 768 evidence shows focus outlines and Enter/Space toggling; no custom keyboard emulation is required.
- **Copy correctness:** `COPY_RESULTS.json` records actual button click followed by actual Meta+V into an empty, unsent composer. Greeting prose, the full two-line TypeScript block, and the unlabelled block each match expected text exactly. `CopyButton.tsx` announces pending/success/error and only claims success after `clipboard.writeText` resolves.
- **Raw preservation:** `MessageMetadata` renders the original response as React text in a bounded `<pre>`. The original screenshots and `REAL_RESPONSE.txt` preserve the producer envelope, unexpected `write_artifact` log, artifact path, token line, and the model's missing newline before the first list item. The frontend does not rewrite that source.
- **History/model preservation:** `HISTORY_PRESERVATION.json` contains all seven prior conversations plus the new rich-response conversation and reports `allPreviousPresent: true`. The manual record confirms the selected model and empty input were retained.
- **Sanitizer boundary:** `responsePresentation.ts` uses the CommonMark/GFM parser's AST offsets to protect genuine code/inline-code ranges, sanitizes nonliteral HTML with DOMPurify and `style` forbidden, then accepts restored raw literals only when the final AST still classifies them as code. `ChatMarkdown` applies `rehype-sanitize` after raw Markdown processing. Rendered adversarial tests cover list continuation, malformed inline content, HTML blocks, footnotes, entity delimiters, fenced code, indented code, thoughts, and action content; they assert no model-controlled `style` or event handler reaches the DOM.
- **Responsive overflow:** CSS gives assistant content `min-width:0/max-width:100%`; tables use `.agk-table-container`; fenced code uses a bounded code block with `white-space:pre`. At 375px the page stays 375px and only the long code viewport scrolls horizontally.
- **Semantic/accessibility structure:** assistant messages are labelled `<article>` elements, Markdown produces real headings/lists/tables/blockquote/link elements, external links use `_blank` plus `noopener noreferrer`, focus uses the independent `--focus-ring`, and copy/error states include text rather than color alone.
- **Streaming and failures:** the two streaming images show stable Working state and a real stop action. Source inspection preserves the existing failure alert and delegated approval/preview action paths; focused tests cover both.
- **Browser health:** `BROWSER_LOGS.json` is an empty array; manual QA records no console warning/error or 503 during the real response.

## Programming and remove-ai-slops pass

I directly applied both perspectives to the scoped production code, CSS, and tests; the code-review report independently records the same coverage.

- No screenshot-only implementation, scattered response-specific raw colors/sizes, public API break, `any`, ignore directive, unsafe assertion, empty catch, debug output, or dead response path was found.
- `ChatMarkdown` and `ChatCodeBlock` are useful reusable seams: the extraction separated an existing large renderer into Markdown and code responsibilities and enables the same copy primitive for response and code actions. It is not speculative indirection.
- `responsePresentation` complexity is justified by a real parser/sanitizer boundary. The AST round-trip replaces the unsafe whitespace classifier described in the prior review; it is not unnecessary normalization.
- The tests assert observable DOM, clipboard, action, and sanitation behavior. They are not deletion-only tests, prose pins, tautologies, snapshots of constants, or implementation mirrors. Adversarial sanitation coverage prevents false confidence.
- No production module in this scoped response implementation exceeds the skill's 250 pure-LOC threshold.
- `CODE_REVIEW_FINAL.md` explicitly includes the `omo:programming` and `omo:remove-ai-slops` perspectives and specifically rules out deletion-only tests, prose pins, tautological expectations, implementation-constant mirrors, and disproportionate production complexity.

## Verification and evidence limits

`VERIFICATION.json` records 105 test files / 1,043 tests passing, plus TypeScript and Vite production build success. `CODE_REVIEW_FINAL.md` notes that a later package-manager wrapper rerun attempted a registry operation and could not replace those captured installed-executable results; this is a tooling limitation, not a UI failure. Biome was unavailable and is correctly reported rather than silently claimed.

The rich real response includes an unexpected model `write_artifact` trace and a missing newline before the first requested list item. Those are preserved model outputs and are explicitly outside this frontend typography contract. They are not approved fixture text and are not treated as frontend corruption.

## Findings

- **NOTE [evidence]** `after-rich-code-768.jpg` and `after-rich-tail-768.jpg` have the same SHA-256. The shared frame contains both the code/table and tail quote/link/actions, so every named visual region is still directly covered; this does not create a criterion gap.
- **NOTE [product]** The real model ignored its tool-use instruction and emitted artifact logs. The frontend correctly leaves operational/action content visible under the stated preservation contract.
- **NOTE [evidence]** Static screenshots cannot independently prove OS-level IME or Electron accessibility. `QA_SCOPE.md` explicitly excludes those claims; native disclosure keyboard behavior, browser focus, and DOM semantics are covered.

## Checked artifact paths

- `docs/qa/2026-10-03-response-style/{QA_SCOPE.md,MANUAL_QA.md,REAL_RESPONSE.txt,CAPTURE_MANIFEST.json,CAPTURE_CHECK.json,COPY_RESULTS.json,HISTORY_PRESERVATION.json,BROWSER_LOGS.json,VERIFICATION.json,STYLE_TOKEN_CHECK.json,TYPOGRAPHY.json,SOURCE_MANIFEST.json,CODE_REVIEW_FINAL.md}`
- `docs/qa/2026-10-03-response-style/captures/` — all 26 manifest JPEG originals and associated DOM captures where applicable
- `docs/qa/2026-10-03-response-style/comparisons/` — all six before/after PNGs and all three diff JSON files
- `dashboard/DESIGN.md`
- `dashboard/src/components/Chat/{ChatMessage.tsx,MessageMetadata.tsx,ChatMarkdown.tsx,ChatCodeBlock.tsx,CopyButton.tsx}`
- `dashboard/src/utils/{responsePresentation.ts,responsePresentation.test.ts}`
- `dashboard/src/components/Chat/__tests__/{ChatMessage.presentation.test.tsx,CopyButton.test.tsx}`
- `dashboard/src/styles/{index.css,codex-workspace.css,workspace-response.css}`

## What is good and must not regress

- The answer is visually open and readable while system decoration remains recoverable in a collapsed disclosure.
- Korean prose uses the local system stack with natural wrapping; code and metadata retain distinct, quieter scales.
- Genuine code remains literal/inert and copyable, including unlabelled blocks, while active HTML is sanitized.
- The transcript owns vertical scrolling, code/table own their necessary horizontal overflow, and the composer remains reachable.
- Raw storage and prior conversation history remain unchanged and inspectable.

## Blocking

None.
