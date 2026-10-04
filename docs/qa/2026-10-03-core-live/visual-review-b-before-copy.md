---
title: Core live chat independent visual review B
date: 2026-10-03
tags: [qa, chat, visual-review, cjk]
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
candidate_sha256: fe56e724849ee35c42474898260eca60c7c2110ba8b63407ce400b2a9bd71031
verdict: PASS
confidence: MEDIUM
---

# Independent visual review B

**VERDICT: PASS for the finite captured `/chat` states. BLOCKING: none.**

The frozen images show readable Korean text, intact Markdown structure, responsive chat layouts, and an active progress row that leaves elapsed time and Stop visible. This is a direct pixel review of the enumerated captures, independent of visual pass A and the source reviewer. It does not assert whole-app correctness, a pixel clone, motion quality, or the behavior of a clicked control.

## Evidence identity and hygiene

- Actual `git rev-parse HEAD`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Candidate: `fe56e724849ee35c42474898260eca60c7c2110ba8b63407ce400b2a9bd71031`. Independently recomputed as SHA-256 of UTF-8 compact JSON containing the ordered `(path, sha256)` pairs in `source-manifest.json`; it matches. All 40 current source/test file contents independently hash to their recorded values, with zero mismatches.
- Independently checked all five image SHA-256 values, JPEG signatures, and dimensions. Opened all five files with `view_image` at original detail; four have unique pixel content because the Markdown deliverable duplicates the 375 rest capture.
- Actual latest production mtime is `1791028675503824212` ns, matching the manifest. Every image's current mtime matches its recorded value and is later than this final production edit. No manifest image has a missing or black compositor region.
- Skill applied: `/Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/4.19.4/skills/visual-qa/SKILL.md`.

| Actual capture | Dimensions | Independently verified SHA-256 | mtime ns |
|---|---|---|---|
| `pre-copy-final-rest-375.jpg` | 375 × 900 JPEG | `fe611b78f5f709a1b30e725d2aa0024a2407c54e0eb9b68eb3c15540fbdb4a85` | `1791029163281740843` |
| `pre-copy-final-rest-768.jpg` | 768 × 900 JPEG | `6658b61ecf291151ed028ca8b6ba67c1b267c6a85f63ca69aede12eaf41c18cc` | `1791029172342934952` |
| `pre-copy-final-rest-1280.jpg` | 1280 × 900 JPEG | `26ee91b0e3cef231f7f992263267f977ed4ac9b2446bca443352874004c92b54` | `1791029213891740942` |
| `pre-copy-final-progress-375.jpg` | 375 × 900 JPEG | `f2ff7e5875e4dce2355570e648b1ce88bf32fa616094bafb85e1492ff8b24cd0` | `1791028822065546093` |
| `pre-copy-final-markdown-375.jpg` | 375 × 900 JPEG | `fe611b78f5f709a1b30e725d2aa0024a2407c54e0eb9b68eb3c15540fbdb4a85` | `1791029163282343137` |

## Pixel observations

| Dimension | Result | Evidence trace |
|---|---|---|
| Typography and CJK | PASS within captured copy | In all rest captures, `확인한 사실`, both list items, and `첫 줄` / `둘째 줄` remain readable, with no visible tofu, missing glyphs, clipped baselines, or orphaned syllables. At 375, the composer placeholder wraps into two readable lines, ending with the intact word `주세요`. Header title ellipsis is contained within its available space. |
| Working progress, time, and Stop | PASS for visible active frame | At 375, the quality/revision status is a separate muted row directly above the composer, near y=654. Its long label ends with an ellipsis; `1m 14s` remains visible on the same row. The white circular Stop control remains fully visible near the lower-right corner of the composer. Neither control overlaps the feed. |
| Answer versus status | PASS | In the active capture, answer lines 284–300 occupy the feed; the copy action follows the answer, and the progress row is below it. In the final captures, the rendered answer contains the heading, list, and code block without progress prose becoming part of the answer. |
| Header, content, composer rhythm | PASS | Both top bars stay aligned and leave room for the chat toolbar at 375 and 768. The desktop sidebar occupies a separate column at 1280. The answer/code block and composer have distinct spacing and surfaces. The mobile composer uses additional vertical height to accommodate its controls, and the wider composers arrange those controls in one lower row. |
| Responsive layout | PASS for 375 / 768 / 1280 frames | No visible horizontal clipping or overlap occurs in the feed, code-block header, copy control, composer, or footer. The sidebar is absent at 375/768 and visible at 1280. These pixels are consistent with the manifest's recorded document widths of exactly 375/768/1280; this review did not operate the browser to remeasure DOM geometry. |
| Long output and Markdown | PASS for captured cases | The active frame shows the tail of a 300-line answer with steady line alignment and a visible composer. Each rest frame shows a rendered heading, two bullets, and a bordered `text` code block with two separate Korean lines. The mobile code block fits its container, and its language/copy header does not collide. `final-markdown-dom.json` separately records heading `확인한 사실`, both list items, and code text `첫 줄\n둘째 줄`, consistent with the pixels. |

## Findings and limits

No actionable product defect is visible in this finite capture set. No blocking finding is recorded.

JPEG compression/softening is visible, most strongly in the 1280 capture. It limits confidence in fine font rasterization, exact glyph edges, and exact contrast or pixel-distance assertions; the layout and text structure remain assessable. No reference image-diff was run because the supplied task has no acceptance baseline or clone target. Dark regions are the coherent dark theme, not missing capture regions. The feed is scrolled to the end of the conversation, so the top of the prior user bubble is outside the captured scroll position.

Static images establish the visibility of progress, time, and Stop, not timer evolution, Stop activation, transitions, or scrolling behavior. The Markdown sample has short code lines; this review does not certify arbitrarily long unbroken code tokens or long CJK prose. Source/font tokens were stated as unchanged for this core cycle; this pixel pass does not independently compare their historical values.

The excluded baseline-memory/TDD failures, older retry/cancel/Q08 captures, and transient replaced resize/fullPage captures were not used as acceptance evidence. Retry, approval, reconnect, and other routes remain outside this visual verdict.
