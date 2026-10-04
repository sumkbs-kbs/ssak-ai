---
title: Studio truthful state implementation evidence
tags: [qa, studio, backend-contract, frontend]
date: 2026-10-04
---

Studio now treats the existing local MLX training-job API separately from model export. There is no implemented GGUF export, artifact download, or Ollama registration endpoint. The three export/registration controls are native-disabled, describe the missing backend connection, have no operation handler, and cannot create success state or toasts. A completed training job still updates actual progress/loss and reports training completion, without asserting export or model registration.

The header reads `/v1/integrations/unsloth/capabilities` through the existing authenticated `apiRequestPath` boundary. A small Studio-specific Zod parser consumes the memory and provider-capability fields actually used by the page. Displayed memory is system available/total memory, not GPU VRAM usage. Local launch is enabled only for an available MLX training capability. Loading, unavailable, malformed and missing capability data do not imply readiness. Loss and loss-history start empty; unavailable throughput is represented by an em dash.

Pipeline navigation preserves numbered steps and declares the active step with `aria-current="step"`; it no longer represents skipped work as completed. Model cards are labelled selection examples and their memory values as estimates, without claiming installation or training compatibility. The disconnected method selector and upload area are informational. Token count, split, Epochs and Optimizer controls are disabled and labelled as unconnected or unsupported. Epochs, Optimizer and split no longer retain mutable UI state. The local MLX request preserves recipe/model/source and supported fields, including Iterations, while omitting `num_train_epochs`, which the backend rejects for MLX.

The scoped `StudioPage.css` uses existing design tokens to distinguish disabled controls and override the previous active hover treatment. Shared global styles were not changed.

Verification:

- Red first: all seven initial truthful-state tests failed against the prior implementation, including enabled pretraining export, false export state after backend training completion, four completed skipped steps, and invented initial loss/history. A separate unsupported Epochs/Optimizer test also failed before its fix.
- Final focused run: `node node_modules/vitest/vitest.mjs run src/pages/StudioPageTruthfulState.test.tsx src/pages/StudioPage.test.tsx src/pages/__tests__/StudioPageRecipePreset.test.tsx` passed 18 tests in three files, exit 0.
- Final targeted ESLint on the four TypeScript files passed with no warnings, exit 0.
- Final `node node_modules/typescript/bin/tsc -b --pretty false` passed, exit 0.
- The installed local executables were used directly. Initial `pnpm exec` attempted a dependency-status/install check and failed before installation; no dependencies were installed.
- CSS Biome LSP is unavailable; TypeScript LSP occasionally timed out. The explicit TypeScript and ESLint checks passed.
- No real training job, model load, installation, auth mutation or browser operation was performed by the executor. Build and real-browser retest remain assigned to the root agent.
- The pre-existing large Studio page was kept within the requested surgical scope. New helper and scoped style are small boundaries; no broad page refactor was attempted.

Read-only review approved with no blockers. Its initial findings about step-test implementation coupling and dead Epochs state were fixed; its later observation about dead Optimizer/split state was also fixed. The first reviewer pass violated the delegated no-Git/no-file-mutation restriction by running read-only Git inspection and ULW status and writing a review file. It reported no Git mutation, and its final pass followed the restrictions. The executor relocated the reviewer-created report to `studio-code-review.md` in this QA directory. That report preserves the original review context; this implementation record captures the subsequent fixes.

Final source SHA-256 values:

| File | SHA-256 |
|---|---|
| `dashboard/src/pages/StudioPage.tsx` | `63fc39c0ab8aca62c8a80cfb8c1d8d4c59c07e18920cdf5c520b25f135b70c92` |
| `dashboard/src/pages/StudioPage.css` | `e633e1934db65065e8bb5a59d3999b13cd5951cb58ba504b49b46fa7b6a6c6d9` |
| `dashboard/src/pages/studioCapabilities.ts` | `860001ed1fee34025e35d09e92f6b4b05c5cc4a3991f79abddce632231b9d3d9` |
| `dashboard/src/pages/StudioPage.test.tsx` | `d729490d2e67e5f28795f5e652185a847ce5b4c4a428a2c3584c6622ca9325ff` |
| `dashboard/src/pages/StudioPageTruthfulState.test.tsx` | `dd074d5edfa008650b4bc6a6ce0939ae2c4d240eb1254ed2f0c60775611c80b3` |
