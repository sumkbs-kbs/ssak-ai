---
title: Core live chat independent visual review B
date: 2026-10-03
tags: [qa, chat, visual-review, cjk]
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
candidate_sha256: 35ed198037fc59f1458077cbb7ec4986118230642eb36351d2d655b0df912485
verdict: PASS
confidence: MEDIUM
---

# Independent visual review B

**VERDICT: PASS for the finite captured `/chat` states. BLOCKING: none.**

The complete fresh set after the composer copy change shows a one-line placeholder, readable Korean text, intact Markdown structure, responsive chat layouts, and an active progress row that leaves elapsed time and Stop visible. This is a direct pixel review of the enumerated captures, independent of visual pass A and the source reviewer. It does not assert whole-app correctness, a pixel clone, motion quality, or the behavior of a clicked control.

## Evidence identity and hygiene

- Actual `git rev-parse HEAD`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Candidate: `35ed198037fc59f1458077cbb7ec4986118230642eb36351d2d655b0df912485`. Independently recomputed as SHA-256 of UTF-8 compact JSON containing the ordered `(path, sha256)` pairs in `source-manifest.json`; it matches both manifests. All 41 current source/test file contents independently hash to their recorded values, with zero mismatches.
- Independently checked all five image SHA-256 values, JPEG signatures, and dimensions. Opened all five files with `view_image` at original detail; four have unique pixel content because the Markdown deliverable duplicates the 375 rest capture.
- Actual latest production mtime is `1791029630475501722` ns, matching the manifest. Every image's current mtime matches its recorded value and is later than this final production edit. No manifest image has a missing or black compositor region.
- Skill applied: `/Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/4.19.4/skills/visual-qa/SKILL.md`.

| Actual capture | Dimensions | Independently verified SHA-256 | mtime ns |
|---|---|---|---|
| `final-rest-375.jpg` | 375 × 900 JPEG | `19fe56ba5b0ce1f2670b884bb5f781a3547c78141ee4a04811eb716854f3b598` | `1791030503152878314` |
| `final-rest-768.jpg` | 768 × 900 JPEG | `2b59bdb198f269f8c67998d26c2b6c2890d4dfcd78e34d8151830a807bb0c28d` | `1791030513445107738` |
| `final-rest-1280.jpg` | 1280 × 900 JPEG | `e5d7eadab8722136cb57e95d8a50a651cbe02d0cf30b7b42ad71cba8309a8ae1` | `1791030522598185869` |
| `final-progress-375.jpg` | 375 × 900 JPEG | `ec1dc7a5eb3404330c8d177cf00dae0f56fda32b37b794f1ee2b62e39285ed8b` | `1791030375014912577` |
| `final-markdown-375.jpg` | 375 × 900 JPEG | `19fe56ba5b0ce1f2670b884bb5f781a3547c78141ee4a04811eb716854f3b598` | `1791030503153075440` |

## Pixel observations

| Dimension | Result | Evidence trace |
|---|---|---|
| Typography and CJK | PASS within captured copy | In all rest captures, `확인한 사실`, both list items, and `첫 줄` / `둘째 줄` remain readable, with no visible tofu, missing glyphs, clipped baselines, or orphaned syllables. `질문이나 작업 내용을 입력하세요` fits on one line in the composer at 375, 768, and 1280, and in the active 375 frame. Header title ellipsis is contained within its available space. |
| Working progress, time, and Stop | PASS for visible active frame | At 375, `Working... 0s` is a distinct muted row directly above the composer, near y=654. Both label and elapsed time are visible. The white circular Stop control remains fully visible near the lower-right corner of the composer. Neither overlaps the feed. This current short label does not test long status truncation. |
| Answer versus status | PASS | In the active capture, the prior answer and the new multiline user request remain in the feed while the Working row sits below the request. In the final captures, the rendered answer contains the heading, list, and code block without Working prose becoming part of the answer. |
| Header, content, composer rhythm | PASS | Both top bars stay aligned and leave room for the chat toolbar at 375 and 768. The desktop sidebar occupies a separate column at 1280. The answer/code block and composer have distinct spacing and surfaces. The mobile composer uses additional vertical height to accommodate its controls, and the wider composers arrange those controls in one lower row. |
| Responsive layout | PASS for 375 / 768 / 1280 frames | No visible horizontal clipping or overlap occurs in the feed, code-block header, copy control, composer, or footer. The sidebar is absent at 375/768 and visible at 1280. These pixels are consistent with the manifest's recorded document widths of exactly 375/768/1280; this review did not operate the browser to remeasure DOM geometry. |
| Multiline text and Markdown | PASS for captured cases | The active 375 frame shows a naturally wrapped Korean request with complete words/phrases and no orphaned syllable or horizontal overflow. Each rest frame shows a rendered heading, two bullets, and a bordered `text` code block with two separate Korean lines. The mobile code block fits its container, and its language/copy header does not collide. Fresh `final-markdown-dom-after-copy.json`, stamped to this candidate at `2026-10-03T12:28:23.159Z`, separately records heading `확인한 사실`, both list items, code text `첫 줄\n둘째 줄`, and the new placeholder, consistent with the pixels. |

## Findings and limits

No actionable product defect is visible in this finite capture set. No blocking finding is recorded.

JPEG compression/softening is visible, most strongly in the 1280 capture. It limits confidence in fine font rasterization, exact glyph edges, and exact contrast or pixel-distance assertions; the layout and text structure remain assessable. No reference image-diff was run because the supplied task has no acceptance baseline or clone target. Dark regions are the coherent dark theme, not missing capture regions. The feed is scrolled to the end of the conversation, so the top of the prior user bubble is outside the captured scroll position.

Static images establish the visibility of progress, time, and Stop, not timer evolution, Stop activation, transitions, or scrolling behavior. The Markdown sample has short code lines; this current set does not certify long status truncation, very long answers, arbitrarily long unbroken code tokens, or long CJK prose. Source/font tokens were stated as unchanged for this core cycle; this pixel pass does not independently compare their historical values.

The prior version of this report was read before updating it. Only the complete current five-image manifest set was used for acceptance. Excluded baseline-memory/TDD failures, older retry/cancel/Q08 captures, pre-copy captures, and transient replaced resize/fullPage captures were not used. The old `final-markdown-dom.json` was not used for this candidate. Retry, approval, reconnect, and other routes remain outside this visual verdict.
