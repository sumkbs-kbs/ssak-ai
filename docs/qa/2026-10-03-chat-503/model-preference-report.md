---
title: Durable Chat Model Preference Store Fix
date: 2026-10-03
tags: [chat, model-preference, regression]
---

Model selections now persist immediately to the existing localStorage preference style under the global `agk_chat_selected_model` key. `loadFromStorage` restores that preference before reading project-scoped session caches, including when there are no sessions. Session serialization, authoritative server snapshots, recommended defaults, and model filtering are unchanged.

Changed files:
- `dashboard/src/stores/chatStore.ts`
- `dashboard/src/stores/__tests__/chatStore.modelPreference.test.ts`

Validation:
- Red: 4 of 5 preference tests failed because reload restored `default` instead of the selected model. The no-preference default test passed. See `model-preference-red.log`.
- Green: all 23 tests passed across model preference, chat sessions, conversation revisions, NX-09 identity, and project store suites. See `model-preference-green.log`.
- Typecheck: `pnpm typecheck` passed with exit 0. See `model-preference-typecheck.log`.
- Skill checker unavailable: its recorded run could not resolve `typescript` from the caller project. The exact log does not establish a TypeScript 7 API mismatch. No dependency changes were made; the project's own `pnpm typecheck` passed. See `model-preference-audit.log`. The lead corrected this wording after the independent review; the original worker report remains in the private temporary evidence folder.

Source SHA-256:
- `chatStore.ts`: `9198078dea08610ebd248020c602a4c5f34ddbbb02ce504364616531d31ad5e8`
- `chatStore.modelPreference.test.ts`: `a2a7388c8327c436070a1d37388fe81eb196d32fbda35a47ffc9f18e1abaa104`

Review:
- The store owns chat session state. The existing file has 356 pure lines; this minimal fix adds 11 pure lines. A responsibility split was left outside the explicitly assigned minimal scope.
- New storage data uses the typed string/null Storage API without introducing an untyped JSON payload.
- No new tagged variants, type assertions, any annotations, ignored TypeScript errors, empty catches, helpers, parameter bloat, or negative names.
- Storage-write errors narrow to DOMException; unexpected errors propagate, and the current in-memory selection remains usable if browser storage is unavailable.
- Reload regression tests fail when the preference changes are removed; the red run confirms this.
- No files were staged or committed, and existing dirty work was preserved.

The lead owns build, runtime refresh, and browser verification. After the new bundle is active, select `qwen3.8:latest` once before reload verification, since a pre-fix choice could not have written this preference.
