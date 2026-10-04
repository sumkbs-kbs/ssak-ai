---
title: Read-only commit and public publish scope audit
date: 2026-10-04
tags: [git, publish, scope, audit]
status: complete
head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
scope: pre-staging shared working tree
---

## Observed repository state

The initial audit observed 698 porcelain status entries: 103 unstaged modified,
173 staged added, 8 staged-and-unstaged modified, 31 staged modified, 2 staged
added-and-unstaged modified, 79 unstaged deleted, and 302 untracked entries.
Directory-level untracked entries are not recursive file counts. The existing
index contains 214 paths: docs 148, scripts 1, src 39, tests 26. Existing staged
changes comprise 56,976 insertions and 1,312 deletions, primarily earlier
cognitive finalization and its evidence. No staging or Git mutation was performed
by this auditor. README editing by another worker began during the audit, so these
counts describe the initial snapshot rather than a final commit manifest.

Initial status entries by top-level product area were dashboard 118, docs 217,
src 244, tests 74, data 1, pyproject.toml 1, uv.lock 1, and vault_data 1. Remaining
entries are local tool stores and temporary work. There are 59 unstaged tracked
dashboard paths and 59 untracked dashboard entries. The 79 tracked deletions
are previous assets under src/antigravity_k/dashboard_dist/assets.

## Minimum decision diagnostics publication closure

The following eight new files contain the complete decision evaluation feature,
including the October 3 base implementation required by the October 4 extension:

```text
src/antigravity_k/engine/decision_evaluation_models.py
src/antigravity_k/engine/decision_evaluation.py
src/antigravity_k/decision_evaluation_cli.py
src/antigravity_k/api/routes/decision_evaluation_api.py
tests/test_decision_evaluation.py
tests/test_decision_evaluation_surfaces.py
tests/test_decision_diagnostics.py
tests/test_decision_diagnostic_surfaces.py
```

Two tracked wiring changes are required and their complete HEAD-to-working diff
contains only this feature's registration:

- src/antigravity_k/cli.py: import decision_eval and register `decision-eval` on
  the existing Typer app.
- src/antigravity_k/api/routes/__init__.py: import decision_evaluation_router and
  include it with the benchmarks tag.

All four production feature files were read. Their only internal module imports
are one another. The existing HEAD contains CLI, server, route aggregator, auth
policy, token service, and tests/conftest.py. The typed feature uses dependencies
already declared at HEAD; the working pyproject.toml addition of Scrapling is
unrelated to this feature. No server.py change is needed for its registration.
The staged bootstrap_cognitive_active startup hunk belongs to earlier cognitive
work and is not a dependency of this evaluation feature.

Direct documentation candidates are the two OH_MY_JEV_UPGRADE plans and selected
public research/usage documents under docs/qa/2026-10-03-oh-my-jev-upgrade and
docs/qa/2026-10-04-oh-my-jev-followup. The English root README is a separately
authorized deliverable. The two QA directories contain 70 files / 196,007 bytes
and 26 files / 86,648 bytes, respectively. Their outputs and source archive are
internal evidence, not required runtime code. Publishing only selected documents
requires checking relative links to omitted receipts and raw evidence. Ten
October 3 log files are ignored by the existing general `*.log` rule; a normal
directory add would not silently include them.

The follow-up source-snapshot archive was inspected by member names only. It
contains the eight feature/test files and its source manifest, no credential or
runtime state file. Nevertheless raw archives are excluded by the root's current
publication scope. This audit is structural closure inspection, not a clean
checkout regression run; root must verify the actual candidate commit tree.

## Authorized current full-product publication

The user explicitly selected publication of all current SSAK-AI product changes
during the audit. This supersedes the minimum-only option above. The publication
requires preserving a coherent source tree rather than staging only already-tracked
modifications. Recommended atomic
groups, each including its direct tests, are:

1. Earlier cognitive engine, active API/dependencies/startup wiring, and cognitive
   tests plus public architecture documentation. Existing staged bytes should
   remain accounted for; partial commits must not accidentally include the entire
   pre-existing index.
2. Dashboard source/components/features/styles, direct unit and E2E scenarios,
   DESIGN.md, package manifest and both existing lock formats. The current set
   includes new files as well as modifications.
3. Chat/model/search/memory/financial/voice runtime changes and their new modules,
   direct tests, relevant dependency manifest and uv.lock. Scrapling belongs here
   with the web reader/search changes, not in the decision-only group.
4. Decision evaluation closure above and its public usage/research documentation.
5. English README and other requested public documentation, with links checked
   against the actual published tree.
6. Packaged dashboard_dist only if publishing the current UI; rebuild it from the
   selected dashboard source and include its matching index/assets as a unit.
   Do not publish just old-asset deletions or a new index without matching assets.

These are commit-scope groups, not claims that the entire product has passed QA.
The latest 137-test evidence covers the decision feature, not the unrelated
backlog. This auditor did not inspect every full-product source diff or rerun its
subsystem gates.

## Exclusions and public-history issue

Exclude local state and temporary artifacts: `.ssak/`, `.pnpm-store/`,
`.freebuff/`, `work/`, root `tmp-*.py`, local vault content, runtime benchmark
results, raw QA archives/screenshots, generated caches, and auth/config stores.
Do not delete or revert them. `data/benchmark_results.json` and `vault_data` have
tracked working changes and should not be pulled in by a broad add.

The root `config.yaml` is already tracked and unchanged. The package defaults
`src/antigravity_k/config.yaml` are separately tracked and unchanged. The root
ignore rule does not remove the existing tracked root config from history. No
user credential/config contents were read by this auditor. Root independently
classified the HEAD blob without printing values: access PIN is unset and API-key
settings contain environment variable names rather than actual keys. This resolves
the root-config candidate concern; it is a parent-reported result, not this
auditor's credential read.
Changing the staging scope or adding ignores cannot sanitize already-present
history. The same applies to old tracked QA/private material in prior commits.

A filename-only pattern scan found current known PIN references in:

```text
docs/qa/2026-10-04-full-live/PIN_CHECK.md
docs/qa/2026-10-04-full-live/PIN_DEBUG_JOURNAL_ARCHIVE.md
docs/qa/2026-10-04-full-live/EVIDENCE_LEDGER.md
```

Older test PIN references also occur in the September 2 remediation plan/report
and F09-F10 auth evidence, and September 4 session-11 auth-bootstrap evidence.
Root confirmed excluding the three current-personal-PIN files from the new
publication. The full-docs scope is explicitly authorized, so a blanket exclusion
of all evidence directories is not an additional requirement of this audit.
Raw archives and personal/live records remain excluded. No secret value is
recorded here.

## Bounded sensitive-pattern and size checks

The auditor scanned 1,796 source/test/script candidate files for private-key
headers, recognizable provider token patterns, AWS key patterns and credential
URLs, skipping individual files larger than 2 MB. All detected source matches
were within tests/fixtures. They occurred in Settings/browser settings tests,
browser adversarial fixtures, secret scanner tests, egress/task runner/Unsloth/web
reader tests, persistent agency and browser memory tests, and test_tool_loop.py.
Follow-up context inspection classified these as deliberately synthetic fixtures:
dashboard constants explicitly named FAKE_KEY/LEGACY_SECRET or containing fake
markers, scanner/redaction/refusal assertions, credential-URL rejection/loopback
validation inputs, and a browser adversarial exfiltration fixture. Detected token
matches were masked in context output. They are not provider authentication calls
and no actual credential was established by these matches.
The latest feature files and both selected QA directories had no matches to those
high-confidence patterns. No symlinks were present in those two QA directories.
This bounded scan is not a comprehensive secret or private-conversation audit.

No currently tracked/untracked working file exceeds 100 MiB. The only blob above
50 MiB in `git rev-list --objects --all` is the existing 60,953,744-byte
`.agent/skills/gstack/bin/gstack-global-discover`, blob
`ebffeeb9e5d11bb02f58d39ea3153581c1ea989f`. There is no history blob above 100 MiB
in the inspected local refs. It is unrelated to the latest feature. Vendor
search binaries are intentionally excluded by existing Git rules and their
materialization workflow is separate. No LFS migration or object rewrite was
performed or recommended automatically.

## Exclusion references and fresh-checkout closure

No src/tests/dashboard file refers to any of the three excluded current-PIN
documents. The documentation link requiring minimal cleanup is
docs/ssak-ai-core/FULL_FUNCTION_LIVE_PLAN_2026-10-04.md:77, which links PIN_CHECK.md.
For the public version, replace the link with a statement that personal
authentication evidence is retained locally. This auditor does not own that file.

The omitted source-snapshot.tar.gz is directly referenced by the frozen
follow-up completion-receipt.json. Preserve historical receipt bytes rather than
editing a signed/hash-bound receipt to describe a different artifact. A public
publication note can state that the archive is local-only. This reference is
informational; no source/test runtime dependency on the archive was found.

Include the synthetic follow-up manual-cases.json because the public USAGE.md
command opens it. Include October 3 isolated_entry.py and subprocess_home.py
together if retaining its reproduction commands: both are QA helper source,
not user stores or raw binary archives. Later evidence and worker reports refer
to the launcher. Removing these helpers would break documented reproduction.
No source/test dependency on the excluded local work/tmp/cache directories was
established by this targeted reference inspection; root must still run the exact
candidate's regression checks.

## Commands and boundaries

Evidence was gathered with read-only git status/diff/cat-file/ls-files/rev-list,
graph discovery, bounded direct source reads, AST internal-import inspection,
filesystem byte-size checks, archive member listing, and filename-only pattern
reports. An initial AST inspection used the system Python 3.9 and rejected Python
3.12 type alias syntax; repeating with the project Python succeeded. This was an
inspection-tool mismatch, not a source defect. No provider, browser, application
startup, external source execution, user credential read, staging, commit, push,
reset, checkout, stash or history rewrite was performed.

Root is proceeding with the user's explicit full-product scope. Use the coherent
groups above, preserve excluded local dirty work, keep actual personal evidence
out of the publication, apply minimal document-link cleanup, and verify the exact
candidate tree before push. This is the final read-only scope audit; the auditor
did not mutate or stage the shared index.
