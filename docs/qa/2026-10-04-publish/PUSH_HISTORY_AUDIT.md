---
title: SSAK-AI public push history feasibility audit
date: 2026-10-04
tags: [git, publication, size-audit, read-only]
audited_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
target: https://github.com/sumkbs-kbs/ssak-ai.git
verdict: no-baseline-history-size-blocker-detected
---

# Scope and conclusion

This read-only audit covers the objects reachable from the exact local HEAD
`8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` on branch
`codex/m1-task-events`. It does not cover newly staged or untracked files,
publication confidentiality, dependency licensing, or the final commit that
will be created after this audit. It made no Git, remote, or credential changes.

No reachable blob exceeds GitHub's 100 MiB regular Git file limit. One
historical binary exceeds the 50 MiB warning threshold. GitHub documents that
such a warning does not itself prevent a push. The baseline history therefore
does not require an LFS migration or history rewrite for the file-size limit.
[GitHub large-file documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

The configured target advertised no refs when queried. This is consistent with
the requested empty repository, but successful public read access does not
establish push authorization. The root agent must verify the final publication
set and then observe the actual authorized push result.

# Commands and observations

The following commands completed successfully:

```text
git rev-parse HEAD
git branch --show-current
git count-objects -vH
git lfs ls-files
git rev-list --objects HEAD
git cat-file --batch-check=%(objectname) %(objecttype) %(objectsize) %(objectsize:disk)
git config --get-all credential.helper
git ls-remote https://github.com/sumkbs-kbs/ssak-ai.git
```

The credential helper value was captured internally and reduced to its helper
name before output. Only `osxkeychain` was reported. No credential lookup,
password, token, helper command, historical file content, or secret value was
printed. No push, dry-run push, fetch, pack generation, rebase, reset, or commit
was performed by this audit.

| Measurement | Observed value |
| --- | ---: |
| Reachable objects | 19,300 |
| Reachable commits | 1,218 |
| Reachable trees | 6,969 |
| Reachable blobs | 11,113 |
| Reachable commit logical bytes | 684,020 |
| Reachable tree logical bytes | 18,495,419 |
| Reachable blob logical bytes | 404,325,128 |
| All reachable logical object bytes | 423,504,567 (about 403.89 MiB) |
| Sum of current reachable object storage sizes | 58,008,117 (about 55.32 MiB) |
| Blobs larger than 100 MiB | 0 |
| Blobs larger than 50 MiB | 1 |
| Entries returned by `git lfs ls-files` | 0 |
| Target refs returned by `git ls-remote` | 0 |

The 55.32 MiB value is an estimate from the current object representations,
not a measured outgoing pack. Delta bases, packing choices, protocol overhead,
and newly committed objects can change the transmitted size. A new pack was
not generated solely to estimate it.

The complete local object database is much larger: `git count-objects -vH`
reported 2.43 GiB of packs plus 111.27 MiB of loose objects. Those numbers cover
more than the requested HEAD ancestry and are not the size of a single-branch
push. Publishing `--all` or `--mirror` would include unrelated refs and is not
appropriate for the requested target.

# Largest reachable blobs

Names and sizes only are shown. These are history paths; their presence here
does not mean the final publication tree includes the same file.

| Historical path | Bytes |
| --- | ---: |
| `.agent/skills/gstack/bin/gstack-global-discover` | 60,953,744 |
| `dashboard/node_modules/@esbuild/darwin-arm64/bin/esbuild` | 9,934,834 |
| `src/antigravity_k/dashboard_dist/assets/ts.worker-DTZAwq0V.js` | 7,043,070 |
| `src/antigravity_k/dashboard_dist/assets/monaco-TowBmCEl.js` | 4,504,933 |
| `.agent/skills/k-skill/docs/assets/k-skill-thumbnail.png` | 2,180,137 |
| `dashboard/node_modules/@rollup/rollup-darwin-arm64/rollup.darwin-arm64.node` | 1,780,336 |

The largest blob is `ebffeeb9e5d11bb02f58d39ea3153581c1ea989f`.
It is approximately 58.13 MiB. Existing historical bundled dependencies and
binaries explain some of the repository weight but are below the hard limit.

# Safe publication handoff

1. Review and commit only the authorized publication files, preserving other
   shared work. Recheck reachable sizes at the resulting exact commit.
2. Publish the selected commit to one explicitly named target branch with an
   ordinary non-forced push. Leave existing local branch history and the old
   remote intact unless the root's publication plan explicitly requires a
   reversible additional remote configuration.
3. Treat a size audit as separate from content review. A public push sends all
   ancestry reachable from that commit, including files deleted later.
4. A successful public `ls-remote` and the `osxkeychain` helper do not prove
   authenticated write permission. Report an actual push failure accurately
   rather than claiming publication from a read-only check.
5. If newly committed objects introduce a hard size failure, preserve the
   current local history. A separate sanitized publication history could be
   prepared as a distinct artifact if needed; rewriting or force-pushing the
   current shared branch is not a prerequisite and was not authorized by this
   audit. No such alternative is needed for the audited baseline sizes.

This report is a feasibility result, not final publication approval or proof
that a push occurred.
