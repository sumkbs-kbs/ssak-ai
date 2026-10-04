---
title: SSAK-AI public repository publication plan
date: 2026-10-04
tags: [publication, git, documentation, checklist]
---

The user explicitly authorized committing all current SSAK-AI changes and
pushing to https://github.com/sumkbs-kbs/ssak-ai.git. The target repository is
public and empty. Preserve the existing local branch/history and original
remote; add a separate target remote and publish its main branch without force.
Personal PIN records, authentication/configuration data, runtime vault contents,
temporary experiments, caches and raw private archives are excluded.

| Deliverable | Status | Acceptance |
| --- | --- | --- |
| Scope, source/index and target-history audit | completed | User selected full product; reachable history has no >100MiB blobs; target write dry-run succeeds |
| English default README and preserved Korean introduction | completed | Current code/document grounding, 28 relative links, no readiness overclaim |
| Publication candidates and relevant checks | completed | Product allow-list; dashboard 1219 tests/build, Python lint, 570-file typing and lock consistency pass; minimal type fix has 39 green tests |
| Atomic commits and target main push | in_progress | Preserve unrelated local artifacts; normal push only; no credentials in output |
| Remote verification and publication receipt | pending | Remote SHA matches local commit; final hook outcomes and expanded Python regression result recorded |

Read-only agents own scope/history audits and README grounding. Root owns final
candidate selection, validation, staging, commits, push and outcome. Prior QA is
historical scope evidence bound to its original SHA/file hashes, not release
approval for the new commits. No whole-program certification is claimed.

Expanded changed-test validation initially produced 1145 passed / 3 failed.
Sequential focused reproduction retained the three failures, so a concurrent
commit hook was not their sole cause. Workers own minimal fixes to quality
progress and vault source identity/deletion; root will validate their handoff
before the remaining commits. Tests and commit hooks run sequentially henceforth.
