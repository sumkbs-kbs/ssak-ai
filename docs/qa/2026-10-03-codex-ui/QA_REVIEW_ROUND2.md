---
title: Manual QA review — Codex-style SSAK-AI UI
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Manual QA review

Verdict: **FAIL for the complete manual-QA gate; PASS for the directly evidenced route/layout and live-chat surfaces.** The failure is deliberate: required adversarial browser cases for native IME composition, controlled 503/CAS faults, late hydration replacement, and model persistence after reload do not have direct root-tab evidence in the ready packet. They are recorded as failures or blockers rather than inferred passes.

Execution mode: **QA-agent-directed/root-executed**. The QA agent inspected the plan, current manifests, observations, DOM captures and screenshots. The root operator executed the browser actions in the existing user-unlocked **IAB browser2/tab1**. The QA agent did not control the browser, enter a PIN, read credentials/storage, or create another browser session.

## Exact binding

- Surface: `IAB browser2/tab1`, `http://127.0.0.1:8000/`
- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` (no commit or staging was created during QA)
- Source manifest: `855b9221a7bfca549813e226f530fd5b406dbefc800cc53c35e31ad45b84cc20` (41 files)
- Main script: `/assets/index-BjO0ehSf.js`, SHA-256 `6f34e2ac4eee4680114937ebeda49a33775b31d7a3843e7103af58a555058121`
- Main CSS: `/assets/index-BXtJe53D.css`, SHA-256 `85eeb82aa7bf1ce6a5ade91948d0bffc78683a10c2fcff5bbcfa6116551c223a`
- Capture packet: 51 route frames (17 routes × 375×812, 768×900, 1280×900) plus 18 interaction frames; all current-build JPEGs passed signature and dimension hygiene.

The current packet supersedes the round-one PIN-locked record. It does not supersede the requirement for direct evidence of an adversarial case: unit tests and source review are expected-behavior evidence, not browser execution evidence.

## `manualQa.surfaceEvidence`

| Scenario ID | Criterion reference | Surface and exact invocation | Actual result | Verdict | Artifact refs |
|---|---|---|---|---|---|
| B01 | `/` initial hydration | Root IAB tab; viewport 375×812; `goto('http://127.0.0.1:8000/')`; wait for chat region; DOM snapshot + screenshot | Shell, status banner, empty chat state and composer rendered on the current bundle. | PASS | A01,A02,A07 |
| B02 | `/chat` alias | Root IAB tab; viewport 375×812; `goto('http://127.0.0.1:8000/chat')`; wait for textbox; DOM snapshot + screenshot | Alias resolved to the chat surface with the same shell and no measured horizontal overflow. | PASS | A02,A08 |
| B03 | `/studio` | Root IAB tab; viewport 375×812; `goto('/studio')`; wait for heading `Unsloth Studio`; DOM snapshot + screenshot | Studio heading and base-model step rendered. | PASS | A02,A09 |
| B04 | `/models` | Root IAB tab; viewport 375×812; `goto('/models')`; wait for heading `Model Hub`; DOM snapshot + screenshot | Model Hub cards and category content rendered; current route frame reports zero measured overflow. | PASS | A02,A10 |
| B05 | `/start` | Root IAB tab; viewport 375×812; `goto('/start')`; wait for heading `Unsloth Start`; DOM snapshot + screenshot | Agent-start choices rendered with labelled headings. | PASS | A02,A11 |
| B06 | `/wiki` | Root IAB tab; viewport 375×812; `goto('/wiki')`; wait for heading `📚 Wiki`; DOM snapshot + screenshot | Wiki page rendered in the shell. | PASS | A02,A12 |
| B07 | `/agent` | Root IAB tab; viewport 375×812; `goto('/agent')`; wait for heading `에이전트 모니터링`; DOM snapshot + screenshot | Monitoring page rendered with its visible sections and filters. | PASS | A02,A13 |
| B08 | `/settings` secrets masking/layout | Root IAB tab; viewport 375×812; `goto('/settings')`; wait for heading `시스템 설정`; DOM snapshot + screenshot | Settings rendered, long logger rows fit after the final CSS correction, and no raw credential value is exposed in the captured DOM. | PASS | A02,A14 |
| B09 | `/skills` | Root IAB tab; viewport 375×812; `goto('/skills')`; wait for heading `Skills Browser`; DOM snapshot + screenshot | Skills page rendered its explicit empty state. The auxiliary skills request is an existing 401; this pass is for displayed UI/layout only. | PASS | A02,A15 |
| B10 | `/data-extraction` | Root IAB tab; viewport 375×812; `goto('/data-extraction')`; wait for page heading; DOM snapshot + screenshot | Data extraction dashboard rendered without measured overflow. | PASS | A02,A16 |
| B11 | `/git` | Root IAB tab; viewport 375×812; `goto('/git')`; wait for heading `🐙 Git 소스 제어`; DOM snapshot + screenshot | Git page and its visible controls rendered. | PASS | A02,A17 |
| B12 | `/history` | Root IAB tab; viewport 375×812; `goto('/history')`; wait for heading `⏱️ 파일 히스토리`; DOM snapshot + screenshot | File history page rendered in the current shell. | PASS | A02,A18 |
| B13 | `/plugins` | Root IAB tab; viewport 375×812; `goto('/plugins')`; wait for heading `플러그인`; DOM snapshot + screenshot | Plugin index rendered. | PASS | A02,A19 |
| B14 | `/mutation` | Root IAB tab; viewport 375×812; `goto('/mutation')`; wait for heading `Mutation test history`; DOM snapshot + screenshot | Mutation history rendered with its filter buttons and records. | PASS | A02,A20 |
| B15 | `/plugins/hello-world` | Root IAB tab; viewport 375×812; `goto('/plugins/hello-world')`; wait for heading `Hello from Plugin System!`; DOM snapshot + screenshot | Plugin page rendered. | PASS | A02,A21 |
| B16 | `/plugins/job-operations` | Root IAB tab; viewport 375×812; `goto('/plugins/job-operations')`; wait for heading `Job Operations`; DOM snapshot + screenshot | Job Operations rendered with its visible healthy/empty-state data. | PASS | A02,A22 |
| B17 | intentional unknown route fallback | Root IAB tab; viewport 375×812; `goto('/ui-qa-not-found')` (the packet’s declared intentional unknown route); wait for heading `페이지를 찾을 수 없습니다`; DOM snapshot + screenshot | NotFound fallback rendered inside the shell. | PASS | A02,A23 |
| B18 | mobile navigation drawer/focus return | Root IAB tab; viewport 375×812; `goto('/')`; click `button[name="탐색 메뉴 열기"]`; DOM/screenshot; press Escape; inspect active control | Drawer and backdrop appeared; Escape dismissed it and root observed focus return without overflow. | PASS | A02,A24 |
| B19 | command palette and shortcut guide | Root IAB tab; viewport 375×812; close prior modal; press `Meta+k`; wait for `dialog[name="명령 팔레트"]`; Escape; press `Meta+/`; wait for `dialog[name="키보드 단축키"]`; DOM/screenshot | Both keyboard surfaces appeared in the foreground, were labelled, and closed through the tested path. | PASS | A02,A25,A26 |
| B20a | model selector mobile layout | Root IAB tab; viewport 375×812; click `button[name="모델 선택"]`; DOM/screenshot; close menu | Popover stayed within the 375px viewport; current selection showed `qwen3.8:latest (27.3B)` and did not activate the 125B model. | PASS | A02,A27 |
| B20b | model preference persistence after reload | Root IAB tab; click model selector, reload, reopen selector; inspect selected model | The ready packet contains menu/selection evidence but no direct post-selection reload capture. | FAIL — direct reload evidence missing | A02,A27 |
| A01 | inspection tabs, bounded panel and handoff | Root IAB tab; 375×812: click `환경 패널 토글`, then tabs `코드` and `변경`; 1280×900: repeat for docked panel; DOM/screenshot; close panel | Environment, code and changes tabs rendered at both compact and desktop surfaces; the compact panel behaved as a labelled modal and desktop panel as a docked column. | PASS | A02,A28,A29,A30,A31 |
| A02 | history drawer selection/route link | Root IAB tab; viewport 375×812; click `대화 기록 열기`; select an existing session button; inspect resulting chat/DOM | History drawer opened with two sessions; selecting an existing session returned to the conversation and preserved the selected content. | PASS | A02,A32,A33 |
| A03a | composer Shift+Enter/plain Enter/copy | Root IAB tab; viewport 375×812; fill `줄바꿈 검증`; press `Shift+Enter`; evaluate `textarea.value.endsWith('\\n')`; clear; use real completed chat; click `응답 복사`; read clipboard | Shift+Enter produced a newline without sending; completed real response was `연결 정상입니다.`; clipboard matched the response. | PASS | A02,A34,A35 |
| A03b | native IME composition | Root IAB tab; native IME composition event sequence | No native IME/device automation was executed in the authorized browser packet. Unit-backed IME tests are not browser-manual evidence. | FAIL — missing native IME prerequisite | A01,A36 |
| A04 | terminal/output viewer read-only safety | Root IAB tab; viewport 1280×900; click `터미널 열기 또는 닫기`; click `출력 탭`; wait for lazy loading to settle; DOM/screenshot; close `터미널 패널 닫기` without entering a command | Output controls rendered; explicit `No output yet`/`0 entries` state was visible; no command was entered or submitted during the read-only inspection. | PASS | A02,A37,A38 |
| A05a | 503 retry/CAS conflict | Root IAB tab; controlled HTTP 503/CAS response injection would be required before navigating/submitting | No fault-injection fixture or controlled response was available in the authorized browser surface. | FAIL — blocker: no controlled 503/CAS prerequisite | A01,A39 |
| A05b | late project hydration replacement guard | Root IAB tab; start empty chat, type a draft before async project identity/history settles, capture before/after hydration | The packet records real reload/history observations and unit coverage, but no direct before/after draft-vs-late-hydration browser artifact. | FAIL — direct hydration-race capture missing | A01,A40 |
| A06 | status disclosure | Root IAB tab; viewport 1280×900; click `label[서버 연결 및 시스템 지표]`; DOM/screenshot; press Escape | Live server details (build, uptime, process, CPU, memory, vault) were visible; Escape closed the disclosure. | PASS | A02,A41,A42 |

The route PASS rows mean the route surface rendered and its captured layout was bounded. They do not mean auxiliary backend APIs succeeded: the ready packet records existing 401 responses for Skills/Metrics and the route captures show the actual page/error state.

## `manualQa.adversarialCases`

| Scenario ID | Criterion reference | Adversarial class | Expected behavior | Verdict | Artifact refs |
|---|---|---|---|---|---|
| ADV-01 | B17 | Unknown-route fallback | An intentional unknown route shows the NotFound page inside the app shell. | PASS | A23 |
| ADV-02 | B18 | Responsive drawer/focus trap | Drawer opens at 375px, Escape closes it, focus returns to the opener, and the page does not overflow horizontally. | PASS | A24 |
| ADV-03 | B20a | Mobile popover overflow | Model popover remains inside 375px and the selected 27.3B model is visible. | PASS | A27 |
| ADV-04 | B20b | Reload persistence | Selected model remains selected after a real reload. | FAIL — not directly run; missing post-reload artifact | A27 |
| ADV-05 | B08 | Secret masking | Settings does not display raw credentials or keys. | PASS | A14 |
| ADV-06 | A03b | Native IME/Enter collision | Active composition is not submitted; plain Enter sends only after composition ends. | FAIL — native IME sequence not executable in this packet | A36 |
| ADV-07 | A03a | Shift+Enter draft newline | Shift+Enter creates a newline and leaves the draft unsent. | PASS | A34 |
| ADV-08 | A04 | Read-only output inspection/command transmission | Opening and reading output does not execute or submit a command. | PASS | A37,A38 |
| ADV-09 | A05a | HTTP 503 retry/CAS conflict | Retry and conflict states are explicit and preserve user input. | FAIL — no controlled HTTP fault fixture | A39 |
| ADV-10 | A05b | Late project hydration replacement | Only an untouched empty chat may be replaced by project cache; draft/session state survives. | FAIL — no direct browser race capture | A40 |
| ADV-11 | B19 | Keyboard modal collision/focus handoff | Palette and shortcut guide are keyboard reachable, foregrounded, dismissible, and do not leave a stale trap. | PASS | A25,A26 |
| ADV-12 | B03–B16 | CJK/long-label/layout clipping | Korean labels and long IDs wrap; route frames have no measured horizontal overflow at required widths. | PASS | A02,A09–A23 |
| ADV-13 | A06 | Live/stale status disclosure | Status details disclose the actual live metrics and close with Escape. | PASS | A41,A42 |

## `manualQa.artifactRefs`

| ID | Kind | Description | Path |
|---|---|---|---|
| A01 | readiness | Current root-operator handoff and explicit manual limits | `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md` |
| A02 | manifest/observation | Current 69-capture manifest and deduplicated current-bundle observations | `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST.json`, `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json` |
| A03 | hygiene | JPEG signature, dimension and current-main-bundle validation | `docs/qa/2026-10-03-codex-ui/CAPTURE_HYGIENE.json` |
| A04 | binding | 41-file source manifest and exact dirty-source digest | `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json` |
| A05 | binding | Built asset manifest, main script and CSS hashes | `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json` |
| A06 | route screenshots | Representative home and alias route screenshots | `docs/qa/2026-10-03-codex-ui/captures/final-375-home.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-chat-alias.jpg` |
| A07 | route DOM | Initial chat DOM snapshot | `docs/qa/2026-10-03-codex-ui/captures/final-375-home.dom.txt` |
| A08 | route screenshot | `/chat` alias screenshot | `docs/qa/2026-10-03-codex-ui/captures/final-375-chat-alias.jpg` |
| A09 | route screenshot/DOM | Studio route | `docs/qa/2026-10-03-codex-ui/captures/final-375-studio.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-studio.dom.txt` |
| A10 | route screenshot/DOM | Model Hub route | `docs/qa/2026-10-03-codex-ui/captures/final-375-models.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-models.dom.txt` |
| A11 | route screenshot/DOM | Start route | `docs/qa/2026-10-03-codex-ui/captures/final-375-start.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-start.dom.txt` |
| A12 | route screenshot/DOM | Wiki route | `docs/qa/2026-10-03-codex-ui/captures/final-375-wiki.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-wiki.dom.txt` |
| A13 | route screenshot/DOM | Agent route | `docs/qa/2026-10-03-codex-ui/captures/final-375-agent.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-agent.dom.txt` |
| A14 | route screenshot/DOM | Settings route and logger-row correction | `docs/qa/2026-10-03-codex-ui/captures/final-375-settings.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-settings.dom.txt` |
| A15 | route screenshot/DOM | Skills route actual empty/error state | `docs/qa/2026-10-03-codex-ui/captures/final-375-skills.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-skills.dom.txt` |
| A16 | route screenshot/DOM | Data extraction route | `docs/qa/2026-10-03-codex-ui/captures/final-375-data-extraction.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-data-extraction.dom.txt` |
| A17 | route screenshot/DOM | Git route | `docs/qa/2026-10-03-codex-ui/captures/final-375-git.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-git.dom.txt` |
| A18 | route screenshot/DOM | File history route | `docs/qa/2026-10-03-codex-ui/captures/final-375-history-page.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-history-page.dom.txt` |
| A19 | route screenshot/DOM | Plugin index route | `docs/qa/2026-10-03-codex-ui/captures/final-375-plugins.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-plugins.dom.txt` |
| A20 | route screenshot/DOM | Mutation route | `docs/qa/2026-10-03-codex-ui/captures/final-375-mutation.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-mutation.dom.txt` |
| A21 | route screenshot/DOM | Hello World plugin route | `docs/qa/2026-10-03-codex-ui/captures/final-375-hello-world.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-hello-world.dom.txt` |
| A22 | route screenshot/DOM | Job Operations route | `docs/qa/2026-10-03-codex-ui/captures/final-375-job-operations.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-job-operations.dom.txt` |
| A23 | adversarial route screenshot/DOM | Intentional NotFound route | `docs/qa/2026-10-03-codex-ui/captures/final-375-not-found.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-not-found.dom.txt` |
| A24 | interaction screenshot | Mobile navigation drawer | `docs/qa/2026-10-03-codex-ui/captures/final-375-navigation.jpg` |
| A25 | interaction screenshot | Command palette | `docs/qa/2026-10-03-codex-ui/captures/final-375-command-palette.jpg` |
| A26 | interaction screenshot | Shortcut guide | `docs/qa/2026-10-03-codex-ui/captures/final-375-shortcut-guide.jpg` |
| A27 | interaction screenshot/DOM | Model menu and bounded popover | `docs/qa/2026-10-03-codex-ui/captures/final-375-model-menu.jpg`, `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json` |
| A28 | interaction screenshot | Compact Environment inspection | `docs/qa/2026-10-03-codex-ui/captures/final-375-inspection-environment.jpg` |
| A29 | interaction screenshot | Compact Code inspection | `docs/qa/2026-10-03-codex-ui/captures/final-375-inspection-code.jpg` |
| A30 | interaction screenshot | Compact Changes inspection | `docs/qa/2026-10-03-codex-ui/captures/final-375-inspection-changes.jpg` |
| A31 | interaction screenshot/DOM | Desktop inspection and output panel | `docs/qa/2026-10-03-codex-ui/captures/final-1280-inspection-environment.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-1280-inspection-code.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-1280-inspection-changes.jpg` |
| A32 | interaction screenshot/DOM | History drawer | `docs/qa/2026-10-03-codex-ui/captures/final-375-history.jpg` |
| A33 | completed-chat screenshot/DOM | Selected existing response | `docs/qa/2026-10-03-codex-ui/captures/final-375-chat-complete.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-chat-complete.dom.txt` |
| A34 | interaction screenshot/DOM | Shift+Enter and completed generation | `docs/qa/2026-10-03-codex-ui/captures/final-375-generation.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-375-chat-complete.dom.txt` |
| A35 | clipboard interaction screenshot | Copy feedback after completed response | `docs/qa/2026-10-03-codex-ui/captures/final-375-copy.jpg` |
| A36 | limitation evidence | Native IME excluded from browser packet | `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md` |
| A37 | output screenshot/DOM | Desktop output panel settled state | `docs/qa/2026-10-03-codex-ui/captures/final-1280-output.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-1280-output.dom.txt` |
| A38 | completed-chat screenshot | Desktop completed result before/after read-only panel | `docs/qa/2026-10-03-codex-ui/captures/final-1280-chat-complete.jpg` |
| A39 | limitation evidence | No controlled 503/CAS fixture in root surface | `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md` |
| A40 | limitation evidence | No direct hydration-race browser capture | `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY.md`, `docs/qa/2026-10-03-codex-ui/VERIFICATION.json` |
| A41 | status screenshot/DOM | Open desktop status disclosure | `docs/qa/2026-10-03-codex-ui/captures/final-1280-status-details.jpg`, `docs/qa/2026-10-03-codex-ui/captures/final-1280-status-details.dom.txt` |
| A42 | live metrics | Measured live typography/layout and status evidence | `docs/qa/2026-10-03-codex-ui/TYPOGRAPHY_LIVE.json` |

## Execution limits and follow-up

No scenario was marked `not_applicable`: each listed class is relevant to this UI change. The four FAIL rows are either direct partial-coverage failures or genuinely unavailable browser prerequisites. Re-running the unit suite would not convert these to browser-manual PASS results. To close the gate, execute a real native IME sequence, provide a controlled 503/CAS fixture, capture the draft/session state before and after late project hydration, and capture the selected model after a real reload in the root tab.
