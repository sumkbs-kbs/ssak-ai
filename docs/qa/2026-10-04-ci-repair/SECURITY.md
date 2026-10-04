# Security job diagnosis — 2026-10-04

## Observed failure

The [Security Scan job](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37167142002/job/111332317871) failed because gitleaks could not resolve its Git revision range. This execution did not establish whether the repository contains credentials.

- Run: `37167142002`; job: `111332317871`.
- Pull-request head: `bae902e7b41caf88921c85beb4df864d52fa31c5` (Dependabot's `docker/setup-buildx-action` update).
- Checked-out pull-request merge: `211c46f5d70ab68ad46583d9aa8c10e7c0a4bafc`.
- Published main examined separately: `0b1aca2d990e08235c784c94f94585ec0c688ac5`.
- Job steps and decoded job logs were retrieved through the authenticated GitHub connector.

Checkout used `fetch-depth: 1` and fetched only the pull-request merge revision. Gitleaks 8.24.3 then requested:

```text
git log -p -U0 --no-merges --first-parent bae902e7b41caf88921c85beb4df864d52fa31c5^..bae902e7b41caf88921c85beb4df864d52fa31c5
```

Git reported an ambiguous revision. Gitleaks reported a partial scan of approximately zero bytes and returned an unexpected exit code 1. Its configured credential-detection exit code was 2. The user account did not require a gitleaks license, so licensing was not this failure's cause.

## Reproduction

A separate temporary checkout of that exact Dependabot branch was created with `--depth 1`. `git rev-parse --is-shallow-repository` returned `true`; `git log --oneline '<head>^..<head>'` failed with exit 128 and the same ambiguous-revision error.

After `git fetch --unshallow` in that temporary checkout, the shallow check returned `false` and the exact range resolved successfully to the Dependabot commit. No shared workspace files or Git history were changed by this reproduction.

## Remediation

Configure the checkout in the `security-scan` job of `.github/workflows/ci.yml` with `fetch-depth: 0`, allowing gitleaks to resolve pull-request head and parent ranges. Published main has the same shallow checkout configuration. Retain gitleaks' normal failure behavior; no secret allowlist, detection-rule exclusion, or history rewrite is warranted by this observed infrastructure error.

The inline internal-scanner script also references `sys.exit(1)` without importing `sys`. This is a separate latent failure when findings are present; adding the missing import preserves rejection of findings. It was not reached in the observed run.

## Coverage boundary

The dependency audit, locked dependency installation, Bandit SAST scan, and internal secret scan were all **skipped** after gitleaks failed. Successful upload steps do not imply successful security scans. A new GitHub execution must complete the actual scans before claiming the Security Scan job is green.

This report does not assert that the full Git history is free of credentials. No credential values, matched secret text, or authenticated download URLs are included.

## Previously skipped scans — verification journal

The clean source export `/tmp/ssak-ci-snapshot.IvGI3A` is used for the dependency audit and Bandit commands. Its locked dev environment reports Python 3.12.13 and Bandit 1.9.4. The initial source export had no `.git` directory; the parent later added the real published Git reference/index for CLI source-head checks. The local host is macOS; GitHub's Linux execution remains the final platform check.

Planned temporary outputs are `/tmp/ssak-ci-dependency-audit-20261004.log`, `/tmp/ssak-ci-audit-inputs-20261004.json`, `/tmp/ssak-ci-bandit-20261004.log`, and `/tmp/ssak-ci-bandit-20261004.sarif`. Only sanitized outcomes will be recorded here. Raw outputs are temporary and must be removed after the parent has consumed the findings. The temporary shallow-check reproduction directory is `/tmp/ssak-ci-security-shallow-20261004`; it can be removed after the reproduced result is recorded.

### Dependency audit result

`AGK_AUDIT_RECORD=/tmp/ssak-ci-audit-inputs-20261004.json bash scripts/audit_python_dependencies.sh` returned **1**. The exported union contains 149 locked package entries; pip-audit actually audited 128 packages for this host. It reported 25 advisory entries affecting six packages. Five chromadb entries matched existing exact exceptions with expiry 2026-12-08; no exceptions were expired. Twenty advisory entries remained unresolved:

| Package | Locked version | Unresolved advisory IDs |
| --- | --- | --- |
| anyio | 4.13.0 | PYSEC-2026-4025, PYSEC-2026-4024 |
| pyjwt | 2.13.0 | PYSEC-2026-4140 through PYSEC-2026-4152 (all 13 IDs) |
| oauthlib | 3.3.1 | PYSEC-2026-4114 |
| sentence-transformers | 5.5.1 | PYSEC-2026-4164 |
| urllib3 | 2.7.0 | PYSEC-2026-4177, PYSEC-2026-4176, PYSEC-2026-4175 |

These are auditor findings, with severity classified as high by the existing conservative PYSEC fallback. This report has not independently assessed exploitability or selected patched versions. Dependency updates require advisory/version verification and another actual audit; broad new exceptions would conceal the current failure.

### Bandit result

The exact hard-gate command `uv run --no-sync bandit -r src/antigravity_k -ll -x src/antigravity_k/engine/secret_scanner.py` returned **1**. It reported 32 medium-severity B608 findings and one high-severity B324 finding:

| Rule | File | Reported lines |
| --- | --- | --- |
| B608 | engine/cognitive/migration.py | 172, 206, 253, 279, 298 |
| B608 | knowledge/wiki.py | 610 |
| B608 | knowledge/wiki_graph.py | 58, 70, 77, 79, 80, 145, 168, 172, 178, 182, 186, 197 |
| B608 | tools/browser_task_memory.py | 572, 578, 582, 612, 822, 830, 881, 917, 955, 965, 972 |
| B608 | tools/browser_task_memory_store.py | 97, 108, 117 |
| B324 | tools/browser_observation.py | 992 |

Paths above are relative to `src/antigravity_k/`. B608 flags constructed SQL and needs data-flow review before deciding whether an input can reach SQL syntax. B324 is in `_token`: SHA1 hashes the frame label into a four-character identifier slug, with an existing comment stating that it is not a security use. An explicit `usedforsecurity=False` preserves the current identifier behavior and documents that actual purpose. These findings were not waived or edited during this read-only verification.

The workflow's earlier report command with `-f sarif` is unsupported by locked Bandit 1.9.4 and produced no SARIF file. Its `|| true` does not make the separate hard gate pass, but the intended report artifact is absent. Use a supported structured formatter or declare the SARIF plugin dependency explicitly while retaining the hard gate.

The parent applied the supported JSON formatter and ran that actual command in the export. It returned exit 1 and generated parseable JSON with the same 33 findings (32 MEDIUM, one HIGH). This corrects reporting without waiving the findings.

### Internal scanner result

The inline workflow's file traversal and `scan_for_secrets` calls were reproduced only in the clean source export, with sanitized rule/path/count output and an explicit nonzero exit on findings. This returned **1** and flagged 196 files. Findings include environment-credential patterns in source declarations and documentation, and provider/bearer patterns in test fixtures. This count is pattern detection, not confirmation of 196 leaked credentials.

The current inline workflow uses the runtime content redactor directly on entire source files, so its findings need source/context classification. The repository gate must distinguish actual embedded credential values from environment-variable names, regular expressions, documentation placeholders, and intentional test data. A directory-wide exemption would hide actual secrets in those directories and is not an appropriate repair. The shared workspace's private files were not scanned.
