---
title: Public publication candidate review
date: 2026-10-04
tags: [publication, scope, review, confidentiality]
scope: current SSAK-AI worktree candidate
verdict: conditional-pass
---

# Result

The product source, tests, English README, Korean README copy, and current
implementation plans can be published as the user requested. Publication must
use an explicit allow-list: the worktree also contains private authentication
evidence, runtime data, raw QA captures, archival copies, and generated local
state that are not source deliverables.

This was a read-only candidate review. It did not start the application, access
the saved-policy-blocked localhost browser, read credentials, stage files,
commit, or push.

## Required product files

Stage the modified tracked product files and their matching tests together.
In addition, the following currently untracked files are required for the
published behavior and documentation to remain coherent on a fresh clone.

### Decision diagnostics

- `src/antigravity_k/engine/decision_evaluation.py`
- `src/antigravity_k/engine/decision_evaluation_models.py`
- `src/antigravity_k/decision_evaluation_cli.py`
- `src/antigravity_k/api/routes/decision_evaluation_api.py`
- `tests/test_decision_evaluation.py`
- `tests/test_decision_evaluation_surfaces.py`
- `tests/test_decision_diagnostics.py`
- `tests/test_decision_diagnostic_surfaces.py`

The graph shows the CLI registration in `src/antigravity_k/cli.py`, the route
registration in `src/antigravity_k/api/routes/__init__.py`, and isolated API and
CLI surface tests. Omitting either the CLI or route file would leave a README
claim pointing at an unavailable public surface.

### Other current product additions

Stage all untracked modules under `src/antigravity_k/` other than the matching
dashboard build output, and all untracked `tests/` files. The current additions
cover stream framing, financial-number extraction, memory recall budgeting,
Ollama process status, voice-audio validation, and HTML/reader/search parsing;
their tests are present in the corresponding untracked test set. The generated
`src/antigravity_k/dashboard_dist/` replacement assets must be committed in the
same commit as the dashboard source that produced them, including deletions of
the old hashed assets and the new `index.html`.

Include `pyproject.toml` and `uv.lock` together: the lock records the declared
Scrapling dependency. Include dashboard `package.json`, `pnpm-lock.yaml`, and
the existing `package-lock.json` update with the dashboard source, rather than
publishing a dependency manifest without its resolved lock data.

### Documentation required by the new README

The English `README.md` links to files that are currently untracked and must be
included:

- `README.ko.md`
- `docs/ssak-ai-core/FULL_FUNCTION_LIVE_PLAN_2026-10-04.md`
- `docs/qa/2026-10-04-oh-my-jev-followup/IMPLEMENTATION_CONTRACT.md`
- `docs/qa/2026-10-04-oh-my-jev-followup/RESULT.md`
- `docs/qa/2026-10-04-oh-my-jev-followup/USAGE.md`

For the decision-diagnostics report set, include the small synthetic input,
source manifest, review and quality receipts only when their linked report is
also included. Do not include a receipt that claims an unavailable artifact is
in the repository.

## Required exclusions

Do not stage the following classes of files for this public target:

- `data/benchmark_results.json` and the `vault_data` gitlink: local/runtime
  state, not source or reproducible fixture data.
- `.ssak/`, `work/`, `.pnpm-store/`, `.freebuff/`, runtime homes, caches,
  temporary root scripts, authentication data, and local configuration.
- Raw QA captures, browser exports, screenshots, archives, baseline source
  copies, backup trees, patches, and large historical NX10 report artifacts.
  This includes the archival-heavy `docs/qa/2026-09-16-followup/nx10/` and the
  capture/archive/baseline subtrees of the October 3 QA directories.
- `docs/qa/2026-10-04-oh-my-jev-followup/source-snapshot.tar.gz`.
- The following private-authentication evidence filenames:
  `docs/qa/2026-10-04-full-live/PIN_CHECK.md`,
  `docs/qa/2026-10-04-full-live/PIN_DEBUG_JOURNAL_ARCHIVE.md`, and
  `docs/qa/2026-10-04-full-live/EVIDENCE_LEDGER.md`.

The current public full-live plan was checked after its privacy edit. It states
only the verification boundary and local retention policy; it no longer needs a
private value to explain the result.

## Conditional blocker before commit

`docs/qa/2026-10-04-oh-my-jev-followup/completion-receipt.json` names the
excluded `source-snapshot.tar.gz`. If the receipt is selected for publication,
either omit that receipt as archival material or update the public evidence
index to state that the snapshot is retained locally and is intentionally not
part of the repository. Leaving a committed receipt that implies a fresh clone
contains a deliberately omitted archive is misleading.

The same rule applies to any evidence document selected from the raw QA
directories: its declared inputs must exist in the public tree or be explicitly
described as local-only. This is a documentation-integrity condition, not a
request to publish raw captures or private data.

## Manifest-specific follow-up

The reviewed candidate manifest contains 746 documentation paths. Its current
documentation allow-list is still too broad for the stated exclusion of raw QA
material: it includes 231 JSON files, 148 text outputs, 18 Python QA drivers,
9 JSONL logs, 7 patches, and 7 XML reports. These are not needed for a usable
fresh clone and are not all publication documentation.

Exclude the raw-output families below while retaining concise Markdown plans,
contracts, summaries, and reviews that do not depend on them:

- `docs/qa/2026-10-03-codex-ui/` machine observations, capture manifests,
  source manifests, image-diff receipts, patch files, and DOM/source listings.
- `docs/qa/2026-10-03-response-style/` browser, capture, history, source
  manifest, task-baseline, and round-directory artifacts.
- `docs/qa/2026-10-03-chat-503/` configuration, runtime, browser, source-hash,
  console, and test-output artifacts.
- `docs/qa/2026-10-03-core-live/`,
  `docs/qa/2026-10-03-external-feature-upgrade/`,
  `docs/qa/2026-10-03-functional-upgrade/`,
  `docs/qa/2026-10-03-oh-my-jev-upgrade/`,
  `docs/qa/2026-10-03-residual-close/`, and
  `docs/qa/2026-10-03-web-search-upgrade/` raw command output, local health
  observations, manual drivers, manifests, pre/post source data, and patches.
- Historical raw machine artifacts below `docs/ssak-ai-core/evidence/`,
  including live-record outputs, manifests, local-driver scripts, JSONL
  ledgers, and command/test output. Preserve only the small human-readable
  architecture/contracts/review summaries needed by current public plans.

One explicit source baseline copy remains in the manifest and must be excluded:
`docs/qa/2026-10-03-residual-close/conversation-store-preimage.txt`.

The manifest already excludes the known private PIN documents and the related
receipt. Filename-only review found no additional candidate path named as a
current PIN record. This is not a content-wide credential scan; raw runtime and
browser artifacts are excluded as a class because their filenames and role do
not provide enough privacy assurance for public publication.

## Quality perspective

The `programming` and `remove-ai-slops` skill perspectives were consulted for
this review. The decision-diagnostics implementation has a typed Pydantic
boundary, a shared summary function, explicit variant matching, and observable
CLI/API tests. The tests exercise schema rejection, bounded input, registered
CLI help, and response behavior; they are not deletion-only, prose-pinning, or
constant-mirroring tests. I found no publication-candidate violation of either
skill perspective in the reviewed decision-diagnostics surface.

This is not a whole-tree slop or security audit. Several large staged modules
and pre-existing broad catches fall outside the bounded surface reviewed here;
they should not be represented as reviewed merely because this publication
candidate is approved.

## Verification basis and limits

- Graph indexing was refreshed for the current checkout; code discovery found
  the decision route, CLI command, calculator, and tests described above.
- `git diff --check` was clean at review time.
- The publication plan records a passing dashboard unit suite and build, a
  passing Ruff run, and one then-active repository-wide type correction. This
  review does not replace the root's final post-fix typecheck or final commit
  verification.
- Browser/manual localhost verification remains excluded because the saved
  browser permission policy is blocked; no bypass was attempted.

## Recommendation

Proceed after resolving the conditional archive-reference issue and after the
root records a green final typecheck for the exact staged source. Use grouped,
allow-listed commits so the dashboard source and bundle, dependency manifests
and locks, and every public API/CLI feature and its tests stay together.
