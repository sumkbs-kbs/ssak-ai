---
title: Manual QA review — Codex-style SSAK-AI UI, round 6
tags: [qa, frontend, manual-qa, codex]
date: 2026-10-03
---

# Manual QA review

Verdict: **REVISE**. The previous guide focus failure and compact modal header failure are resolved on this build. All 78 captured frames are fresh and valid. Remaining closure is Korean helper/empty-state wrapping, mobile Mutation provenance clipping, recent-conversation navigation after a nonchat cold load, and settled Git route evidence. No authentication or approval change is requested.

Execution mode: **QA-agent-directed/root-executed**. This judge sent operator steps before execution, accepted root's clarification that the actual handoffs use Meta+K and Meta+Slash, and waited for the current QA_CAPTURE_READY.md to declare READY. Root alone operated the existing user-unlocked **IAB browser2/tab1** at http://127.0.0.1:8000/. This judge directly opened **all 78 JPEGs**, inspected semantic heading/control/loading evidence from **all 51 fresh route DOM snapshots**, read the complete current directed/live-chat results, and independently checked source/output/capture bytes. Relevant guide, handoff, composer, hydration, API and model-preference tests were inspected through the codebase graph. This lane did not open a browser profile, request/enter a PIN, read browser authentication storage, transfer credentials, modify production code, stage files or create a commit.

## Exact reviewed binding

This is the frozen **round 6** packet. JSON names below now use their immutable _ROUND6 copies; their bytes and SHA values are unchanged. Captures are archived under captures/round6/, and the 45 manifested files are archived under source-round6/ with their original repository paths. Manifest entries retain their original captures/final-* names; each maps by basename to the archive. All 78 frozen JPEG and 45 frozen source hashes were independently rechecked and still match. Later live-source edits and subsequent packets are excluded from this verdict.

| Artifact | SHA-256 / identity |
|---|---|
| Git HEAD | 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382, plus dirty source |
| SOURCE_MANIFEST_ROUND6.json | a1552cf1f91459253bfb96910eeb7fcd0d29e5e8cb0e836cbcfc93267014d3b8, 45 files |
| BUNDLE_MANIFEST_ROUND6.json | 5be0fded71aeea0d94de81337b5f6e4a03e59acfc0e10a277fc871e54f361acf, 104 output files |
| Main JavaScript | /assets/index-DNX9exh1.js; 0e7120f581ecf35751f5cdc32552e083b95356747c97d7c707e2879a1ccfd836 |
| Main CSS | /assets/index-BLgp1deP.css; 78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b |
| CAPTURE_MANIFEST_ROUND6.json | 568f7bfbae5cc9c4fbbc51fd2f622c21e951536a6af1c997895100bab4e79b3f |
| BROWSER_OBSERVATIONS_ROUND6.json | 0849e3dcda7f7f1162cbc026738c36f0442d084c86c577c3d3ffa17a7346174d |
| QA_DIRECTED_RESULTS_ROUND6.json | acc3c9c5549ecf0d2e75c1efbe53c2931a94ecd239c158a314da8c3ebb1d5acc |
| LIVE_CHAT_RESULT_ROUND6.json | e456ca1b78017866a01e5ce5a8a1be9be1d9488fa1ae07cc14db12b2b3c38ffd |
| VERIFICATION_ROUND6.json | 56323bbba21c0097235b7c8fcc13f9e29a396e91b0208c941d7ec03f6eb61bc5 |
| LIVE_STYLE_BINDING_ROUND6.json | 17ee4d92af6a62ec4af48c3d45741be360afa43f69770329348280e993ff5790 |

All 45 source hashes and all 104 production-output hashes matched the actual files. Protected chatStore.ts, projectStore.ts, api/client.ts and accessPinCredential.ts actual hashes matched their identical before/after values.

The packet contains **78 unique observations and 78 unique JPEGs**: **17 routes × three viewports = 51 route frames**, plus **27 state frames**. Viewports are 375×812, 768×900 and 1280×900. Independent checks found zero image hash/signature/dimension failures, zero missing route DOM snapshots and zero captures predating the latest source edit, 2026-10-03T03:08:38.190751+00:00. All 51 DOM files also postdate that edit. Every observation records the current JavaScript, and live style binding records current CSS. Zero primary-page horizontal overflow is measured across the route inventory. These measurements establish hygiene and bounded geometry, not a blanket visual PASS.

Only current route DOM and current directed/state evidence are used. Older state DOM and earlier-round frames remain historical. Early palette/guide frames mean the first actually observed frame, with no invented transition timing. E02 enumerates the complete JPEG inventory; every listed image was opened by this judge.

## Blocking findings

### C1 — Korean helper and empty-state words fracture across lines [product, P2]

The Korean prose wrapping contract is not consistently applied to secondary text:

| Current frame | Visible location / fracture | Matching DOM text |
|---|---|---|
| final-375-wiki.jpg | Empty paragraph below book icon: 생성 ends one line and 하세요. is isolated on the next. | 왼쪽 트리에서 문서를 선택하거나 새 문서를 생성하세요. |
| final-1280-history-page.jpg | Helper below empty Files message in first column: 저장됩 / 니다. | 파일을 편집하면 자동으로 스냅샷이 저장됩니다 |
| final-1280-settings.jpg | Default-model helper in section 02: 보여줍 / 니다. | 서버 구성(defaults.reasoning) 값을 보여줍니다 |

The Wiki fracture is especially clear at native 375px and was independently acknowledged by root before final review. Both desktop frames were directly opened, including Settings at original detail. These are breaks inside ordinary Korean words, not code/path wrapping. dashboard/DESIGN.md §4 requires word-break: keep-all and natural spacing for Korean prose; the plan requires readable Korean at all three widths. The current NotFound 주소가 and Data Extraction 만원/억원 repairs show the intended behavior elsewhere.

Required closure: apply the prose wrapping contract to these empty-state/helper primitives so ordinary Korean words stay intact and lines wrap at spaces. Preserve bounded wrapping/scrolling for technical identifiers. Confirm these three exact text examples and neighboring helper copy in the real UI. This lane made no production edit. Batch this with the independent visual reviewers' located findings before rebuilding and obtaining a complete fresh final packet.

### C2 — Mutation mobile provenance SHA clips its final character [product, P2]

Direct reinspection of frozen final-375-mutation.jpg at original detail confirms that the Source commit value runs past its panel edge and visibly ends in ...5149. The matching frozen route DOM contains the complete 40-character value **6d0a24d4e6a0686693ce29a4d13a69443ae5149b**. The final b is not visible inside the mobile viewport. The 768/1280 frames show the complete identifier. This independently confirms VISUAL_REVIEW_B_ROUND6.md finding B6-4; zero page overflow does not prove nested identifier containment.

Required closure: wrap the actual provenance code value within its shrinking definition/container while keeping all 40 characters readable. Verify the exact token at all three widths, retain the existing historical/stale provenance wording, and avoid changing mutation behavior or data.

### C3 — Nonchat cold-load sidebar falsely shows no recent conversations [product, P2; existing goal gap]

The frozen 1280px Studio frame and its matching route DOM show the recent-conversation region labelled 최근 대화 with only **첫 대화 시작하기**. In contrast, the frozen chat/history evidence retains four actual conversation records. Root additionally confirmed the same false-empty sidebar through a direct Studio cold load on this binding. This is a route-dependent recent-navigation hydration gap, not evidence that conversations were deleted, and root identifies it as an existing baseline issue. It still prevents the requested conversation-first sidebar from working consistently across the app.

Required closure: restore real recent conversations when landing directly on a nonchat route, using stable conversation IDs and the existing persistence contract. Then cold-load Studio and another nonchat route and select an existing recent conversation through the visible sidebar; confirm the exact selected record and preserved history/draft. New source/tests reported by root after this binding are not accepted as round 6 closure.

### E1 — Git images are loading frames rather than settled inspection evidence [evidence, P2]

All three current final-{375,768,1280}-git.jpg frames show **Loading status...** and an empty changes area. The 375px DOM likewise records loading. In contrast, current 768px and 1280px DOM snapshots already contain the real branch and populated staged/unstaged/untracked lists (433 native buttons each). The 768px snapshot begins with the actual branch, 214 staged, 62 unstaged and 147 untracked entries; none appear in its paired JPEG.

The source and route are bound correctly, but the image and later DOM represent different states. The packet does not visually verify the populated Git inspection surface at any required width. This is a timing gap, not a demonstrated Git API/product regression. No staging, unstage, commit or other Git mutation was executed by this QA lane.

Required closure: await the actual populated Git status/list, then capture matching settled JPEG and DOM at all three widths and remeasure page bounds. Repair timing without inventing backend success or changing Git behavior. If source remains unchanged, replace only defective evidence; after the C1 source repair, final approval still requires a complete fresh packet on the new source/build.

## Resolved blockers and good evidence

- **Guide lifecycle resolved:** history → guide at 375/768 focuses the named Close button. Actual Tab and Shift+Tab remain there with only the guide dialog and four inert background regions. X and Escape leave zero dialogs/inert regions, restore the history opener and retain the unsent Korean draft. Source now uses useModalDialog with a Close ref; seven direct guide behavior tests and inspection/history handoff tests support the observed fix.
- **Header layering resolved:** history plus all three inspection tabs at both compact widths have complete title/close headers. All eight close-center hits are true with main z-index auto. Actual X restores the relevant opener/draft and releases modal state; the 768px inspection Escape result additionally records the same closure. All three 1280px docked inspection headers remain visible.
- **Opaque foreground entry resolved:** early and settled 375px palette/guide and settled 768px frames are readable. Palette opacity is 1, background rgb(24, 24, 24), animation none; guide opacity is 1, background rgb(37, 37, 37), animation none. Inspection → Meta+K leaves only the palette with search combobox focus. Escape restores inspection opener/draft at both widths. No palette menu handoff was invented.
- **Navigation containment resolved:** real 375px reverse wrap reaches terminal, forward wrap reaches Close, and Escape restores the navigation opener with zero dialogs/inert. The executed navigation draft is empty; no unsent-draft preservation claim is inferred from that case.
- **Real chat/preservation evidence valid:** current 27.3B is pressed after reload, earlier conversations are retained, normal replies complete and both copied responses match. Shift+Enter adds a newline. The first synthetic layout prompt also elicited an existing engine computer_use approval notice; root did not approve it. A subsequent no-tool greeting completed normally.

## Original 25-scenario matrix — manualQa.surfaceEvidence

Original **B01–B20 and A01–A05** IDs are retained. B12 is file history; A02 is the conversation drawer. R means the current final-{375,768,1280}-<suffix> JPEGs and fresh route DOM enumerated in E02. A PASS certifies the stated rendered scope and named interactions, not every backend operation.

| ID | Criterion / actual current invocation | Current result / mode | Evidence |
|---|---|---|---|
| B01 | / home; chat shell and explicit new-chat empty state | PASS — manual. Bounded composer/model and empty prompt render. | R home, E04, final-375-empty.jpg |
| B02 | /chat alias | PASS — manual. Same bounded conversation shell at all widths. | R chat-alias |
| B03 | /studio; base-model step, pipeline/cards and shared sidebar | REVISE — C3 false-empty recent conversations after nonchat cold load. Page geometry renders; no training started. | R studio, C3 |
| B04 | /models; active list | PASS — manual surface. qwen3.8 27.3B active; other models only viewed. | R models, E04 |
| B05 | /start; bridge choices/copy controls | PASS — manual surface. No bridge command executed. | R start |
| B06 | /wiki; tree/empty state | REVISE — manual visual C1 at 375px; tree/controls otherwise render. | R wiki, C1 |
| B07 | /agent; idle/unavailable monitoring | PASS — manual actual displayed state; no all-API-success claim. | R agent |
| B08 | /settings; masked/bounded controls | REVISE — C1 in 1280px default-model helper. Keys stay masked; no credential edit. | R settings, C1 |
| B09 | /skills; actual empty/error state | PASS — manual displayed state. Existing auxiliary401 is not backend success. | R skills, E01 |
| B10 | /data-extraction; A/B action/Korean units | PASS — manual surface. A/B action and 만원/억원 intact. Metrics401 is not backend success. | R data-extraction |
| B11 | /git; read-only inspection | PARTIAL — loaded768/1280 DOM, but all three JPEGs show loading. E1 must close before approval. No mutation claim. | R git, E1 |
| B12 | /history; file-history empty state | REVISE — C1 in1280px Files helper. Distinct from conversations. | R history-page, C1 |
| B13 | /plugins; index | PASS — manual surface. No install/removal executed. | R plugins |
| B14 | /mutation; historical provenance | REVISE — C2 mobile commit identifier clips. Stale/historical wording retained; no live mutation run claimed. | R mutation, C2 |
| B15 | /plugins/hello-world; registered surface | PASS — manual route surface; no toast action claim. | R hello-world |
| B16 | /plugins/job-operations; healthy/zero state | PASS — manual surface. Zero jobs/history; no job creation/retry. | R job-operations |
| B17 | /ui-qa-not-found; deliberate fallback/CJK | PASS — manual. Return controls visible; 주소가 intact. | R not-found |
| B18 | 375 navigation; real reverse/forward wrap/Escape | PASS — manual. Focus contained, opener restored. | E03, final-375-navigation.jpg |
| B19 | Inspection → Meta+K/Escape; history → Meta+Slash; guide Tab/Shift+Tab/X/Escape | PASS — manual375/768. Opaque surfaces, initial focus, guide containment/restoration. Current palette Tab is not separately asserted. | E03, current palette/guide frames |
| B20 | Compact model bounds/reload preservation | PASS — manual. 27.3B pressed after reload, bounded popover and prior titles retained. No125B load/switch claim. | E03–E04, final-375-model-menu.jpg |
| A01 | Compact/docked inspection3; reachable header/close | PASS — manual. Tabs render375/768/1280; compact real X/hits/focus/draft restoration pass. | E02–E03, all9 inspection frames |
| A02 | Conversation history closure/retention; distinct file history | PASS — observed manual closure/retention. Both widths have header/X/Escape/focus/draft proof. Session selection semantics retain automated coverage; no fresh manual selection claim. | E03–E05, history frames |
| A03 | Shift+Enter, real send/copy, IME guard | PASS — manual newline/generation/copy. Both copies match. Native OS IME/key229 portion AUTOMATED-only. | E04–E05, generation/completion/copy |
| A04 | Desktop output viewer without command | PASS — manual read-only. Filters and actual No output yet render; no command sent. | final-1280-output.jpg, E02 |
| A05 | Controlled503/CAS/late hydration augmentation | AUTOMATED-only. Typed failure/conflict and draft/new-session preservation; no injected browser/retry-UI PASS. | E05 |

Counts: **18 manual PASS, five manual REVISE, one PARTIAL, one AUTOMATED-only row**. A03 also labels its IME portion AUTOMATED-only. These are the retained 25 rows, with their actual execution modes.

## Directed and adversarial cases — manualQa.adversarialCases

| Boundary | Actual result / mode | Evidence |
|---|---|---|
| D01: reload/model/history | 27.3B pressed after real reload; earlier records retained and one finalQA conversation added through UI. No deletion. PASS — manual. | E03–E04 |
| D02: navigation wraps | Both contained; Escape restores opener and clears modal/inert state. PASS — manual. | E03 |
| D03: inspection → palette | Only palette owns focus; opaque; Escape restores opener/draft at375/768. PASS — manual. | E03 |
| G1: history → guide | Initial Close focus, real Tab/Shift+Tab contained, X/Escape restore opener/draft at both widths. Prior blocker resolved. | E03, E05 |
| Compact header/pointer boundary | All8 title/close tests visible/hit true; real X works on history and each inspection tab. PASS — manual. | E03 |
| Korean secondary-copy boundary | Three word fractures remain. REVISE — product C1. | E02, C1 |
| Nested mobile identifier boundary | Mutation provenance loses the final SHA character at 375px. REVISE — product C2. | E02, C2 |
| Nonchat cold-load recent navigation | Studio sidebar shows a false empty state despite retained chat records. REVISE — existing goal gap C3; frozen frame/DOM and root's direct confirmation. | E02, C3 |
| Async Git capture boundary | JPEGs loading; later768/1280 DOM populated. PARTIAL — evidence E1. | E02, E1 |
| Native OS IME/key229 | Automated event guards retain draft/avoid submit. No native-device run. | E05 |
| Controlled503/CAS/late hydration | Typed migration/conflict, permission failure preservation, early draft/new-session guards inspected as automated evidence. No browser injection claimed. | E05 |

## Artifact references — manualQa.artifactRefs

Paths are under docs/qa/2026-10-03-codex-ui/ unless stated otherwise.

| ID | Paths / scope |
|---|---|
| E01 | [READY round 6](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY_ROUND6.md), [source manifest](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST_ROUND6.json), BUNDLE_MANIFEST_ROUND6.json, CAPTURE_HYGIENE_ROUND6.json, LIVE_STYLE_BINDING_ROUND6.json; frozen source-round6/original repository paths |
| E02 | [capture manifest](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST_ROUND6.json); all 78 listed captures/round6/final-*.jpg; BROWSER_OBSERVATIONS_ROUND6.json; all 51 matching fresh route captures/round6/final-*.dom.txt. Older state DOM excluded. |
| E03 | [directed results](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/QA_DIRECTED_RESULTS_ROUND6.json), QA_OPERATOR_INSTRUCTIONS_ROUND6.md; actual root-operated actions/focus/draft/header hits |
| E04 | [live chat result](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-03-codex-ui/LIVE_CHAT_RESULT_ROUND6.json); round 6 generation/completion/copy/model/history frames |
| E05 | VERIFICATION_ROUND6.json preserves the reported 102 files/987 tests and typecheck/build exit 0. This judge directly inspected the round 6 raw results before the next source changes. Guide/handoff/composer/hydration tests are retained in source-round6/, plus inspected unchanged dashboard/src/api/client.test.ts and dashboard/src/stores/__tests__/chatStore.modelPreference.test.ts. The test/build raw logs were not archived and are now overwritten; no frozen 987-test/build raw file is claimed. |
| E06 | source-round6/dashboard/DESIGN.md; docs/frontend/EXECUTION_PLAN_2026-10-03.md; original/retained matrix in QA_REVIEW_ROUND1.md, QA_REVIEW_ROUND4.md, QA_REVIEW_ROUND5.md; independent VISUAL_REVIEW_B_ROUND6.md corroborates C1/C2 |

## Review limits and final closure

This one-shot report records actual browser actions and remaining defects on **a155/DNX9/BLgp**. It does not approve a newer binding, exact proprietary Codex Desktop pixels/fonts, native OS IME, controlled browser faults, auxiliaryAPI success, axe/Lighthouse scores or backend full-suite health. ReactDoctor remains the disclosed exit1 advisory for a pre-existing ignored nonshipping mutation fixture. These limits are not additional release blockers.

Historical validation caveat: root confirms that round 6 test/build raw log bytes were not copied before the live filenames were overwritten by the subsequent 1000-test build. Those old bytes are unavailable from this frozen packet. The 987-test/typecheck/build result above is a prior directly inspected observation and a preserved verification record, not a reproducible frozen raw-log artifact. Current 1000-test logs are excluded from this verdict. The remaining old TYPECHECK_CURRENT log can be archived by root; no missing log is reconstructed or fabricated.

The engine approval notice is retained as real response content; root did not approve it and the subsequent no-tool reply/copy completed normally. Store/API/PIN protection hashes match. No security permission change is requested.

Root owns the bounded C1 prose repair, C2 provenance containment, C3 nonchat recent navigation and E1 timing correction. Final approval requires resolved rendered evidence, a complete fresh packet on the resulting binding and a new independent review. Retain the current modal and preservation improvements; the resolved guide/header failures are not reopened.
