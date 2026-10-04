# SSAK-AI Codex-inspired frontend goal review

## Verdict

- **recommendation:** REJECT
- **confidence:** High
- **reviewed HEAD:** `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- **reviewed source-manifest SHA-256:** `6b1aacf46676070701e3367fde89ecdecc4cd379ca57ef96d7f0c31513bb3006`
- **reviewed production entry:** `assets/index-C1osb2i9.js`
- **review scope:** the artifact bound above, before the responsive-page repair that root assigned after this review found the failures below

## Original intent

The user found the existing application disordered and hard to read. They asked for a careful study of the current Codex desktop composition, typography and UI/UX and for those qualities to be implemented in SSAK-AI. Because the public `openai/codex` repository is a Rust TUI/app-server rather than the proprietary Desktop React source, success means an honest Codex-inspired adaptation: quiet system typography, project/conversation-first navigation, a readable conversation canvas, a stable composer, coherent responsive pages, and preserved SSAK-AI behavior. It does not mean an unsupported pixel-perfect clone or copied proprietary font assets.

## Desired outcome

The shipped React/Vite dashboard should feel calmer and easier to read across its real routes at 375, 768 and 1280 pixels. Navigation, model choice, chat history, inspection, keyboard interaction and actual status data should remain functional. PIN authentication, project/session identity, server revisions/CAS, local-model preference, Markdown sanitization/approval behavior and UNKNOWN/0/stale distinctions must remain intact. Evidence must bind the reviewed sources to the production bundle and show settled route and modal states rather than preview, stale-bundle or loading-only frames.

## Blockers

1. **violatedCriterion:** `UI-RESP-01` — “375/768/1280 가로 넘침·한글 잘림·본문 가림 없음.”  
   **observation:** The current 375px Model Hub and Studio captures visibly show a full-page horizontal scrollbar and right-edge clipping. Model-category controls extend beyond the viewport; Studio header badges and pipeline steps are cut off. This is primary-page overflow, not a harmless code/table scroller.  
   **evidencePointer:** `captures/final-375-models.jpg`, `captures/final-375-studio.jpg`; execution-plan checklist in `docs/frontend/EXECUTION_PLAN_2026-10-03.md`.

2. **violatedCriterion:** `QA-ROUTES-01` — “전체 라우트 목록과 최신 캡처 연결, 독립 기능/시각 검토.”  
   **observation:** At review time no passing `QA_CAPTURE_READY.md` or final current-build capture manifest existed. The Round 1 packet was explicitly blocked behind PIN and rejected stale `index-CJUpMcF4.js` captures. The newly produced Settings frame shows only `Loading...`, so it does not establish the settled route. The 768px and 1280px final route matrices were still absent.  
   **evidencePointer:** `QA_CAPTURE_READY_ROUND1.md`, `CAPTURE_MANIFEST_ROUND1.json`, `captures/blocked-pin-lock-1280x720.jpg`, `captures/final-375-settings.jpg`; required matrix in `docs/frontend/EXECUTION_PLAN_2026-10-03.md`.

These blockers require a responsive repair, a new source manifest and production build binding, and fresh settled captures. Evidence from the currently reviewed hash must not be reused to approve changed source.

## Criterion-by-criterion review

| Criterion | Result | Evidence |
| --- | --- | --- |
| `REF-01` Public Codex scope is represented honestly, with no exact Desktop CSS claim | PASS | `docs/frontend/CODEX_REFERENCE_2026-10-03.md` cites Codex SHA `604061ce…`, distinguishes Rust TUI/app-server from Desktop React, and documents adaptation limits. |
| `DESIGN-01` System sans/Korean fallbacks, 14px UI, 16px conversation and readable line height | PASS for changed chat shell | `dashboard/DESIGN.md`; token implementation in `dashboard/src/styles/index.css` and workspace CSS; fresh `final-375-chat.jpg` shows legible Korean conversation text. |
| `NAV-01` Named 248px desktop navigation and dismissible compact drawer | PASS in source and 375 evidence | `WorkspaceNavigation.tsx`, `WorkspaceProjects.tsx`, `WorkspaceThreads.tsx`, `Sidebar.tsx`; `captures/final-375-navigation.jpg`; focus/escape tests in `Sidebar.test.tsx`. |
| `CHAT-01` Conversation and composer share a 760px measure and have separate scroll ownership | PASS for chat surface | `workspace-chat.css`, `ChatPage.tsx`, `ChatComposer.tsx`; `captures/final-375-chat.jpg`. |
| `FUNC-01` Model/project/tool/send/stop behavior preserved | PASS within available evidence | Protected store/API hashes match; 101 files/980 tests pass; current chat capture shows selected `qwen3.8:latest (27.3B)` and working controls. Root also recorded a real completed response and restored conversation in `VERIFICATION.json`. |
| `STATE-01` Actual telemetry keeps UNKNOWN/0/stale/offline distinctions | PASS | `SystemTelemetricsBar.tsx`, disclosure tests, `captures/final-375-status.jpg`; no synthetic quota was added. |
| `KEY-01` Cmd/Ctrl+K, IME Enter, Shift+Enter, modal handoff and focus return | PASS in tests and captured states | `ChatPageComposer.test.tsx`, `InspectionFrameHandoff.test.tsx`, `ChatHistory.test.tsx`, `Sidebar.test.tsx`; `final-375-command-palette.jpg` and `final-375-shortcut-guide.jpg`. |
| `SEC-01` PIN/auth, identity, CAS, sanitization and approvals preserved | PASS | Four protected hashes match `SOURCE_MANIFEST.json`; `SECURITY_REVIEW.md` independently passes; hostile markup/approval behavior remains covered in `ChatMessage.test.tsx`. |
| `MODEL-01` Local model preference persists and 125B remains selectable | PASS | Protected `chatStore.ts` hash is bound in the manifest; current selector behavior and separate recovery evidence show 27.3B selected while 125B remains available. |
| `DEPS-01` No new dependency or copied proprietary font | PASS | No package/lock change in scoped patch; system font stack is used; bundle scan in `SECURITY_REVIEW.md` found no copied OpenAI font asset. |
| `BUILD-01` TypeScript/tests/production build | PASS | `TESTS_CURRENT.log`: 101 files/980 tests; `BUILD_CURRENT.log`: successful TypeScript/Vite production build; `VERIFICATION.json`: exit 0 and clean diff check. |
| `BIND-01` Source and production bundle are traceable | PASS for this rejected revision | All 39 live source hashes reproduce; manifest digest is `6b1aacf…`; `BUNDLE_MANIFEST.json` binds it to `index-C1osb2i9.js` and `index-Gvc9kB2l.css`. |
| `UI-RESP-01` No overflow, clipping or obscured body at 375/768/1280 | **FAIL** | Full-page horizontal scroll/right-edge clipping is visible in current 375px Model Hub and Studio captures. |
| `QA-ROUTES-01` Fresh all-route and modal-state matrix at 375/768/1280 | **FAIL** | Round 1 was PIN-blocked; current Settings is loading-only; final 768/1280 matrices and a passing readiness packet were absent at review time. |

## User-outcome review

The redesigned chat workspace is materially calmer and more readable than the retained before captures. The current 375px chat, navigation and inspection views show the intended neutral surfaces, system typography, named controls and conversation-first hierarchy. The implementation also avoids pretending that the public Codex repository contains Desktop React styles.

The application as a whole is not ready for the user-visible outcome because two real product pages still break at the required mobile width. A user reaching Model Hub or Studio must horizontally pan and sees clipped controls. The incomplete route matrix also leaves the desktop/tablet composition and several settled route states unverified. These are direct failures of the written plan, rather than preferences about architecture or pixel fidelity.

## Edge-case and adversarial review

1. **Korean IME confirmation:** PASS — composition Enter and legacy key code 229 do not submit; plain Enter submits once; Shift+Enter retains native newline behavior.
2. **Late project identity hydration:** PASS — an untouched empty chat restores project-scoped history once; a draft, attachment, created session or stream prevents overwrite.
3. **Concurrent/stale conversation revision:** PASS — existing revision/CAS and typed conflict recovery remain in the protected flow and are not bypassed by the redesign.
4. **Compact modal handoff:** PASS — sidebar/history/inspection release focus trapping before command palette, folder browser or shortcut guide takes foreground focus; Escape/focus return have behavioral tests.
5. **Clipboard denial/unavailable API/content change:** PASS — copy success is announced only after resolution; failure/unavailable states remain retryable; stale completions are ignored.
6. **Telemetry zero versus unknown versus stale/offline:** PASS — numeric zero is formatted as data, null remains UNKNOWN and elapsed observations transition to stale without inventing health.
7. **Long mobile navigation/page controls:** FAIL — Model Hub categories and Studio pipeline controls force/clue full-page horizontal overflow at 375px.
8. **Loading-only route capture:** FAIL as evidence — a lazy-route loading frame cannot prove the final Settings page composition, accessibility or overflow behavior.
9. **No unlocked browser surface:** correctly handled — the QA executor did not request/inspect credentials and recorded the PIN lock as a blocker rather than forging coverage.
10. **Historical/stale capture reuse:** correctly rejected — `index-CJUpMcF4.js` captures and `after-375-empty.jpg` were excluded from current approval.

## Direct programming and remove-ai-slops pass

The production diff and tests were checked directly for untyped escapes, suppression directives, broad new exception handling, speculative abstractions, redundant parsing/normalization, deletion-only tests, requested-removal tests, tautologies and implementation-mirroring assertions. The new behavioral tests cover keyboard composition, focus ownership, modal handoff, hydration, clipboard outcomes and telemetry disclosure. They are useful behavior locks rather than count inflation. New component extraction gives named UI responsibilities and does not add a parallel state layer.

Nonblocking maintenance notes:

- `ChatPage.tsx`, `App.tsx`, `ChatMessage.tsx`, `EnvironmentPanel.tsx` and the inherited global stylesheet exceed the remove-ai-slops 250-pure-LOC preference. The change reduces some responsibilities but does not eliminate the inherited size debt. No stated success criterion requires a module split, so this is a NOTE.
- React Doctor reports one `artifact-secret-leak` in ignored, pre-existing `dashboard/reports/mutation/mutation.html`. `SECURITY_REVIEW.md` classifies it as fake/test fixture content absent from Git, the source manifest and shipping bundle. This does not block the scoped UI criteria.
- `CODE_REVIEW.md` explicitly records its own `omo:programming` and `omo:remove-ai-slops` pass and covers the overfit/slop criteria. This agrees with the direct gate pass; it does not replace it.

## Checked artifacts

- `docs/frontend/CODEX_REFERENCE_2026-10-03.md`
- `docs/frontend/EXECUTION_PLAN_2026-10-03.md`
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-03-codex-ui/source-files.txt`
- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/WORKTREE.patch`
- `docs/qa/2026-10-03-codex-ui/BASELINE.json`
- `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/VERIFICATION.json`
- `docs/qa/2026-10-03-codex-ui/TESTS_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/BUILD_CURRENT.log`
- `docs/qa/2026-10-03-codex-ui/TOKEN_CONTRAST.json`
- `docs/qa/2026-10-03-codex-ui/REACT_DOCTOR_CURRENT_RESULT.json`
- `docs/qa/2026-10-03-codex-ui/CODE_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/SECURITY_REVIEW.md`
- `docs/qa/2026-10-03-codex-ui/QA_CAPTURE_READY_ROUND1.md`
- `docs/qa/2026-10-03-codex-ui/QA_REVIEW_ROUND1.md`
- `docs/qa/2026-10-03-codex-ui/CAPTURE_MANIFEST_ROUND1.json`
- Fresh current-build captures inspected directly: `final-375-chat.jpg`, `final-375-navigation.jpg`, `final-375-inspection-env.jpg`, `final-375-models.jpg`, `final-375-studio.jpg`, `final-375-settings.jpg`, and `blocked-pin-lock-1280x720.jpg`.
- Full current contents of the 39 files bound by `SOURCE_MANIFEST.json`, with relevant protected store/API/auth callers checked against their manifest hashes.

## Exact evidence gaps

- No passing current-build `QA_CAPTURE_READY.md` existed for this reviewed source digest.
- No final settled 768×900 or 1280×900 all-route capture matrix existed.
- The 375px Settings capture showed only the loading fallback.
- Current route capture metadata had not yet classified primary document width versus legitimate bounded internal scrolling for every route.
- After root repairs responsive pages, `SOURCE_MANIFEST.json`, `WORKTREE.patch`, `BUNDLE_MANIFEST.json`, tests/build evidence, capture manifest, code/context/QA reviews and this goal review must all be regenerated or re-bound. The present report must not approve later hashes.
