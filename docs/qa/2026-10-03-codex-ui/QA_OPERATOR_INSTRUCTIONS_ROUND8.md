---
title: QA operator instructions — Codex-style SSAK-AI UI, round 8
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Round 8 operator checks

Execution mode is QA-agent-directed/root-executed. Root operates only the existing user-unlocked IAB browser2/tab1 at http://127.0.0.1:8000/. The QA judge remains an independent, one-shot leaf. Do not create an authenticated browser session, request or enter a PIN, inspect authentication storage, transfer credentials, delete conversations, execute tools, approve tool requests, mutate Git, or edit credentials for these checks.

The intended binding is HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus the dirty 46-file source manifest SHA-256 `131a1c743bd2e79e14acf6578b89afc0c777e0fdb149521c856091d50c072bb9`. Main assets must be `index-DZRjcX6h.js` and `index-C19bV3rn.css`. The round 8 delta is the narrow four-CSS-file `FINAL_CSS_DELTA.patch`; TypeScript, protected contracts and tests must match frozen round 7. Any later source change invalidates this binding and requires fresh evidence.

## Complete fresh packet

Capture all 17 routes at 375, 768 and 1280px (51 route originals and matching fresh semantic DOM files). Routes are `/`, `/chat`, `/studio`, `/models`, `/start`, `/wiki`, `/agent`, `/settings`, `/skills`, `/data-extraction`, `/git`, `/history`, `/plugins`, `/mutation`, `/plugins/hello-world`, `/plugins/job-operations` and `/ui-qa-not-found`.

Capture the same 27 state originals as round 7: at 375, model-menu, history, navigation, inspection-environment, inspection-code, inspection-changes, command-palette-early, command-palette, shortcut-guide-early, shortcut-guide, status, empty, generation, chat-complete and copy; at 768, history, the three inspection states, command-palette and shortcut-guide; at 1280, the three inspection states, output, status-details and chat-complete. Each image must have the correct signature, requested viewport, complete compositing, post-edit timestamp, hash and current asset binding. The judge must open all 78 originals individually at original detail after READY.

Reset viewport before taking a fresh full 757×954 `deliverable.jpg`. Compare it only with the actual full `captures/before-default.jpg`; convert to RGB PNG with no resize, crop, padding or redraw. Refresh IMAGE_DIFF_RECEIPT and map all 64 grid hotspots. The padded historical baseline768 comparison remains invalid for approval. This diagnostic is not an exact Codex pixel target.

## Concrete runtime checks

1. On successful Settings, scroll the actual `.settings-row-hint` for the default reasoning model into view at all three widths. Read the complete helper and neighboring prose. At 1280, record DOM Range bounds for the five individual characters in `보여줍니다`; they must share the same line. At compact widths the whole word must wrap naturally, remain readable and stay within page bounds. Recheck Wiki `생성하세요.` and History `저장됩니다`. Preserve Mutation's entire 40-character SHA including its last `b` at all three widths.
2. At 375, measure the rendered main controls, all three inspection close actions and environment-footer controls. The compact minimum is 36×36px, while desktop minimum is 32×32px. Keep the actual count and per-control bounds in COMPACT_CONTROL_BOUNDS; do not infer this from CSS declarations alone.
3. At 375 and 768, open History and each environment/code/changes inspection modal with an unsent Korean draft. Verify visible title and clickable close bounds; click X, then separately reopen and press Escape. Both closures must restore the opener, release inert state and retain the unchanged draft. Inspect the desktop docked states too.
4. Exercise inspection → Meta+K and history → Meta+Slash handoffs. Assert that only the foreground modal remains. Verify palette initial named search focus, guide initial named Close focus, guide Tab and Shift+Tab wrap, then X/Escape return focus and preserve draft. Exercise compact navigation Tab/Shift+Tab wrap and Escape/opener restoration. Record first-observed and settled palette/guide states without claiming invented transition timing. State explicitly whether palette Tab cycle was tested.
5. Use the actually selected `qwen3.8:latest (27.3B)` model for one ordinary synthetic greeting with an explicit no-tools instruction. Record Shift+Enter newline, real send, generation, completion and exact clipboard-copy match. Never approve a tool request. If this creates a sixth saved conversation, record the new title, time and count accurately; earlier captures before creation may still show five. Do not delete any prior record.
6. Reload chat and verify retained model/transcript/history. Cold-reload Studio, Wiki and Settings, wait for visible recent titles, and select one pre-final conversation by its actual visible title. Wait for its prior prompt/reply and 27.3B model, then return to the newest QA conversation. Keep per-route counts/time evidence rather than imposing a single count on captures taken at different times.
7. For Git, wait for populated Staged Changes content and actual file lists at each width. Keep its current branch/counts and read-only boundary. Bounded Skills/Metrics 401 states may pass visual display coverage but cannot establish authenticated API success. Output may honestly remain `No output yet`.

Native OS IME, forced 503/CAS409, and late-hydration/early-draft races remain AUTOMATED-only unless they are actually exercised through the browser with fresh evidence. No full axe, Lighthouse, Electron-native or backend-suite claim follows from this packet. ReactDoctor's pre-existing ignored nonshipping mutation.html finding must remain disclosed.

## Original scenario IDs and expected evidence

| ID | Scenario | Evidence required |
|---|---|---|
| B01 | Home/new empty conversation | Actual route and new-empty state, prior conversations retained. |
| B02 | /chat alias | Routed chat and bounded composer. |
| B03 | Studio | Three widths, cold recents restoration and prior selection; no training claim. |
| B04 | Models / active model | Listing and actual 27.3B selection; no 125B load claim. |
| B05 | Start / bridge setup | Displayed choices/controls; distinguish display from invocation. |
| B06 | Wiki | Tree/empty state and intact Korean prose; no note creation claim. |
| B07 | Agent dashboard | Bounded actual idle/unavailable state; no blanket API claim. |
| B08 | Settings | All widths and actual helper repair, masked controls/cold recents; no credential edit. |
| B09 | Skills | Actual bounded empty/error state, including 401 boundary. |
| B10 | Data extraction | Displayed A/B controls and intact 만원/억원; no extraction claim. |
| B11 | Git | Settled populated three-width read-only evidence. |
| B12 | File history page | Bounded Files view and intact 저장됩니다. |
| B13 | Plugins index | Displayed index; no installation/removal claim. |
| B14 | Mutation report | Entire SHA, accurate historical wording; no live mutation claim. |
| B15 | Hello-world plugin | Displayed controls; distinguish Test Toast invocation. |
| B16 | Job operations plugin | Displayed health/zero-job state; no creation/retry claim. |
| B17 | Intentional not-found route | Readable routed fallback and return controls. |
| B18 | Compact navigation | Actual focus wrap, Escape and opener return. |
| B19 | Command palette / shortcut guide | Actual handoffs, named focus, guide Tab wrap and X/Escape. |
| B20 | Model menu / sidebar reload | Menu, retained 27.3B, cold-route recents and prior selection. |
| A01 | Environment/code/changes inspection | Nine originals and compact title/X/Escape/draft/focus checks. |
| A02 | Conversation history | Drawer checks and actual restored prior selection. |
| A03 | Multiline/send/generation/copy | Actual normal path; OS IME remains automated-only. |
| A04 | Output / status | Actual output-empty/status display with no manufactured command. |
| A05 | Controlled failure / hydration races | Meaningful automated tests; no fabricated manual PASS. |

## READY handoff and independent judgement

Root supplies READY only after the full 78-image/51-route-DOM packet, comparison receipt, live interaction receipts, source/bundle manifests and fresh test/typecheck/build logs are finalized. The judge then audits bytes, timestamps, complete image inventory, semantic DOM coverage, actual runtime outcomes and all hotspots. Final QA_REVIEW must preserve all 25 IDs and separate manual, automated-only and unexercised boundaries. Any visible product failure or invalid/stale evidence requires REVISE with a concrete location; a clean independent result may PASS only this exact packet.

## Execution stopped on an actual failure

The round 8 run stopped before READY after root reproduced a first-click recent-conversation failure twice. From a cold `/settings` load, one click on a previous visible title navigates to `/chat` but displays the newest cached greeting. Frozen `archive-round8/RECENT_SELECTION_FAILURE_ROUND8.json`, the original failure JPEG and matching DOM establish the mismatch on source `131a…` and `index-DZRjcX6h.js`.

The frozen partial inventory has 72 records: 51 route frames plus 21 state frames. Six desktop states were not run: the three inspection tabs, output, status-details and chat-complete. The 375 inventory contains a `status-closed` frame, without a current open-status disclosure claim. Copied old full-manifest/directed/restore/style/comparison receipts remain historical. This one-shot judge therefore produced a scoped **REVISE F8-1**, directly opening eight current originals and inspecting failure/Settings/normal-chat evidence. It did not claim all 78 originals opened or a full final gate. The subsequent selection repair requires a new independent QA lane and a complete fresh packet.
