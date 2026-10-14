# Clean publication candidate v1

Base HEAD: `b345bbb7601f1611e6de639161f9fbd241ac1eba`.
Worktree: `/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai`.

Only the following paths were edited; no staging, commit, or push was performed:

- `dashboard/src/api/client.ts`
- `dashboard/src/api/client.streamChannels.test.ts`
- `dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx`

The root task-only patch's first import context did not match the clean worktree's existing `createAccessPinHeaders` import. The existing import was preserved and only the additional Zod import/schema/private Error/check were applied. The two test hunks applied directly. Dirty root files were not copied over the clean sources.

Fresh candidate validation: **59 passed, 0 failed, 0 skipped**, TypeScript exit 0, scoped ESLint exit 0, `git diff --check` exit 0. ESLint reports one existing unused `createAccessPinHeaders` import warning; the clean preimage is separately passed to ESLint via stdin and recorded in `baseline-lint.*`. No warning was suppressed or repaired outside this task.

`receipts.json` contains exact executable argv, clean dashboard cwd, timestamps, and exit statuses. The single focused selector was the existing API suite, stream-channel suite, and ChatPage stream-channel suite. `vitest.json`, `junit.xml`, and `tests.stdout` record all scenarios. Specifically the rendered ChatPage test uses the real parser with a fetch stream fixture, preserves the queued message and partial answer, and observes only one chat request. The parser cases prove typed errors call onError once and onDone zero times across EOF/split frames; normal content, DONE, final content, abort, and revision conflict regressions pass.

`source-before.json` and `source-after.json` bind dashboard sources/configuration throughout all checks. `source/` saves the three tested files. `candidate.patch` is the exact three-file HEAD diff. `preimage/` matches the three files at the stated base HEAD. `patch-reconstruction.json` records applying the candidate patch to those preimages and comparing SHA256 values with tested/current files. `result.json` derives case counts/statuses from the actual JSON report, and `artifact-manifest.json` binds this candidate's evidence.

Dependencies were reused through an ignored local `dashboard/node_modules/` directory containing symlinks to already installed root dependencies. Node invoked the existing Vitest/TypeScript/ESLint binaries directly; no package installation, dependency change, or config change was made.

Scope remains offline parser and jsdom consumer validation. No live provider, browser rendering, visual design, full application, or release PASS is claimed. Root owns independent review and publication. The earlier root-tree 59-test result is separate evidence and was not used as proof of this candidate.
