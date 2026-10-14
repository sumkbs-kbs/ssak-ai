---
title: IMP20 release documentation and contract repair
status: SCOPED_CONTRACTS_PASS
release_status: NOT_APPROVED
---

# Result and scope

Candidate worktree: `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`.
Seven assigned tracked files changed; 14 existing ROOT originals restored unchanged. No product source edit, shared ROOT product/document edit, staging, commit, historical script execution, broad suite, provider, inference, soak, or GA approval was performed by this worker. Other workers' changes remain untouched.

Final narrow result: **101 passed, 1 skipped, 0 failures**, exit **0**. The existing skipped test requires historical `.omo/evidence/commercial-reliability/CR-14` gate reports absent from the candidate. That historical report check is **not validated** by this work. GA remains **NOT_APPROVED**; the historical verdict remains **NO-GO**.

## Changes

- README explicitly labels the CR paragraph historical, links the verdict owner, distinguishes implementation history from release approval, and preserves technical/human blockers. Adopted the reviewed four-line ROOT delta with one historical label added.
- EX-05 becomes `INCONCLUSIVE — DONE 아님`, preserving passing JSON metrics while recording the already documented wrapper exit 141 and unverified candidate binding. This reconciles the ledger with the existing current-status document; it is not a new soak observation.
- The verdict has an explicit `ARCHIVED` declaration status and current HEAD `NOT_APPROVED`. Its historical SHA, fingerprint and original record body are retained.
- Archived-declaration tests validate the fingerprint against its recorded commit. Active declarations require exact candidate SHA == current HEAD plus matching committed and working-tree fingerprints. Mutation cases reject changed source, dirty source, even docs-only HEAD advancement, mismatched historical fingerprints, missing/duplicate/unknown status and archive overclaim. Existing real/synthetic F-22 movement detection remains.
- NX07 parses the existing Markdown table/URL formatting and checks that mutations really modify the input, including missing port fields/URLs.
- Secret scanning retains existing dirty/untracked selection and content/placeholder rules. If no eligible dirty/untracked text file exists, it scans the explicit tracked production/configuration policy in `_BASELINE_PATHS`. That policy covers `src/`, `scripts/`, `config/`, `dashboard/src/`, `.github/`, deployment/desktop/extension source and named package/deployment configuration. Historical evidence and test fixture corpora are not the clean-tree baseline. Changed files in those directories remain subject to the original scanner. No content suppression was added. Existing suffix and 2 MB eligibility limits remain.

A whole-tracked-file probe found 38 pattern hits in historical QA/test fixtures (locations only in `tracked-scan-policy-probe.txt`). This policy conflict was reported; the parent authorized the production/config baseline. The final production baseline scanned **1,164** eligible text files, zero hits. This is a scoped pattern scan, not a full secret-security audit.

## Invocation and binary evidence

Exact final invocation, from the candidate cwd:

```sh
sh /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-RELEASE-DOC-CONTRACTS-01/run-contracts.sh after-02-source-bound
```

The runner records the exact six pytest file arguments and isolated `AGK_PATH_*`/hook-vault environment. Runtime lives under candidate `.omo/`, outside the public evidence manifest. To reproduce, pass a new run-directory name. Thirty bound paths have identical SHA-256 receipts before and after the invocation (`after-02-source-bound/source-before.sha256`, `source-after.sha256`, `source-stability.txt`). `source-binding.json` records owned source hashes; `bound-paths.txt` also includes direct test dependencies and restored files. This does not assert an immutable entire release candidate.

All artifact paths below are relative to this report's directory. Test rows use the invocation above, with exact scenario names recorded as JUnit `testcase` names.

| Criterion | Exact scenario / invocation | Binary observable | Captured artifact |
|---|---|---|---|
| README history, owner, technical/human blockers | `test_readme_does_not_claim_that_only_the_human_axis_remains`; CR12 documentation file in the same invocation | Relevant JUnit cases have no failure/error/skip | `after-02-source-bound/junit.xml`, `after-02-source-bound/pytest.log` |
| Real Markdown port formats and mutation checks | `test_readme_guidance_matches_the_code_default_port`, `test_teeth_readme_port_drift_is_detected` | Both cases pass; every mutation changes its input and is rejected | `after-02-source-bound/junit.xml` |
| EX-05 unresolved execution/binding | `test_soak_phases_stay_separated`, `test_teeth_soak_done_promotion_is_detected` | Both cases pass; DONE promotion rejected | `after-02-source-bound/junit.xml` |
| Historical fingerprint preserved; active HEAD binding enforced | `test_declared_fingerprint_is_the_declared_candidates_own_tree`, `test_release_declaration_binds_to_its_explicit_status`, `test_teeth_declaration_scope_preserves_archive_and_rejects_active_drift[ARCHIVED]`, `test_teeth_declaration_scope_preserves_archive_and_rejects_active_drift[ACTIVE]`, `test_teeth_active_declaration_requires_head_even_after_docs_only_commit` | Five cases pass; actual historical commit fingerprint matches; negative mutations rejected | `after-02-source-bound/junit.xml`, `historical-record-preservation.json` |
| Clean tracked scan and planted secret detection | `test_clean_tracked_production_baseline_detects_synthetic_secret[False]`, `test_clean_tracked_production_baseline_detects_synthetic_secret[True]` | Clean temporary Git tree scanned count == 1; planted invalid token reports exactly `src/app.py:2 (openai_key)`; changed fixture secret also detected | `after-02-source-bound/junit.xml` |
| Meaningful tracked production/config corpus | `_scan_secret_paths(candidate, git ls-files -z -- *_BASELINE_PATHS)` | eligible_text_scanned == 1164, hits == [] | `production-baseline-scan.json` |
| Existing artifact restoration and all local link closure | Byte verification of ROOT/candidate/archive for every `restored-files.json` entry; `test_local_relative_links_resolve`; `test_qwen_repo_prompt_budget.py` | 14 files match size/SHA across all three copies; links and budget regressions pass | `original-byte-verification.json`, `restored-files.json`, `after-02-source-bound/junit.xml` |
| Narrow quality checks | `.venv/bin/python -m ruff check` and `ruff format --check` on the four changed test files; `git diff --check` on seven owned tracked files | All exit 0 | `final-ruff.log`, `final-ruff-exit.txt`, `final-format.log`, `final-format-exit.txt`, `diff-check.log`, `diff-check-exit.txt` |

## Failures retained and provenance limits

- Initial narrow invocation (five files, before changes): **12 failed, 57 passed, 2 skipped**. Captured `initial-capture/before/pytest.log`, `junit.xml`, `exit-code.txt`. Its environment used the repository's autouse isolation and an evidence variable; the later runner adds explicit owned path isolation. Baseline hashes were reconstructed directly from the assigned `481a634` git objects, not captured before this initial run; this limit is explicit in `baseline-source-binding.json`.
- Clean temporary Git tree reproduction of the old scanner failed its `scanned > 0` assertion: `clean-tree-before.json`.
- Interim run after initial nine restorations: **1 failed, 98 passed, 1 skipped**, exposing remaining links: `interim-pytest.log`, `interim-junit.xml`, `missing-links-after-initial-restoration.json`. Parent authorized five additional existing originals. No missing evidence was reconstructed.
- First passing run: `after-01/`, **101 passed, 1 skipped**. Repeated once with pre/post source receipts to close the source-binding gap: `after-02-source-bound/`.
- Metadata finalization initially used a host Python lacking `datetime.UTC`; the complete metadata/byte-verification step was rerun using candidate `.venv/bin/python`. Captured `finalization-repair.json`. Product/test source did not change.
- `restored-files.json` records each ROOT path, current size/SHA, tracked/ignored state and available path history. `originals/` stores its unchanged bytes. `provenance.json` records committed September document references and the existing local budget hash record. Document references corroborate identities, not exact historical byte hashes. The fixture agrees with its existing local hash record; that record is not immutable committed execution proof. Historical execution and exact historical bytes remain unverified unless separately established.
- The public manifest excludes runtime/temp directories. `owned-paths.txt` is the exact publication list; `owned.patch` contains only seven tracked-file edits. The parent owns staging/publication and any full-gate rerun.
