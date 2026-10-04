---
title: Independent goal and Visual-A review — Codex UI round 9
tags: [qa, goal-review, visual-review, frontend, codex]
date: 2026-10-03
---

# Verdict: PASS

Confidence: HIGH within the stated evidence scope. The requested Codex-inspired fonts and arrangement are implemented as a responsive, token-driven SSAK-AI workspace. Conversation text has priority, named navigation replaces the compact icon rail, and the composer remains outside transcript scrolling. The real selected `qwen3.8:latest (27.3B)`, existing tools, project identity, history and authorization boundaries remain represented by actual components and state. **No current Goal or Visual-A blocker was found.**

This is a fresh, independent, one-shot review of the final round 9 packet. It does not inherit the historical round 7/8 visual decisions. I opened **all 81 current JPEG originals individually with `view_image` at `detail: original`**, plus both valid 757×954 PNG comparisons and `deliverable.jpg`. Every capture is enumerated below. I did not replace original inspection with a contact sheet or sample. I read the current design, reference, execution plan, READY packet, directed interaction results, final source delta, and previous REVISE findings. I changed only this report; no browser or application source was changed.

## Exact source and evidence binding

| Artifact | Independently verified binding |
| --- | --- |
| Full Git HEAD | `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` |
| Dirty source manifest, 46 files | SHA-256 `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd` |
| Capture manifest, 81 originals | SHA-256 `ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3` |
| Shipping bundle manifest, 104 files | SHA-256 `db2ba38c29213b147e851a1e3febfdf10933edce5d4afccb24d90c669f0959de` |
| Shipping index.html | SHA-256 `2e31beb80b227bbc72d61ba64a7c1476bd0db6e9f9f76afa6e9db5f03490e373` |
| Main script | `/assets/index-CEvvbZ3V.js`, SHA-256 `a908583776aaa9446bc34f5aeb1da5ca36e7e9aef8ab9a5ba47ed3128382e2a4` |
| Main styles | `/assets/index-C19bV3rn.css`, SHA-256 `4c09077334dbfb6c5416e4b5e55f603b673b216a82b5218a8190590a95a2119f` |
| Directed QA results including settled palette focus | SHA-256 `27a5b015863af36f7e6c90da597c2186b56a1b6ca5aaf8117ee0937405ad1eb3` |
| Valid comparison receipt | SHA-256 `1092877e99d63f88ccbac9432bc360abc5188edcdd108735cbd7ba059f5bbc5d` |
| Diagnostic image diff | SHA-256 `5dd9e9104df7b06d9073c21963ed2c3e88822ce90e409d820b4db14de23c1f58` |

Recomputed 46/46 source hashes and all four protected file hashes. The protected `chatStore.ts`, `projectStore.ts`, `api/client.ts`, and `accessPinCredential.ts` each equal the manifest's identical before/after task-baseline hash. Protection is relative to that task baseline, not an assertion that the baseline itself equals HEAD. Recomputed all 104 shipping hashes and compared actual inventory: no missing or unlisted file. Recomputed all 81 capture hashes, checked JPEG signatures and actual SOF dimensions, checked matching refreshed DOM files, and matched the 81 current-only browser observations. All images match their declared viewports; document width equals viewport width and each recorded horizontal-overflow count is zero.

The last manifested source edit is `2026-10-03T04:23:14.886966+00:00`. All 81 captures are later, from `04:28:57.807Z` through `04:39:23.167Z`. The two refreshed 768 Code/Changes frames are the settled replacements, with the selected tabs and Changes opacity 1. No source change followed this binding. Git HEAD alone is insufficient to identify this dirty working state.

## Goal and Visual-A assessment

| Requirement | Decision and evidence |
| --- | --- |
| Codex-inspired arrangement | PASS. Quiet neutral shell, compact server disclosure, named navigation, restrained borders, open assistant prose, subtle right-aligned user bubble and aligned composer. This is the adaptive contract in `dashboard/DESIGN.md`, not an exact Desktop screenshot clone. |
| Public reference provenance | PASS. `docs/frontend/CODEX_REFERENCE_2026-10-03.md` pins public `openai/codex` at `604061ce51d194a3aa6aad3b3170240d096e1725`. Its CLI/Rust TUI/app-server code informs concepts; it does not supply Desktop React/CSS or a proprietary typeface. The implementation makes neither claim. |
| Typography and Korean | PASS. Root system/Korean sans stack is local, with no font download requirement. Live UI is 14px/21px; assistant prose 16px/27.2px; composer 16px/25.6px. Actual captures show readable Korean/English without missing glyphs, clipped baselines or the previous fractured predicates. Monospace is limited to appropriate code/data. |
| Neutral design tokens | PASS. `index.css` centralizes primary `#202020`, sidebar `#181818`, tertiary `#292929`, elevated `#333333`, text, spacing and focus tokens. `codex-workspace.css` composes shell/chat/history/inspection/page rules. State colors retain their meaning; the new chrome uses shared SVG `AppIcon` controls. Some legacy operational content retains its existing icons/styles, as disclosed by the scoped design contract. |
| Geometry and composer | PASS. Live desktop sidebar 248px, assistant reading width 760px and UI sizing agree with the design. ChatPage's actual textarea, send/stop callbacks, attachment handling, permission/search/code/MCP controls and model selector render through extracted components. Composer is a nonshrinking sibling of the scrolling feed; compact toolbars wrap and output/inspection states do not cover it. |
| Navigation and responsive panels | PASS. Real route links and project/recent buttons render through WorkspaceNavigation/WorkspaceThreads. Compact navigation is a modal drawer below 1024px; inspection becomes a modal below 1280px and docks at desktop. Actual tab selection, dialog headings, close actions and internal scrolling are visible. No primary-page horizontal overflow appears in the 51 route frames or 30 other frames. |
| Real content and state | PASS. The current pixels correspond to actual DOM/components and store/API callbacks. No screenshot background, flattened replacement UI, mock model capacity or static fake interaction is used for the reviewed shell. Generated assistant quality/emoji content belongs to the existing reply renderer; it is not chrome or fabricated completion evidence. |
| Functional preservation | PASS for the evidenced scope. Unchanged protected contracts and current code/security reviews support preserved auth/project/CAS boundaries. Source retains project-epoch checks, authoritative history snapshots, revision conflict handling and Markdown sanitization. Current manual evidence shows actual normal greeting completion/copy, history retention and first-click prior-session selection; automated-only cases remain labelled below. |

For source discovery I used the codebase graph first. Its indexed current results supplied the actual reusable components and ChatComposer/Sidebar snippets. Subsequent graph calls returned `Transport closed`; only then did I read precise known current paths. Direct source inspection covered `Sidebar`, `WorkspaceNavigation`, `WorkspaceThreads`, `ChatComposer`, `InspectionFrame`, `useModalDialog`, `ChatPage`, `ChatMessage`, `AppIcon`, the root tokens and workspace styles. Real native controls, semantic articles/navigation/dialogs/tabs, shared layout rules and genuine state callbacks support the design-system assessment. This is not a standalone exhaustive code or accessibility audit.

## Closure of previous REVISE priorities

| Previous priority | Current verification and disposition |
| --- | --- |
| Round 7 Goal G7-01 / Visual-B P2: Settings 1280 fractured `보여줍 / 니다` | CLOSED. Opened all three Settings route originals and all three helper originals. The helper renders `보여줍니다` as a whole word at 375/768/1280. `SETTINGS_WORD_GEOMETRY.json` places all five characters at the same y for each width: 422.28125, 466.28125, 475.28125. Actual `.settings-row-hint` uses Korean keep-all wrapping with technical-string fallback. |
| Round 7 Visual-B P2: compact attach/mic/send/inspection close were 32×32 despite the 36px contract | CLOSED. Current compact CSS overrides the real shared targets. `COMPACT_CONTROL_BOUNDS.json` measures 18 actual controls per 375/768 width, including navigation opener, inspection close and navigation footer; every measured width/height is at least 36px. The compact generation and all inspection originals show preserved toolbar/panel fit. Desktop remains the documented 32px minimum. |
| Earlier CJK/content priorities: Wiki `생성하세요`, History `저장됩니다`, full Mutation commit SHA | CLOSED in the current three-width originals. The two predicates wrap as whole words. The full 40-character Mutation SHA, including final `b`, is visible with bounded wrapping at 375. |
| Round 7 comparison: old 768 frame had black compositor padding | CLOSED as an evidence repair. The current comparison uses original 757×954 images and RGB-only conversions; independent decoded RGB equality passes for each JPEG/PNG pair. Old `baseline-768.png` and `IMAGE_DIFF_INVALID_BASELINE768.json` remain explicitly excluded. Their equal file dimensions never established valid layout geometry. |
| Round 8 QA F8-1 P1: one old-recent click from a cold nonchat route opened the cached newest conversation | CLOSED for the current execution scope. Current Sidebar calls existing `saveToStorage()` immediately after `switchSession(sessionId)` and before `/chat` navigation, so ChatPage's mount restore uses the selected ID. The real Sidebar→ChatPage regression fails before the fix and passes afterwards with distinct session/content/revision/model assertions. `RECENT_SINGLE_CLICK_LIVE.json` binds exactly one successful prior-title click each from cold Studio, Wiki and Settings to the current source; no retry or second selection is substituted. Each displays the prior header/prompt/reply. These receipt interactions are at the operator's default surface; they are not nine separate compact/desktop click trials. The current round 9 operator scope combines these three live route selections with all three-width route visuals and the shared-handler integration regression. No missing nine-trial claim is invented. |
| Round 8 incomplete 72-frame gate and missing six desktop states | CLOSED. Current complete set is 81: 51 route + 27 state + 3 helper frames. Desktop inspection Environment/Code/Changes, output, status details and completed chat are all present and opened. Historic partial results are not labelled as current approvals. |
| Freshness of 768 Code/Changes and palette focus evidence | CLOSED. Opened both settled replacements: correct selected underline and fully opaque Changes content. Read the appended named-element palette cycle while retaining the earlier transient recorder observations. Neither an animation explanation nor those transient observations is used as proof. |

The first Studio selection receipt briefly labels the same selected model as `qwen3.8:latest` while model metadata loads; Wiki/Settings receipts and settled current frames explicitly show `27.3B`. This is not evidence of a changed model. Subsequent normal generation and retained final frames use the actual 27.3B model.

## Current interaction evidence and its limits

`QA_DIRECTED_RESULTS.json` contains 42 checks and eight layer proofs. Actual 375/768 history and all three compact inspection panels support X/Escape close, visible/hit-testable titles, draft preservation, opener focus and inert release. Foreground inspection→palette and history→guide handoffs leave only the intended foreground modal active. Guide initial focus and both Tab directions stay contained; navigation wraps to its terminal footer action and back to its close control, then Escape returns focus.

The settled 768 palette receipt names the actual input `검색어 입력`, then real Shift+Tab reaches the final option `Plugin: Open Hello World panelPlugin` **inside** the palette, and real Tab returns to the input. Escape returns to the composer with `QA 포커스 검증 초안 — 전송하지 않음` preserved and zero inert/dialog remnants. No plugin option is activated. Earlier standalone transient composer-focus/null-label observations remain historical entries and are not conflated with this settled proof. Modal screenshots alone do not prove keyboard containment; the directed active-element receipts and shared focus/inert implementation supply that evidence.

`LIVE_CHAT_RESULT.json` records the explicit no-tool prompt `도구를 쓰지 말고 짧게 인사 한 문장만 답하세요.`, real Shift+Enter newline, actual generation and normal completed greeting on 27.3B, plus copied raw Markdown containing the greeting. There is no displayed 503 or approval click in that final path. The six records present before generation become seven afterwards; `NONCHAT_RESTORE_LIVE.json` shows all seven on fresh cold Studio/Wiki/Settings reloads, retaining the original conversation. The task created six synthetic records overall and deleted none. Counts in earlier route/state frames are correctly time-dependent, not evidence of lost history.

Read the retained current raw logs and verification receipt: **103 test files / 1001 tests pass**, TypeScript and production build exit 0. The targeted actual-route selection regression has RED 1 failed/13 passed and GREEN 3 files/26 tests passed. Current independent Code and Security round 9 PASS reports bind the same source/bundle and corroborate the preservation check; they are not substitutes for this original-image review. I did not rerun tests/build or operate the user-unlocked browser session.

Native OS IME/key229 behavior, controlled permission-503 read-only/error handling, typed CAS409 and integrity/migration503 responses, and late-project-hydration/draft/new-conversation races are **automated-only** evidence. No failed-send draft-retention assertion is made. Skills/Metrics401 screenshots establish bounded error/empty rendering, not backend success. React Doctor still exits 1 for a pre-existing ignored nonshipping mutation fixture. No full axe, Lighthouse, native Electron, exact Codex Desktop pixel match or proprietary-font match is claimed. The browser operator was root in the sole existing unlocked IAB session; this reviewer used the evidence packet only and did not access authentication storage, transfer credentials, approve tools, delete history or mutate Git.

## Complete original-image inspection inventory

Each row was opened individually at original detail. SHA-256 and decoded dimensions match the current manifest. All filenames below resolve under this QA directory; each has its refreshed same-stem `.dom.txt`. Fit observations refer to the displayed state, without inventing unexecuted backend success.

| # | Original | Dimensions | SHA-256 | Independent pixel observation |
| --- | --- | --- | --- | --- |
| 1 | `captures/final-375-home.jpg` | 375×812 | `2cbc7877d7cf370e73c2f9ad38134f9e4ae519b43ece1c7388ab25c87ee72918` | Restored transcript, real 27.3B selector and composer fit; open assistant prose and subtle user bubble. Compact toolbar wraps into two contained rows. |
| 2 | `captures/final-375-chat-alias.jpg` | 375×812 | `db8a33fb40d4b2615a54860001cbd3da065beb790281dce7d102c3081b77a651` | Same actual chat workspace through /chat; title, transcript and composer remain contained. Compact toolbar wraps into two contained rows. |
| 3 | `captures/final-375-studio.jpg` | 375×812 | `f5aeddb6f019eab2e8fa684fdcd9e060457951501e7f467e60f88cad49478296` | Pipeline cards and model/title remain legible; operational panels reflow and scroll vertically. Pipeline uses two columns and a final left card. |
| 4 | `captures/final-375-start.jpg` | 375×812 | `e9b3b4a25131768790d8ce587325bd07f104d307124abf40aa2ac3fd0a6b7f7d` | Getting-started cards, environment/code paths and local endpoint remain readable and contained. |
| 5 | `captures/final-375-wiki.jpg` | 375×812 | `dadb1696bd664de92ac9a2f689a6f3a65d1e011e027edfc0a3da2b415548995b` | Actual tree/editor empty state is readable; 생성하세요 stays a whole Korean word. |
| 6 | `captures/final-375-agent.jpg` | 375×812 | `bf8c66c5b61aa22562ee3f4dc2e44cead5e5d77a1d9e9698711aed1cb804fe7c` | Idle task/log/timeline panels and zero counters remain distinct and contained. |
| 7 | `captures/final-375-settings.jpg` | 375×812 | `e94598bbb6733a9e7a47867a695447d0913dd4eac78a6bd618bbd246e2b7b4f5` | Masked provider rows, labels and controls fit; full helper inspection recorded separately below. |
| 8 | `captures/final-375-skills.jpg` | 375×812 | `fd52de936779da3c990d26dd8976c9f951c8d8a733ebf4b4a69064782c4ae686` | Skill tabs and bounded empty/error state fit; this does not establish authenticated backend success. |
| 9 | `captures/final-375-data-extraction.jpg` | 375×812 | `71c935d5fc8d97988facf79437c02d9b9f3c9f6c739fcc77fce27da72e5899f7` | Extraction controls and A/B action label fit; Korean amount phrases remain readable. |
| 10 | `captures/final-375-git.jpg` | 375×812 | `d1c8175ee991d25869a527c2d207df1792f5824cdaf414c1985d5a3ecd5c198f` | Populated staged/unstaged/untracked lists and branch fit; bounded diff area scrolls internally. |
| 11 | `captures/final-375-history-page.jpg` | 375×812 | `b71752d586eb0d61106db849ad2ddfae15f0f4d6447a61d587dfd849b33c162b` | Repository history panes and explanatory prose fit; 저장됩니다 stays a whole word. |
| 12 | `captures/final-375-plugins.jpg` | 375×812 | `405fb122ed317fae94522fd18498549c838f0bfa090ae96359c8f2acf154c968` | Plugin list/status and available actions remain named and readable. |
| 13 | `captures/final-375-mutation.jpg` | 375×812 | `8fa2e40d43f523c4be27231a7bcbecedbdda119cb6e93b757785b2a3968f3c00` | Mutation report and full 40-character source SHA are visible with contained wrapping. |
| 14 | `captures/final-375-hello-world.jpg` | 375×812 | `25ce4a530ac7c98debf22dd980db4252f67834d54ea9e5808702573dccd544ea` | Actual plugin instructions and toast action remain readable; action is not executed. |
| 15 | `captures/final-375-job-operations.jpg` | 375×812 | `34f3648ef59131041297978925e7026c179b80daceaae22f4fb501f5bd0e554a` | Actual healthy zero-job state and metrics reflow; no job execution is inferred. Metrics stack in one column. |
| 16 | `captures/final-375-not-found.jpg` | 375×812 | `bd378532731ee501612569c03858462631d0daa6c834412485173fa81de1e2c0` | Intentional routed 404 and return actions are readable; whole Korean words remain intact. |
| 17 | `captures/final-375-models.jpg` | 375×812 | `3a04175bd7303af5686ef0c151b8b8d73805cf405898956cbcf4bcba07408b0c` | Real active 27.3B model card, filters and operational metadata fit without page overflow. |
| 18 | `captures/final-375-history.jpg` | 375×812 | `80cfb8953a647cad0565a6bccc23ea8882a505d7ed3635fd3a6ff5cf48cbe7e4` | History drawer has visible title/X, selectable rows and edit/delete controls; truncation is intentional. |
| 19 | `captures/final-375-inspection-environment.jpg` | 375×812 | `a67c834c9fbcfe892fcb85549e2231e6dfcb028c41440dcd44d54d7a583ca838` | Environment tab is selected; real idle metrics/log panels fit with reachable title and close action. |
| 20 | `captures/final-375-inspection-code.jpg` | 375×812 | `41fa84b7fc26485201d23e9c53ac5ff14a2b6c36805d62a38b7db0a1d2c14cf6` | Code tab is selected; actual editor/file status is contained with visible title and close action. |
| 21 | `captures/final-375-inspection-changes.jpg` | 375×812 | `1688550401854b249edd19d192481a47ba9a0b17e0531f29137c64bcd3be2945` | Changes tab is selected; fully opaque empty state, title and close action are visible. |
| 22 | `captures/final-375-command-palette-early.jpg` | 375×812 | `cb05ca19a7b4fce126fd3437e0f0527d590f2e6868dcc1d4f210b70c4ede514d` | First captured palette surface is opaque and bounded; rows/input are legible, not standalone focus proof. |
| 23 | `captures/final-375-command-palette.jpg` | 375×812 | `b60d3deff7d7c4f9f5d171bfc90c1cf33af920c9b26b55ddd586bac3bba7dd4f` | Settled palette input and named options fit; separate directed receipt supplies actual contained focus cycle. |
| 24 | `captures/final-375-shortcut-guide-early.jpg` | 375×812 | `47541cf9d7c365ad80dd4282ab086b93a056b7ebea959b203ad8d96248545b7d` | First guide surface has visible title/X and bounded shortcut rows; keyboard proof is separate. |
| 25 | `captures/final-375-shortcut-guide.jpg` | 375×812 | `052730aaf4b52a484c80ed0687d3c6d9621e2909d690b9ce1676559ca14660d9` | Settled guide is legible with visible title/X and internal scrolling, backed by directed focus receipts. |
| 26 | `captures/final-375-model-menu.jpg` | 375×812 | `c3e35db8fa7f3bf3282c27281c2d096d086caddf422ee201925e109090ac1f59` | Selected local 27.3B model is distinct; menu stays above composer and rows remain bounded. |
| 27 | `captures/final-375-navigation.jpg` | 375×812 | `f9b6e102dfe02e6102e1fcc31b629eca8609741a709a886b7f8d12dd35685653` | Named route/project/recent rows and close/footer controls fit; footer remains reachable by focus. |
| 28 | `captures/final-375-status-closed.jpg` | 375×812 | `f40f41a30f08ce389c2ae4f88096634949c148c2898dcfae436197d16d0a76ae` | Closed status returns unobstructed chat; visible navigation focus ring and stable composer. |
| 29 | `captures/final-375-empty.jpg` | 375×812 | `f67426b752e4f8e896cecc9a6b22a29e626858d83bc919a3a33c1df51b099598` | Centered welcome, actual suggestions and composer reflow without overlap. Compact toolbar wraps into two contained rows. |
| 30 | `captures/final-375-generation.jpg` | 375×812 | `1d8c3fab87d64a339c3c47708e68062b1ec7a2db31ed99e957b7579aaf6098be` | Actual working status and stop action appear with stable composer and contained transcript. Compact toolbar wraps into two contained rows. |
| 31 | `captures/final-375-chat-complete.jpg` | 375×812 | `028d4b6c3774a3d91267c56dcd6f14b77efb0f4ee6b448bb95f869e968647d2a` | Completed real normal greeting, copy action and 27.3B composer remain readable. Compact toolbar wraps into two contained rows. |
| 32 | `captures/final-375-copy.jpg` | 375×812 | `4dfb6975ec0e59ee33bb8660dda0c4c49177e71bfbc7a3e87c77e0beb86f0fa0` | Copied confirmation is visible without shifting or clipping the response/composer. Compact toolbar wraps into two contained rows. |
| 33 | `captures/final-768-home.jpg` | 768×900 | `da6d5a29f2f6b30d33d189900b7b856967cb96e71d8f8a683fca39b48bb6907b` | Restored transcript, real 27.3B selector and composer fit; open assistant prose and subtle user bubble. |
| 34 | `captures/final-768-chat-alias.jpg` | 768×900 | `b5b70ac675e967d278093914edc1b8e534404e23a244463b34e9e992f6eb3e25` | Same actual chat workspace through /chat; title, transcript and composer remain contained. |
| 35 | `captures/final-768-studio.jpg` | 768×900 | `35a8f55c1767515b9391728ddf72e64bc9f5fc02bf3faee87a16adb0ebec6139` | Pipeline cards and model/title remain legible; operational panels reflow and scroll vertically. |
| 36 | `captures/final-768-start.jpg` | 768×900 | `26385dafacf33daea84f23132d9afca544212f5292197f6e0cda7b93dffbeb23` | Getting-started cards, environment/code paths and local endpoint remain readable and contained. |
| 37 | `captures/final-768-wiki.jpg` | 768×900 | `f481302a314c4fd69543899459733cce75d6290d227d42899f0a3d30f0136d5b` | Actual tree/editor empty state is readable; 생성하세요 stays a whole Korean word. |
| 38 | `captures/final-768-agent.jpg` | 768×900 | `230a41d26b3c254bf0bd570f75f154973218a53d7c549bfd4389b18240927253` | Idle task/log/timeline panels and zero counters remain distinct and contained. |
| 39 | `captures/final-768-settings.jpg` | 768×900 | `0ac40a8534566f7c21c2895e017171d14e6f3df0d1b6ae4fabe34a708a0f907b` | Masked provider rows, labels and controls fit; full helper inspection recorded separately below. |
| 40 | `captures/final-768-skills.jpg` | 768×900 | `c6e4bbe38f0c5c6869a6480abb2e081c535dce0cc59dd85c1b9b2689177bf192` | Skill tabs and bounded empty/error state fit; this does not establish authenticated backend success. |
| 41 | `captures/final-768-data-extraction.jpg` | 768×900 | `efda9f3a44a5ebb854d02197cc6487a6946ef36a3157e922fad8a8cf4677e8b8` | Extraction controls and A/B action label fit; Korean amount phrases remain readable. |
| 42 | `captures/final-768-git.jpg` | 768×900 | `5e1bcb7c369a45ab164c3f4a555a6018429c27fc42389a170400aaa8bbed8d4b` | Populated staged/unstaged/untracked lists and branch fit; bounded diff area scrolls internally. |
| 43 | `captures/final-768-history-page.jpg` | 768×900 | `fcbad533c6fb4887a9fdd2d7909ef107e2f29cde3ed3e3eacb326b165190d84c` | Repository history panes and explanatory prose fit; 저장됩니다 stays a whole word. |
| 44 | `captures/final-768-plugins.jpg` | 768×900 | `bee9513462b8576669ff480596f204bc7a6ea0dd86090a6b7819aa932c2b1334` | Plugin list/status and available actions remain named and readable. |
| 45 | `captures/final-768-mutation.jpg` | 768×900 | `410d8377f6abc57d5dff8f151c1129e5ea5b75909b90e9ab80ed3748db8d2b24` | Mutation report and full 40-character source SHA are visible with contained wrapping. |
| 46 | `captures/final-768-hello-world.jpg` | 768×900 | `9e1b05405498921156b87cf377a7159e0a9f40ee45cc388f514fb4c5be75aa4d` | Actual plugin instructions and toast action remain readable; action is not executed. |
| 47 | `captures/final-768-job-operations.jpg` | 768×900 | `6590d7e7a0ceb7a15095ed8509e4d249cffe267b9a0e6e9face9f15d5e08240e` | Actual healthy zero-job state and metrics reflow; no job execution is inferred. Metrics use a 2×2 grid. |
| 48 | `captures/final-768-not-found.jpg` | 768×900 | `e7cf676e53ba2ccdc8a5d5127d8287a40978eed8632a4ab29ba055353b3af63d` | Intentional routed 404 and return actions are readable; whole Korean words remain intact. |
| 49 | `captures/final-768-models.jpg` | 768×900 | `82a4712bf5b11c0eda5ca8235a1f6f5cb2a6b500d4b82c3f3313e5f2be0b3d04` | Real active 27.3B model card, filters and operational metadata fit without page overflow. |
| 50 | `captures/final-768-history.jpg` | 768×900 | `07e015e0bbcda9ca95cd7218bfb7d4168f8fb0e4422cd80780cbfeac799f6390` | History drawer has visible title/X, selectable rows and edit/delete controls; truncation is intentional. |
| 51 | `captures/final-768-inspection-environment.jpg` | 768×900 | `d03ade01139005b9104bb292ba7c249ee247b412be81732b71379e35a59afd09` | Environment tab is selected; real idle metrics/log panels fit with reachable title and close action. |
| 52 | `captures/final-768-inspection-code.jpg` | 768×900 | `133591f3ab981246cdf88b1b23fbd38156e3a54450bfa5493414488d34086cd4` | Code tab is selected; actual editor/file status is contained with visible title and close action. This is the refreshed settled replacement. |
| 53 | `captures/final-768-inspection-changes.jpg` | 768×900 | `bef926d5eaf4e03cf5403dafa9dde790b85ba79387799a57f4fd63bfab2072f3` | Changes tab is selected; fully opaque empty state, title and close action are visible. This is the refreshed settled replacement. |
| 54 | `captures/final-768-command-palette.jpg` | 768×900 | `8f62bf7506f2915233154f4750b0d1e7f7108bde7b620cac3c1fc093199727df` | Settled palette input and named options fit; separate directed receipt supplies actual contained focus cycle. |
| 55 | `captures/final-768-shortcut-guide.jpg` | 768×900 | `e86e1f7d08822a85edd8c63ab39126b7e695a8cf45ef2ca0b64c082a44579104` | Settled guide is legible with visible title/X and internal scrolling, backed by directed focus receipts. |
| 56 | `captures/final-1280-home.jpg` | 1280×900 | `d5dce6a80e5b2224549acd4d7b4fc9bfeec01e4b297d6671ca95a75566731280` | Restored transcript, real 27.3B selector and composer fit; open assistant prose and subtle user bubble. Persistent named sidebar and recent history are visible. |
| 57 | `captures/final-1280-chat-alias.jpg` | 1280×900 | `06991a726af8b447f8da7a92a6c2f781ad6a414f43b50d8fa81f2e3b8670cbd6` | Same actual chat workspace through /chat; title, transcript and composer remain contained. Persistent named sidebar and recent history are visible. |
| 58 | `captures/final-1280-studio.jpg` | 1280×900 | `b4744bdf687623bd1fd75895039b026a94f01756de9c4e29459de4f75a870ab8` | Pipeline cards and model/title remain legible; operational panels reflow and scroll vertically. Persistent named sidebar and recent history are visible. |
| 59 | `captures/final-1280-start.jpg` | 1280×900 | `2a3fd6a85c868921b6251302c348af38a7ed59961cd8d31c141ef63b22f8fddf` | Getting-started cards, environment/code paths and local endpoint remain readable and contained. |
| 60 | `captures/final-1280-wiki.jpg` | 1280×900 | `bfd36912d3506f63a0f4db1d91bd6aa53f49e24706a15297859d12ed25c854ce` | Actual tree/editor empty state is readable; 생성하세요 stays a whole Korean word. Persistent named sidebar and recent history are visible. |
| 61 | `captures/final-1280-agent.jpg` | 1280×900 | `bc807a98db5a85760049445db57016b1c7c6a26e395ec11869d34143fcb11340` | Idle task/log/timeline panels and zero counters remain distinct and contained. |
| 62 | `captures/final-1280-settings.jpg` | 1280×900 | `907b4da152a8137e8947feb6a99244420a6425bd93747f090db7381e8d13bf72` | Masked provider rows, labels and controls fit; full helper inspection recorded separately below. Persistent named sidebar and recent history are visible. |
| 63 | `captures/final-1280-skills.jpg` | 1280×900 | `b8fa24aa21f94e6f0768b094de83ed54e843bce3ed7d9484441afbe424023f2a` | Skill tabs and bounded empty/error state fit; this does not establish authenticated backend success. |
| 64 | `captures/final-1280-data-extraction.jpg` | 1280×900 | `712a4b2ce051b5fd08f949afa169e33839863acba71699fef2f2c6bf4ccbf1dd` | Extraction controls and A/B action label fit; Korean amount phrases remain readable. |
| 65 | `captures/final-1280-git.jpg` | 1280×900 | `53b08e693ce6ea158af260ceb482fc757afcbbbe7c35cb47bfb67725f60420a5` | Populated staged/unstaged/untracked lists and branch fit; bounded diff area scrolls internally. |
| 66 | `captures/final-1280-history-page.jpg` | 1280×900 | `8769c838194ca1761723894fdf0c049fe70a26dc6a143f81b4b5717aadaab42b` | Repository history panes and explanatory prose fit; 저장됩니다 stays a whole word. |
| 67 | `captures/final-1280-plugins.jpg` | 1280×900 | `8ddb60f6a68cd0d4fd683c6cf4e18a8aaf3df46f97bfe147244b1e407ffa504b` | Plugin list/status and available actions remain named and readable. |
| 68 | `captures/final-1280-mutation.jpg` | 1280×900 | `dc9d9de13e289ea72376313ebea6389d295edacc4f13369475ebbbde2e1baa82` | Mutation report and full 40-character source SHA are visible with contained wrapping. |
| 69 | `captures/final-1280-hello-world.jpg` | 1280×900 | `71f79292c6f5fe7e468985fd275ca3568850537ad6492656cd53e64fca592a2b` | Actual plugin instructions and toast action remain readable; action is not executed. |
| 70 | `captures/final-1280-job-operations.jpg` | 1280×900 | `c92d24798b4722bdba5c1d04308c20115c7172bdfaecbb9bf46f081a9e0f984b` | Actual healthy zero-job state and metrics reflow; no job execution is inferred. Metrics use four columns. |
| 71 | `captures/final-1280-not-found.jpg` | 1280×900 | `1ebbd2471a0c040ffdc514c6c74a74e8e9c237305eee84a516cdfed9b36b0c98` | Intentional routed 404 and return actions are readable; whole Korean words remain intact. |
| 72 | `captures/final-1280-models.jpg` | 1280×900 | `6068fa0658d3037af980f86327f99067e7fca8c073c60cbb7acd792ad48fb7d9` | Real active 27.3B model card, filters and operational metadata fit without page overflow. |
| 73 | `captures/final-1280-inspection-environment.jpg` | 1280×900 | `93cc35d980e48faffe16639e178c7d11665d6e59437870b7541901db8a04f87b` | Environment tab is selected; real idle metrics/log panels fit with reachable title and close action. Desktop inspector is docked. |
| 74 | `captures/final-1280-inspection-code.jpg` | 1280×900 | `2773995acbd2db48aaac049f4bfa5f7ac7fb1d19330a8356a4940e5c8cdf3d58` | Code tab is selected; actual editor/file status is contained with visible title and close action. Desktop inspector is docked. |
| 75 | `captures/final-1280-inspection-changes.jpg` | 1280×900 | `67799594eae0d47c5b344b292279125debde394b6787eebea542ae0225a38674` | Changes tab is selected; fully opaque empty state, title and close action are visible. Desktop inspector is docked. |
| 76 | `captures/final-1280-output.jpg` | 1280×900 | `5c079c8f1fa229634e21291d055e823db248897488ea0af15b18315fe49169eb` | Actual output panel shows honest No output yet; chat composer remains available above it. |
| 77 | `captures/final-1280-status-details.jpg` | 1280×900 | `a081edee4a9abac85a5222a25c84fd7a84332b419676954f49de65f03d20407f` | Expanded actual server/metric disclosure is bounded and distinct from chat content. |
| 78 | `captures/final-1280-chat-complete.jpg` | 1280×900 | `4a47aa42b0982f42364362e24e055b42e89f842fb3bdf6bcc77479842cf04bea` | Completed real normal greeting, copy action and 27.3B composer remain readable. Persistent named sidebar and recent history are visible. |
| 79 | `captures/final-375-settings-helper.jpg` | 375×812 | `3354cf17ec1f85846ccfeff6cda8d68c1558914831359139a444a6537959871e` | Actual default-model helper is fully visible; 보여줍니다 remains a whole word. The complete helper fits on a single line. |
| 80 | `captures/final-768-settings-helper.jpg` | 768×900 | `70cd6e0f1c09d48b0f0dbc239768161cf35177befd644ff649ddba5a4c790be7` | Actual default-model helper is fully visible; 보여줍니다 remains a whole word. The complete helper fits on a single line. |
| 81 | `captures/final-1280-settings-helper.jpg` | 1280×900 | `cf7716ce49dc65ddfcd7cea79f75b33f0e1754beafcec6b17a1a6c5da9464f7a` | Actual default-model helper is fully visible; 보여줍니다 remains a whole word. The predicate moves together to the second line. |

The inventory covers 17 declared routes at each of 375×812, 768×900 and 1280×900, plus 27 states and three located Settings helper frames. Modal early/settled images are separate actual captures, not counted twice as one file. No glyph loss, clipped Korean baseline, overlapping primary control, hidden modal header or black compositor-padding defect was observed in this current inventory.

## Valid original comparison and every diagnostic hotspot

Also opened individually at original detail: `baseline-757.png`, `actual-757.png`, and `deliverable.jpg`, all full 757×954. The receipt binds original `captures/before-default.jpg` SHA `980c78578fecb33dba0e99e61b66172aab26357b7edb81441dd6c33f93a04040`, current `deliverable.jpg` SHA `ac43b9cbf30e945ab4bf7aef6120b0c7d063c660c7a8babd98d5ccf8cf424b34`, baseline PNG SHA `55361e5ac0b9263fa8ecacc4e36467d8df453049570d95fda4688814d93a29ae`, and actual PNG SHA `dd3818247a7e8166864d27c47a139d48abd9d38007aa19c29f7f8f18df57f0f6`. Independent image decoding confirms exact RGB pixel equality for each original JPEG→PNG pair: no resizing, padding, clipping or redrawing. The old black-padded 768 comparator is excluded, as required by `IMAGE_DIFF_RECEIPT.json`.

`IMAGE_DIFF.json` reports equal geometry, 722,178 total pixels, 721,893 different pixels, ratio 0.9996 and similarity 0. The baseline is the prior SSAK layout and a different known synthetic conversation; it is not a Codex Desktop ground-truth image. The near-global background change and deliberately different content make that diagnostic score unsuitable as a quality/fidelity verdict. No alpha-integrity or transition excuse is used to hide a defect.

Every one of the **64 unique 8×8 grid regions** is mapped explicitly below using its actual coordinates, dimensions and ratio. Coordinates are `gridX,gridY`, zero-based; rectangles are `x,y,width,height` in original pixels. Empty-region differences still have a specific token cause. Source correspondence: **root tokens** = `dashboard/src/styles/index.css`; **shell** = `workspace-shell.css` with native Sidebar/WorkspaceNavigation/AppIcon; **chat** = `workspace-chat.css` with actual ChatPage/ChatComposer/ChatMessage; **content** = the distinct recorded synthetic prompt/reply/usage counts. These are causal design/content mappings, not numerical quality scores.

| Grid (x,y) | Rectangle (x,y,w,h) | diffRatio | Specific token/layout/content explanation |
| --- | --- | --- | --- |
| (0,0) | (0,0,94,119) | 0.9992 | Old research/build banner and icon-rail origin become the named workspace/navigation control; system sans and neutral shell tokens. |
| (1,0) | (94,0,95,119) | 0.9992 | Old build/node header becomes quiet workspace header and breadcrumb spacing; shell and root typography. |
| (2,0) | (189,0,94,119) | 0.9996 | Old navigation/telemetry band and former title segment become current breadcrumb/title area; chat 14px hierarchy. |
| (3,0) | (283,0,95,119) | 1 | Old telemetry/title band becomes current editable conversation title; actual new synthetic title and neutral header. |
| (4,0) | (378,0,95,119) | 0.9996 | Old telemetry values and empty header strip become restrained neutral header; root primary background and chat header. |
| (5,0) | (473,0,94,119) | 0.9995 | Old telemetry/right-header actions become native SVG inspection/action controls; shell/chat spacing and AppIcon. |
| (6,0) | (567,0,95,119) | 0.9998 | Old SYS/status and panel controls become current LIVE disclosure and history/panel actions; shell semantic status. |
| (7,0) | (662,0,95,119) | 1 | Old LINK/rightmost controls become bounded server disclosure and monitor action; shell layout and neutral background. |
| (0,1) | (0,119,94,119) | 0.9998 | Old left icon rail becomes full-width neutral reading canvas and left SSAK-AI identity at the lower edge; shell/chat. |
| (1,1) | (94,119,95,119) | 0.9948 | Old left user bubble and avatar position become open canvas; current user message moves to the right, avatar chrome removed. |
| (2,1) | (189,119,94,119) | 0.9916 | Old left user prompt and assistant name position become neutral canvas/identity edge; chat alignment and actual content. |
| (3,1) | (283,119,95,119) | 0.9968 | Old prompt continuation becomes open canvas before the current right-aligned bubble; chat spacing. |
| (4,1) | (378,119,95,119) | 1 | Old prompt tail becomes the start of the current user bubble near x404; current prompt and elevated bubble token. |
| (5,1) | (473,119,94,119) | 1 | Former blank region contains the actual new prompt within a right-aligned rounded bubble; chat 16px and content. |
| (6,1) | (567,119,95,119) | 1 | Former blank region contains current prompt continuation; chat user alignment, elevated surface and content. |
| (7,1) | (662,119,95,119) | 1 | Former blank right region contains the bounded user-bubble end near x733; responsive chat padding and content. |
| (0,2) | (0,238,94,119) | 0.9989 | Old rail/empty left strip now contains assistant mode/greeting/quality starts at x24; open assistant layout and content. |
| (1,2) | (94,238,95,119) | 0.9989 | Old assistant mode/greeting/quality at x114 shifts to the new left reading margin; 16px/27.2px typography and content. |
| (2,2) | (189,238,94,119) | 0.9987 | Old reply/quality continuation becomes longer current greeting and quality continuation; actual different synthetic reply. |
| (3,2) | (283,238,95,119) | 0.9998 | Old empty reply-side area contains the longer actual greeting; 16px/27.2px reading layout and content. |
| (4,2) | (378,238,95,119) | 1 | Old blank area contains the tail of the actual greeting/emoji near x380; generated content, not native chrome. |
| (5,2) | (473,238,94,119) | 1 | Both regions are blank; root primary background changes from the old near-black surface to #202020. |
| (6,2) | (567,238,95,119) | 1 | Both regions are blank; root primary background changes to #202020 across the open reading canvas. |
| (7,2) | (662,238,95,119) | 1 | Both regions are blank; root primary background changes to #202020 up to the bounded right edge. |
| (0,3) | (0,357,94,120) | 0.9999 | Old rail/empty margin becomes actual token-badge start and response-copy control; chat left alignment and native action. |
| (1,3) | (94,357,95,120) | 1 | Old token-badge start becomes current badge continuation with different recorded token counts; content and chat alignment. |
| (2,3) | (189,357,94,120) | 1 | Old token-badge middle becomes current badge end/open canvas; actual counts plus shifted reading margin. |
| (3,3) | (283,357,95,120) | 1 | Old token-badge end becomes neutral open canvas; assistant alignment and root primary background. |
| (4,3) | (378,357,95,120) | 1 | Empty canvas differs through the primary #202020 background token; no missing content is implied. |
| (5,3) | (473,357,94,120) | 1 | Empty canvas differs through the primary #202020 background token; no missing content is implied. |
| (6,3) | (567,357,95,120) | 1 | Empty canvas differs through the primary #202020 background token; no missing content is implied. |
| (7,3) | (662,357,95,120) | 1 | Empty canvas differs through the primary #202020 background token at the right edge; no missing content is implied. |
| (0,4) | (0,477,94,119) | 1 | Old narrow rail and divider become full-width reading canvas; shell removes compact rail, root background changes. |
| (1,4) | (94,477,95,119) | 1 | Empty middle-left canvas changes to root primary #202020; intentional breathing room remains. |
| (2,4) | (189,477,94,119) | 1 | Empty reading canvas changes to root primary #202020; intentional breathing room remains. |
| (3,4) | (283,477,95,119) | 1 | Empty reading canvas changes to root primary #202020; intentional breathing room remains. |
| (4,4) | (378,477,95,119) | 1 | Empty reading canvas changes to root primary #202020; intentional breathing room remains. |
| (5,4) | (473,477,94,119) | 1 | Empty reading canvas changes to root primary #202020; intentional breathing room remains. |
| (6,4) | (567,477,95,119) | 1 | Empty reading canvas changes to root primary #202020; intentional breathing room remains. |
| (7,4) | (662,477,95,119) | 1 | Empty right canvas changes to root primary #202020; intentional breathing room remains. |
| (0,5) | (0,596,94,119) | 1 | Old rail/divider becomes neutral full-width canvas; shell compact navigation strategy and root primary token. |
| (1,5) | (94,596,95,119) | 1 | Empty lower-left canvas changes to root primary #202020; transcript/composer remain separate. |
| (2,5) | (189,596,94,119) | 1 | Empty lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (3,5) | (283,596,95,119) | 1 | Empty lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (4,5) | (378,596,95,119) | 1 | Empty lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (5,5) | (473,596,94,119) | 1 | Empty lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (6,5) | (567,596,95,119) | 1 | Empty lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (7,5) | (662,596,95,119) | 1 | Empty right lower canvas changes to root primary #202020; transcript/composer remain separate. |
| (0,6) | (0,715,94,119) | 1 | Old rail/margin/context-card edge becomes composer edge at x24 and Korean placeholder start; chat layout and tertiary token. |
| (1,6) | (94,715,95,119) | 0.9996 | Old project context card becomes Korean composer placeholder; context is moved below composer, chat typography. |
| (2,6) | (189,715,94,119) | 1 | Old project/local context becomes current placeholder continuation; chat composition and 16px textarea. |
| (3,6) | (283,715,95,119) | 1 | Old branch context becomes Korean placeholder continuation; context moved below, actual composer content. |
| (4,6) | (378,715,95,119) | 1 | Old context-card tail/blank canvas becomes placeholder tail and composer fill; tertiary token and chat layout. |
| (5,6) | (473,715,94,119) | 1 | Old blank canvas becomes neutral tertiary composer fill and border; chat rounded card and root border tokens. |
| (6,6) | (567,715,95,119) | 1 | Old blank canvas becomes neutral tertiary composer fill and border; chat card spans available width. |
| (7,6) | (662,715,95,119) | 1 | Old blank right canvas becomes rounded composer end near x733; chat responsive margins and border radius. |
| (0,7) | (0,834,94,120) | 0.9996 | Old rail/avatar/left composer becomes plus action, composer edge and quiet footer-context start; shell/chat layout. |
| (1,7) | (94,834,95,120) | 1 | Old styled permission pill becomes quiet native permission action and project/local footer; semantic warning retained. |
| (2,7) | (189,834,94,120) | 1 | Old permission/search pills become search/code actions and local/branch footer; quiet toolbar and system typography. |
| (3,7) | (283,834,95,120) | 1 | Old search/code pills become code/MCP actions and branch-footer tail; chat spacing and actual controls. |
| (4,7) | (378,834,95,120) | 1 | Old code/MCP badges become quiet space before the current model selector; toolbar redistribution and neutral fill. |
| (5,7) | (473,834,94,120) | 1 | Old MCP/model area becomes actual 27.3B selector start; real model metadata and chat toolbar alignment. |
| (6,7) | (567,834,95,120) | 1 | Old model area becomes current selector continuation and disabled microphone; actual model preserved, native SVG. |
| (7,7) | (662,834,95,120) | 0.9992 | Old microphone/send glyphs become native disabled mic/send and bounded rounded edge; action token and shared controls. |

These maps explain the actual before/after pixels and cannot excuse a defect on another route. Settings, compact geometry, modal focus and cold history selection were evaluated against their own current originals, measurements, source and interaction receipts above.

## Final scope

**PASS — no outstanding Goal or Visual-A product/evidence blocker on this exact round 9 binding.** The final delivered browser image has original 757×954 geometry, no visible dialog/output panel and an empty draft; the temporary viewport override was reset and the user's tab retained. This report approves the requested adaptive font/layout result and the evidenced preservation behavior. It does not issue another lane's QA/Visual-B decision or expand the stated automated/manual limitations. Later source or capture changes require a new bound review.
