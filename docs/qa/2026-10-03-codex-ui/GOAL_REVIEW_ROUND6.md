---
title: Codex UI goal and visual A review — round 6
tags: [qa, frontend, codex, goal-review, visual-a]
date: 2026-10-03
---

# Verdict: REVISE

Confidence: HIGH. The Codex-inspired font, neutral workspace hierarchy, fixed composer, and responsive drawer work meet the central visual goal. Two bounded product issues remain: Korean words split in two empty-state hints, and the persistent recent-conversation navigation shows a false empty state on direct non-chat page loads. No pasted screenshot substitute or new material overlap defect was found.

This is one independent GOAL + VISUAL A review of the complete round6 packet. All references to “current” in this report mean the immutable reviewed a155 build, not subsequent repairs. The 78 viewed originals are retained under `captures/round6/`; original source paths/line numbers below resolve against `source-round6/` (for example `source-round6/dashboard/src/components/Layout/Sidebar.tsx`). The matching *_ROUND6.json artifacts and `QA_CAPTURE_READY_ROUND6.md` preserve the reviewed binding. I directly opened all 78 original JPEG files with `view_image(detail=original)`, plus both original comparison PNGs, rather than approving representative frames or a contact sheet. I performed no browser, Git, production edits, or child-agent work. Only this review file is authored by this reviewer. The entire finding set is below; it is not a rolling subset.

## Exact reviewed binding

- Manifest-declared HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, plus 45 dirty source/test/design files.
- `SOURCE_MANIFEST_ROUND6.json` SHA-256: `a1552cf1f91459253bfb96910eeb7fcd0d29e5e8cb0e836cbcfc93267014d3b8`.
- `CAPTURE_MANIFEST_ROUND6.json` SHA-256: `568f7bfbae5cc9c4fbbc51fd2f622c21e951536a6af1c997895100bab4e79b3f`.
- Main script: `/assets/index-DNX9exh1.js`, SHA-256 `0e7120f581ecf35751f5cdc32552e083b95356747c97d7c707e2879a1ccfd836`.
- Main CSS: `/assets/index-BLgp1deP.css`, SHA-256 `78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b`.
- Last declared source edit: `2026-10-03T03:08:38.190751+00:00`. All 78 capture entries postdate it and bind the same main script.

I independently recomputed every declared source hash (45/45 match), every capture hash (78/78 match), capture JPEG signatures and dimensions (78/78 match), and every production bundle file hash relative to `src/antigravity_k/dashboard_dist` (104/104 match). Both comparison PNGs opened during this pass have valid PNG signatures and 768×900 dimensions. SOURCE and CAPTURE manifests still matched the above hashes after the inspection. HEAD is taken from the signed-by-hash packet; no separate Git command was run. `CAPTURE_HYGIENE_ROUND6.json` reports `allValid=true`, `dimensionAndSignatureValid=true`, and `postdatesAllSourceEdits=true` for the current 78 JPEGs.

## Complete actionable product findings

### F1 — [product] [CJK readability] [P2] Keep Korean empty-state words intact

Two independently visible examples fail DESIGN.md §4's Korean `word-break: keep-all` contract:

1. `captures/round6/final-375-wiki.jpg`, SHA `31c1b8de155bd2e77d7d6bdba3ca088d11510195af26bc26cbc0577a1dfdec55`: the lower empty-state sentence at approximately x48–321, y650–688 ends its first line with `생성` and starts the next with `하세요.`. The actual Korean is `왼쪽 트리에서 문서를 선택하거나 새 문서를 생성하세요.`; `생성하세요` is one word. Source: `dashboard/src/pages/wiki/ContentPanel.tsx:85` and `:89`. The paragraph has an inline 14px size, but neither it nor the wiki body gets the Korean wrapping rule from the new workspace page stylesheet.
2. `captures/round6/final-1280-history-page.jpg`, SHA `1bf7843054a75aa8379dc6dfff3656730662b4ee2ddcabe08acafac941c19e55`: the left Files pane hint at approximately x299–466, y591–615 splits the end of `저장됩니다`, leaving `니다` on its own line. Source: `dashboard/src/pages/HistoryPage.tsx:72`, `.history-file-empty` at `dashboard/src/styles/index.css:6824`, and `.history-file-empty-hint` at `:6842`. The hint inherits normal Korean breaking, with a narrow pane and legacy 10px size. The legacy size is an existing inconsistency, not a separate newly introduced finding; the visible word split still violates the current readability contract.

Concrete fix: apply the existing Korean prose wrapping policy to the Wiki empty paragraph and history empty-state prose in the shared workspace layer, using `word-break: keep-all` and a safe long-token fallback. Preserve anywhere breaking for technical paths/IDs. Keep the correction scoped to text behavior; a new page or store is unnecessary.

Acceptance: freshly capture Wiki 375×812 and History 1280×900 and inspect the complete empty-state hints. `생성하세요` and `저장됩니다` must stay intact, natural spaces must remain, and each containing pane must remain width-bounded. Check the paired 768 and other required widths for new overflow. An assertion that merely repeats a CSS property is insufficient evidence of the rendered Korean outcome.

### F2 — [product] [goal / conversation discoverability] [P2] Restore recent conversations outside the chat route

The same selected `Ssak-Ai` project has four saved recent conversations in `captures/round6/final-1280-home.jpg` and `captures/round6/final-1280-chat-alias.jpg`. In every direct non-chat 1280 route frame from Studio through Models, the persistent sidebar instead displays `최근 대화` → `첫 대화 시작하기`. The fresh corresponding round6 DOM files, for example `captures/round6/final-1280-studio.dom.txt` and `captures/round6/final-1280-wiki.dom.txt`, independently confirm this empty state. The source explains it: `Sidebar.tsx:18` subscribes to the canonical chat sessions, but its effects restore only project/Git data. `WorkspaceThreads.tsx:55` treats a zero-length projection as an actual first-conversation state. Conversation cache restoration lives in the route-mounted `ChatPage.tsx:225` and the guarded identity retry around `:264`; `chatStore.ts:117` initializes `sessions: []`.

This is a present goal gap in the persistent navigation required by DESIGN.md §1 and §5, not a claim that data was deleted. The original Sidebar also relied on the ChatPage-populated store, as the preserved `WORKTREE.patch` demonstrates: the underlying route-only restoration predates this redesign. Saved data is visibly retained and restored by returning to `/chat`. Nevertheless, a returning user opening `/studio` or `/wiki` directly cannot discover those saved conversations in the new stable sidebar.

Reproduction: with saved conversations for the active project, directly load or reload `/studio` at 1280px. After project hydration, inspect the recent-conversation list; it currently says first conversation. Load `/chat`; the same project then restores its saved rows. At 375/768, the equivalent list is in the navigation drawer.

Concrete fix: make the shared shell/sidebar read or safely restore the canonical project's existing conversation projection after project identity resolves, independent of ChatPage mounting. Keep one canonical store and retain the existing revision, project epoch, draft/attachment/stream protections. Do not indiscriminately run `loadFromStorage()` on each render or replace an active conversation. Distinguish loading/unavailable from a confirmed empty history if restoration is asynchronous.

Acceptance: save a conversation, reload a non-chat route, and confirm it is visible and selectable in the persistent sidebar / compact drawer without first visiting `/chat`. Selection must open the existing conversation. Verify delayed project hydration, project switching, no saved conversations, retained unsent drafts/attachments, active streams, and the existing model-preference / server-revision guards. This reviewer did not perform browser replay; this reproduction follows both the current real captures and the source path, and should be confirmed during the root's final batch validation.

## Goal and design-system criteria

| Criterion | Source and evidence | Assessment |
|---|---|---|
| Codex-inspired adaptive workspace | `dashboard/DESIGN.md` and `docs/frontend/EXECUTION_PLAN_2026-10-03.md` explicitly distinguish the public CLI/TUI/app-server source from proprietary Desktop styling | Correct scope: inspiration, no unsupported exact desktop-pixel or copied OpenAI font claim |
| Font / readable conversation measure | Canonical `--font-sans`, `--chat-font-size`, `--chat-content-width`; `workspace-chat.css`; `TYPOGRAPHY_LIVE_ROUND6.json` bound to current script | Real system/Korean stack, assistant 16px / 27.2px line height and 760px measure; sidebar 248px, UI body 14px. Chat copy is readable at all inspected widths |
| Real design system | `codex-workspace.css` imports shared shell/chat/history/inspection/pages layers; semantic color/font/space/radius/focus tokens; real reusable AppIcon, ChatComposer, WorkspaceNavigation, WorkspaceProjects, WorkspaceThreads, InspectionFrame, ChatHistory | Coherent reusable implementation, not mock-only composition. Existing operational one-off values/emoji remain known pre-existing inconsistencies, not evidence of a pasted/faked UI |
| Real DOM and functional wiring | Controlled textarea and send/stop handlers in ChatComposer/ChatPage; native navigation links; project/thread store callbacks; details-backed system status; tabs and dialog semantics | Live components and state paths, no raster screen standing in for controls |
| Status truth | `SystemTelemetricsBar.tsx` derives unknown/live/stale/disconnected and preserves null versus zero; details screenshot exposes real CPU/memory/vault/build | Correct visible summary plus on-demand details; no synthetic quota or fabricated health |
| Responsive containment | 17 routes × 3 widths; current BROWSER_OBSERVATIONS + capture manifest; shared intrinsic grids, min-width:0 and wrapping toolbars | All 51 route captures have document width equal to viewport and zero measured main horizontal overflow. Direct visual inspection found no missing compositor region, overlapping primary controls, or hidden composer |
| Conversation / composer hierarchy | Chat transcript named scroll region; bounded user bubble; open assistant prose; separate composer; generation/empty/completed/copy frames | Strong hierarchy across 375/768/1280; send/stop/copy affordances remain visible. Empty chat uses centered start composition; established chat docks the composer |
| Keyboard dialogs | Shared `useModalDialog`, InspectionFrame, ChatHistory, Sidebar, KeyboardShortcutsModal | Current 375/768 screenshots show visible modal headers/close controls. QA_DIRECTED_RESULTS proves X/Escape closes, retained unsent Korean draft, opener focus, modal handoff and real guide Tab/ShiftTab containment |
| Motion | Current early + settled 375 palette/guide frames; current computed animation:none / opacity:1; new workspace message and page entrance overrides | No current in-flight animation is used to excuse a diff or missing header. Both opening observations are readable; focus/color feedback serves interaction |
| Korean page prose | All 78 images opened; selected empty-state source locations | REVISE F1; remaining directly visible Korean headings/body text read naturally without clipping |
| Stable recent conversations | Persistent sidebar and canonical session projection | REVISE F2; the non-chat direct-load false-empty state prevents route-independent discovery |
| Validation | TESTS_CURRENT.log: 102 files / 987 tests passed; TYPECHECK_CURRENT exit0 and BUILD_CURRENT success packet | Meaningful supporting checks, not a substitute for the located visual/goal issues. No extra test runs were performed by this reviewer |

`TOKEN_CONTRAST.json` gives primary 10.69–15.03, secondary 6.37–8.95, muted 4.83–6.79 across canonical dark surfaces, and focus 6.96–9.78. This supports token contrast only; it is not a blanket WCAG audit or a guarantee for all user-customized accents.

## Preserved limitations and inherited states

The actual 27.3B reply and copy/newline checks in `LIVE_CHAT_RESULT_ROUND6.json` bind the current source and script. Both completed replies are visible in the chat captures. The first reply includes the existing engine computer-use approval notice; no approval was clicked. Its token/quality/engineering decoration is generated or inherited response content, not a new shell defect or a UI 503. Existing Skills/Metrics 401 responses, Git loading/UNKNOWN frames, and unavailable operational state remain distinct from newly introduced layout issues; this review claims bounded rendering, not backend success for those routes. Original conversation data is retained.

Native OS IME and controlled 503/CAS409 faults, late hydration/draft races are automated-only in the supplied packet. Source has the IME composition guard and Shift+Enter behavior, but this reviewer does not upgrade those to a native/browser manual pass. ReactDoctor's existing ignored nonshipping mutation fixture remains separate from the shipping UI. The root's broader code/security review remains the authority for unrelated implementation risks.

## Original comparison PNGs and image-diff interpretation

I opened `baseline-768-round6.png` and `actual-768-round6.png` individually. These are the historical SSAK screen and the current SSAK screen; neither is an exact Codex target. They are both valid 768×900 PNG files, and IMAGE_DIFF reports `dimensionsMatch=true`, `alphaChannelIntact=true`, `totalPixels=691200`, `diffPixels=691053`, `diffRatio=0.9998`, and `similarityScore=0`.

There is an explicit evidence limit: the historical baseline's visible UI stops around x=375 and y=812, with opaque black content to its right and below. It is not a complete same-viewport before frame. Also, conversation contents and scroll positions differ. Thus the near-total diff cannot quantify design fidelity or prove improvement. I map every hotspot below to what is actually visible, including the baseline's clipped/black regions. The current 78-frame inventory is fully composited; the historical baseline limitation is not a newly introduced black product surface. Use the visual contract and current frame inspection for the verdict, and keep the historical diff labelled non-comparable rather than presenting its score as a success/failure threshold. No hotspot is dismissed because of animation.

Comparison artifact hashes:

- `baseline-768-round6.png`: `4c42a8c4d1d05dc9d9dd3889a5e338d93b7eeff2bf687519aa8513495e3e1e92`.
- `actual-768-round6.png`: `95f309eec86dfe494e1a7d830a73676e31d352e108e56e7dd20e8c7fa0d32673`.
- `IMAGE_DIFF_ROUND6.json`: `424e759817b92ec2a8ed743c347df8cb6f40884fac329b4a4819e31f83ee3227`.

The following table covers all 64/64 unique hotspot cells, preserves every supplied hotspot field, and adds the region interpretation. H=header/status, P=prose/transcript, C=composer/footer. Intentional differences refer to the current adaptive DESIGN contract, not pixel matching to the incomplete baseline.

| # | gridX | gridY | x | y | width | height | diffRatio | Visual mapping and judgement |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 3 | 0 | 288 | 0 | 96 | 112 | 1 | partial legacy terminal build/title chrome to x375; opaque black beyond x375 → H: title and approval text. Intentional semantic header/status redesign; visible controls. |
| 2 | 4 | 0 | 384 | 0 | 96 | 112 | 1 | opaque black historical region beyond x375 → H: title/approval continuation. Intentional semantic header/status redesign; visible controls. |
| 3 | 5 | 0 | 480 | 0 | 96 | 112 | 1 | opaque black historical region beyond x375 → H: action group and approval continuation. Intentional semantic header/status redesign; visible controls. |
| 4 | 6 | 0 | 576 | 0 | 96 | 112 | 1 | opaque black historical region beyond x375 → H: status/action group and approval continuation. Intentional semantic header/status redesign; visible controls. |
| 5 | 7 | 0 | 672 | 0 | 96 | 112 | 1 | opaque black historical region beyond x375 → H: status disclosure / final header actions. Intentional semantic header/status redesign; visible controls. |
| 6 | 2 | 1 | 192 | 112 | 96 | 113 | 1 | user bubble / assistant heading → P: revision text. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 7 | 4 | 1 | 384 | 112 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: revision tail. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 8 | 5 | 1 | 480 | 112 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 9 | 6 | 1 | 576 | 112 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 10 | 7 | 1 | 672 | 112 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 11 | 4 | 2 | 384 | 225 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 12 | 5 | 2 | 480 | 225 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 13 | 6 | 2 | 576 | 225 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 14 | 7 | 2 | 672 | 225 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: transcript edge. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 15 | 0 | 3 | 0 | 337 | 96 | 113 | 1 | legacy icon rail + token metadata / dark canvas → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 16 | 1 | 3 | 96 | 337 | 96 | 113 | 1 | token metadata / dark canvas → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 17 | 2 | 3 | 192 | 337 | 96 | 113 | 1 | token metadata / dark canvas → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 18 | 3 | 3 | 288 | 337 | 96 | 113 | 1 | partial legacy token metadata / dark canvas to x375; opaque black beyond x375 → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 19 | 4 | 3 | 384 | 337 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: right-aligned user bubble start. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 20 | 5 | 3 | 480 | 337 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: user bubble text. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 21 | 6 | 3 | 576 | 337 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: user bubble text. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 22 | 7 | 3 | 672 | 337 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: user bubble end / scroll edge. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 23 | 4 | 4 | 384 | 450 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: assistant reply. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 24 | 5 | 4 | 480 | 450 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: reply tail. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 25 | 6 | 4 | 576 | 450 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: neutral canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 26 | 7 | 4 | 672 | 450 | 96 | 112 | 1 | opaque black historical region beyond x375 → P: transcript scroll edge. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 27 | 2 | 5 | 192 | 562 | 96 | 113 | 1 | dark transcript canvas → P: token tail. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 28 | 3 | 5 | 288 | 562 | 96 | 113 | 1 | partial legacy dark transcript canvas to x375; opaque black beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 29 | 4 | 5 | 384 | 562 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 30 | 5 | 5 | 480 | 562 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 31 | 6 | 5 | 576 | 562 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 32 | 7 | 5 | 672 | 562 | 96 | 113 | 1 | opaque black historical region beyond x375 → P: transcript scroll edge. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 33 | 0 | 6 | 0 | 675 | 96 | 112 | 1 | legacy icon rail + project context / partial composer → C: composer start / placeholder. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 34 | 1 | 6 | 96 | 675 | 96 | 112 | 1 | project context / partial composer → C: readable placeholder. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 35 | 2 | 6 | 192 | 675 | 96 | 112 | 1 | project context / partial composer → C: readable placeholder. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 36 | 3 | 6 | 288 | 675 | 96 | 112 | 1 | partial legacy project context / partial composer to x375; opaque black beyond x375 → C: placeholder continuation. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 37 | 4 | 6 | 384 | 675 | 96 | 112 | 1 | opaque black historical region beyond x375 → C: placeholder tail. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 38 | 5 | 6 | 480 | 675 | 96 | 112 | 1 | opaque black historical region beyond x375 → C: textarea surface. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 39 | 6 | 6 | 576 | 675 | 96 | 112 | 1 | opaque black historical region beyond x375 → C: textarea surface. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 40 | 7 | 6 | 672 | 675 | 96 | 112 | 1 | opaque black historical region beyond x375 → C: transcript / composer edge. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 41 | 0 | 7 | 0 | 787 | 96 | 113 | 1 | legacy icon rail + partial composer above y812; black below y812 → C: tools and project footer. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 42 | 1 | 7 | 96 | 787 | 96 | 113 | 1 | partial composer above y812; black below y812 → C: tools and project/branch footer. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 43 | 2 | 7 | 192 | 787 | 96 | 113 | 1 | partial composer above y812; black below y812 → C: MCP tools and branch footer. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 44 | 3 | 7 | 288 | 787 | 96 | 113 | 1 | partial legacy partial composer above y812; black below y812 to x375; opaque black beyond x375 → C: composer surface / branch tail. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 45 | 4 | 7 | 384 | 787 | 96 | 113 | 1 | opaque black historical region beyond x375; also below y812 → C: model selector start. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 46 | 5 | 7 | 480 | 787 | 96 | 113 | 1 | opaque black historical region beyond x375; also below y812 → C: model selector text. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 47 | 6 | 7 | 576 | 787 | 96 | 113 | 1 | opaque black historical region beyond x375; also below y812 → C: selector / microphone. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 48 | 7 | 7 | 672 | 787 | 96 | 113 | 1 | opaque black historical region beyond x375; also below y812 → C: send affordance and composer edge. Intentional bounded composer and quiet secondary context; controls remain reachable. |
| 49 | 0 | 2 | 0 | 225 | 96 | 112 | 0.9999 | legacy icon rail + engineering prose / metadata → P: reply / token / copy start. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 50 | 1 | 4 | 96 | 450 | 96 | 112 | 0.9999 | dark transcript canvas → P: assistant heading and reply. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 51 | 2 | 4 | 192 | 450 | 96 | 112 | 0.9999 | dark transcript canvas → P: assistant heading and reply. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 52 | 3 | 4 | 288 | 450 | 96 | 112 | 0.9999 | partial legacy dark transcript canvas to x375; opaque black beyond x375 → P: assistant reply. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 53 | 1 | 1 | 96 | 112 | 96 | 113 | 0.9998 | user bubble / assistant heading → P: warning + revision text. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 54 | 3 | 1 | 288 | 112 | 96 | 113 | 0.9998 | partial legacy user bubble / assistant heading to x375; opaque black beyond x375 → P: revision text. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 55 | 0 | 5 | 0 | 562 | 96 | 113 | 0.9997 | legacy icon rail + dark transcript canvas → P: quality / token / copy start. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 56 | 1 | 5 | 96 | 562 | 96 | 113 | 0.9997 | dark transcript canvas → P: quality / token metadata. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 57 | 0 | 0 | 0 | 0 | 96 | 112 | 0.9996 | legacy icon rail + terminal build/title chrome → H: navigation toggle / crumb / approval icon. Intentional semantic header/status redesign; visible controls. |
| 58 | 2 | 0 | 192 | 0 | 96 | 112 | 0.9996 | terminal build/title chrome → H: title and approval text. Intentional semantic header/status redesign; visible controls. |
| 59 | 0 | 1 | 0 | 112 | 96 | 113 | 0.9996 | legacy icon rail + user bubble / assistant heading → P: warning and revision icons. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 60 | 1 | 2 | 96 | 225 | 96 | 112 | 0.9995 | engineering prose / metadata → P: reply / token / copy labels. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 61 | 0 | 4 | 0 | 450 | 96 | 112 | 0.9995 | legacy icon rail + dark transcript canvas → P: assistant identity / engine icons. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 62 | 1 | 0 | 96 | 0 | 96 | 112 | 0.9994 | terminal build/title chrome → H: title and approval text. Intentional semantic header/status redesign; visible controls. |
| 63 | 3 | 2 | 288 | 225 | 96 | 112 | 0.9971 | partial legacy engineering prose / metadata to x375; opaque black beyond x375 → P: neutral transcript canvas. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |
| 64 | 2 | 2 | 192 | 225 | 96 | 112 | 0.9933 | engineering prose / metadata → P: reply and token tail. Intentional neutral/prose hierarchy plus different saved conversation; no current overlap. |

## Complete directly opened screenshot inventory

All entries below were opened individually as their original local image through `view_image`; every hash was independently recomputed against the manifest. Order is the manifest order, using zero-based indices. The 51 route and 27 state frames are all included.

| Index | Original path | Dimensions | SHA-256 | Opened |
|---:|---|---|---|---|
| 0 | `captures/round6/final-375-model-menu.jpg` | 375×812 | `00b76daabd290b43d410c2b2eb96a2ec7ec1688ccb603566e6bf506f98885486` | yes |
| 1 | `captures/round6/final-375-history.jpg` | 375×812 | `2c966baecc12e05d7f8f4b29e8251f39b16106f3e04c5c82d252d30634511970` | yes |
| 2 | `captures/round6/final-375-inspection-environment.jpg` | 375×812 | `167470b85d0d9aac18ef0f1c772a8270c389ef9529ee4dd9e70b0732775fdea7` | yes |
| 3 | `captures/round6/final-375-inspection-code.jpg` | 375×812 | `108e6e1589a90c269ca3e6fcaea8cc33afd737ec6ae26c54520c5d72f3421321` | yes |
| 4 | `captures/round6/final-375-inspection-changes.jpg` | 375×812 | `5d191a4e864a84b87d06a9aab19c4928d877048bb796adccf78e797ace603010` | yes |
| 5 | `captures/round6/final-375-command-palette-early.jpg` | 375×812 | `a45add5da83bf70ff43606ff68c24611250747c1889d2f0d13e5b69a8ccb24f3` | yes |
| 6 | `captures/round6/final-375-command-palette.jpg` | 375×812 | `665114580ecf7a785066be8c8295411a8dc690ff75676ed57bedb17ebb5dc8cb` | yes |
| 7 | `captures/round6/final-375-shortcut-guide-early.jpg` | 375×812 | `616391fb0bdc85a26b963aecce46d3529d36c954a904db7f2747e761ef2c7d0b` | yes |
| 8 | `captures/round6/final-375-shortcut-guide.jpg` | 375×812 | `555fcf6ceed000f20b0ab108bf0f11c5fc88bbcd5c20a9e0a9ccbe08b763b9ba` | yes |
| 9 | `captures/round6/final-375-navigation.jpg` | 375×812 | `fba24bbf4b55ad76b9d4a5b39f945b64ad886c521b5682300bb6c10a045eb84e` | yes |
| 10 | `captures/round6/final-375-status.jpg` | 375×812 | `017dde0c28451f74fe73acc692be2b2b09983ddb0f29d6adc0a6ae0f285cddd3` | yes |
| 11 | `captures/round6/final-375-home.jpg` | 375×812 | `fe13d24468b5537e08904bfe4fc705e0ab4dae6fdd0230205e3bb1087505414a` | yes |
| 12 | `captures/round6/final-375-chat-alias.jpg` | 375×812 | `b14eb5ecc210e470789a7decd2ec4e81d941581e37114b62fabbba5b2fd6ce88` | yes |
| 13 | `captures/round6/final-375-studio.jpg` | 375×812 | `f5aeddb6f019eab2e8fa684fdcd9e060457951501e7f467e60f88cad49478296` | yes |
| 14 | `captures/round6/final-375-start.jpg` | 375×812 | `e9b3b4a25131768790d8ce587325bd07f104d307124abf40aa2ac3fd0a6b7f7d` | yes |
| 15 | `captures/round6/final-375-wiki.jpg` | 375×812 | `31c1b8de155bd2e77d7d6bdba3ca088d11510195af26bc26cbc0577a1dfdec55` | yes |
| 16 | `captures/round6/final-375-agent.jpg` | 375×812 | `bf8c66c5b61aa22562ee3f4dc2e44cead5e5d77a1d9e9698711aed1cb804fe7c` | yes |
| 17 | `captures/round6/final-375-settings.jpg` | 375×812 | `e94598bbb6733a9e7a47867a695447d0913dd4eac78a6bd618bbd246e2b7b4f5` | yes |
| 18 | `captures/round6/final-375-skills.jpg` | 375×812 | `fd52de936779da3c990d26dd8976c9f951c8d8a733ebf4b4a69064782c4ae686` | yes |
| 19 | `captures/round6/final-375-data-extraction.jpg` | 375×812 | `b3e8ed1bf67bb1ce99e47abf4b3ce1bd8b4512b18d87469a7d593ab81430644b` | yes |
| 20 | `captures/round6/final-375-git.jpg` | 375×812 | `cbd7410500bb27fdc92c36fc69f89ea1b1f1803d5b1002a117e46bd487bca81b` | yes |
| 21 | `captures/round6/final-375-history-page.jpg` | 375×812 | `b71752d586eb0d61106db849ad2ddfae15f0f4d6447a61d587dfd849b33c162b` | yes |
| 22 | `captures/round6/final-375-plugins.jpg` | 375×812 | `75677e4368776f376433511b45b21968ee87e8554d93d4845362b86ad97f409f` | yes |
| 23 | `captures/round6/final-375-mutation.jpg` | 375×812 | `cadec083cd7f8d6584bbc67d2a045dadb8d66f6a8efc883a983d2dce7e737db2` | yes |
| 24 | `captures/round6/final-375-hello-world.jpg` | 375×812 | `25ce4a530ac7c98debf22dd980db4252f67834d54ea9e5808702573dccd544ea` | yes |
| 25 | `captures/round6/final-375-job-operations.jpg` | 375×812 | `34f3648ef59131041297978925e7026c179b80daceaae22f4fb501f5bd0e554a` | yes |
| 26 | `captures/round6/final-375-not-found.jpg` | 375×812 | `bd378532731ee501612569c03858462631d0daa6c834412485173fa81de1e2c0` | yes |
| 27 | `captures/round6/final-375-models.jpg` | 375×812 | `c19905c0b52b54dcd665d548d61845b35bd9083990593907e2defd1003fca31c` | yes |
| 28 | `captures/round6/final-375-empty.jpg` | 375×812 | `0bf1d4b62ed3a47034bbf94f785b092fed02785fe90aedf1e398310449c7e56b` | yes |
| 29 | `captures/round6/final-375-generation.jpg` | 375×812 | `8bdb1f482132004e6bc4d2bd9e4c1351a56e01de536e87266ab765937b90c1e7` | yes |
| 30 | `captures/round6/final-375-chat-complete.jpg` | 375×812 | `616f457e4e4b17fdb6b50971e527be19c6a39f5ce7635737dd427a685b350463` | yes |
| 31 | `captures/round6/final-375-copy.jpg` | 375×812 | `9df8541910662cca1ac4386e23ff6ab0e5a98a8dea9f453ee110ed4aff140ab1` | yes |
| 32 | `captures/round6/final-768-home.jpg` | 768×900 | `8b5ad30b84bfa89e5f58dfd5f700ef88ec454752d3b00ab41329c3ca2f74b842` | yes |
| 33 | `captures/round6/final-768-chat-alias.jpg` | 768×900 | `644f69bb0f876f13ca74418d4105031e84051235c749aeaf54cc1b8ecad53bc8` | yes |
| 34 | `captures/round6/final-768-studio.jpg` | 768×900 | `9052c666f077cc3e7927f4ba9ba9b58f883f799993391fde252bd72f1541454d` | yes |
| 35 | `captures/round6/final-768-start.jpg` | 768×900 | `26385dafacf33daea84f23132d9afca544212f5292197f6e0cda7b93dffbeb23` | yes |
| 36 | `captures/round6/final-768-wiki.jpg` | 768×900 | `f481302a314c4fd69543899459733cce75d6290d227d42899f0a3d30f0136d5b` | yes |
| 37 | `captures/round6/final-768-agent.jpg` | 768×900 | `230a41d26b3c254bf0bd570f75f154973218a53d7c549bfd4389b18240927253` | yes |
| 38 | `captures/round6/final-768-settings.jpg` | 768×900 | `0ac40a8534566f7c21c2895e017171d14e6f3df0d1b6ae4fabe34a708a0f907b` | yes |
| 39 | `captures/round6/final-768-skills.jpg` | 768×900 | `c6e4bbe38f0c5c6869a6480abb2e081c535dce0cc59dd85c1b9b2689177bf192` | yes |
| 40 | `captures/round6/final-768-data-extraction.jpg` | 768×900 | `41e97779d72840e832e3a90aeaf2dc5edf2bf29782f11c5fd6902ee87e03cab5` | yes |
| 41 | `captures/round6/final-768-git.jpg` | 768×900 | `cd116c48ff3833c9b91b327e57b7ef8b173b48b46e311ac5e6045dd2e1d185c9` | yes |
| 42 | `captures/round6/final-768-history-page.jpg` | 768×900 | `fcbad533c6fb4887a9fdd2d7909ef107e2f29cde3ed3e3eacb326b165190d84c` | yes |
| 43 | `captures/round6/final-768-plugins.jpg` | 768×900 | `0f99c013a84a345810e50c03a3865720f4c30668f37c46e6efc7087109b01fa8` | yes |
| 44 | `captures/round6/final-768-mutation.jpg` | 768×900 | `410d8377f6abc57d5dff8f151c1129e5ea5b75909b90e9ab80ed3748db8d2b24` | yes |
| 45 | `captures/round6/final-768-hello-world.jpg` | 768×900 | `9e1b05405498921156b87cf377a7159e0a9f40ee45cc388f514fb4c5be75aa4d` | yes |
| 46 | `captures/round6/final-768-job-operations.jpg` | 768×900 | `6590d7e7a0ceb7a15095ed8509e4d249cffe267b9a0e6e9face9f15d5e08240e` | yes |
| 47 | `captures/round6/final-768-not-found.jpg` | 768×900 | `e7cf676e53ba2ccdc8a5d5127d8287a40978eed8632a4ab29ba055353b3af63d` | yes |
| 48 | `captures/round6/final-768-models.jpg` | 768×900 | `752701c7d03c88e5b590beb55c49fc0548f7fc052c62cc17d79aace148a21f72` | yes |
| 49 | `captures/round6/final-768-history.jpg` | 768×900 | `f1c3eedac20b2ddee2c5373cc0805b1a451356d2fbc9b570b8923ec5eee30bb0` | yes |
| 50 | `captures/round6/final-768-inspection-environment.jpg` | 768×900 | `d73005fb017543cffef8b3c6fb865d0d1bca82aa4a977caa62e7396176eea712` | yes |
| 51 | `captures/round6/final-768-inspection-code.jpg` | 768×900 | `1c38059db8ec30ebac9a18fe9584c0df594bbcdf7599c80eb250b8c78f4cacb7` | yes |
| 52 | `captures/round6/final-768-inspection-changes.jpg` | 768×900 | `e2c8cd37e9bf07e88a069809138ee7c7aa7fd167eaac94f354ce9d97897d9113` | yes |
| 53 | `captures/round6/final-768-command-palette.jpg` | 768×900 | `aeb4274bc9f24db49cd92cab4f7f4c3ce3d83346c8a1f0d7917b3500d4002abb` | yes |
| 54 | `captures/round6/final-768-shortcut-guide.jpg` | 768×900 | `cceed84aa3f1e2d6caf6e7ce3f9c106257d5d9f31223179e63764865e794cca8` | yes |
| 55 | `captures/round6/final-1280-home.jpg` | 1280×900 | `66a6c583f61a704faff053fd845338b3e7d1612bd2dec2792d5c439d7f94a326` | yes |
| 56 | `captures/round6/final-1280-chat-alias.jpg` | 1280×900 | `a39eca73e937719b5b265e063b2777d7925bfbe41e5f8915c0071378cf57967a` | yes |
| 57 | `captures/round6/final-1280-studio.jpg` | 1280×900 | `f10bc7f7503497cf3162dbcae4fc99b963217550ebcd304c17b004d288b21698` | yes |
| 58 | `captures/round6/final-1280-start.jpg` | 1280×900 | `2a3fd6a85c868921b6251302c348af38a7ed59961cd8d31c141ef63b22f8fddf` | yes |
| 59 | `captures/round6/final-1280-wiki.jpg` | 1280×900 | `bfd36912d3506f63a0f4db1d91bd6aa53f49e24706a15297859d12ed25c854ce` | yes |
| 60 | `captures/round6/final-1280-agent.jpg` | 1280×900 | `1cfec226b0d9189c658f9e6717c087bb584b38f3d79b6d875e10b505d01fd15a` | yes |
| 61 | `captures/round6/final-1280-settings.jpg` | 1280×900 | `0bac59871cd47b26028c5a8c50d54d4f149554e60ae403d4ed0bebadb7135a98` | yes |
| 62 | `captures/round6/final-1280-skills.jpg` | 1280×900 | `b8fa24aa21f94e6f0768b094de83ed54e843bce3ed7d9484441afbe424023f2a` | yes |
| 63 | `captures/round6/final-1280-data-extraction.jpg` | 1280×900 | `7505d01afb05496bfa3469863b74e235da51fa13482ae59b3e135a1e7ba9a5e5` | yes |
| 64 | `captures/round6/final-1280-git.jpg` | 1280×900 | `dd88b9546a95f2df5ff152cc7aa2d35e29c4ab844381bcc6423cb1919fc926eb` | yes |
| 65 | `captures/round6/final-1280-history-page.jpg` | 1280×900 | `1bf7843054a75aa8379dc6dfff3656730662b4ee2ddcabe08acafac941c19e55` | yes |
| 66 | `captures/round6/final-1280-plugins.jpg` | 1280×900 | `f1346f94e1206b956df6e5d16a3db3239265b0ac13c87737439b166e72411003` | yes |
| 67 | `captures/round6/final-1280-mutation.jpg` | 1280×900 | `dc9d9de13e289ea72376313ebea6389d295edacc4f13369475ebbbde2e1baa82` | yes |
| 68 | `captures/round6/final-1280-hello-world.jpg` | 1280×900 | `71f79292c6f5fe7e468985fd275ca3568850537ad6492656cd53e64fca592a2b` | yes |
| 69 | `captures/round6/final-1280-job-operations.jpg` | 1280×900 | `c92d24798b4722bdba5c1d04308c20115c7172bdfaecbb9bf46f081a9e0f984b` | yes |
| 70 | `captures/round6/final-1280-not-found.jpg` | 1280×900 | `b9f11598c3bd3ea3d1e396ac439e22864b98a0eac3e4fbf2af6dd85c7fe3ed87` | yes |
| 71 | `captures/round6/final-1280-models.jpg` | 1280×900 | `b7a9d1dcf8d6c110033129977928d71a523cddaa24236cf2753be03b5f894b7f` | yes |
| 72 | `captures/round6/final-1280-inspection-environment.jpg` | 1280×900 | `7734426062ebed2fb00123f2adf13229a0867824c4c55d1aead70bcddf167e6f` | yes |
| 73 | `captures/round6/final-1280-inspection-code.jpg` | 1280×900 | `483cb9189d17f1dc186e12495fb78b5bcfe2e29e9023918f7aef4423032630d3` | yes |
| 74 | `captures/round6/final-1280-inspection-changes.jpg` | 1280×900 | `6b308b217c757dfa3f1f72cc4eb908ab95c0e932cb9847b7b548c5834a1d9170` | yes |
| 75 | `captures/round6/final-1280-output.jpg` | 1280×900 | `43de618df19177bef21925dd5fbcea17c1fdbe8127d4f94ecfaeb87da92e6346` | yes |
| 76 | `captures/round6/final-1280-status-details.jpg` | 1280×900 | `446b27037106172c324168e87d53530a8549db13a3849ceb815ab8fd0a19253c` | yes |
| 77 | `captures/round6/final-1280-chat-complete.jpg` | 1280×900 | `1ddf0925b30289476af38e085e512d0037be64e49244ce909710a9d0a60616f5` | yes |


## Blocking / approval conclusion

Blocking: F1 and F2. Fix the scoped Korean prose wrapping and independently confirm/correct direct non-chat recent-history hydration, then bind fresh relevant captures to the resulting source/build. The historical comparison warning is an evidence interpretation limit, not a demand for exact Codex pixels or historical reconstruction. No other material product defect was found in this complete pass. The current font, tonal hierarchy, live control structure, responsive containment, composer visibility, and repaired modal header/focus behavior should be preserved.
