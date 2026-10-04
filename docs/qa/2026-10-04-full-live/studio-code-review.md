# Code quality review: Studio truthful state

## Scope reviewed

- `dashboard/src/pages/StudioPage.tsx`
- `dashboard/src/pages/studioCapabilities.ts`
- `dashboard/src/pages/StudioPage.test.tsx`
- `dashboard/src/pages/StudioPageTruthfulState.test.tsx`

Goal reviewed: make the Studio surface truthful about unavailable GGUF/Ollama export and registration; stop navigation from representing completed work; source readiness and memory from capability data; omit unsupported MLX epochs from the job request; preserve the existing training-job API.

The ULW status command reported `ULW_LOOP_PLAN_MISSING`, so this report uses the required fallback evidence path.

## Evidence inspected

- Current scoped diff and current source for all four files.
- Backend contracts: `src/antigravity_k/api/routes/unsloth_studio_api.py:52`, `src/antigravity_k/engine/provider_adapters/unsloth_capability_contracts.py:87`, `src/antigravity_k/api/routes/training_jobs_api.py:216`, and `src/antigravity_k/finetune/hyperparameters.py:118`.
- Existing and new Studio tests. Executor-reported test evidence was not treated as sufficient by itself; this review did not rerun the suite because the parent owns build and browser QA.

## Skill-perspective check

Ran: yes. I loaded `omo:remove-ai-slops` and `omo:programming`, including the TypeScript reference.

- `programming`: no newly introduced `any`, type assertion, suppression, or untyped API boundary was found. The capability response is parsed with Zod in `studioCapabilities.ts:4-23`; the start-job payload continues to use the existing client boundary.
- `remove-ai-slops`: the change removes several false-state variables and does not add needless parsing or extraction. Two maintainability findings below remain: a test that mirrors a CSS implementation detail and UI state retained solely for controls declared unavailable.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

1. `dashboard/src/pages/StudioPageTruthfulState.test.tsx:56-64` verifies the absence of the private `completed` CSS class. This is an implementation-mirroring, removal-oriented test: another implementation can truthfully show no completed work without that exact class, while a future reintroduction of a check-mark indicator using a different class would evade it. Assert the user-visible step numbers/check marks or an accessibility state instead. This is not a release blocker because the shipped behavior is currently correct.

2. `dashboard/src/pages/StudioPage.tsx:99,135,565` retains the `epochs` state and updates it from a recipe even though the now-disabled Epochs control is expressly unsupported and `handleStartTraining` omits it from the payload (`dashboard/src/pages/StudioPage.tsx:231-244`). This dead state creates an apparent editable/request-bound setting with no effect. Keeping an informational disabled value is understandable, but the state and recipe write are needless production complexity; use a non-interactive display or remove the unused update path.

### LOW

None in the scoped change.

## Correctness observations

- Capability readiness fails closed: malformed data is rejected by Zod, and the launch button is disabled until the MLX training record is `available` (`StudioPage.tsx:89-91, 614`; `studioCapabilities.ts:4-23`). The fields match the server contract.
- Displayed memory is derived from the capability response rather than a literal (`StudioPage.tsx:291-293`).
- The code preserves the existing start/poll/cancel job flow and sends MLX-supported `iterations`, while excluding `num_train_epochs` (`StudioPage.tsx:231-245`). The backend confirms that MLX rejects the epochs key (`hyperparameters.py:156-159`).
- Export and local registration controls have no handlers, are disabled, and have an unavailable explanation (`StudioPage.tsx:697-728`). Completion leaves a training-only toast and no export success state.
- `StudioPage.tsx` is 661 pure lines, already above the anti-slop skill’s nominal module-size ceiling. That condition predates this scoped change and a broad split was explicitly outside this review's scope; it is not counted as a finding against this task.

## Decision

- `codeQualityStatus`: WATCH
- `recommendation`: APPROVE
- `blockers`: none
