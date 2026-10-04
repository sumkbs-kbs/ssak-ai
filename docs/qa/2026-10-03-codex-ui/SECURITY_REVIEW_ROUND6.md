---
title: Final security review — Codex-style SSAK-AI UI round 6
tags: [qa, security, frontend, codex]
date: 2026-10-03
---

# Final security review

## Recommendation

**PASS** for the exact source and shipping bundle below. No actionable security finding or blocker was identified in the final shortcut-guide modal delta.

## Exact binding

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Dirty source scope: 45 files, independently rehashed with zero mismatches
- Source manifest SHA-256: `a1552cf1f91459253bfb96910eeb7fcd0d29e5e8cb0e836cbcfc93267014d3b8`
- Bundle manifest SHA-256: `5be0fded71aeea0d94de81337b5f6e4a03e59acfc0e10a277fc871e54f361acf`
- Shipping directory: `src/antigravity_k/dashboard_dist/`
- Shipping index SHA-256: `853bc09c1cf515bd58b2e152c04af35a5660a37a762989a6af6843391864f6f8`
- Entry: `assets/index-DNX9exh1.js`, SHA-256 `0e7120f581ecf35751f5cdc32552e083b95356747c97d7c707e2879a1ccfd836`
- Styles: `assets/index-BLgp1deP.css`, SHA-256 `78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b`
- Review stamp: `SECURITY-PASS/2026-10-03/HEAD-8cc94cf5/SOURCE-a1552cf1/BUNDLE-0e7120f5`

The bundle manifest names this exact source-manifest digest. All 104 actual shipping files match its relative-path inventory, with no unlisted or absent file. The actual shipping index references DNX9exh1/BLgp1deP. This lane independently verifies source and packaged artifacts; it does not use an older browser entry asset as evidence for this bundle.

## Original intent and final delta

The requested Codex-style font, layout, and readability improvements must retain existing chat, project, model, API, PIN/authentication, approval, and sanitization contracts. The final correction gives the shortcut guide the existing shared modal behavior: initial focus on its close button, contained Tab/Shift+Tab navigation, background inertness, and restoration of the opening control after dismissal.

Comparing `SOURCE_MANIFEST_ROUND5.json` with the current manifest identifies exactly four changed inventory entries:

| Path | Change |
| --- | --- |
| `dashboard/src/components/UI/KeyboardShortcutsModal.tsx` | Newly included in the dirty-source inventory; current SHA-256 `f1bdbe96c4088d1ffb3cd176b0a1bb2df69820a7dd8effa43990b752de5c70a8`. |
| `dashboard/src/components/UI/KeyboardShortcutsModal.test.tsx` | New focused test file, SHA-256 `de0cd29db39e7de347a73a387cb28fce9beb27f58925738da4dd8aafb6eb0383`. |
| `dashboard/src/components/Chat/__tests__/ChatHistory.test.tsx` | Guide handoff assertions updated; SHA-256 `bf7b51c48aad7a1c03ed24b8f03cc91f2f7565a6fcd46653093080f081442fce`. |
| `dashboard/src/components/Chat/__tests__/InspectionFrameHandoff.test.tsx` | Guide handoff assertions updated; SHA-256 `28e76f6b1c25200731a9b8f7f26a053cd23c6cde07ec07c5fe41d60e813c47ba`. |

The modal existed at Git HEAD. Its full Git diff consists of importing `useModalDialog`, replacing the unused overlay ref with dialog/close-button refs, invoking the hook while visible, attaching those refs, and adding `aria-modal="true"` plus `tabIndex={-1}`. Existing Escape, backdrop, close-button, and React text-rendering behavior is retained.

The shared hook itself matches Git HEAD. It contains Tab within the referenced dialog, marks background siblings inert, removes its listener/timer on cleanup, restores prior inert state, and releases background inertness before restoring focus. No new handler constructs requests, credentials, URLs, raw HTML, authorization decisions, or persistent storage. No dependency or sanitizer setting changes in this delta.

The seven focused guide tests cover initial close-button focus, modal semantics, forward and reverse Tab containment, and focus restoration after Escape, close-button, and backdrop dismissal. The two existing handoff files use the actual guide and verify contained Tab behavior, that the guide is outside inert ancestors, and release/restoration after dismissal. The recorded red full-suite run exposes the prior incompatible Tab expectations; the current full-suite log records 102/102 files and 987/987 tests passing.

## Independent security and contract checks

| Check | Result | Evidence |
| --- | --- | --- |
| Exact source | PASS | HEAD and assigned manifest digest match; all 45 current source file hashes match. |
| Final production delta | PASS | The only newly changed production source since round five is the shortcut-guide modal; remaining manifest differences are its focused tests and two handoff test files. |
| Core task-baseline preservation | PASS | All four protected paths match `BASELINE.json` and manifest before/after hashes. |
| Authentication and transport | PASS | API client, PIN credential utility, PIN modal, and WebSocket ticket utility match Git HEAD by hash. Credential values were not inspected or returned. |
| Sanitization | PASS | `formatContent.ts` and `mermaidRuntime.ts` match Git HEAD; `ChatMessage.tsx` matches the approved round-five source. |
| Permissions and approvals | PASS | All seven task/browser approval production paths listed below match Git HEAD by hash. |
| Modal primitive | PASS | `useModalDialog.ts` matches Git HEAD; existing shared focus/inert cleanup is reused. |
| Other production seams | PASS | `App.tsx`, `main.tsx`, `ChatComposer.tsx`, `ChatPage.tsx`, `InspectionFrame.tsx`, and `SettingsPage.tsx` match round five. |
| Dependencies | PASS | `dashboard/package.json` and `dashboard/pnpm-lock.yaml` match Git HEAD. |
| Shipping bundle | PASS | All 104 actual shipping hashes match `BUNDLE_MANIFEST.json`; no unlisted or absent shipping file. |
| Security bundle chunks | PASS | API client, DOMPurify, markdown core/highlight, and WebSocket ticket chunk filenames and hashes match round five. |
| Shipping credential-pattern scan | PASS | All 100 shipping JS/CSS/HTML/JSON files have zero named AWS access-key, GitHub-token, OpenAI-token, JWT-shaped, or private-key-header matches; only counts were returned. |
| Build and test records | PASS | `BUILD_CURRENT.log` records successful production build with DNX9exh1/BLgp1deP; `TESTS_CURRENT.log` records 102 files and 987 tests passing. Logs were inspected, not rerun in this lane. |

### Preserved core hashes

| Path | SHA-256 |
| --- | --- |
| `dashboard/src/stores/chatStore.ts` | `9198078dea08610ebd248020c602a4c5f34ddbbb02ce504364616531d31ad5e8` |
| `dashboard/src/stores/projectStore.ts` | `b5e299c80e07f20f53b186c282cda882c39546bda6663d737ca23a55cd0e5db2` |
| `dashboard/src/api/client.ts` | `76e331749eae7bf6571ee35462c81e9b9f77b5e0c306921d5b547fb8b9438c6e` |
| `dashboard/src/utils/accessPinCredential.ts` | `9ff139d1bcd47bbffec45412a5316667b948abed0a7ba544d81da3d886640efd` |

`chatStore.ts` already differed from Git HEAD at the task baseline. Its preservation is equality with that recorded baseline, not a claim of equality with HEAD. The other three paths also independently match Git HEAD.

### Additional preserved security production paths

Hash-only comparisons against Git HEAD confirm:

- `dashboard/src/components/UI/PinModal.tsx`
- `dashboard/src/utils/wsTicket.ts`
- `dashboard/src/utils/formatContent.ts`
- `dashboard/src/utils/mermaidRuntime.ts`
- `dashboard/src/features/task-execution/ApprovalQueue.tsx`
- `dashboard/src/features/task-execution/useApprovalQueue.ts`
- `dashboard/src/features/task-execution/approvalApi.ts`
- `dashboard/src/features/browser-approval/browserApprovalApi.ts`
- `dashboard/src/features/browser-approval/useBrowserApprovals.ts`
- `dashboard/src/features/browser-approval/BrowserApprovalSection.tsx`
- `dashboard/src/features/browser-approval/BrowserApprovalPanel.tsx`

Discovery first used graph project `Users-mr.k-program-coding-ssak_comp-Ssak-Ai`. Graph search/snippets found the current modal and shared hook, and a call trace found the existing history/sidebar/inspection/palette consumers. The graph transport closed on helper snippet reads; the remaining helper inspection used the already-resolved `useModalDialog.ts` path. This fallback did not change scope or production source.

## React Doctor advisory

The recorded current React Doctor status remains **exit 1**, with one `artifact-secret-leak` diagnostic at `dashboard/reports/mutation/mutation.html:334:94421`. The original and current result JSON have the same diagnostic ID. Independent Git metadata confirms the fixture is ignored and untracked; it is absent from both the 45-file source manifest and the verified 104-file shipping bundle.

This remains an advisory scoped to that pre-existing nonshipping mutation-test fixture. React Doctor is not globally clean, and its exit status is not claimed to be zero. The fixture contents and alleged credential value were not read. The current shipping text assets separately have zero matches for the named credential patterns.

## Checked artifacts and limits

Artifacts checked: `BASELINE.json`; current and round-five source/bundle manifests; `SECURITY_REVIEW_ROUND5.md`; `BUILD_CURRENT.log`, `TYPECHECK_CURRENT.log`, `TESTS_CURRENT.log`, and `TESTS_GUIDE_HANDOFF_RED.log`; original/current React Doctor diagnostic metadata; all manifested source hashes; protected seams by hash; and all packaged shipping files. Artifact names are relative to `docs/qa/2026-10-03-codex-ui/` unless a production path is explicit.

- This is a final modal-delta and artifact verification against the previous approved security review, not a new whole-repository security audit.
- Credential-pattern checks cover the named formats and do not prove absence of every possible secret format.
- This lane does not assert browser recapture or user-flow completion. The verification packet and browser captures are owned by separate lanes; no stale browser asset is used to support this PASS.
- Existing Skills/Metrics 401 behavior is outside any claim of backend authorization success or bypass.
- No browser or backend suite was run in this lane, and build/frontend tests were not rerun here.
- No private auth/environment file, credential value, PIN, browser storage, or mutation fixture content was read. No production source was edited; only this report was written.

## Findings and blockers

Findings: `[]`

Blockers: `[]`
