# Visual QA Pass B — Visual Fidelity and CJK Precision

**VERDICT: REVISE**  
**CONFIDENCE: HIGH**

## Summary

The response surface is a substantial visual improvement and the implementation matches the documented typography contract: assistant prose is 16px/1.7, H1/H2 is 18px/600, code is 13px, tables are 14px, and metadata is 13px. Code owns horizontal scrolling, tables remain contained, the transcript has no primary horizontal overflow, disclosures are readable, and Korean glyphs are intact across 375/768/1280px.

One narrow-screen CJK/emoji wrapping defect blocks this focused visual pass. At 375px, the ordinary greeting ends with `😊` alone on a new line in `after-greeting-375`, and the same orphan persists in the open information and open original states. The DOM contains one intact paragraph, so this is presentation rather than source content. The scoped response rule combines inherited `word-break: keep-all` with `overflow-wrap: anywhere`, permitting the trailing emoji to detach even though the phrase can be reflowed more naturally. This violates the design contract's “Korean prose uses word-break:keep-all and natural spacing” requirement.

The model-generated first list item being joined to the preceding paragraph is not counted as a frontend defect: `REAL_RESPONSE.txt` has no separating newline, and the UI preserves that exact source. The visible tool/artifact log is likewise preserved operational content rather than a style fixture.

## Blocking finding

- **[product] [CJK/reflow] [medium]** At 375px the final `😊` is orphaned on a line by itself in `after-greeting-375`, `after-info-375`, and `after-original-375`. Evidence: original-detail images at `captures/after-greeting-375.jpg`, `captures/after-info-375.jpg`, and `captures/after-original-375.jpg`; DOM paragraph at `captures/after-greeting-375.dom.txt:20`; source interaction at `dashboard/src/styles/workspace-chat.css:36` (`word-break: keep-all`) and `dashboard/src/styles/workspace-response.css:1-8` (`overflow-wrap: anywhere`). Fix the ordinary assistant-prose wrapping policy so punctuation/emoji remains with the preceding Korean phrase while retaining emergency wrapping for genuinely unbreakable strings, then recapture all three 375px greeting states.

## What is good

- All reviewed frames are fully composited with no black/missing capture regions. `CAPTURE_CHECK.json` reports correct JPEG/PNG signatures, exact viewport dimensions, and freshness against final source.
- Source binding reproduced: HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; `SOURCE_MANIFEST.json` SHA-256 `83be9b42fb18a0a4a9d09e040e5e2133888f08da0e9ace723aaeb67827941c72`.
- Typography evidence (`TYPOGRAPHY.json`) matches `dashboard/DESIGN.md`: H1 18px/27px/600, prose 16px/27.2px, code 13px/22.1px, table headers 14px/21px, summaries 13px/19.5px. The system Korean fallback stack is consistently used and glyph rendering is intact.
- The neutral, open assistant canvas reads as a Codex-like answer treatment without asserting or attempting an exact proprietary Desktop clone. Metadata is quiet and progressively disclosed.
- Rich Markdown is legible at every breakpoint. Heading hierarchy, inline code, the real list item, labelled and unlabelled fenced code, table, quote, and link remain visually distinct. At 375px, long code stays inside its own horizontal scroller; measured PRE overflow is intentional internal overflow, not page overflow.
- Expanded `응답 정보` and `원문 보기` states remain contained and readable at all three widths. The 375px raw pre wraps inside its bounded region without clipping.
- Working start/progress frames show the concise live status and retained stop action without layout corruption. Copy-success frames show clear, localized feedback.
- Copy evidence preserves the greeting emoji and exact labelled/unlabelled code; history evidence retains all seven previous conversations and adds only the QA conversation.

## Original captures reviewed at original detail (26/26)

`before-greeting-1280`, `before-greeting-768`, `before-greeting-375`; `after-greeting-1280`, `after-info-1280`, `after-original-1280`; `after-greeting-768`, `after-info-768`, `after-original-768`; `after-greeting-375`, `after-info-375`, `after-original-375`; `stream-start-1280`, `stream-progress-1280`; `after-rich-top-1280`, `after-rich-code-1280`, `after-rich-tail-1280`; `copy-typescript-1280`, `copy-unlabelled-1280`; `after-rich-top-768`, `after-rich-code-768`, `after-rich-tail-768`; `after-rich-top-375`, `after-rich-code-375`, `after-rich-tail-375`; `deliverable` (757×954).

All `CAPTURE_MANIFEST.json` fields were consumed for each entry: name, phase, absolute path, capturedAt, viewport/page width, scripts, styles, and every measured block's tag/class/color/font/size/line/geometry/clientWidth/scrollWidth/text. The three baseline captures intentionally use the earlier JS/CSS assets; all after/interaction/deliverable captures use `index-CEGI_KeS.js` and `index-Btu4ZXQb.css`.

## Comparison images reviewed at original detail (6/6)

`comparisons/before-greeting-375.png`, `after-greeting-375.png`, `before-greeting-768.png`, `after-greeting-768.png`, `before-greeting-1280.png`, `after-greeting-1280.png`.

The before/after images show the intended structural change: producer decoration, quality, and token records move from the primary answer into a quiet disclosure, while the greeting remains primary prose. Similarity values are descriptive only. Header-time pixels and response relocation account for the broad diff; they are not a proprietary fidelity target.

## Hotspot trace (55/55)

Every hotspot was inspected against the paired images and source/DOM. Coordinates are `x,y,width,height`; ratios are the JSON region ratios.

### 375px — 28 regions

1. `46,357,47,120` 0.6224 — removed legacy token badge / relocated footer zone; intended.
2. `46,238,47,119` 0.6192 — legacy assistant label/decorated response replaced by open prose; intended.
3. `93,238,47,119` 0.6079 — same response-body relocation; intended.
4. `0,238,46,119` 0.5657 — left edge of old decorated response versus new prose; intended.
5. `93,357,47,120` 0.5303 — old token/footer versus new action/disclosure placement; intended.
6. `140,357,47,120` 0.4734 — old token/footer versus empty canvas; intended.
7. `0,357,46,120` 0.4574 — old token/footer/action zone; intended.
8. `140,238,47,119` 0.3901 — greeting relocation; intended.
9. `187,357,47,120` 0.3583 — old token badge tail; intended.
10. `187,238,47,119` 0.2589 — greeting relocation; intended.
11. `234,238,47,119` 0.2466 — greeting tail; includes the new orphaned emoji presentation and contributes to the blocking finding.
12. `234,0,47,119` 0.1450 — live timestamp/header time change; expected live-state variation.
13. `187,0,47,119` 0.1234 — live status/header time change; expected.
14. `0,715,46,119` 0.0987 — composer caret/scrollbar state; expected interaction-state variation.
15. `281,238,47,119` 0.0928 — greeting/action tail; intended structure.
16. `281,0,47,119` 0.0672 — header status/time variation; expected.
17. `140,119,47,119` 0.0581 — unchanged user bubble anti-aliasing/state timing.
18. `187,119,47,119` 0.0579 — unchanged user bubble anti-aliasing/state timing.
19. `234,119,47,119` 0.0578 — unchanged user bubble anti-aliasing/state timing.
20. `281,119,47,119` 0.0570 — unchanged user bubble anti-aliasing/state timing.
21. `93,119,47,119` 0.0558 — unchanged user bubble anti-aliasing/state timing.
22. `46,119,47,119` 0.0556 — unchanged user bubble anti-aliasing/state timing.
23. `0,119,46,119` 0.0386 — title/user-bubble edge and anti-aliasing.
24. `328,238,47,119` 0.0201 — right edge of content; no clipping or page overflow.
25. `328,119,47,119` 0.0172 — user-bubble right edge; no clipping.
26. `234,357,47,120` 0.0163 — minor old/new footer anti-aliasing.
27. `0,477,46,119` 0.0080 — empty canvas/background; no defect.
28. `46,477,47,119` 0.0078 — empty canvas/background; no defect.

### 768px — 16 regions

1. `0,238,96,119` 0.5437 — decorated label/body removed; greeting/action relocation intended.
2. `96,238,96,119` 0.5032 — same response relocation; intended.
3. `0,357,96,120` 0.2897 — legacy token/footer zone removed; intended.
4. `96,357,96,120` 0.2857 — same; intended.
5. `288,238,96,119` 0.2314 — old greeting/decorations versus open prose; intended.
6. `192,238,96,119` 0.1993 — old greeting/decorations versus open prose; intended.
7. `288,119,96,119` 0.1493 — user bubble/text anti-aliasing and timing.
8. `192,357,96,120` 0.1422 — old token badge tail; intended removal.
9. `96,119,96,119` 0.1219 — user bubble/text anti-aliasing.
10. `192,119,96,119` 0.1214 — user bubble/text anti-aliasing.
11. `576,0,96,119` 0.1193 — header LIVE timestamp change; expected.
12. `0,119,96,119` 0.0929 — title/user content edge; no defect.
13. `672,0,96,119` 0.0826 — header LIVE timestamp change; expected.
14. `384,238,96,119` 0.0497 — greeting end/actions; no clipping or orphan at 768px.
15. `0,715,96,119` 0.0483 — composer caret state; expected.
16. `384,119,96,119` 0.0086 — user bubble edge; no defect.

### 1280px — 11 regions

1. `320,238,160,119` 0.3850 — old assistant label/decorations replaced by open prose; intended.
2. `480,238,160,119` 0.3282 — greeting relocation; intended.
3. `480,357,160,120` 0.2491 — legacy token/footer removed; intended.
4. `320,357,160,120` 0.2311 — legacy token/footer removed; intended.
5. `640,238,160,119` 0.1639 — greeting/action tail; intended and unclipped.
6. `480,119,160,119` 0.1422 — user bubble/text anti-aliasing.
7. `640,119,160,119` 0.1144 — user bubble/text anti-aliasing.
8. `1120,0,160,119` 0.1045 — header LIVE timestamp variation; expected.
9. `320,119,160,119` 0.0881 — user bubble/text anti-aliasing.
10. `960,0,160,119` 0.0293 — header LIVE timestamp variation; expected.
11. `800,119,160,119` 0.0020 — user bubble right edge; no defect.

## Evidence reviewed

- `QA_SCOPE.md`, `MANUAL_QA.md`, `REAL_RESPONSE.txt`, `COPY_RESULTS.json`, `HISTORY_PRESERVATION.json`, `VERIFICATION.json`, `STYLE_TOKEN_CHECK.json`, `TYPOGRAPHY.json`, `CAPTURE_CHECK.json`, `CAPTURE_MANIFEST.json`, `SOURCE_MANIFEST.json`.
- `dashboard/DESIGN.md`, `dashboard/src/styles/workspace-response.css`, `dashboard/src/styles/workspace-chat.css`, `dashboard/src/styles/codex-workspace.css`, `dashboard/src/styles/index.css`.
- `dashboard/src/components/Chat/ChatMessage.tsx`, `MessageMetadata.tsx`, and captured DOM snapshots for all states.
- `comparisons/diff-375.json`, `diff-768.json`, `diff-1280.json`, including all scalar fields and all 55 hotspots.

## Blocking

1. `[product]` Repair and re-evidence the 375px ordinary assistant-prose wrap so the trailing emoji is not isolated from the greeting. Required recaptures: greeting collapsed, response information open, and original open at 375×954.
