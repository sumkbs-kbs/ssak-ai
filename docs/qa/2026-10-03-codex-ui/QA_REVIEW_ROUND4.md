---
title: Manual QA review — Codex-style SSAK-AI UI, round 3
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Manual QA review

Verdict: **FAIL**. The refreshed packet proves the route surfaces, real 27B generation, copy, reload preservation and keyboard handoff. It also reveals a visible mobile defect: the history and compact inspection headers, including their close controls, are obscured by the status bar. The palette/help captures additionally show overlapping background text and need legible settled-state evidence. These visible problems fail the requested UI scope; unrun native IME and controlled API faults are not additional release blockers.

Execution mode: **QA-agent-directed/root-executed**. This QA agent sent three concrete mobile scenarios before review. Root executed them in the existing user-unlocked **IAB browser2/tab1** and persisted the results. This agent independently read the original plan/design contract, all 51 route DOM snapshots, the current observations/manifests, the directed results, relevant automated test cases and 18 focused screenshots. This agent did not control root's browser profile, create another browser, enter a PIN, read authentication storage or transfer credentials. No source edit, commit or staging operation was made by this QA lane.

## Exact reviewed binding

- Surface: `IAB browser2/tab1`, `http://127.0.0.1:8000/`.
- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- `SOURCE_MANIFEST.json`: SHA-256 `4abc26596d09679a03b0e5e077bc1fb97f9a72c7148fae59b484bcf95653ef75`, 43 files.
- `BUNDLE_MANIFEST.json`: SHA-256 `3826d1f03818531bcd4a1004e6f8194d6815efeca45b93b4a8caba041d65871e`.
- Main script: `/assets/index-CYlhq3Mt.js`, SHA-256 `57732b8b8b74c41b81681724d52ff6b797dbbb635a16c29453e4df4fa1ad86f2`.
- Main CSS: `/assets/index-eFoPJE3Q.css`, SHA-256 `5c177e1f3d82f3549c4b337734c9ecf6355f2781671ad58f2d3074cf25c7b75d`.
- `CAPTURE_MANIFEST.json`: SHA-256 `190b37b471006e3e553bb1773ebe884cdd53354bb972998947f8fa9f32b5130c`.
- `BROWSER_OBSERVATIONS.json`: SHA-256 `3f9543037cbd46249c33fb7e2d408723a7c336b9441d4a581cb51ebc297fbea1`.
- `QA_DIRECTED_RESULTS.json`: SHA-256 `fb84de727b24c60facd45295cce455d3de1814c7ebbf52611784f2cf927e85f2`.
- `LIVE_CHAT_RESULT.json`: SHA-256 `d996b4aa2848f3f045940469ea2bb73b83f591ddd6944d1f5111e5f8a0e72065`.

Independent byte checks matched all 43 source files, all indexed bundle assets and all 70 capture hashes. All 70 frames have JPEG signatures and valid declared dimensions. Every capture postdates the latest bound source edit (`2026-10-03T02:37:11.067026Z`). The 51 route frames contain the same complete 17-route set at 375×812, 768×900 and 1280×900; no route DOM is missing. All 70 observations bind the current main script and report no horizontal overflow. `LIVE_STYLE_BINDING.json` directly records the current main CSS URL. Geometric bounds do not prove that an overlay is above its siblings: the defects below are present despite zero overflow.

The source manifest preserves the recorded before/after hashes of `chatStore.ts`, `projectStore.ts`, `api/client.ts` and `accessPinCredential.ts`. This report reviews the binding above; a later repair requires fresh evidence and a new review.

## Blocking findings

### M1 — compact history and inspection headers are behind the status bar [product]

At 375×812, `final-375-history.jpg` shows the history list but hides the title and close control behind the 48px shell status strip. Only the count is partly visible beneath it. `final-375-inspection-environment.jpg`, `final-375-inspection-code.jpg` and `final-375-inspection-changes.jpg` likewise hide the inspection title and close header. The desktop docked environment capture has a visible title and close action, so this is a compact overlay problem.

`dashboard/DESIGN.md` §4–5 requires labelled compact modals with reachable close headers. The source explains the stacking failure: `index.css:646` gives `.main-content` a stacking context at z-index 1; `workspace-shell.css:6` puts the status bar at z-index 60; the history overlay at `workspace-history.css:1` and compact inspection overlay at `workspace-inspection.css:23` remain descendants of the lower main context. Their larger local z-index values cannot put them above the sibling status bar.

Required closure: place these overlays in a shared top-level modal layer or otherwise remove the trapping stacking context while preserving focus/inert behavior. Capture the history and all three compact tabs with their complete title and close controls visible, then recheck Escape, focus return and draft handoff. Escape working does not make an invisible pointer close control acceptable.

### M2 — palette and shortcut-guide evidence has overlapping background text [evidence; product classification pending settled-state check]

`final-375-command-palette.jpg` visibly superimposes the underlying chat over the search field and results. `final-375-shortcut-guide.jpg` similarly shows chat/composer text through the guide. The DOM and D03 prove the palette owns focus; they do not prove its visible legibility. Root separately confirmed the overlap in these frames and is repairing foreground surfaces.

The palette's declared source background is opaque `var(--bg-secondary)` (`index.css:2816`), but its 150ms `cmd-in` animation varies opacity. Therefore these screenshots alone do not establish whether the overlap persists after the entrance animation or was captured mid-transition. This report does not invent a proven translucent computed background.

Required closure: obtain settled palette and shortcut-guide frames after their entrance animations, with background/opacity observed. If overlap remains, correct the foreground surface; if it disappears, repair capture timing. A readable settled foreground is required before B19 can pass. M1 independently makes the current verdict FAIL regardless of this distinction.

## Original 25-scenario matrix — `manualQa.surfaceEvidence`

The IDs below retain B01–B20 and A01–A05 from `QA_REVIEW_ROUND1.md`. That QA-created matrix incorrectly described `/history` as conversation sessions; B12 is corrected to the actual **file history** route, while A02 covers conversations. Native IME and A05 fault/race checks were originally source-backed augmentation checks, not a user requirement for browser-only fault injection. They remain explicitly AUTOMATED.

For B01–B17, root navigated the listed URL in the existing IAB tab, awaited its rendered page content, and captured DOM/screenshots at all three required viewports. Artifact R means the matching `final-{375,768,1280}-<suffix>` entries in E02/E03; the suffix is named in each row.

| ID | Criterion and actual invocation | Actual result | Verdict | Evidence |
|---|---|---|---|---|
| B01 | `/`; navigate home; inspect composer/model and separately open new-chat empty state | Home renders the chat shell; explicit empty frame shows heading and composer; 27B remains selected. | PASS — manual | R `home`, E08 |
| B02 | `/chat`; navigate alias | Same conversation surface and bounded shell render. | PASS — manual | R `chat-alias` |
| B03 | `/studio`; await `Unsloth Studio` | Base-model selection step, labelled pipeline and model cards render. No training was started. | PASS — manual | R `studio` |
| B04 | `/models`; await `Model Hub` | Current qwen3.8 27.3B is active in the rendered list. The 125B entry was only viewed. | PASS — manual | R `models` |
| B05 | `/start`; await `Unsloth Start` | Agent bridge choices and existing command copy controls render. No command was run. | PASS — manual | R `start` |
| B06 | `/wiki`; await Wiki heading | Document tree and actual selection-empty state render. | PASS — manual | R `wiki` |
| B07 | `/agent`; await `에이전트 모니터링` | Monitoring sections, actual idle/unavailable states and disabled controls render. This is no claim that all agency APIs succeeded. | PASS — manual | R `agent` |
| B08 | `/settings`; inspect masked API fields and layout | Captured credential controls show placeholders/status rather than raw keys; settings/logger content is bounded. No credential was edited. | PASS — manual | R `settings` |
| B09 | `/skills`; await `Skills Browser` | Actual `로드된 스킬이 없습니다.` state renders. Existing auxiliary 401 limits this PASS to displayed layout/state. | PASS — manual | R `skills`, E01 |
| B10 | `/data-extraction`; inspect A/B action and Korean units | `A/B 테스트 실행` is unbroken; `만원` and `억원` remain intact words in the compact body. Dashboard and controls render. Existing metrics 401 is not backend success. | PASS — manual | R `data-extraction`, E09 |
| B11 | `/git`; await Git heading | Git inspection controls and actual working-tree content render. No Git mutation was executed. | PASS — manual | R `git` |
| B12 | `/history`; await `파일 히스토리` | File history surface renders. This route is not the conversation drawer. | PASS — manual | R `history-page` |
| B13 | `/plugins`; await plugin heading | Plugin index renders. | PASS — manual | R `plugins` |
| B14 | `/mutation`; await `Mutation test history` | Historical snapshot content, provenance and filters render; no live mutation run is claimed. | PASS — manual | R `mutation` |
| B15 | `/plugins/hello-world`; await plugin heading | Registered plugin content renders. | PASS — manual | R `hello-world` |
| B16 | `/plugins/job-operations`; await `Job Operations` | Actual healthy/zero-jobs/empty-history state renders. No job was created or retried. | PASS — manual | R `job-operations` |
| B17 | `/ui-qa-not-found`; intentional unknown route | NotFound renders inside the shell; `주소가` now stays intact. Return controls are visible. | PASS — manual | R `not-found`, E09 |
| B18 | 375px; open nav, Shift+Tab at first control, Tab at last, Escape | Both focus wraps stay inside navigation. Escape leaves zero visible dialogs/inert regions and returns focus to `탐색 메뉴 열기`. | PASS — manual | D02, E05, E10 |
| B19 | 375px; Meta+K from inspection with draft; Escape; Meta+/ guide | Palette combobox owns focus; dismissal releases inert state and retains draft. Supplied palette/guide frames have overlapping background text, so foreground legibility is not accepted. | FAIL — visible evidence | D03, E05, E11 |
| B20 | 375px; real reload, reopen model selector and history | 27B option is pressed; original two history titles remain. Popover fits the viewport. No 125B load or model switch occurred. | PASS — manual | D01, E05, E12 |
| A01 | 375px compact and 1280px docked environment/code/changes tabs | Tabs/content render and desktop close header is visible. Compact title/close header is hidden by the status strip. | FAIL — product M1 | E13 |
| A02 | 375px; open conversation history and select existing session | Existing titles/content are retained and selection returns to chat; drawer title/close header is hidden. `/history` is separately verified as file history. | FAIL — product M1 | E12, E13, R `history-page` |
| A03 | 375px; Shift+Enter; plain Enter for real prompt; copy completed response; IME source-backed checks | Live reply is `연결이 정상적으로 활성화되어 있습니다.`. Newline and clipboard match are true, and copied feedback is visible. IME/keyCode229 guards pass automated cases; no native IME sequence was run. | PASS — manual keyboard/chat/copy; IME AUTOMATED | E06, E07, E14 |
| A04 | 1280px; open bottom panel, choose output, await controls; close without command | `출력 탭`, source filters and explicit `No output yet`/0 entries render. No command was entered or sent. | PASS — manual | E15 |
| A05 | Source-backed 503/CAS/hydration recovery augmentation | Passing automated cases cover typed migration503/conflict errors, failed permission503 preservation and early draft/new-session hydration guards. No browser fault injection or hydration race was executed. No browser retry UI PASS is asserted. | AUTOMATED — not manually asserted | E07 |

Counts: **21 manual PASS, 3 manual FAIL, 1 AUTOMATED-only row**. A03 additionally labels its IME portion AUTOMATED. These are 25 original rows, not 25 claimed browser passes.

## Directed and adversarial results — `manualQa.adversarialCases`

| ID | Boundary | Observed result | Result / mode | Evidence |
|---|---|---|---|---|
| D01 | Actual reload/model/history preservation | Pressed 27B and original two titles retained after reload; a third synthetic QA conversation was subsequently added through normal UI without deleting either original. | PASS — root manual execution | E05, E12 |
| D02 | Forward/reverse nav focus wrap and Escape | Reverse reaches terminal control, forward reaches close control; both remain inside nav; Escape returns to opener with dialogs/inert zero. | PASS — root manual execution | E05, E10 |
| D03 | Draft before inspection → foreground palette → dismissal | Active `검색어 입력` combobox, only foreground palette; dismissal leaves dialogs/inert zero and retains unsent draft. Visible palette legibility remains M2. | PASS for focus/draft; FAIL for supplied visual evidence | E05, E11 |
| B17 | Unknown route and Korean wrapping | Intentional fallback renders; `주소가` is no longer fractured. | PASS — manual surface | E09 |
| B20 | Mobile model popover bounds | Popover fits 375px and current 27.3B is visible. | PASS — manual surface | E12 |
| A01/A02 | Reachable compact modal header | Title and pointer close controls are behind status strip. | FAIL — product | E13 |
| A03 | Shift+Enter, send and copy | Newline without send; real completed 27B reply; copied feedback and clipboard match. | PASS — root manual execution | E06, E14 |
| A03 IME | Active composition / legacy key229 | Automated event tests preserve draft and do not invoke stream submission. | AUTOMATED only | E07 |
| A05 | 503/CAS/late hydration | Typed failure/error and state-preservation tests pass; no manual injected browser case claimed. | AUTOMATED only | E07 |
| A04 | Output read-only inspection | Actual empty output viewer inspected; no terminal command sent. | PASS — root manual execution | E15 |

Supplemental status disclosure: `final-1280-status-details.jpg` and its DOM show actual build, uptime, process, CPU, memory and zero indexed vault entries; root exercised Escape dismissal. `final-375-status` is a closed disclosure frame. This is supplemental evidence, not a newly invented 26th original scenario. Only the observed LIVE state is manually asserted; UNKNOWN/zero/stale distinctions retain automated/source coverage.

## Artifact references — `manualQa.artifactRefs`

All paths below are within `docs/qa/2026-10-03-codex-ui/` unless stated otherwise.

| ID | Kind | Path / scope |
|---|---|---|
| E01 | Readiness and honest limits | `QA_CAPTURE_READY.md` |
| E02 | Full 70-image inventory | `CAPTURE_MANIFEST.json` |
| E03 | Full 70 current observations; 51 route DOM files | `BROWSER_OBSERVATIONS.json`, `captures/final-{375,768,1280}-<route>.dom.txt` as enumerated in E02 |
| E04 | Hash/format/dimension/CSS/freshness evidence | `SOURCE_MANIFEST.json`, `BUNDLE_MANIFEST.json`, `CAPTURE_HYGIENE.json`, `LIVE_STYLE_BINDING.json` |
| E05 | Independent QA instructions executed by root | `QA_DIRECTED_RESULTS.json` |
| E06 | Current real chat/newline/clipboard result | `LIVE_CHAT_RESULT.json` |
| E07 | Automated coverage and current verification | `VERIFICATION.json`, `TESTS_CURRENT.log` (101 files/980 tests); `dashboard/src/components/Chat/__tests__/ChatPageComposer.test.tsx`, `ChatPageHydration.test.tsx`, `dashboard/src/api/client.test.ts`, `dashboard/src/stores/__tests__/chatStore.modelPreference.test.ts` |
| E08 | Explicit empty-state capture | `captures/final-375-empty.jpg` |
| E09 | Repaired CJK surfaces | `captures/final-375-data-extraction.jpg`, `captures/final-375-not-found.jpg` and matching DOM |
| E10 | Navigation focus surface | `captures/final-375-navigation.jpg`, matching DOM; D02 post-dismissal observations in E05 |
| E11 | Foreground modal overlap evidence | `captures/final-375-command-palette.jpg`, matching DOM, `captures/final-375-shortcut-guide.jpg`; D03 in E05 |
| E12 | Reload/model/history evidence | `captures/final-375-model-menu.jpg`, `captures/final-375-history.jpg`, `captures/final-375-reload-history.dom.txt` |
| E13 | Compact overlay header defect and desktop contrast | `captures/final-375-history.jpg`, `captures/final-375-inspection-environment.jpg`, `captures/final-375-inspection-code.jpg`, `captures/final-375-inspection-changes.jpg`, `captures/final-1280-inspection-environment.jpg` |
| E14 | Real generation/completion/copy states | `captures/final-375-generation.jpg`, `captures/final-375-chat-complete.jpg` and DOM, `captures/final-375-copy.jpg` |
| E15 | Actual output/status surfaces | `captures/final-1280-output.jpg` and DOM, `captures/final-1280-status-details.jpg` and DOM |
| E16 | Design and original matrix | `dashboard/DESIGN.md`, `docs/frontend/EXECUTION_PLAN_2026-10-03.md`, `QA_REVIEW_ROUND1.md` |

## Review scope and limitations

The user asked to adapt Codex-inspired typography/composition while preserving current chat/core/auth. There is no supplied exact Desktop pixel target, no proprietary font-copy claim, no native-device IME run, no browser axe/Lighthouse score and no backend full-suite rerun. The auxiliary Skills/Metrics 401 states remain existing limitations; route PASS rows certify rendered UI/state, not API success.

The earlier round-two demand for native IME, controlled503/CAS and hydration-race browser-only proof expanded the actual task unnecessarily. Those automated checks are valuable preservation evidence and are honestly labelled here; they do not cause this FAIL. The actual blockers are the compact modal layering defect and the unreadable foreground evidence. This one-shot QA lane ends with the report; root owns fixes and fresh re-review on the next source/CSS/capture binding.
