---
title: Manual QA review — Codex-style SSAK-AI UI, round 9
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Manual QA review

Verdict: **PASS for this exact packet and the scoped scenarios below.** There are **24 manual PASS scenarios and one AUTOMATED-only scenario**, retaining all original B01–B20 and A01–A05 IDs. No current product blocker remains in this QA lane. This is not an approval of unexercised backend operations or a substitute for the other independent review lanes.

Execution mode: **QA-agent-directed/root-executed**. This judge supplied [round 9 operator instructions](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/QA_OPERATOR_INSTRUCTIONS_ROUND9.md); root alone operated the existing user-unlocked **IAB browser2/tab1** at http://127.0.0.1:8000/. This judge opened **all 81 current original JPEGs individually at original detail**, both valid comparison PNGs, and inspected semantic heading/control/state evidence from **all 51 route DOM snapshots** plus the three targeted Settings helper DOMs. Root authorized preliminary reading of completed current frames while assembling the packet. After READY, the frozen hashes matched every inspected image, including both replacement 768 inspection originals. No montage, thumbnail sampling or inferred page coverage substituted for these opens.

This judge used the visual-qa and codebase-memory skills. Graph-first discovery returned “project not found or not indexed” for this checkout, and list_projects did not contain Ssak-Ai; automated source corroboration therefore used precise known-path fallback. This lane did not operate a browser, create a profile, request or enter a PIN, inspect browser authentication storage, transfer credentials, approve tool requests, modify product code, stage files or create a commit.

## Exact reviewed binding

Declared HEAD is **8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382**, plus the dirty source bound below. Main JavaScript is **/assets/index-CEvvbZ3V.js**, SHA-256 **a908583776aaa9446bc34f5aeb1da5ca36e7e9aef8ab9a5ba47ed3128382e2a4**. Main CSS is **/assets/index-C19bV3rn.css**, SHA-256 **4c09077334dbfb6c5416e4b5e55f603b673b216a82b5218a8190590a95a2119f**. A later source, bundle or capture packet cannot inherit this PASS.

| Artifact | SHA-256 |
|---|---|
| [SOURCE_MANIFEST.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json) | f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd |
| [BUNDLE_MANIFEST.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json) | db2ba38c29213b147e851a1e3febfdf10933edce5d4afccb24d90c669f0959de |
| [CAPTURE_MANIFEST.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json) | ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3 |
| [BROWSER_OBSERVATIONS.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json) | d029afe7d88d84dadc7bc5c9e5226a720448d384a94475162a974d82ce3139cb |
| [QA_DIRECTED_RESULTS.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/QA_DIRECTED_RESULTS.json) | 27a5b015863af36f7e6c90da597c2186b56a1b6ca5aaf8117ee0937405ad1eb3 |
| [LIVE_CHAT_RESULT.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/LIVE_CHAT_RESULT.json) | c52a0756c633decc8a2f151474efd98f9289e3ffa10fb99ce095f325bafc344f |
| [NONCHAT_RESTORE_LIVE.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/NONCHAT_RESTORE_LIVE.json) | 342ea00724238b5bf56cda7fd85d176f26c4066b7286a740f500ff4ecf9a7701 |
| [RECENT_SINGLE_CLICK_LIVE.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/RECENT_SINGLE_CLICK_LIVE.json) | b57cc93203971f438a0e93ee66a3bff59547b462c53441e9a6a397e36cd28694 |
| [VERIFICATION.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/VERIFICATION.json) | 7701cb55578359f1ded66542d79c7a614adeb5862c5adb01c4c21ea99ff14e0e |
| [LIVE_STYLE_BINDING.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/LIVE_STYLE_BINDING.json) | b3081e58c9256499bff334a023edb1e768c606281b6c0d579fc535268be13d8e |
| [TYPOGRAPHY_LIVE.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/TYPOGRAPHY_LIVE.json) | fa6ea5c7ac03ee884313f355d7232f3645fdc2507b71435539b0b57f453fa91e |
| [CAPTURE_HYGIENE.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/CAPTURE_HYGIENE.json) | 046afecfbbab43940374b6ebec2707f811128c17a91c474eb1589544f64f511b |
| [COMPACT_CONTROL_BOUNDS.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/COMPACT_CONTROL_BOUNDS.json) | 9be7696aae53bf27c23d9ac91834214ebb65a4fd75032038a7a8ac85b04d4942 |
| [SETTINGS_WORD_GEOMETRY.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/SETTINGS_WORD_GEOMETRY.json) | 5d0449193db5ae47b995bbf9d3e23d9f9ccbabee718a7727d3ab7718b6ebc55a |
| [IMAGE_DIFF_RECEIPT.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/IMAGE_DIFF_RECEIPT.json) | 1092877e99d63f88ccbac9432bc360abc5188edcdd108735cbd7ba059f5bbc5d |
| [IMAGE_DIFF.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/IMAGE_DIFF.json) | 5dd9e9104df7b06d9073c21963ed2c3e88822ce90e409d820b4db14de23c1f58 |
| [TESTS_CURRENT.log](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/TESTS_CURRENT.log) | df1e9623a6322365c38af0bc8bc247c9e7852b9c453a352bfb13bb45025b80a6 |
| [TYPECHECK_CURRENT.log](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/TYPECHECK_CURRENT.log) | e90110ef984abdd22f8cbd8c2b5b03205318ac3bb196df57ca1e8350439e51c1 |
| [BUILD_CURRENT.log](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/BUILD_CURRENT.log) | b737b2df5703e59a2ea40e9d93937841cf250199c95be3fbf7f8d9efee9611c4 |

All **46 source files, four protected contracts, 104 shipping output files and 81 captures** reproduced their declared hashes. Protected chatStore.ts, projectStore.ts, api/client.ts and accessPinCredential.ts matched identical before/after hashes. There are **81 unique capture IDs and 81 unique current-source observations**. All JPEG signatures, dimensions and capture hashes are valid; all 81 matching DOM files are present and postdate the latest source edit.

Latest source edit is **2026-10-03T04:23:14.886966+00:00**. The final captures range from **2026-10-03T04:28:57.807Z** to **2026-10-03T04:39:23.167Z**. Every capture references the current JavaScript. Live style binding confirms current CSS. Every frame has document width equal to its requested viewport and measured horizontal overflow zero. Direct image inspection found no missing compositor region or unexplained black padding in this final set.

## Closure and actual runtime evidence

**Korean prose and provenance.** The previously fractured Settings word **보여줍니다** is now intact in the successful page. The three targeted, scrolled original frames expose the actual default-model helper rather than relying on offscreen DOM text. All five characters share the same measured line at each width: y **422.28125** at 375, **466.28125** at 768 and **475.28125** at 1280. The current helper uses keep-all with a long-token fallback. Neighboring Settings prose is readable. Wiki **생성하세요.** and History **저장됩니다** remain intact. Mutation shows the full SHA **6d0a24d4e6a0686693ce29a4d13a69443ae5149b**, including its last **b**, at all three widths; its historical/stale wording does not imply a current CI result.

**Compact controls.** COMPACT_CONTROL_BOUNDS records **18 actual controls at each of 375 and 768**, all at least **36×36px**: 16 main controls including the navigation opener, plus the shared inspection close action and navigation footer action. Accessible names and per-control bounds were inspected. This verifies that enumerated chat/navigation/inspection set, not an exhaustive accessibility audit of every legacy operational-page control.

**Recent conversation selection and reload.** RECENT_SINGLE_CLICK_LIVE records exactly one first click on the visible older title from cold Studio, Wiki and Settings, on the current source, before final generation when there were six saved records. Each result reaches the selected old title and its prior prompt/reply; no retry or second-selection workaround establishes this PASS. The selected model remains qwen3.8:latest, with the 27.3B label visible once model metadata settles. The new actual Sidebar → ChatPage regression test reproduces the old cached-active-session overwrite in its RED log and passes after Sidebar saves the selection before navigation.

NONCHAT_RESTORE_LIVE separately records fresh cold reloads of all three pages after generation, each showing **all seven saved conversations**. The prior original conversation and earlier QA records remain. The first 375 route/history captures precede the new send and show six; later 768/1280 evidence shows seven. LIVE_CHAT_RESULT records **six before / seven after**, one conversation created this round and six synthetic QA conversations created during the overall UI task. These scenario IDs are not conversation IDs. No record was deleted.

**History and inspection dialogs.** At 375 and 768, actual History X and Escape closures restore the history opener, release inert state to zero and preserve the Korean unsent draft. Each of the three inspection tabs has an actual X closure; the shared inspection Escape path is also exercised at both widths. All eight title/close hit checks find the visible title and clickable close control. Desktop environment/code/changes remain bounded in their docked states. The preserved draft for these checks is **QA 임시 초안 — 전송하지 않음**.

This judge located two **capture** defects during assembly: the first 768 Code frame retained the Environment underline, and the first Changes frame had an unsettled underline and faint empty-state content. Root recaptured both after the transitions settled without a source edit. The replacement originals were individually reopened; Code/Changes indicators match their selected tabs, Changes content is readable, and the current receipt records **selected 변경 / content opacity 1**. The initial frames are not used to approve the surface.

**Foreground handoffs and keyboard access.** Inspection → Meta+K leaves only the palette, initially focused on **검색어 입력**; Escape restores the inspection opener and preserves the draft. History → Meta+Slash leaves only the shortcut guide, focused on its named Close control. Actual Tab and Shift+Tab remain inside the guide, and X/Escape restore the history opener and draft, at both compact widths. Palette/guide surfaces have opacity 1 and no animation in the recorded style checks. First-observed and settled 375 originals are readable; no fabricated transition timing is claimed.

The separate **768 palette** keyboard check is now explicit: settled focus is the INPUT/combobox **검색어 입력**; real Shift+Tab reaches the final text-labelled BUTTON/option **Plugin: Open Hello World panel** inside the palette; real Tab returns to the named search input. All three active-element receipts confirm withinPalette=true. Escape returns to the composer, releases inert state and preserves **QA 포커스 검증 초안 — 전송하지 않음**. Earlier transient recorder entries with composer focus/null aria-label and an empty draft are retained honestly and are not the basis for the named-focus/wrap PASS. No plugin option was activated. Compact navigation's actual 375 Shift+Tab/Tab wrap and Escape/opener return are exercised with an empty draft.

**Normal chat, copy, Git and status.** The latest actual no-tools greeting used **qwen3.8:latest (27.3B)**. Shift+Enter inserted a newline; real send produced generation and a completed greeting. The 375 generation, completed and copied originals show the corresponding working/stop, completed reply and **복사됨** states. Actual clipboard contents are **raw Markdown containing the completed greeting**; they are not asserted byte-equal to rendered DOM text. No displayed 503 or approval click is recorded. Existing engine quality/usage wrappers remain visible. The earlier blocked computer_use notice is historical evidence and was never approved.

All three Git originals are settled and populated, with branch **codex/m1-task-events** and observed counts **214 staged / 62 unstaged / 147 untracked**. Their DOMs contain actual Staged Changes controls and populated file lists. No Git mutation was exercised. Output honestly shows **No output yet**; no command was run to manufacture content. Status details display actual system fields in a bounded popover. Skills/Metrics 401 observations support displayed bounded empty/loading/error coverage, not authenticated backend success.

## Original scenario matrix

PASS applies only to the stated manual evidence. **A05 remains AUTOMATED-only**, and the native OS IME portion of A03 remains automated-only.

| ID | Original scenario | Result and evidence boundary |
|---|---|---|
| B01 | Home/new empty conversation | PASS — three-width home and actual new-empty state; saved conversations retained. |
| B02 | /chat alias | PASS — routed chat and bounded composer at all three widths. |
| B03 | Studio | PASS — three-width displayed surface, cold recents and first-click prior selection; no training run. |
| B04 | Models / active model | PASS — listing, current model/menu and actual 27.3B greeting; no 125B load or model-switch invocation. |
| B05 | Start / bridge setup | PASS — displayed choices and copy controls; bridge execution and copy invocation not exercised. |
| B06 | Wiki | PASS — tree/empty surface and intact 생성하세요.; no note creation. |
| B07 | Agent dashboard | PASS — bounded idle/unavailable surface and semantic status/actions; no blanket API-success claim. |
| B08 | Settings | PASS — masked controls, helper repair at all widths and cold recents; no credential/configuration edit. |
| B09 | Skills | PASS — bounded displayed empty/error surface; observed 401 does not establish backend success. |
| B10 | Data extraction | PASS — displayed search/A/B controls and intact 만원/억원; no extraction execution. |
| B11 | Git | PASS — populated, settled, read-only evidence at all widths; no Git mutation. |
| B12 | File history page | PASS — bounded empty Files surface and intact 저장됩니다; distinct from conversation history. |
| B13 | Plugins index | PASS — displayed index; no installation/removal/toggle invocation. |
| B14 | Mutation report | PASS — entire SHA and accurate historical/stale wording; no live mutation or CI execution. |
| B15 | Hello-world plugin | PASS — displayed registered panel and controls; Test Toast not invoked. |
| B16 | Job operations plugin | PASS — displayed healthy/zero-job surface; no job creation or retry. |
| B17 | Intentional not-found route | PASS — readable routed fallback and return controls; not a backend error test. |
| B18 | Compact navigation | PASS — actual 375 focus wrap, Escape and opener restoration. |
| B19 | Command palette / shortcut guide | PASS — compact foreground handoffs, named focus, guide wrap/X/Escape; settled 768 palette Shift+Tab/Tab/Escape with preserved draft. |
| B20 | Model menu / sidebar reload | PASS — bounded menu, retained 27.3B, all seven cold-route recents and first-click old selection. |
| A01 | Environment/code/changes inspection | PASS — all nine width/state originals, title/close hit checks, each compact X and shared Escape/draft/focus paths; both unsettled 768 frames replaced. |
| A02 | Conversation history | PASS — 375/768 X/Escape/draft/focus plus actual prior-conversation selection from restored sidebar. |
| A03 | Multiline/send/generation/copy | PASS — actual Shift+Enter, send, generation, completion and raw-Markdown copy containing greeting; native OS IME/key229 AUTOMATED-only. |
| A04 | Output / status | PASS — actual output-empty and status display; no manufactured command/tool output. |
| A05 | Controlled failure / hydration races | AUTOMATED-only — meaningful permission-503, typed API 409/integrity/migration-503 and hydration/early-draft tests; no browser fault injection or native IME PASS. |

## Complete individually opened capture inventory

Each name has the captures/final- prefix and .jpg suffix, with its refreshed .dom.txt. All three widths were individually opened for every route.

| Route suffix | Path | Widths |
|---|---|---|
| home | / | 375, 768, 1280 |
| chat-alias | /chat | 375, 768, 1280 |
| studio | /studio | 375, 768, 1280 |
| models | /models | 375, 768, 1280 |
| start | /start | 375, 768, 1280 |
| wiki | /wiki | 375, 768, 1280 |
| agent | /agent | 375, 768, 1280 |
| settings | /settings | 375, 768, 1280 |
| skills | /skills | 375, 768, 1280 |
| data-extraction | /data-extraction | 375, 768, 1280 |
| git | /git | 375, 768, 1280 |
| history-page | /history | 375, 768, 1280 |
| plugins | /plugins | 375, 768, 1280 |
| mutation | /mutation | 375, 768, 1280 |
| hello-world | /plugins/hello-world | 375, 768, 1280 |
| job-operations | /plugins/job-operations | 375, 768, 1280 |
| not-found | /ui-qa-not-found | 375, 768, 1280 |

| Width | State suffixes individually opened | Count |
|---|---|---|
| 375 | model-menu; history; navigation; inspection-environment; inspection-code; inspection-changes; command-palette-early; command-palette; shortcut-guide-early; shortcut-guide; status-closed; empty; generation; chat-complete; copy | 15 |
| 768 | history; inspection-environment; inspection-code; inspection-changes; command-palette; shortcut-guide | 6 |
| 1280 | inspection-environment; inspection-code; inspection-changes; output; status-details; chat-complete | 6 |
| 375, 768, 1280 | settings-helper, one at each width | 3 |

Total: **51 route originals + 27 interaction-state originals + three helper originals = 81**. The two corrected 768 state originals were reopened after replacement. Semantic DOM review covers every declared route/width pair, including disabled/unavailable states, real control names, Settings helper, full provenance and Git population. Expanded navigation may put recents below the scroll viewport; it is not interpreted as lost history.

## Valid comparison and all 64 hotspots

This judge opened both full **757×954** comparison PNGs at original detail and verified their hashes, PNG dimensions/signatures and decoded RGB equality to the actual JPEG originals. Conversion performs no resize, padding, crop or redraw.

| Comparison input | SHA-256 |
|---|---|
| captures/before-default.jpg | 980c78578fecb33dba0e99e61b66172aab26357b7edb81441dd6c33f93a04040 |
| deliverable.jpg | ac43b9cbf30e945ab4bf7aef6120b0c7d063c660c7a8babd98d5ccf8cf424b34 |
| baseline-757.png | 55361e5ac0b9263fa8ecacc4e36467d8df453049570d95fda4688814d93a29ae |
| actual-757.png | dd3818247a7e8166864d27c47a139d48abd9d38007aa19c29f7f8f18df57f0f6 |

Dimensions match; **721,893 of 722,178 pixels differ**, diffRatio **0.9996**, reported similarity **0**, alphaChannelIntact **true**. This is a historical SSAK-to-current diagnostic with deliberate layout/background changes and different known synthetic conversation content. It is **not a Codex fidelity or quality score**. The old baseline768 contains compositor black padding outside its real 375×812 content despite a 768×900 file size; its comparison is invalid for approval and remains excluded.

All 64 flagged coordinates are listed explicitly below. Coordinates are (gridX, gridY); each listed cell has been mapped to its visible cause. The x bands are 0–93, 94–188, 189–282, 283–377, 378–472, 473–566, 567–661 and 662–756.

| y band | Every covered hotspot | Observed cause across the listed cells |
|---|---|---|
| 0–118 | (0,0), (1,0), (2,0), (3,0), (4,0), (5,0), (6,0), (7,0) | Old double telemetry/header and icon rail become compact workspace status and chat header; typography, spacing and canvas colors change throughout. |
| 119–237 | (0,1), (1,1), (2,1), (3,1), (4,1), (5,1), (6,1), (7,1) | Old left user bubble becomes the right-aligned current bubble, with changed prompt text; removed rail, open assistant label and neutral canvas explain the surrounding cells. |
| 238–356 | (0,2), (1,2), (2,2), (3,2), (4,2), (5,2), (6,2), (7,2) | Old inset avatar/assistant composition becomes open assistant prose with different gutters and type; the completed synthetic reply also differs; canvas explains empty cells. |
| 357–476 | (0,3), (1,3), (2,3), (3,3), (4,3), (5,3), (6,3), (7,3) | Usage metadata moves toward the current gutter; different values, visible copy control and reply extent alter content cells; background explains the others. |
| 477–595 | (0,4), (1,4), (2,4), (3,4), (4,4), (5,4), (6,4), (7,4) | Deliberate idle-canvas change from near-black to charcoal across every column; no compositor-only black block is accepted. |
| 596–714 | (0,5), (1,5), (2,5), (3,5), (4,5), (5,5), (6,5), (7,5) | The same intentional full-row canvas change. |
| 715–833 | (0,6), (1,6), (2,6), (3,6), (4,6), (5,6), (6,6), (7,6) | Old context chip appears around y788; the current wider composer starts around y769. Composer prompt, gutters, removed rail and surrounding canvas explain the cells. |
| 834–953 | (0,7), (1,7), (2,7), (3,7), (4,7), (5,7), (6,7), (7,7) | Old composer/profile rail become the current composer ending around y897 plus the environment footer around y919; controls, grouping, gutters and canvas differ. |

No flagged cell is left unexplained by this diagnostic, and no high diff is waved through because of motion. The final approving state frames are judged separately on current settled originals.

## Automated corroboration and limits

Current raw log bytes were inspected: **103 files / 1001 tests pass**, **typecheck exit 0**, **production build exit 0**. Build retains the known >500kB Monaco/Mermaid chunk advisory. The pnpm update-check network warning is present in successful logs and is not recast as a failed build.

The 14 Sidebar-history cases cover three cold nonchat routes, project-ID readiness, excluded chat routes, existing list/session/message/stream state, early-created conversation protection and the real Sidebar → ChatPage old-selection regression. The RED log fails by restoring the wrong cached active session; GREEN targeted checks pass. Guide tests assert named initial Close focus, modal semantics, real key handlers for both Tab directions, X/Escape/backdrop dismissal and opener return. Composer tests assert IME/isComposing and key229 draft preservation, native Shift+Enter allowance, Enter submitting once, and permission-503 retaining read-only mode with an error toast. Hydration tests defer initial resolution and assert stored-history restoration or preservation of an early session/draft. API tests assert typed stale-revision 409, integrity 409 and migration-required 503 results.

**Native OS IME, controlled browser 503/CAS409 and late-hydration/early-draft races remain AUTOMATED-only.** The permission-503 test does not assert failed-send draft retention; no such coverage is claimed. Normal successful browser generation is not evidence for those fault paths.

ReactDoctor still exits **1** for the pre-existing ignored, nonshipping reports/mutation/mutation.html fixture at line 334; the shipping bundle excludes it. It is not claimed clean. No full axe, Lighthouse, native Electron, complete backend suite or exact Codex desktop pixel match is claimed. Measured system/Korean typography is UI 14px, assistant 16px/27.2px, composer 16px/25.6px, sidebar 248px and assistant content 760px; no proprietary font copying is asserted.

Historical round 6 raw TESTS/BUILD bytes were overwritten before archive; ROUND6_LOG_RECEIPT discloses that retention limitation. Historical round 7 and partial round 8 artifacts are preserved as earlier evidence, not reused as approval of this source. This PASS is bound to the fresh round 9 packet above.
