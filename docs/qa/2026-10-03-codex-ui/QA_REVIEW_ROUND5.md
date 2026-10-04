---
title: Manual QA review — Codex-style SSAK-AI UI, round 5
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Manual QA review

Verdict: **REVISE**. The fresh 375px captures and actual close actions resolve the previous compact history/inspection layering defect and show readable opaque palette/guide entry. A new real keyboard failure blocks B19: the shortcut guide opens without moving focus inside, reverse Tab escapes to the background message-send button, and close/Escape do not restore the opener. This verdict is for the exact partial round-five binding below; it is not an approval of a complete current-build route packet.

Execution mode: **QA-agent-directed/root-executed**. This independent QA judge sent concrete operator instructions before execution. Root alone operated the existing user-unlocked **IAB browser2/tab1** at `http://127.0.0.1:8000/`, using real clicks and keys. This judge independently inspected the plan/design contract, original 25-row matrix, all 10 unique current partial screenshots, 11 current observations, directed results, source/bundle hashes, modal implementation and relevant automated tests. This judge did not open another browser profile, request/enter a PIN, inspect authentication storage, transfer credentials, edit production source, stage or commit changes.

## Exact reviewed binding

- Git HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus dirty source.
- `SOURCE_MANIFEST_ROUND5.json`: SHA-256 `7adf26f802aa3a1092a96f606951bbdc9606785eb9c20f83b22df0c35b93c236`, 43 files.
- `BUNDLE_MANIFEST_ROUND5.json`: SHA-256 `65c37d975b7cf2dc37e1104cf240d15abf58c7c46e57886fbdab8a2f5a825dd1`.
- Main JavaScript: `/assets/index-D6IQTpgA.js`, SHA-256 `8489943e7e1646edc48391f7f43af547a7a5a4026cab3bc9abf5e2a9330b1f87`.
- Main CSS: `/assets/index-BLgp1deP.css`, SHA-256 `78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b`.
- `BROWSER_OBSERVATIONS_ROUND5.json`: SHA-256 `232d347d09f5bfacd0c67e6ceeba6fbcd14bf486aef7757cb8b62833adb34e14`.
- `QA_DIRECTED_RESULTS_ROUND5.json`: SHA-256 `8261966121054199b6d7f255022ad58049cbe51e8d3fc5193109fb059a4575e7`.

Independent checks matched all 43 source hashes and all 104 production-output asset hashes in `src/antigravity_k/dashboard_dist`. These checks were made before the newly assigned guide repair. A subsequent source/bundle must be reviewed with a new binding.

The partial packet has **11 observations and 10 unique screenshots**, all 375×812 and all observing `index-D6IQTpgA.js`. The earlier shortcut-guide-early attempt had no guide dialog; the latest observation at `2026-10-03T03:01:27.275Z` and matching stored screenshot correctly show the guide. All 10 unique images have JPEG signatures and exact 375×812 dimensions. Each was opened directly, including the code-tab frame at original detail. The packet is archived in `captures/round5/`.

The planned fresh 72-frame inventory was stopped when the real guide flaw was discovered. There is no complete fresh 17-route × three-viewport packet or current 768px closure proof for this binding. `QA_CAPTURE_READY_ROUND4.md` and `CAPTURE_MANIFEST_ROUND4.json` describe the previous 70-frame `4abc…/CYlhq3Mt` build and cannot certify this build. Root explicitly instructed this one-shot review to finish REVISE on the new observed blocker, with a full fresh packet required after its repair.

## Blocking finding

### G1 — shortcut guide does not contain or restore keyboard focus [product, P1]

At 375×812, root pressed **Meta+Slash** to open the visible `키보드 단축키` dialog. The active element stayed on **대화 기록 열기** outside the guide. Tab reached its close button, but **Shift+Tab from that close button reached 메시지 전송 outside the guide**. Actual X dismissal and a second opening/Escape both closed the guide while leaving focus on the body instead of returning to the opener. The unsent draft remained intact.

This is recorded in `QA_DIRECTED_RESULTS_ROUND5.json` → `guideFailure`: `initialActive: 대화 기록 열기`, `closeShiftTab.insideGuide: false`, `closeShiftTab.active: 메시지 전송`, and `closeAndEscape.restoredOpener: false`. The separate `375 guide close` and `375 guide Escape` observations record zero dialogs/inert regions but a body-derived active-element label. Closing correctly and preserving the draft do not satisfy focus containment/return.

The inspected pre-repair `dashboard/src/components/UI/KeyboardShortcutsModal.tsx` (SHA-256 `93aa52be9ca129bf986f04de421a3e6c6f58bded67dc6c4c118f231b015a5fe6`) uses a standalone window Escape effect and an overlay ref; it does not use the shared modal-dialog focus lifecycle. This matches the observed behavior. `dashboard/DESIGN.md` §4–5 and §8 require keyboard containment and restoration for modal interactions.

Required closure: apply the shared modal-dialog focus/inert lifecycle to the guide, then use actual browser keys/clicks at 375×812 and 768×900 to prove initial focus inside, forward and reverse Tab containment, X/Escape restoration, zero released dialogs/inert regions, preserved draft, and retained opaque first/settled entry. The repair is owned by root's implementation lane; this judge made no production edit.

## Previous blockers and current good evidence

- **Compact header layering resolved at 375px:** the history and environment/code/changes screenshots all show the complete title and close X above the status strip. Root recorded close-center hit testing `hit: true`, computed main-content z-index `auto`, and actual pointer dismissal. History and inspection close/Escape returned focus to their openers with zero dialogs/inert regions and the same unsent draft. `final-375-inspection-code.jpg` SHA-256 `8ec073ea8c79523dce3956195c23af5a1039ccc59eac7bdb7d85442bd8082832` was re-opened at original detail and visibly contains both `검사` and X; an initial visual misread was corrected and is not a finding. The unrun 768px proof remains part of the next full packet.
- **Opaque foreground entry resolved at 375px:** first/settled palette and guide frames contain readable text without underlying chat text crossing their surfaces. Palette computed background is `rgb(24, 24, 24)`, opacity `1`, animation `none`, with the combobox focused. Guide opacity is `1`, animation `none`. Palette Escape restores the inspection opener and preserves the draft. These visual improvements do not waive G1.
- **Navigation focus remains correct at 375px:** reverse wrap reaches the terminal control, forward wrap reaches the drawer close control, and Escape returns to `탐색 메뉴 열기` with zero dialogs/inert regions and preserved draft.
- **Model popover remains bounded:** the fresh compact menu displays qwen3.8:latest 27.3B as current selection. This partial run does not reassert a new reload or real-generation proof.

## Original 25-scenario matrix — `manualQa.surfaceEvidence`

The IDs and scope retain **B01–B20 and A01–A05** from rounds one/four. `QA_SCENARIOS.md` and `QA_SCENARIO_MATRIX.md` were absent when this judge started. B12 is the actual file-history route; A02 is the separate conversation-history drawer. Prior evidence below means the documented earlier `4abc…/CYlhq3Mt` execution in `QA_REVIEW_ROUND4.md`, not a current-build PASS. Incomplete current coverage is disclosed rather than inflated to 25 browser passes.

| ID | Retained criterion / actual current invocation | Current result / mode | Evidence |
|---|---|---|---|
| B01 | `/` home, empty state, composer/model | NOT RE-RUN in this partial binding; earlier manual route/empty coverage retained as history. | E06 |
| B02 | `/chat` alias | NOT RE-RUN; earlier manual route coverage retained as history. | E06 |
| B03 | `/studio`, heading/pipeline/model cards | NOT RE-RUN; no training-start claim. | E06 |
| B04 | `/models`, active model list | NOT RE-RUN; no model-load/switch claim. | E06 |
| B05 | `/start`, bridge choices/copy controls | NOT RE-RUN; no command-run claim. | E06 |
| B06 | `/wiki`, tree and selection-empty state | NOT RE-RUN. | E06 |
| B07 | `/agent`, monitoring and actual idle/unavailable state | NOT RE-RUN; no all-API-success claim. | E06 |
| B08 | `/settings`, masked credentials and bounded layout | NOT RE-RUN; no credential edit. | E06 |
| B09 | `/skills`, actual empty/error state | NOT RE-RUN; existing auxiliary401 is not API success. | E06 |
| B10 | `/data-extraction`, A/B control and Korean units | NOT RE-RUN; earlier CJK repair evidence remains historical. | E06 |
| B11 | `/git`, read-only inspection | NOT RE-RUN; no Git mutation. | E06 |
| B12 | `/history`, file history | NOT RE-RUN; this route is not conversation history. | E06 |
| B13 | `/plugins`, plugin index | NOT RE-RUN. | E06 |
| B14 | `/mutation`, historical snapshot/provenance | NOT RE-RUN; no live mutation run. | E06 |
| B15 | `/plugins/hello-world`, registered plugin | NOT RE-RUN. | E06 |
| B16 | `/plugins/job-operations`, actual empty/healthy state | NOT RE-RUN; no job creation/retry. | E06 |
| B17 | `/ui-qa-not-found`, intentional fallback/CJK | NOT RE-RUN. | E06 |
| B18 | 375px navigation; Shift+Tab/Tab wraps, Escape | PASS — current manual. Both wraps stay inside; opener focus and draft return. | E03, E04 |
| B19 | 375px inspection → Meta+K/Escape; Meta+Slash; guide Tab/Shift+Tab/X/Escape | REVISE — current manual. Opaque surfaces and palette handoff pass; guide initial focus, reverse containment and restoration fail G1. | E02–E04 |
| B20 | Model selector bounds, selection and reload preservation | PARTIAL — fresh bounded menu/current27B; reload not rerun for this binding. | E03, E06 |
| A01 | Compact/docked environment/code/changes, reachable header and close | PARTIAL — all three375px headers and real close/Escape pass; 768/1280 not rerun. | E02–E04 |
| A02 | Conversation history close/selection; distinct file-history route | PARTIAL —375px visible header/hit/real close/Escape pass; selection and768px not repeated. | E02–E04, E06 |
| A03 | Shift+Enter, real send/copy; IME guard | NOT RE-RUN manually in this binding; prior real chat/copy/newline evidence remains historical. IME portion AUTOMATED-only. | E05, E06 |
| A04 | Desktop settled output viewer without sending a command | NOT RE-RUN in this binding; prior manual read-only output proof retained as history. | E06 |
| A05 | 503/CAS/late hydration preservation augmentation | AUTOMATED-only, source-backed; no browser fault injection/retry-UI PASS asserted. | E05 |

Current partial-run counts: **1 complete manual PASS, 1 manual REVISE, 3 PARTIAL, 19 NOT RE-RUN, 1 AUTOMATED-only row**. A03 additionally labels its IME portion AUTOMATED. These are the original 25 rows, not 25 current manual passes. The existing guide failure is sufficient for REVISE without inventing backend fault scenarios.

## Directed and adversarial results — `manualQa.adversarialCases`

| Boundary | Actual result / mode | Evidence |
|---|---|---|
| Compact header z-index/close hit | History and all inspection tabs are above status; actual pointer closes release modal state and restore focus/draft at375px. | E02–E04 |
| Palette foreground handoff | Combobox focus, opacity1/background24/animationnone; Escape restores inspection opener/draft. | E02–E04 |
| Guide keyboard boundary | Opener remains focused on opening; Shift+Tab escapes to send; X/Escape do not restore opener. REVISE G1. | E02–E04 |
| Navigation forward/reverse wrap | Both stay inside drawer; Escape restores opener/draft with zero dialogs/inert. | E02–E04 |
| Native OS IME / legacy229 | Composition guards preserve draft and do not call submission in automated event tests. No native-device sequence run. | E05 |
| Controlled503 / CAS / late hydration | Typed503/conflict, failed permission preservation, and early draft/new-session hydration guards inspected as automated evidence. No manual injected browser case claimed. | E05 |

## Artifact references — `manualQa.artifactRefs`

All paths are inside `docs/qa/2026-10-03-codex-ui/` unless stated otherwise.

| ID | Kind / paths |
|---|---|
| E01 | Immutable exact binding: `SOURCE_MANIFEST_ROUND5.json`, `BUNDLE_MANIFEST_ROUND5.json` |
| E02 | Actual directed actions, guide failure and layer proof: `QA_DIRECTED_RESULTS_ROUND5.json`; pre-execution instructions: `QA_OPERATOR_INSTRUCTIONS_ROUND5.md` |
| E03 | All11 exact-script observations: `BROWSER_OBSERVATIONS_ROUND5.json`; all10 unique archived JPEGs in `captures/round5/` |
| E04 | Focused frames: `final-375-history`, `final-375-inspection-environment`, `final-375-inspection-code`, `final-375-inspection-changes`, `final-375-command-palette-early`, `final-375-command-palette`, `final-375-shortcut-guide-early`, `final-375-shortcut-guide`, `final-375-navigation`, `final-375-model-menu` (all `.jpg` under `captures/round5/`) |
| E05 | Automated-source-only preservation: `dashboard/src/components/Chat/__tests__/ChatPageComposer.test.tsx`, `ChatPageHydration.test.tsx`, `dashboard/src/api/client.test.ts`, `dashboard/src/stores/__tests__/chatStore.modelPreference.test.ts`; prior full-suite result in `TESTS_CURRENT.log`/`VERIFICATION_ROUND4.json`. No new test run claimed by this judge. |
| E06 | Prior full packet, explicitly historical: `QA_REVIEW_ROUND4.md`, `QA_CAPTURE_READY_ROUND4.md`, `CAPTURE_MANIFEST_ROUND4.json`, `QA_REVIEW_ROUND1.md` |
| E07 | Intent and contract: `docs/frontend/EXECUTION_PLAN_2026-10-03.md`, `dashboard/DESIGN.md`; inspected pre-repair guide source: `dashboard/src/components/UI/KeyboardShortcutsModal.tsx` |

## Review limits and next gate

This is a one-shot REVISE review of a partial interrupted capture run. It does not certify all routes or768/1280 for7adf, an exact proprietary Desktop/font clone, native IME, injected axe/Lighthouse scores, backend full-suite health, or auxiliary Skills/Metrics API success. Those limits do not cause G1; the actual guide keyboard defect does.

Root owns the focused guide fix and the subsequent source/bundle. Final approval requires fresh complete route/state evidence on that new binding, both375/768 modal/focus closures, and a new independent review. Previous70 frames and this partial10-frame packet remain historical evidence and cannot be silently reused as final approval.
