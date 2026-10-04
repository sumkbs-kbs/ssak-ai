---
title: Core live chat visual review A
date: 2026-10-03
tags: [qa, visual, chat, cjk]
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
candidate_sha256: 35ed198037fc59f1458077cbb7ec4986118230642eb36351d2d655b0df912485
---

# Visual review A — PASS in finite scope

**Verdict: PASS. Blocking findings: none in the enumerated current captures. Confidence: HIGH for source/hash validity and the 375px copy repair; MEDIUM for larger JPEG visual detail.** The short composer placeholder fits one complete line at 375px in both the final and active states. The prior Korean auxiliary orphan is resolved. This is a fresh review of the entire current finite manifest, based on directly opened current images and current source; the previous report or another agent's report was not reused as a visual PASS.

## Candidate and evidence validity

- HEAD independently read from Git: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- All **41** selected source/test files were independently hashed from actual filesystem contents; every SHA-256 matches `source-manifest.json`.
- Independently recomputed the aggregate from those actual hashes in preserved manifest order: `sha256(json.dumps([(path, actual_sha256), ...], separators=(',', ':')).encode('utf-8'))`. It exactly equals `35ed198037fc59f1458077cbb7ec4986118230642eb36351d2d655b0df912485`, shared by the source manifest, visual manifest and after-copy Q15 DOM record.
- Composer SHA-256 is `137e25c6b9924289a782cbf1705b9462dbb7ede6a1e6e5db9c36875dacad459e`. The previous 40 selected files remain content-identical. This selected-file candidate includes preserved prior user changes; it is not a Git commit or whole-working-tree review.
- All **5** image SHA-256 values were independently recomputed and match the visual manifest. All five were directly opened with `view_image` at original detail. The final Markdown deliverable is byte-identical to final rest 375, giving **4 unique states**.
- All JPEGs have correct `ffd8ff` signatures and independently checked dimensions matching the requested viewports. No incomplete compositor region is visible. The frames are opaque JPEG evidence, so PNG alpha comparison is inapplicable; no unexpected opaque/black region is visible in the actual dark surfaces.
- Independently measured the latest selected production mtime as `1791029630475501722` ns, matching the visual manifest. Every current image's actual mtime is later.

| Capture | State / dimensions | Exact SHA-256 | Actual mtime ns |
|---|---|---|---|
| `final-rest-375.jpg` | Q15 final after copy, 375 × 900 | `19fe56ba5b0ce1f2670b884bb5f781a3547c78141ee4a04811eb716854f3b598` | `1791030503152878314` |
| `final-rest-768.jpg` | Q15 final after copy, 768 × 900 | `2b59bdb198f269f8c67998d26c2b6c2890d4dfcd78e34d8151830a807bb0c28d` | `1791030513445107738` |
| `final-rest-1280.jpg` | Q15 final after copy, 1280 × 900 | `e5d7eadab8722136cb57e95d8a50a651cbe02d0cf30b7b42ad71cba8309a8ae1` | `1791030522598185869` |
| `final-progress-375.jpg` | Q15 active Working… 0s / Stop after copy, 375 × 900 | `ec1dc7a5eb3404330c8d177cf00dae0f56fda32b37b794f1ee2b62e39285ed8b` | `1791030375014912577` |
| `final-markdown-375.jpg` | Q15 final 375 duplicate deliverable | `19fe56ba5b0ce1f2670b884bb5f781a3547c78141ee4a04811eb716854f3b598` | `1791030503153075440` |

The prior report was read before replacement and is preserved at `visual-review-a-before-copy.md`. Historical baseline, retry, cancel, pre-copy and Q08-after-copy images listed in the current manifest were excluded from this verdict. No old capture is a pixel target or current acceptance artifact. This is not clone/pixel-match QA, so no image-diff similarity score is claimed.

## Copy repair and CJK verification

`ChatComposer.tsx:60` now supplies the exact native textarea placeholder `질문이나 작업 내용을 입력하세요`. In both current 375px final and active captures, it appears on one complete line near x25–231 / y709. There is no isolated `주세요`, particle, final syllable, auxiliary or clipped baseline. The former `적어 / 주세요` split is absent from current pixels and the current source literal. The after-copy Q15 DOM record also reports this exact placeholder.

The 768px and 1280px captures retain the complete single-line placeholder. Heading, two item labels and both code lines show no visible tofu, CJK clipping or unnatural phrase orphan. The active user prompt wraps at complete-word boundaries; its complete short instruction clauses remain readable. These direct observations satisfy the loaded `omo:visual-qa` CJK rule for the enumerated content, without a claim about arbitrary future prose.

The form still renders the same native controlled textarea/ref, change/keyboard callbacks, accessible input name and hint. Its native streaming Stop button and trimmed-input Send branch remain wired at `ChatComposer.tsx:56`–93. Copy shortening does not replace the live form with a static mock.

## Fresh source/design and state checks

Structural discovery previously found the exact live symbols through the knowledge graph. On this fresh pass, exact graph snippet retrieval twice failed with `Transport closed`; the permitted fallback read the bounded known source files directly. Current `DESIGN.md` and `workspace-chat.css` were re-read and are byte-for-byte unchanged from their earlier full reads. Current token definitions and the live message/form/status branches were independently re-read. A parallel narrow source check corroborated the copy and wiring, but this verdict is based on this reviewer's direct source and image inspection.

| Dimension | Verdict and current evidence |
|---|---|
| Live DOM/component tree | **PASS.** `ChatPage.tsx:1409` maps message state to live `ChatMessage` articles; `ChatMessage.tsx:73` renders literal user text or real `ChatMarkdown`. `ChatComposer.tsx:56` renders a native textarea and action buttons. No raster/screenshot substitute appears in the inspected implementation. |
| Existing design-system contract | **PASS within the finite changed boundary.** `DESIGN.md` names the conversation canvas/composer, Korean system typography, 16px prose, tokenized neutral surfaces and bounded transcript. `workspace-chat.css:25`–39 uses these existing surface/text/type/spacing/radius variables. The copy repair introduces no font, color, token or layout rule. |
| Status separated from assistant output | **PASS.** Current `ChatPage.tsx:774` writes status only to `streamStatus`; final content at line 778 replaces assistant content and clears status. `WorkingIndicator` is a separate sibling below messages at line 1413. The fresh active capture displays Working… / 0s outside the message bubble, and all fresh final captures have only the requested final content. |
| Working/time/Stop fit | **PASS for the captured active default state.** Working… and 0s remain legible near y655 with no overlap. The 375px Stop control is clear at approximately x315–351 / y803–840 and separate from the status row. `ChatActivity.tsx:24`–30 renders text/title/time spans; `workspace-chat.css:111`–113 bounds and ellipsizes long labels while keeping time/dots from shrinking. This fresh set does not contain a long active status or minute-duration label, so those mechanical protections are source evidence, not a new runtime stress certification. |
| Title, tools and composer fit | **PASS in all current states.** The long narrow conversation title ellipsizes without covering header actions. At 375px the tools occupy the first toolbar row and model/mic/Send-or-Stop occupy the next; at 768/1280 the wider composer carries them together. No clipped label or overlapping control is visible. |
| Q15 hierarchy and whitespace | **PASS in all final viewports.** Exact heading `확인한 사실`, two bullets `첫 번째 항목` / `두 번째 항목`, and a named `text` code block containing `첫 줄` / `둘째 줄` appear separately. `final-markdown-dom-after-copy.json` records the exact heading, both items and `첫 줄\n둘째 줄` for this candidate. The code/action area stays inside the answer measure. |
| Horizontal containment | **PASS for current captured content.** Current manifest/root DOM observations report viewport/document widths 375/375, 768/768 and 1280/1280. All current frames fit their page bounds without visible primary-page horizontal overflow. `workspace-chat.css:23`–31 retains `min-width:0`, bounded user bubbles and `overflow-wrap:anywhere`. The fresh set does not expose a complete long-path stress prompt or a new user/client/scroll-width measurement, so no old 332px observation is reused as current evidence. |
| Vertical ownership | **PASS for current frames.** The transcript scrollbar and intentional feed scroll position are separate from the docked composer. The top of a user bubble is outside the final transcript scroll position; this is not partial compositing. `workspace-chat.css:16` gives the feed vertical scrolling and line 65 keeps the composer a nonshrinking sibling. |
| CJK/form typography | **PASS for enumerated content.** Existing `--font-sans` at `index.css:64`, `--chat-font-size` at line 107 and `workspace-chat.css:82` remain in effect. The shortened Korean phrase fits and has no orphan/clip; visible answer and tool text remains readable. Larger JPEG softness prevents fine raster/font-metric assurance. |

## Limited findings and verification limits

There are no product or evidence blockers for this finite current set. The larger JPEGs are visibly softer than the 375px frames. They are correctly sized, fully composited native captures, so layout/content fit is assessable; fine antialiasing, exact font metrics, single-pixel borders and pixel-perfect visual fidelity are not certified. Overall rendered-detail confidence remains MEDIUM.

Inherited working-dot styles at `index.css:14481` still contain hardcoded color/geometry/pulse timing. The changed status/user-wrap rules consume existing tokens, but this review does not assert that all legacy activity styling is token-only or accept whole-app design debt.

The supplied current after-copy frontend log records **202 passed / 22 files**, and the after-copy production build ends successfully with its existing large-bundle warning. Those artifacts were read, not re-executed by this reviewer. The prior backend result was 425 passed with 2 environment-disabled skips; the backend production files remain hash-identical, but no new backend run or runtime certification is claimed here.

This PASS covers only the entire current finite `/chat` manifest: Q15 final/rest 375/768/1280, Q15 active Working… 0s / Stop at 375, and the duplicate final375 deliverable. It does not certify whole-app design, every Markdown/output type, long-path or long-status runtime stress after the copy edit, retry/cancel, approvals, reconnect, hover/focus transitions, Stop activation, animation timing, Lighthouse scores or screen-reader operation. No production source, browser, server, test or global setting was changed by this read-only review. Only this owned report was replaced.
