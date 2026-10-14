# Dashboard release surface diagnosis

Status: implementation in progress; no post-change build or browser success claimed.

The run directory name is an identifier, not a claimed wall-clock start timestamp. The first inspected clock during this work was 2026-10-14T23:00:41Z.

The parent baseline recorded accessibility 33 passed / 2 failed, browser witnesses 18 passed / 12 failed, and ambient 11 passed / 5 failed. Raw parent logs are preserved under `parent-logs/`. The witness and accessibility failure attachments were already replaced by the parent's later ambient invocation before this task copied `dashboard/test-results`; those missing attachments are not claimed as preserved. Available ambient attachments and the original generated bundle were captured with hashes in `preimage-manifest.json`.

## Findings

1. Agent status uses literal legacy colors. The normal idle label was an axe contrast failure at both viewport sizes. Metric labels were overridden by a later generic `.metric-label` rule. ROOT already contains an uncommitted repair at the same two locations. This candidate uses the existing semantic text/status tokens for those repairs; it does not overwrite ROOT's working files.
2. CR-07 requires the former `Codex Desktop Navigation` accessible label. The current source and committed bundle expose `SSAK-AI 탐색`. Chunk failure classification, recovery buttons, preserved shell, retry, reload, and stored-data invariants remain required.
3. CR-08 checks inert directly on the `aside`, while the current sidebar is wrapped inside the inert background layer. An inert ancestor has the same browser interaction semantics. The corrected check must still prove sidebar and content are inert, focus is trapped/restored, and inert is removed after closing.
4. CR-09 and all five ambient file-explorer cases stop in the shared `goToChat` helper, which searches old `AI 채팅|Chat` text. The current navigation has a named `대화` link. Use that actual navigation action and wait for the conversation textbox, preserving the downstream Markdown, sanitization, editor, and panel assertions.
5. CR-10 reads `innerText` inside a closed native disclosure. A user must open `서버 연결 및 시스템 지표` before reading the values. Existing API equality, UNKNOWN, health, and restart assertions remain unchanged.
6. The palette contrast failure needs exact-node inspection in a real browser before any additional CSS repair.

The bundle is in `src/antigravity_k/dashboard_dist`, as specified by Vite. Its published commit is newer than the latest dashboard source commit. The current stale-selector evidence does not establish that the bundle is stale.

Graph discovery returned `project not found or not indexed`. The parent already attempted indexing and recorded a timeout; this task used exact known paths and textual fallback. The frontend design/perfection, programming TypeScript/Python, modern-web color, browser owned-engine, and visual-QA instructions were read. This is an existing-design repair with an existing `dashboard/DESIGN.md` and semantic token set; no new visual system or dependencies are introduced. The modern-web color guide calls for normal-text contrast of at least 4.5:1 and existing tokens before new colors.

The Node REPL cannot initialize `loadOmowright` because `process` is absent in that runtime. The same documented guarded loader initializes successfully under the installed Bun runtime. Browser QA uses an owned profile, not the user's browser profile. The owned runtime reserves a non-listening model endpoint and uses isolated application state.

Implementation is limited to six approved source/test paths and the standard generated bundle/provenance. The parent requested a commit window; candidate builds and tests are paused until the parent resumes them. No successful tests have been repeated.
