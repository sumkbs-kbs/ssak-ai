---
title: 최종 Codex UI 브라우저 캡처 인수 패킷
tags: [qa, frontend, codex]
date: 2026-10-03
---

# Status: READY — round 9 final source

HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus dirty 46-file SOURCE_MANIFEST SHA `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd`.
Main `/assets/index-CEvvbZ3V.js` SHA `a908583776aaa9446bc34f5aeb1da5ca36e7e9aef8ab9a5ba47ed3128382e2a4`; CSS `/assets/index-C19bV3rn.css` SHA `4c09077334dbfb6c5416e4b5e55f603b673b216a82b5218a8190590a95a2119f`.
CAPTURE_MANIFEST SHA `ace91095874923c893bd4948274fa324e0407828959c6cbc94400014d4e7b1d3`. Source and all104 shipping files independently reproduced. No more source edits planned.

81 current JPEGs:51 route frames (17 declared routes at375×812,768×900,1280×900),27 state frames,3 targeted Settings helper frames. All originals postdate all46 source edits, have matching JPEG signature/viewport dimensions, document-width equality and measured horizontal overflow0. Each has refreshed DOM. BROWSER_OBSERVATIONS is current-source only/deduplicated. Git awaits Staged Changes; desktop route frames await the retained original recent record. Two768 inspector frames were replaced after transitions settled; Changes opacity1 and selected-tab receipt is in QA_DIRECTED_RESULTS.

Declared routes: home /,chat-alias /chat,studio /studio,start /start,wiki /wiki,agent /agent,settings /settings,skills /skills,data-extraction /data-extraction,git /git,history-page /history,plugins /plugins,mutation /mutation,hello-world /plugins/hello-world,job-operations /plugins/job-operations,not-found /ui-qa-not-found,models /models. Intentional404 is a routed error state.

State frames:375 model-menu/history/navigation/inspection3/palette-first+settled/guide-first+settled/statusclosed/empty/generation/chat-complete/copy;768 history/inspection3/palette/guide;1280 inspection3/output/status-details/chat-complete. Targeted Settings frames show actual helper after a static-text click scrolled it into view. No configuration edits.

QA_DIRECTED_RESULTS:actual X/Escape, header hit tests, unsent Korean draft, opener focus/inert release, foreground palette/guide handoff, guide initial focus and both Tab directions, palette named-target ShiftTab/Tab/Escape cycle. COMPACT_CONTROL_BOUNDS:18 actual controls at each375/768 (16main including navigation plus inspection close/navigation footer), all>=36px. SETTINGS_WORD_GEOMETRY:all five characters of 보여줍니다 share a line at all3widths.

RECENT_SINGLE_CLICK_LIVE records cold Studio/Wiki/Settings, each exactly one old-title click selecting its prior header/prompt/reply at six cached records after the Sidebar persist-before-navigation repair. Actual Sidebar→ChatPage regression RED/GREEN retained. LIVE_CHAT_RESULT:latest explicit no-tool greeting completed normally on27.3B, ShiftEnter newline, raw Markdown copy contains the rendered greeting, no displayed503 or approval click. Before this final generation6records, afterwards7; original record and prior UI QA records preserved. UI task created6synthetic records overall, none deleted. NONCHAT_RESTORE_LIVE fresh cold reloads show all7. Earlier blocked computer_use notice was never approved and is preserved in archive-round6 evidence.

TYPOGRAPHY_LIVE:system/Korean font stack, UI14px, assistant16px/27.2px, composer16px/25.6px, desktop sidebar248px/content760px. No proprietary font copied. DELIVERABLE:viewport override reset to original757×954, visible dialogs0/outputpanel false/draft empty; user tab retained.

TESTS_CURRENT103files/1001tests exit0; BUILD_CURRENT and TYPECHECK_CURRENT exit0. ReactDoctor remains exit1 pre-existing ignored nonshipping fixture; independent code/security9PASS. Existing Skills/Metrics401 are bounded error states, backend success excluded. Native OS IME/key229, permission503 read-only/error, API CAS409/integrity/migration503 and late-hydration races are automated-only. No failed-send draft-retention assertion, fullaxe/Lighthouse/nativeElectron or exact Codex desktop pixel-fidelity claim.

IMAGE_DIFF compares full original757×954 before-default.jpg and final deliverable.jpg converted only to RGB PNG, without resize/padding/crop/redraw. IMAGE_DIFF_RECEIPT binds originals/conversions/diff to source and capture digest. Black-padded old768 baseline excluded/preserved. Valid diagnostic diff includes intentional layout/background and distinct synthetic content; similarity0 is not a quality/fidelity score. Both visual reviewers must open ALL81 original JPEGs plus both valid757 PNGs and map ALL64 hotspots individually (grid coordinates may be grouped only with explicit per-hotspot coverage). Historical round7 and partial round8 are immutable archives, not final approvals. ROUND6_LOG_RECEIPT discloses missing old987 raw-log retention.
