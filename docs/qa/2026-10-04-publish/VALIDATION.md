---
title: SSAK-AI publication validation record
date: 2026-10-04
tags: [publication, validation, regression]
---

## Observed checks

- Dashboard: `pnpm --dir dashboard test` completed with 122 test files and
  **1219 passing tests**. `pnpm --dir dashboard run build` completed TypeScript
  checking and the Vite production build into the packaged dashboard directory.
  The existing large-chunk warning remains.
- Python static checks: Ruff passed for source, tests and scripts. Project mypy
  1.20.2 checked **570 source files** without errors. `uv lock --check` passed.
- Expanded initial changed-test run: **1145 passed / 3 failed** in 460.71 seconds.
  All **258 selected cognitive tests** passed within that run. The three failures
  were reproduced sequentially (3 failed / 27 passed), so concurrency with a
  commit hook was not their sole cause.
- Quality regression: the existing failing progress-event test became green;
  **176 related tests** passed through the temporary-home isolation launcher.
- Wiki regression: **24 related tests** passed; temporary-storage library usage
  preserved two distinct same-title paths, removed Obsidian graph links and
  preserved manually created entries.
- Post-fix changed runtime tests plus the existing wiki privacy test:
  **891 passed** in 34.64 seconds. This run followed source formatting and used
  the isolation launcher with dotenv disabled.
- After the final SSE payload annotation and pinned formatter, the TDD boundary
  tests passed again: **15 passed** in 1.24 seconds. The pinned mypy 1.14.1 hook
  checked **570 source files** without errors; runtime and decision commits
  completed with all applicable hooks passing.
- The final dashboard build completed again in 19.42 seconds after the
  end-of-file hook removed one extra blank line from ChatMarkdown.
- Manual CLI usage: help and synthetic decision evaluation exited **0**;
  malformed input exited **2** with the safe schema error. The synthetic input
  produced total=6, scored=2 and accuracy=0.5. These are example results, not
  measured real-model quality.

The isolation launcher sets temporary home, authentication and storage paths
before project imports. No provider, personal vault or live browser access was
needed. The initial local type check required a behavior-preserving boolean
conversion in direct task execution. The pinned mypy 1.14.1 commit hook also
identified a typed SSE payload inference difference; its final result is recorded
in the publication receipt after the hook completes.

## Publication boundaries

The full selected suite was not claimed to be green before fixing its failures.
The expensive cognitive tests were not repeated after unrelated runtime fixes;
the subsequent regression run covers the changed runtime surfaces. Historical
reviews bind to their original source identities. Final commits and hook results
are recorded separately. This is a publication record, not whole-program,
real-model, browser or production-readiness certification.

Raw outputs are retained locally. See [PUBLICATION_SCOPE.md](PUBLICATION_SCOPE.md)
for intentionally omitted supporting artifacts and the public documentation scope.
