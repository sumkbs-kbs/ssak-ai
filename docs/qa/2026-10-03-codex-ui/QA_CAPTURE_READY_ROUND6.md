---
title: 최종 Codex UI 브라우저 캡처 인수 패킷
tags: [qa, frontend, codex]
date: 2026-10-03
---

# Status: READY

HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus dirty45file SOURCE_MANIFEST SHA `a1552cf1f91459253bfb96910eeb7fcd0d29e5e8cb0e836cbcfc93267014d3b8`. Main `/assets/index-DNX9exh1.js` SHA `0e7120f581ecf35751f5cdc32552e083b95356747c97d7c707e2879a1ccfd836`; CSS `/assets/index-BLgp1deP.css` SHA `78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b`.

CAPTURE_MANIFEST.json binds78 fresh valid JPEGs after all45 source/test edits:51 declared route frames (17routes×375×812,768×900,1280×900) plus27 state frames. BROWSER_OBSERVATIONS.json is current-build only, deduplicated. Every frame dimensions/signature/source ordering is validated in CAPTURE_HYGIENE.json. All51 route frames have bounded width and measured main horizontal overflow0; visual text/CJK inspection remains independent.

Declared routes: home/,chat-alias/chat,studio/studio,start/start,wiki/wiki,agent/agent,settings/settings,skills/skills,data-extraction/data-extraction,git/git,history-page/history,plugins/plugins,mutation/mutation,hello-world/plugins/hello-world,job-operations/plugins/job-operations,not-found/ui-qa-not-found,models/models. The intentional404 is a routed error-state test.

State frames:375 model-menu/history/navigation/inspection3/palette first+settled/guide first+settled/statusclosed/empty/generation/chat-complete/copy;768 history/inspection3/palette/guide;1280 inspection3/output/status-details/chat-complete. Early means first observed frame, no fabricated millisecond timing. Route DOM51 are fresh; state screenshots and QA_DIRECTED_RESULTS are authoritative current interaction evidence, older unrefreshed state DOM files are historical and are not used for current coverage.

QA_DIRECTED_RESULTS.json records independent-agent-directed root-operated history/inspection close hit tests, visible title geometry, actual X/Escape closes, retained Korean unsent draft and opener focus at375+768. Meta+K handoff leaves only palette; Meta+Slash handoff leaves only guide. Guide auto focus on close, real Tab/ShiftTab containment and X/Escape restoration now pass. Palette/guide computed opacity1, animation:none. No PIN/storage/auth transfer or security permission change.

LIVE_CHAT_RESULT.json records actual27.3B replies, both copied synthetic response matches and ShiftEnter newline. First font/layout prompt returned 정상적으로 연결되어 있습니다. plus an existing engine computer_use approval notice. Root did not approve that tool; subsequent no-tool greeting returned 안녕하세요, 오늘도 함께 작업해 주셔서 감사합니다! 😊. No displayed503. Three pre-final records were retained; one additional finalQA conversation makes4. No original conversation was deleted.

TESTS_CURRENT:102files/987tests exit0; TYPECHECK_CURRENT exit0; BUILD_CURRENT exit0. ReactDoctor remains exit1 for preexisting ignored nonshipping mutation fixture. Native OS IME, controlled503/CAS409 faults and latehydration/draft races are AUTOMATED-only; no browser fault injection/nativeIME pass claimed. Existing Skills/Metrics401 captured as bounded error states, no backend-success claim.

IMAGE_DIFF compares historical SSAK baseline768 with current768 route frame, NOT a Codex pixel target. Every hotspot must be mapped by both visual reviewers. Two independent visual reviewers must open the entire78-frame inventory before verdict; no representative-only approval.
