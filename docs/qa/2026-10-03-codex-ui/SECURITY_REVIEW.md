---
title: Final security review — Codex-style SSAK-AI UI round 9
tags: [qa, security, frontend, codex]
date: 2026-10-03
---

# Final security review

## Recommendation

**PASS** for the exact source and shipping bundle below. The final session-selection delta introduces no actionable security finding or blocker. This verdict continues the frozen round-eight security approval and independently verifies the current files, the complete shipping inventory, the actual patch, the supporting storage contract, and the preserved security boundaries.

## Exact binding

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, independently resolved with `git rev-parse HEAD`.
- Dirty source scope: 46 files, independently rehashed with zero mismatches.
- Source manifest SHA-256: `f8d138c7f6f47059dfb98ff672057fc7a0b5df993be18d6de1dd524f257236cd`.
- Bundle manifest SHA-256: `db2ba38c29213b147e851a1e3febfdf10933edce5d4afccb24d90c669f0959de`.
- Shipping directory: `src/antigravity_k/dashboard_dist/`.
- Shipping index SHA-256: `2e31beb80b227bbc72d61ba64a7c1476bd0db6e9f9f76afa6e9db5f03490e373`.
- Entry: `assets/index-CEvvbZ3V.js`, SHA-256 `a908583776aaa9446bc34f5aeb1da5ca36e7e9aef8ab9a5ba47ed3128382e2a4`.
- Styles: `assets/index-C19bV3rn.css`, SHA-256 `4c09077334dbfb6c5416e4b5e55f603b673b216a82b5218a8190590a95a2119f`.
- Final session patch SHA-256: `d6fe8459179e4952b57616baee07fc9b511194a6073c4e511516a9e978b05b3c`.
- Review stamp: `SECURITY-PASS/2026-10-03/HEAD-8cc94cf5/SOURCE-f8d138c7/BUNDLE-a9085837`.

The bundle manifest's source digest equals the independently computed source-manifest digest. All 104 actual shipping files match the manifest inventory and hashes, with no missing, unlisted, mismatched, or symlinked file. The index digest, its complete ten `/assets/` references, and all ten declared entry-asset hashes match the manifest. The index also references the packaged icons and `manifest.json`; those files are covered by the complete inventory. Earlier entry assets and browser captures are not substituted for this binding.

## Final delta and storage contract

The frozen predecessor is `archive-round8/SECURITY_REVIEW.md`, bound to source manifest SHA-256 `131a1c743bd2e79e14acf6578b89afc0c777e0fdb149521c856091d50c072bb9`. Comparing the two source inventories identifies exactly two changed hashes, with no added or removed entry:

| Path | Final change | Current SHA-256 |
| --- | --- | --- |
| `dashboard/src/components/Layout/Sidebar.tsx` | Call existing `saveToStorage()` after `switchSession(sessionId)` and before navigation to `/chat`. | `e76d8fa6367457507139d09514e33cbb3ba8870b6f73f6f47e6c716b95a2d9dc` |
| `dashboard/src/components/Layout/__tests__/SidebarHistory.test.tsx` | Mount the actual ChatPage after one click from Settings and assert that the older selected conversation, revision, model preference, and displayed messages survive restoration. | `778fdca669efd8023335ea6f3ff1f5026ad9d1e5579077118d226a34541ff376` |

`FINAL_SESSION_DELTA.patch` was read in full. Reversing it against temporary copies of both current files exited 0 and reproduced both frozen round-eight hashes exactly. The other 44 manifested paths retain their frozen hashes. There is no store, API client, authentication, sanitizer, approval, or dependency path in this final delta.

The supporting flow was inspected in current source:

- `switchSession` selects only a matching session already present in the store's session list and synchronously updates the active ID, session, messages, and conversation revision.
- The unchanged `saveToStorage` reads current store state with `get()` after that switch. It writes the existing `{ sessions, activeSessionId }` payload under `antigravity_chat_` plus the existing key precedence: active project ID, active project path, persisted active project, then `/`.
- The unchanged `loadFromStorage` uses that same key contract. With an active project ID, it reads that project's ID key; the final change adds no legacy key lookup, key enumeration, cache adoption, migration, or alternate project source.
- The unchanged ChatPage mount effect calls `loadFromStorage` before synchronizing the selected conversation with the existing server API. Persisting the new active ID before navigation prevents the old cached active ID from replacing the user's selection on mount.
- Selected-model preference remains managed separately. The added persistence call writes no credential, PIN, access header, selected-model field, or new payload field. It performs no transport request and changes no authentication or approval decision.

The regression uses the actual Sidebar and ChatPage with six cached conversations and an older selected conversation at revision 37. It checks the rendered message region and selected navigation state as well as restored state. The recorded red run fails because ChatPage restores the previous cached conversation; the recorded green run passes. Fixture networking is isolated to the test, and global stubs are removed during cleanup.

## Independent checks

| Check | Result | Evidence |
| --- | --- | --- |
| Current source | PASS | 46/46 hashes match `SOURCE_MANIFEST.json`. |
| Exact final delta | PASS | Two changed entries only; reverse patch reproduces both predecessor hashes. |
| Shipping inventory | PASS | 104/104 hashes and inventory entries match `BUNDLE_MANIFEST.json`. |
| Current asset binding | PASS | Source digest, index digest, ten asset references, and ten entry hashes match. |
| Protected baseline | PASS | All four protected hashes equal manifest before/after values and the recorded task baseline. |
| Frozen baseline | PASS | `BASELINE.json` is byte-identical to its round-eight archive. |
| Authentication/transport | PASS | API client, PIN credential utility, PIN modal, and WebSocket ticket utility retain baseline hashes. |
| Sanitization | PASS | `formatContent.ts` and `mermaidRuntime.ts` retain baseline hashes; ChatMessage retains its frozen round-eight hash. |
| Task/browser approvals | PASS | All seven approval production paths listed below retain baseline hashes. |
| Modal primitive | PASS | `useModalDialog.ts` retains its baseline hash. |
| Security bundle chunks | PASS | API client, DOMPurify, markdown core/highlight, and WebSocket ticket filenames and hashes equal the frozen bundle. |
| Named credential patterns | PASS | Bounded scan of all 100 shipping JS/CSS/HTML/JSON files returns zero credential-format matches with token boundaries. |
| Frontend test record | PASS | `TESTS_CURRENT.log` and `VERIFICATION.json` record 103 files and 1001 tests passing, exit 0. |
| Build/typecheck record | PASS | Current build names CEvvbZ3V/C19bV3rn and completes; current typecheck log contains no compiler diagnostic. `VERIFICATION.json` records exit 0 for both. These commands were not rerun in this lane. |

### Protected hashes

| Path | SHA-256 |
| --- | --- |
| `dashboard/src/stores/chatStore.ts` | `9198078dea08610ebd248020c602a4c5f34ddbbb02ce504364616531d31ad5e8` |
| `dashboard/src/stores/projectStore.ts` | `b5e299c80e07f20f53b186c282cda882c39546bda6663d737ca23a55cd0e5db2` |
| `dashboard/src/api/client.ts` | `76e331749eae7bf6571ee35462c81e9b9f77b5e0c306921d5b547fb8b9438c6e` |
| `dashboard/src/utils/accessPinCredential.ts` | `9ff139d1bcd47bbffec45412a5316667b948abed0a7ba544d81da3d886640efd` |

The chat store already differed from Git HEAD at the recorded task baseline. Independent comparison confirms it still differs from HEAD; its preservation means equality with that task baseline, not equality with HEAD.

Additional current-versus-baseline comparisons cover `PinModal.tsx`, `wsTicket.ts`, `formatContent.ts`, `mermaidRuntime.ts`, `useModalDialog.ts`, and these seven approval paths:

- `dashboard/src/features/task-execution/ApprovalQueue.tsx`
- `dashboard/src/features/task-execution/useApprovalQueue.ts`
- `dashboard/src/features/task-execution/approvalApi.ts`
- `dashboard/src/features/browser-approval/browserApprovalApi.ts`
- `dashboard/src/features/browser-approval/useBrowserApprovals.ts`
- `dashboard/src/features/browser-approval/BrowserApprovalSection.tsx`
- `dashboard/src/features/browser-approval/BrowserApprovalPanel.tsx`

These exact comparisons preserve the security boundaries covered by the predecessor review. No dependency change is present in the final two-file delta; this lane does not claim a new dependency vulnerability audit. Other generated chunk filenames changed during rebuilding, so no claim that every generated JavaScript file is byte-identical to the predecessor is made.

## Credential scan and preserved advisory

The shipping scan covered 100 text assets totaling 19,557,137 bytes, with an 8 MiB per-file read bound. The largest file was 7,043,070 bytes, so no text asset exceeded the bound or was skipped. Output contained counts only, never a matched credential value.

| Named pattern | Matches |
| --- | ---: |
| AWS access-key IDs | 0 |
| GitHub classic tokens | 0 |
| GitHub fine-grained tokens | 0 |
| OpenAI-shaped tokens with lexical boundaries | 0 |
| JWT-shaped values | 0 |
| Private-key headers | 0 |

An initial boundary-free `sk-` substring matcher returned 14 fragments embedded in `task-` identifiers. All 14 were independently classified by their identifier prefix, without printing match values; none remained after applying lexical token boundaries. The table records the credential-format scan, not those identifier suffixes. Named-format checks do not prove the absence of every possible secret representation.

React Doctor remains a **recorded exit 1**, with one `artifact-secret-leak` error at `dashboard/reports/mutation/mutation.html:334:94421`, zero warnings, and one affected file. `REACT_DOCTOR_CURRENT_RESULT.json` is byte-identical to the frozen round-eight record. `git check-ignore` confirms the fixture is ignored; independent inventory checks confirm it is absent from both the 46-file source scope and all 104 shipping files. Its existing classification as a nonshipping fixture is preserved. This lane did not read fixture contents or any alleged credential value.

This preserved advisory is not a finding introduced by the session delta. React Doctor is not globally clean, and no exit-0 or zero-diagnostic claim is made. It was not rerun for this revision.

## Scoped limits

`SECURITY.md` was read. The read-only security capability preflight exited 0 with status `ready`. This is the delegated, bounded review of the final delta and release evidence; it does not claim a new durable Codex Security scan or whole-repository/backend audit.

Code discovery followed the codebase-memory preference: `list_projects`, `search_graph`, and `get_code_snippet` resolved Sidebar and the three chat-store session/storage functions. A call trace returned no callee edges, and a later graph search returned `project not found or not indexed`; precise reads and literal searches of the already-resolved files completed the review. No reindexing was attempted.

- Fresh manual capture QA was still underway in a separate lane. This review claims no manual browser scenario completion or 81-capture coverage.
- No browser session, backend suite, frontend test command, build command, typecheck command, or React Doctor command was run in this lane.
- Existing Skills/Metrics 401 behavior supplies no backend authorization-success or bypass evidence.
- No private environment/auth file, PIN, browser storage contents, credential value, or mutation fixture contents were inspected.
- No production source was edited, no commit was created, and no children were spawned. Only `SECURITY_REVIEW.md` was written in the workspace. Reverse-patch copies were confined to an automatically removed temporary directory.

## Findings and blockers

Findings: `[]`

Blockers: `[]`
