# SAST and internal credential scan review — 2026-10-04

codeQualityStatus: WATCH
recommendation: REQUEST_CHANGES

## Scope and evidence

Read-only review of baseline `0b1aca2d990e08235c784c94f94585ec0c688ac5` plus the current CI workflow diff. No product code, configuration, tests, commits, or pushes were changed by this reviewer. Other implementation work is concurrent. This is remediation advice, not approval of an implementation or a green CI claim.

Evidence inspected: `docs/qa/2026-10-04-ci-repair/SECURITY.md`, `/tmp/ssak-ci-bandit-20261004.log`, the six Bandit source files below, `.github/workflows/ci.yml`, `engine/secret_scanner.py`, `engine/secret_scanner_patterns.py`, `engine/static_type_security_gate.py`, and `tests/test_static_type_security_gate.py`. Source paths below are relative to `src/antigravity_k/`. The supplied sanitized report records 196 matching files; this reviewer did not independently classify all 196 matches or certify them as harmless. No credentials are reproduced.

Graph-first discovery used the already indexed clean export project `tmp-ssak-ci-snapshot.IvGI3A`, because the requested workspace graph was unavailable. Relevant source was verified in the workspace. Graph discovery was insufficient for a repository scanner, so narrowly scoped file discovery supplemented it. `omo-agent-toolkit ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`; canonical reviewer artifact is `.omo/evidence/ci-sast-code-review.md`. No notepad was supplied.

## Findings by severity

### CRITICAL

None established.

### HIGH

None established as an exploitable application vulnerability in these 33 Bandit locations. This does not certify the entire repository or Git history.

### MEDIUM

1. **The legacy CI credential entry point confuses runtime text redaction with repository scanning.** `.github/workflows/ci.yml` internal scanner step calls `scan_for_secrets` on whole files. `engine/secret_scanner.py:125` applies every regular expression without syntax context. `engine/secret_scanner_patterns.py:43-52` treats credential-like names followed by space/assignment characters as possible values. Environment declarations, source references and fixtures therefore can be findings. The job remains nonzero; restoring `sys` only fixes the exception, not classification. Do not suppress all test/docs/source paths or weaken the runtime redactor to force green.

2. **Catalog membership is not SQL identifier validation.** `engine/cognitive/migration.py:169-178` checks `table in known_tables`, where names originate in `sqlite_master`, then interpolates the name unquoted. All observed production callers use fixed application table constants; graph inbound trace found no callers of the generic `_count` wrapper. Thus no externally reachable injection is established here. But the existing whitelist comment is insufficient rationale by itself. A temporary in-memory SQLite probe created tables named `normal` and `normal WHERE 0`; the latter passed catalog membership, while the unquoted count returned 0 and the correctly quoted count returned 1. Any suppression must cite the actual constant-only call chain. A bounded alternative is restrict `_count_on` to the three existing application identifiers, or use correct SQLite identifier quoting if arbitrary table names are an intended contract. Do not add a generic SQL sanitization framework.

### LOW

1. **B324 misstates the current hash purpose.** `tools/browser_observation.py:991-993` derives a four-hex frame-label slug and concatenates session/snapshot/element identifiers. This is not a password, signature, integrity decision, or authorization credential. `hashlib.sha1(frame_label.encode("utf-8"), usedforsecurity=False)` is the minimal correction. A local probe confirmed identical digest output with this keyword. Keep the existing identifier algorithm; changing the hash just for the scan can unnecessarily change identifiers. This review does not assert that a four-hex slug is collision-proof.

2. **Previous SARIF artifact command was unsupported.** The inspected log and sanitized report establish Bandit 1.9.4 lacked the requested formatter. Current workflow diff uses one JSON report command with the same `-ll` severity threshold and no swallowed exit code, and uploads that JSON artifact. That bounded change is appropriate; actual execution remains required.

## Classification of every B608 location

| Source and baseline lines | SQL syntax provenance | Value provenance and verdict |
| --- | --- | --- |
| `engine/cognitive/migration.py:172` | `_count_on` table parameter; actual `counts()` calls pass EVENTS_TABLE, OBJECTIVES_TABLE, OBJECTIVE_TASKS_TABLE | No observed production untrusted identifier path; catalog-membership caveat above. |
| `engine/cognitive/migration.py:206` | Local tuple of fixed table constants and fixed column strings at 193-197 | Row content enters digest only, not SQL syntax. False positive for current call chain. |
| `engine/cognitive/migration.py:253,279,298` | Module `Final` table strings, defined at 45-47 | No input reaches interpolated SQL syntax. False positives. |
| `knowledge/wiki.py:610` | Direction branches select fixed from/to predicates, generated `?` placeholders; optional category clause is a fixed literal (590-607) | Seed IDs and categories supplied in `relation_params`. User category/direction text is never interpolated. False positive. |
| `knowledge/wiki_graph.py:58,70` | Repeated `?` markers or literal `(from_id = ? AND to_id = ?)` predicates | Node/edge IDs supplied separately in execute arguments. False positives. |
| `knowledge/wiki_graph.py:77,79,80` | `table` iterates literal pair `wiki_node_rewards`, `wiki_link_rewards` at 75 | Decay factor is bound; no input in syntax. False positives. |
| `knowledge/wiki_graph.py:145,168,172,178,182,186` | Comma-separated `?` strings generated from chunk lengths | IDs separately bound, including repeated tuple for both endpoints. False positives. |
| `knowledge/wiki_graph.py:197` | Local tuple has two fixed table and column combinations at 193-196 | No external identifier input. False positive. |
| `tools/browser_task_memory.py:572,578,582,612,830,881,917,955,965,972` | Imported `TABLE` is `Final = "browser_task_memory"`, from store module line 29 | Dedupe key, glob value, body, owner/entry IDs and remaining data supplied as parameters. False positives. |
| `tools/browser_task_memory.py:822` | Same fixed TABLE; `_load_rows` appends only literal owner/origin/kind predicates at 811-819 | Owner/origin/kind values are appended to params, not `where`. False positive. |
| `tools/browser_task_memory_store.py:97,108,117` | Same module-owned fixed TABLE | Replacement body and entry IDs separately bound. False positives. |

There are 32 B608 locations total. Ruff's existing `noqa: S608` annotations do not instruct Bandit. For the 31 unequivocal constant/placeholder cases, a per-location `nosec B608` with the reviewed reason is lower risk than changing working queries or adding validators. For line 172, resolve/document the constant-only contract explicitly before annotating. Avoid global B608 skip, broad directory exclusion, wrapper functions that merely conceal execute calls, and duplicate static query branches just to appease the scanner. Rerun the exact hard gate to check multiline comment placement.

## Existing scanner alternatives and bounded recommendation

Graph and filesystem review found no ready repository-wide, source-aware replacement for the legacy scanner in this checkout. `StaticTypeSecurityGate.audit_code` (`engine/static_type_security_gate.py:62-87`) is not suitable: its credential check is a narrow assignment regex, broadly skips a line containing `environ`/`os.getenv`, adds unrelated eval/shell rules, and retains raw `culprit_code` that its formatter prints. Its AST phase does not make the credential regex source-aware. Replacing CI with this would lose coverage and risk leaking values in logs.

The existing gitleaks step is the actual dedicated repository/history credential scanner; retain it and fix checkout history depth as already proposed. A safe internal CI entry requires a separate, bounded repository-scanning contract: scan tracked public files, distinguish environment references from literal values at that boundary, report only path/line/rule, and fail on unreadable or missing required scope. Do not scan local private data or change the installed automatic privacy gate. Fixtures need exact reviewed finding-level handling, never an entire tests/docs exemption. A token merely containing a word like `test` must not be automatically trusted.

A proposed CLI shape such as `python scripts/scan_repository_credentials.py` would be a NEW implementation, not an existing command. It must retain detection of provider keys, credential assignments, bearer values, credential URLs/private keys as applicable to the original contract. This is materially more effort than Bandit annotations and should be an explicit bounded follow-up if safe source classification cannot be completed now. Do not claim green by silently removing the internal scanner. Until that work exists, keep it failing truthfully and report the blocker.

## Validation and skill-perspective check

Loaded and consulted `omo:remove-ai-slops` and `omo:programming`. Reviewed the current workflow diff and relevant existing source with their anti-overfit/complexity criteria. No new production abstractions, parsing, normalization, untyped escapes, or tests exist in this SAST remediation diff at review time. No violation introduced by the reviewed workflow changes was found. Existing large modules and broad catches were not used to justify an unrelated rewrite. Reject deletion-only tests, source-text assertions that merely count `nosec` markers, hash-constant pins, and tests asserting a requested removal. Useful checks are observable behavior: migration counts/digests, wiki category/direction search, graph deletion/rewards, browser memory owner isolation/revocation, and actual scanner exit codes on both malicious synthetic credentials and harmless environment-reference controls.

Executed only a standalone in-memory SQLite identifier probe and nonsecurity hash equivalence probe; no application suite was run by this reviewer, and no actual secrets were planted in the shared repository. Existing Bandit results were inspected, not rerun. Main findings are dataflow review, not claimed runtime exploit reproduction.

## Blockers before claiming CI repair complete

- Apply and rerun the bounded Bandit correction, with special attention to migration line 172 rationale and multiline suppression placement.
- Resolve internal repository-scanner classification without changing runtime privacy protection or reducing actual credential coverage; verify adversarial/benign controls at the real CI entry point.
- Complete the remaining dependency audit and actual GitHub scans described in `SECURITY.md`; passing the reviewed configuration changes alone is insufficient.
