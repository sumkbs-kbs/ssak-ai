---
title: Final security review — Codex-style SSAK-AI UI round 5
tags: [qa, security, frontend, codex]
date: 2026-10-03
---

# Final security review

## Recommendation

**PASS** for the exact source and shipping bundle below. No actionable security finding or blocker was identified in the final CSS delta.

## Exact binding

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- Dirty source scope: 43 files, independently rehashed with zero mismatches
- Source manifest SHA-256: `7adf26f802aa3a1092a96f606951bbdc9606785eb9c20f83b22df0c35b93c236`
- Bundle manifest SHA-256: `65c37d975b7cf2dc37e1104cf240d15abf58c7c46e57886fbdab8a2f5a825dd1`
- Shipping directory: `src/antigravity_k/dashboard_dist/`
- Shipping index SHA-256: `fd5b1ec4cd021ba9bb52ad5d018e5b35bafd04312e346cbda4f3b40f49f73a08`
- Entry: `assets/index-D6IQTpgA.js`, SHA-256 `8489943e7e1646edc48391f7f43af547a7a5a4026cab3bc9abf5e2a9330b1f87`
- Styles: `assets/index-BLgp1deP.css`, SHA-256 `78707fc2efc6f8ea16a3e575a11a4156098251598ef3f346ec8ebbf4749db40b`
- Review stamp: `SECURITY-PASS/2026-10-03/HEAD-8cc94cf5/SOURCE-7adf26f8/BUNDLE-8489943e`

This review independently checks packaged files. It does not borrow the round-four entry asset or source binding.

## Original intent and desired outcome

Deliver the requested Codex-style font, layout, and readability improvements while retaining existing chat, project, model, API, PIN/authentication, approval, and sanitization contracts. The final correction lets workspace popovers escape an unintended content stacking context and suppresses entry animations that create transient layout or stacking behavior.

## Final delta and user outcome review

PASS within this security scope. Comparing `SOURCE_MANIFEST_ROUND4.json` with the current source manifest identifies exactly one changed source file: `dashboard/src/styles/codex-workspace.css`. Its digest changes from `2d4f4fc731bfcfc4ccd0e2d0dbf673c900dfc4e548d54696967704277e4d5aa0` to `fd2658d9f01c55416f9e74f2e6103cc258cc6109215f0bafa051708b05dad2f3`.

I reconstructed the previous CSS in memory by removing the declarations below and matched the previous recorded digest exactly. This verifies the entire delta, rather than relying on its description:

```css
.workspace-shell .main-content { z-index: auto; }
/* Added to the existing .app-shell .page-container rule: */
animation: none;

.command-palette, .shortcuts-modal,
.app-shell .settings-section, .app-shell .dex-card-enter {
  animation: none;
}
```

The delta has no handler, request, markup insertion, URL construction, credential flow, authorization decision, persistent storage, sanitizer configuration, or dependency change. Existing pointer-event and approval behavior is unchanged. The five existing local stylesheet imports are preserved; there is no new import, `url(...)`, `@font-face`, or CSS expression. No new source abstraction, defensive branch, logging, or implementation-mirroring test is introduced.

## Security and contract checks

| Check | Result | Independent evidence |
| --- | --- | --- |
| Exact source | PASS | Current HEAD and manifest digest match the assigned revision; all 43 file hashes match. |
| Final delta scope | PASS | Only `codex-workspace.css` differs from round four; reconstructed old CSS matches its recorded hash. |
| Core task-baseline preservation | PASS | All four protected paths match `BASELINE.json` and both manifest before/after values. |
| Authentication and transport | PASS | PIN credential utility, PIN modal, API client, and WebSocket ticket utility match Git HEAD by hash. Contents or credential values were not returned. |
| Sanitizers | PASS | `formatContent.ts` and `mermaidRuntime.ts` match Git HEAD by hash; `ChatMessage.tsx` matches the previous approved source manifest. |
| Permissions and approvals | PASS | All seven task/browser approval production files listed below match Git HEAD by hash. |
| Other production seams | PASS | `App.tsx`, `main.tsx`, `ChatComposer.tsx`, `ChatPage.tsx`, `InspectionFrame.tsx`, and `SettingsPage.tsx` match round four. |
| Dependencies | PASS | `dashboard/package.json` and `dashboard/pnpm-lock.yaml` match Git HEAD by hash. |
| Actual shipping bundle | PASS | All 104 shipping files match `BUNDLE_MANIFEST.json`; no unlisted file exists in the shipping directory. The actual index references D6IQTpgA/BLgp1deP. |
| Security bundle chunks | PASS | API client, DOMPurify, markdown core/highlight, and WebSocket ticket chunks retain their round-four filenames and hashes. |
| Shipping credential-pattern scan | PASS | All 100 shipping JS/CSS/HTML/JSON files have zero AWS access-key, GitHub-token, OpenAI-token, JWT-shaped, or private-key-header matches. Values are suppressed. |
| Build evidence | PASS | `BUILD_CURRENT.log` records `tsc -b && vite build`, the exact D6IQTpgA/BLgp1deP assets, and successful completion. |
| Frontend test evidence | PASS | `TESTS_CURRENT.log` records 101/101 files and 980/980 tests passing. No tests changed after round four. |

### Preserved core hashes

| Path | SHA-256 |
| --- | --- |
| `dashboard/src/stores/chatStore.ts` | `9198078dea08610ebd248020c602a4c5f34ddbbb02ce504364616531d31ad5e8` |
| `dashboard/src/stores/projectStore.ts` | `b5e299c80e07f20f53b186c282cda882c39546bda6663d737ca23a55cd0e5db2` |
| `dashboard/src/api/client.ts` | `76e331749eae7bf6571ee35462c81e9b9f77b5e0c306921d5b547fb8b9438c6e` |
| `dashboard/src/utils/accessPinCredential.ts` | `9ff139d1bcd47bbffec45412a5316667b948abed0a7ba544d81da3d886640efd` |

These four checks use the recorded task baseline. `chatStore.ts` already differs from Git HEAD at that baseline; its preservation must not be described as equality with HEAD.

### Additional independently preserved production paths

Hash-only comparison against Git HEAD confirms:

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

Code discovery used the requested graph project first. The graph found the sanitizer, app, and approval API seams; a later graph query returned `Transport closed`, so remaining approval/PIN path discovery used the permitted filesystem fallback. No source changes followed that fallback.

## React Doctor advisory

React Doctor remains **exit 1**, with one `artifact-secret-leak` diagnostic at `dashboard/reports/mutation/mutation.html:334:94421`. The original and current result JSON contain the same diagnostic ID. The file is a pre-existing ignored, untracked mutation-test fixture. It is absent from both the 43-file source manifest and the independently verified 104-file shipping bundle.

This remains an advisory scoped to that nonshipping fixture. React Doctor is not globally clean, and this review does not claim its exit status is zero. The fixture contents and any alleged credential value were not read. The current shipping text assets separately have zero credential-pattern matches.

## Checked artifacts

- `BASELINE.json`
- `SOURCE_MANIFEST.json` and `SOURCE_MANIFEST_ROUND4.json`
- `BUNDLE_MANIFEST.json` and `BUNDLE_MANIFEST_ROUND4.json`
- `SECURITY_REVIEW_ROUND4.md`
- `BUILD_CURRENT.log` and `TESTS_CURRENT.log`
- `REACT_DOCTOR_RESULT.json` and `REACT_DOCTOR_CURRENT_RESULT.json`
- All 43 manifested source paths, protected seams by hash, and all 104 packaged shipping files

Artifact names above are relative to `docs/qa/2026-10-03-codex-ui/` unless an explicit production path is given.

## Findings and blockers

Findings: `[]`

Blockers: `[]`

## Evidence limits

- This is a final CSS-delta and artifact verification against the previous approved security review, not a new whole-repository security audit.
- Credential-pattern checks cover the named patterns; they do not prove the absence of every possible secret format.
- Existing Skills/Metrics 401 behavior remains outside any claim of backend authorization success or bypass.
- No browser or backend suite was run in this lane. Existing build/test logs were inspected; this reviewer did not rerun them.
- No secret, private auth/environment file, credential value, PIN, or browser storage was read. No production source was edited; only this report was written.
