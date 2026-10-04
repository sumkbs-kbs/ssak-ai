---
title: Core live chat visual review A
date: 2026-10-03
tags: [qa, visual, chat, cjk]
---

# Visual review A — BLOCK

**Verdict: BLOCK. Confidence: HIGH for the enumerated static states and source boundaries.** One product CJK phrase split remains in the 375px composer placeholder. The changed status/output boundary, Q15 Markdown formatting, control fit and observed horizontal geometry otherwise pass. This is the independent source/design-system pass; it does not certify the whole application or uncaptured interactions.

## Candidate and evidence validity

- HEAD independently read from Git: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Candidate label shared by `source-manifest.json`, `visual-manifest.json`, and Q15 DOM evidence: `fe56e724849ee35c42474898260eca60c7c2110ba8b63407ce400b2a9bd71031`.
- Independently recomputed all **40** source/test file SHA-256 values; every one matches the frozen source manifest. This verifies its selected file contents, including preserved prior user changes. It is not a claim that the candidate label is a Git commit or that unrelated dirty files were reviewed.
- Independently recomputed all **5** supplied image SHA-256 values; every one matches the visual manifest. `pre-copy-final-markdown-375.jpg` is byte-identical to `pre-copy-final-rest-375.jpg`, so there are **4 unique visual states**, all directly opened with `view_image` at original detail.
- Each JPEG has the correct `ffd8ff` signature, extension and independently checked dimensions. No incomplete compositor region was visible. JPEGs are opaque evidence; PNG alpha fidelity is inapplicable. The actual dark surfaces have no unexpected black/opaque patch in the inspected frames.
- The latest manifest production edit is `1791028675503824212` ns. Every image below has a later actual filesystem modification time. All selected source hashes still matched when this review checked them.

| Capture | State / dimensions | Exact SHA-256 | Actual mtime ns / freshness |
|---|---|---|---|
| `pre-copy-final-rest-375.jpg` | Q15 final, 375 × 900 | `fe611b78f5f709a1b30e725d2aa0024a2407c54e0eb9b68eb3c15540fbdb4a85` | `1791029163281740843`, fresh |
| `pre-copy-final-rest-768.jpg` | Q15 final, 768 × 900 | `6658b61ecf291151ed028ca8b6ba67c1b267c6a85f63ca69aede12eaf41c18cc` | `1791029172342934952`, fresh |
| `pre-copy-final-rest-1280.jpg` | Q15 final, 1280 × 900 | `26ee91b0e3cef231f7f992263267f977ed4ac9b2446bca443352874004c92b54` | `1791029213891740942`, fresh |
| `pre-copy-final-progress-375.jpg` | Q13 active quality revision, 375 × 900 | `f2ff7e5875e4dce2355570e648b1ce88bf32fa616094bafb85e1492ff8b24cd0` | `1791028822065546093`, fresh |
| `pre-copy-final-markdown-375.jpg` | Duplicate of Q15 final 375 | `fe611b78f5f709a1b30e725d2aa0024a2407c54e0eb9b68eb3c15540fbdb4a85` | `1791029163282343137`, fresh, verified duplicate |

The excluded baseline/retry/cancel images in the visual manifest were not used for this verdict: `baseline-memory-failure.jpg`, `baseline-tdd-policy-failure-375.jpg`, `retry-behavior-375.jpg`, `final-q08-375.jpg`, and `final-cancel-new-answer-375.jpg`. This review is not a screenshot clone or pixel-match exercise, so no image-diff similarity score or baseline target is claimed.

## Blocking finding

**[product] [CJK phrase integrity] BLOCK — isolated composer auxiliary at 375px.** In `pre-copy-final-rest-375.jpg` and `pre-copy-final-progress-375.jpg`, the empty composer at approximately x24–346 / y704–744 wraps the placeholder as `만들고 싶은 것, 수정할 내용, 궁금한 점을 적어` followed by `주세요`. The final auxiliary occupies its own line. It is visible and not clipped, but it splits the Korean verb/auxiliary phrase `적어 주세요`.

Source: `dashboard/src/components/Chat/ChatComposer.tsx:60` supplies that literal. `dashboard/src/styles/workspace-chat.css:82` uses the existing 16px chat size, Korean font stack and `word-break: keep-all`; that preserves each word but does not keep this multiword phrase together.

Rule applied: `omo:visual-qa` `SKILL.md`, Step 3 Pass B, explicitly treats a connective/auxiliary expression split across lines (example `쓸 수 / 있지만`) and an orphaned ending line as a blocking CJK finding. `dashboard/DESIGN.md` also requires natural Korean spacing and legible reflow at 375px. This is an existing placeholder detail exposed by the enumerated current states, not evidence that the stream-boundary changes introduced it. Its existing origin does not make the fresh visual gate pass.

Concrete narrow repair: replace the long placeholder with a natural short phrase such as `질문이나 작업 내용을 입력하세요`, keeping the font, tokens, textarea behavior and control arrangement. Verify the phrase on one line at 375px, then refresh the selected-source candidate and the complete finite capture set before a new independent approving review. No broader feature change is needed for this finding.

## Source and design-system integrity

Graph discovery used project `Users-mr.k-program-coding-ssak_comp-Ssak-Ai`, then exact `get_code_snippet` reads for `ChatPage`, `WorkingIndicator`, `ChatComposer` and `ChatMessageComponent`. CSS/token and Markdown contract reads used their known files. No production source, browser state or global setting was changed by this reviewer.

A parallel narrow read-only supporting audit independently confirmed token reuse and live DOM rendering in the status/user-wrap rules. It also identified inherited working-dot styling at `index.css:14481`: its color `#8b949e`, geometry and pulse timing remain hardcoded. That pre-existing detail limits the token-only claim to the changed text/wrap rules; it is not a new blocker for this finite cycle and has not been accepted as whole-app design-system compliance.

| Dimension | Result | Evidence |
|---|---|---|
| Real live component tree | PASS | `ChatPage.tsx:1409` maps real message state into `ChatMessage`; `ChatMessage.tsx:72` renders semantic articles, literal user text and live `ChatMarkdown`; `ChatComposer.tsx:56` renders the actual labelled textarea and native action buttons. No screenshot/raster substitute drives the reviewed surface. |
| Design-system continuity | PASS within changed boundary | `dashboard/DESIGN.md` records the calm conversation workspace, existing color/type scale and composer primitive. `index.css:6` supplies canonical semantic colors, `index.css:64` supplies the Korean/system sans stack, `index.css:106`–107 supplies the 760px measure and 16px prose size. `workspace-chat.css` consumes these variables; the new user wrapping/status shrink rules add layout constraints, without new font or color tokens. |
| Status separated from final answer | PASS | `ChatPage.tsx:774` sends status into `streamStatus` only; `ChatPage.tsx:778` replaces assistant content through the final-content callback and clears status. The separate `WorkingIndicator` is below message articles at `ChatPage.tsx:1413`. The final Q15 images show only the requested heading, two items and two-line code, with no working/quality text appended to that answer. |
| Working row fit | PASS | `ChatActivity.tsx:24` renders a live text status, a full-status `title`, and elapsed time as separate spans. `workspace-chat.css:111`–113 makes the row shrink, ellipsizes the label, and protects dots/time from shrink. The active 375px frame keeps `1m 14s` readable on the same row; the shortened status does not collide with the composer. |
| Title and tool/control fit | PASS for captured states | The narrow title uses ellipsis (`workspace-chat.css:7`). Header actions remain visible. Mobile composer actions occupy their own row (`workspace-chat.css:141`), leaving the selected model, microphone and Stop control visible. The active Stop button is clear at x315–351 / y803–840 and does not overlap the status/time row. Static captures prove fit, not activation or hover/focus behavior. |
| User paths and horizontal containment | PASS for supplied observed geometry / source | User spans use `max-width:100%` plus `overflow-wrap:anywhere` (`workspace-chat.css:31`), while the higher-specificity user bubble rule retains `max-width:86%`, `min-width:0` and `width:fit-content` (`workspace-chat.css:23`–29). The root's manifest observations are viewport/document 375/375, feed 364, user/client/scroll 332/332; documents at 768 and 1280 equal their viewport widths. The supplied bottom-of-feed screenshots do not expose the complete long-path prompt; that claim is bounded to root DOM geometry and the reviewed wrapping source. |
| Q15 content hierarchy | PASS | All three final viewport captures show `확인한 사실`, two distinct list bullets and a named `text` code block containing `첫 줄` and `둘째 줄` on separate lines. `final-markdown-dom.json` records the exact heading, both items, `첫 줄\n둘째 줄`, and document width 375 for this candidate. |
| CJK glyph/readability | PASS except blocker | Inspected heading, list text, code text, status and tool labels have no tofu, missing baseline, clipped glyph or overlap. The 375px placeholder phrase split above prevents an overall PASS. |
| Vertical ownership | PASS for captured resting/active states | Transcript stays above the docked composer, with an intentional transcript scrollbar. The top of the user message is outside the captured feed scroll position, not a compositing defect. `workspace-chat.css:16` names transcript scrolling; the composer is a nonshrinking sibling (`workspace-chat.css:65`). |

## Verification limits

The supplied logs record 425 backend tests passed with 2 environment-disabled skips and 182 frontend tests passed; the production build log ends in success with its existing large-bundle warning. These are corroborating supplied artifacts, not tests re-executed by this read-only visual reviewer. They do not resolve the pixel-visible CJK split.

This verdict covers only `/chat` final/rest at 375/768/1280 and active quality revision at 375. It does not certify whole-app layout, every Markdown/output type, retry/cancel behavior, approvals, reconnect behavior, keyboard/hover transitions, motion timing, Lighthouse scores or screen-reader operation. No baseline-failure image was treated as a target. A fresh independent review must judge the repaired candidate before the finite visual gate can pass.
