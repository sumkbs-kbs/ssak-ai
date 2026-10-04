---
title: Codex UI context-mining review
tags: [frontend, qa, codex, context-review]
date: 2026-10-03
---

# Recommendation

**FAIL** — confidence **high (0.94)**.

The implementation direction matches the user's current request, and the source-bound automated evidence is strong. The requested final user-visible outcome is not yet demonstrated because the acceptance checklist explicitly requires browser coverage at 375/768/1280, every route, keyboard/panel behavior, latest captures, and the production bundle. The current browser evidence contains only three 375px chat-root observations; one records an overflowing model popover. There is no route-by-route browser matrix and no 768px or 1280px after-state capture.

# Original intent

The user reported a disordered frontend with poor readability and asked the team to study `github.com/openai/codex`, absorb useful patterns, and implement them. The latest clarification prioritizes the **current Codex UI/UX, especially fonts and screen layout**, using the current dirty folder as the baseline. Existing core behavior, PIN authentication, server conversation revision/CAS, model preference, project identity, chat behavior, and real telemetry semantics must remain intact.

# Desired outcome

- A calm, readable, current Codex-inspired SSAK-AI workspace using a system sans/Korean fallback without copying or claiming the proprietary OpenAI font.
- Labelled project/thread navigation, conversation-first hierarchy, readable 16px/1.7 prose, a 760px reading/composer measure, and a composer fixed outside the transcript scroll region.
- Real model/project/tool/send-stop behavior, real telemetry distinctions, safe initial history hydration, and preserved authentication/API/store contracts.
- Responsive and keyboard-safe behavior at 375/768/1280, including navigation/history/inspection modals, focus trapping/return, Escape, Cmd/Ctrl+K, Shift+Enter, and Korean IME Enter.
- Evidence tied to the current source and production bundle, covering every route and the latest browser captures.

# User outcome review

The code and design artifacts reflect the intended visual and interaction direction. `dashboard/DESIGN.md` explicitly distinguishes the public Codex Rust TUI/app-server from the private Desktop React implementation, uses system font fallbacks, and avoids unsupported exact-font or pixel-perfect claims. The implementation replaces the old fake quota/PR/scheduling presentation with genuine destinations and state, splits navigation/projects/threads into labelled components, keeps chat as the primary canvas, and adds explicit composer, model selector, copy, inspection, and modal primitives.

Source-bound tests cover the main contract risks: 101 test files and 980 tests pass in `TESTS_CURRENT.log`; the current `BUILD_CURRENT.log` records successful `tsc -b` and Vite production build; tests exercise project-ID hydration without overwriting an early conversation or draft, IME/Shift+Enter/plain Enter, compact navigation focus and dismissal, history/inspection focus handoff, telemetry zero/stale/offline distinctions, copy failures, and protected model preference behavior.

That evidence does not yet show the complete user outcome. `BROWSER_OBSERVATIONS.json` has only `after-375-chat`, `after-375-models`, and `after-375-generation`, all at `/` and 375×812. The model observation reports `.model-selection-popover` in `overflowElements`. No after-state observation or capture proves 768px, 1280px, labelled navigation drawer behavior, inspection/history modal behavior, all declared routes, or the latest production bundle in the running app. The execution plan itself therefore keeps step 4 `in_progress` and step 5 `pending`.

# Blockers / missed requirements

## B1 — responsive browser acceptance is incomplete

- **violatedCriterion:** `UI-QA-375-768-1280` — execution-plan checklist: “375/768/1280 가로 넘침·한글 잘림·본문 가림 없음”; `dashboard/DESIGN.md` section 4 names all three required widths.
- **observation:** Browser evidence covers only 375px. At that width the model-selection observation explicitly records `.model-selection-popover` as an overflow element. There is no browser evidence for 768px or 1280px.
- **evidencePointer:** `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`; `docs/qa/2026-10-03-codex-ui/captures/` (only 375px after-state files and one `preview-1280-empty.jpg`, with no 768px after-state or browser observation).
- **required closure:** Record browser checks at 375, 768, and 1280 against the source-bound production bundle, including model popover, long Korean prose/IDs, transcript/composer, navigation, history, and inspection; fix or explicitly disprove the recorded model-popover overflow.

## B2 — all-route and interaction browser matrix is missing

- **violatedCriterion:** `UI-QA-ROUTES-KEYBOARD` — execution-plan checklist: “전체 라우트 목록과 최신 캡처 연결, 독립 기능/시각 검토” and “Cmd/Ctrl+K, 한글 IME Enter, Shift+Enter, 패널과 이력 동작.”
- **observation:** The app declares `/`, `/chat`, `/studio`, `/models`, `/start`, `/wiki`, `/agent`, `/settings`, `/skills`, `/data-extraction`, `/git`, `/history`, `/plugins/*`, `/plugins`, and `/mutation`, but the browser observation file records only `/`. Component tests are useful but do not satisfy the explicit real-browser route/capture criterion.
- **evidencePointer:** `dashboard/src/App.tsx:359`; `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`; absence of a route/manual-QA matrix in `docs/qa/2026-10-03-codex-ui/`.
- **required closure:** Add a source-bound manual QA matrix for every route and the named keyboard/focus scenarios, with pass/fail and latest capture/evidence pointers.

## B3 — running production bundle verification is not evidenced

- **violatedCriterion:** `UI-QA-PRODUCTION-BUNDLE` — execution-plan checklist: “실행 중 production bundle 확인.”
- **observation:** The build and bundle manifest are internally source-bound, but the browser observations loaded `/assets/index-CJUpMcF4.js`, while the current `dashboard_dist/index.html` and `BUNDLE_MANIFEST.json` bind `/assets/index-C1osb2i9.js` and `/assets/index-Gvc9kB2l.css`. The browser session therefore does not prove the current production bundle was the artifact under test.
- **evidencePointer:** `docs/qa/2026-10-03-codex-ui/BROWSER_OBSERVATIONS.json`; `docs/qa/2026-10-03-codex-ui/BUNDLE_MANIFEST.json`; `src/antigravity_k/dashboard_dist/index.html`.
- **required closure:** Re-run browser QA after serving the current bundle and record the loaded JS/CSS asset hashes or paths matching `BUNDLE_MANIFEST.json`.

# Verified evidence

- `HEAD` reproduced as `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- `SOURCE_MANIFEST.json` SHA-256 reproduced as `6b1aacf46676070701e3367fde89ecdecc4cd379ca57ef96d7f0c31513bb3006`.
- Every file hash listed in `SOURCE_MANIFEST.json` matched the current file bytes.
- Protected hashes matched for `dashboard/src/stores/chatStore.ts`, `dashboard/src/stores/projectStore.ts`, `dashboard/src/api/client.ts`, and `dashboard/src/utils/accessPinCredential.ts` relative to the declared UI baseline.
- `TESTS_CURRENT.log`: 101 files passed, 980 tests passed.
- `BUILD_CURRENT.log`: `tsc -b && vite build` completed successfully; large-chunk warnings remain non-blocking for the stated criteria.
- `BUNDLE_MANIFEST.json` binds the current source-manifest digest and current `dashboard_dist/index.html` SHA-256 `69ba1da3511af14ee6e316fbd1e2169f3e257334e186ade0089fedf01c215a30`.
- `TOKEN_CONTRAST.json` shows canonical enabled text/focus token combinations meeting its stated AA scope; it correctly does not claim a full accessibility audit.
- History/blame confirms the old UI came from commits including `07b51a08` (three-zone workspace) and `cb9f9df5` (task UI/command palette). The current uncommitted `DESIGN.md` intentionally replaces earlier fake/pixel-perfect Codex claims with an adaptive, evidence-bounded design.
- Command-palette integration remains present through `dashboard/src/components/UI/CommandPalette.tsx`, `dashboard/src/features/command-palette/commandRegistry.ts`, the global shortcut handling in `dashboard/src/App.tsx`, and modal-handoff tests in Sidebar and InspectionFrame.

# Direct programming and remove-ai-slops pass

No slop finding independently blocks a stated acceptance criterion.

Notes:

- The new focused tests assert observable behavior for hydration, composition keys, modal focus, copy success/failure, telemetry disclosure, and navigation. They are not deletion-only tests and do not merely grep source or assert that requested old prose disappeared.
- A small number of existing tests still inspect CSS classes or literal display prose. These mostly predate or support rendering details and do not create a demonstrated failure of the user criteria. They should not be counted as proof of visual acceptance.
- `ChatPage.tsx` remains 1,318 lines, `EnvironmentPanel.tsx` 579 lines, and `ChatMessage.tsx` 427 lines. The current change does extract several coherent UI pieces, but these oversized modules remain maintenance debt. This is a NOTE because the user asked for the UI outcome, not a full module-size refactor.
- Existing broad/swallowed async catches remain in the chat and environment code. The reviewed change did not establish a user-visible regression from them, so they are maintenance notes rather than blockers here.
- The tests do not mirror a parser/normalizer introduced solely for testing, and there is no unnecessary new production abstraction evident in the scoped UI diff.

# Historical decisions and references

- `604061ce51d194a3aa6aad3b3170240d096e1725` is the verified public `openai/codex` reference point. It supports TUI/app-server patterns only; it is not evidence for Desktop React CSS or exact font metrics.
- The installed ChatGPT/OpenAI application inspection established the existence of shared OpenAI Sans assets and system fallbacks. It did not establish Desktop-wide CSS tokens. The implementation correctly uses a neutral system-sans/Korean stack and makes no exact-font claim.
- The prior UI history contained fabricated or misleading quota, pull-request, and scheduling labels. The current navigation uses genuine SSAK-AI routes and keeps status data server-backed.
- The initial project-ID/path race is handled in `ChatPage` only and tested to restore untouched history once without replacing an early session or draft.
- The approved Qwen 3.8 latest 27.3B reply and preserved explicit 125B option are outside this frontend context pass and were not re-tested.

# Sources searched

- `docs/frontend/EXECUTION_PLAN_2026-10-03.md`
- `docs/frontend/CODEX_REFERENCE_2026-10-03.md`
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-03-codex-ui/SOURCE_MANIFEST.json`
- `docs/qa/2026-10-03-codex-ui/source-files.txt`
- `docs/qa/2026-10-03-codex-ui/WORKTREE.patch`
- `docs/qa/2026-10-03-codex-ui/{BASELINE,BROWSER_OBSERVATIONS,BUNDLE_MANIFEST,REACT_DOCTOR_RESULT,TOKEN_CONTRAST}.json`
- `docs/qa/2026-10-03-codex-ui/{TESTS_CURRENT,BUILD_CURRENT}.log`
- Current scoped source, styles, component tests, E2E specs, route declarations, command registry/palette, and production `dashboard_dist/index.html`.
- Git `log`, `show`, and `blame` for `dashboard/DESIGN.md`, Sidebar, ChatPage, command palette, and dashboard history.

# Sources skipped / unavailable

- **Codebase knowledge graph:** unavailable in this agent's tool surface/transport; repository search was limited to the exact scoped files and literal cross-references, consistent with the documented fallback.
- **Private GitHub issues/PRs:** unavailable because prior `gh api` returned 401 invalid credentials. No credential was exposed and no new login was requested. Public official references already captured in `CODEX_REFERENCE_2026-10-03.md` were used.
- **Slack and Notion:** connectors are not installed; skipped, with no invented search results and no external messages.
- **Old agent threads/tools:** skipped because the user did not request thread review.
- **Interactive browser driving:** skipped because the QA agent exclusively owns IAB/browser execution for this effort.

# Exact evidence gaps

1. No 768px after-state browser observation or capture.
2. No source-bound 1280px after-state browser observation; `preview-1280-empty.jpg` alone has no scenario metadata or route matrix.
3. No browser proof for the compact navigation drawer, history drawer, inspection modal, focus return/trap, Cmd/Ctrl+K, IME Enter, or Shift+Enter against the current production bundle.
4. No browser observation for routes other than `/`.
5. The only model-popover browser observation records an overflow element.
6. Browser-loaded asset `index-CJUpMcF4.js` does not match the current bundle-manifest entry `index-C1osb2i9.js`.
7. No standalone code-review report or manual QA matrix exists in the QA directory at review time; direct review and automated logs support implementation quality, but they do not replace criteria B1–B3.
