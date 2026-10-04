---
title: 최종 Codex UI 브라우저 캡처 인수 패킷
tags: [qa, frontend, codex]
date: 2026-10-03
---

# Status: READY

Current HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus dirty source manifest `4abc26596d09679a03b0e5e077bc1fb97f9a72c7148fae59b484bcf95653ef75` (43 files). Main script `/assets/index-CYlhq3Mt.js`, SHA256 `57732b8b8b74c41b81681724d52ff6b797dbbb635a16c29453e4df4fa1ad86f2`. No commit, staging, checkout or auth transfer.

## Inventory

CAPTURE_MANIFEST.json contains 70 fresh current-build screenshots: 51 route frames (17 routes × 375×812, 768×900, 1280×900) and 19 extra interaction-state frames. CAPTURE_HYGIENE.json verifies all JPEG signatures and exact viewport dimensions. BROWSER_OBSERVATIONS.json contains only these current bundle observations, deduplicated by capture name. All 51 route frames report viewport-bounded document width and zero measured main-element horizontal overflow; this geometric probe is not a substitute for visual/CJK review.

The 17 declared routes are home `/`, chat alias `/chat`, studio `/studio`, start `/start`, wiki `/wiki`, agent `/agent`, settings `/settings`, skills `/skills`, data extraction `/data-extraction`, git `/git`, file history `/history`, plugins `/plugins`, mutation `/mutation`, hello world `/plugins/hello-world`, job operations `/plugins/job-operations`, intentional404 `/ui-qa-not-found`, models `/models`.

Extra states: 375px generation, completed response, copied feedback, model menu, history, environment/code/changes inspection tabs, foreground command palette, foreground shortcut guide, navigation, closed-status chat; 1280px environment/code/changes docked inspection, settled output panel, open status details, completed chat. `final-375-empty` is the new-chat empty state; route home/alias frames show a completed conversation. `final-375-status` is a CLOSED status/frame, not an open disclosure. The open disclosure is `final-1280-status-details`. Lazy routes and output panels were awaited until their actual heading/control content appeared; earlier loading-only frames are archived under round1 and excluded.

## Actual operator results

Root used the existing user-unlocked IAB browser2/tab1. Final-build local qwen3.8:latest27.3B returned `연결이 정상적으로 활성화되어 있습니다.` without displayed503. Copy feedback and clipboard content match were actually checked. Shift+Enter produced a textarea newline and did not send; the root-created draft was cleared. Real reload verified27B pressed and original2 sessions retained; then a third synthetic QA chat was added via UI, with no deletion. 375px nav/history/inspection modal handoff, Meta+K foreground search, Meta+/ foreground shortcut guide and Escape close were exercised. 1280px docked inspection tabs, actual output controls after lazy loading, and live status details with Escape were exercised. TYPOGRAPHY_LIVE.json binds measured body14px, assistant16px/27.2px, sidebar248px, assistant width760px.

Independent QA uses QA-agent-directed/root-executed mode because executor browser profiles cannot see root's user-unlocked session. No PIN/token transfer or duplicate unlocking request is permitted. Unit-backed IME/failed access-mode/history-draft guards are not claimed as manually injected browser cases.

## Reference and diff semantics

User requested Codex-inspired fonts and composition, with no supplied exact Desktop screenshot or pixel target. CODEX_REFERENCE_2026-10-03.md distinguishes official CLI/TUI repository from proprietary Desktop React styling. System fonts with Korean fallbacks are used; proprietary font files were not copied. The before768 screenshot and current768 screenshot are both768×900. IMAGE_DIFF.json is a before/after layout-change diagnostic, NOT a Codex pixel-fidelity score. Its hotspots must be explained by the deliberate neutral palette, removed busy rail, centered transcript, fixed composer and real content/status differences. PNGs are conversion-only originals for the script; live UI remains actual DOM.

## Verification and limits

TESTS_CURRENT.log: 101 files /980 tests passed. BUILD_CURRENT.log: TypeScript and production build passed after final class/CSS edit. Security/code final reports bind all43 source hashes. React Doctor exit1 is accurately retained as a pre-existing ignored nonshipping mutation-fixture advisory. No new dependency or remote font source.

Skills/Metrics auxiliary API requests return existing401 and their page/API source is unchanged. Their route captures verify actual displayed layout/error states, not backend success. No backend full-suite rerun, native Electron/IME-device automation, injected axe/Lighthouse score or exact Desktop/font copy is claimed.


## Final supplemental evidence

QA_DIRECTED_RESULTS.json records all three independent QA-agent instructions on this final source/bundle:375px reload/model/history; nav Tab/Shift+Tab wrap+Escape focus return; unsent draft before inspection, Meta+K foreground combobox, Escape with no dialogs/inert, draft preserved. LIVE_CHAT_RESULT.json records the final real reply and clipboard/newline results. CAPTURE_MANIFEST includes the exact main CSS identity and source-edit time; all70 images postdate every bound source edit. LIVE_STYLE_BINDING.json directly observes the loaded stylesheet URLs. CJK repairs are scoped flex-wrap/nowrap for A/B controls, keep-all for404 paragraphs and data-extraction body, with technical path wrapping retained.
