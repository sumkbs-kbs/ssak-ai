# Dependency audit verification — 2026-10-04

## Outcome and scope

The real dependency gate still **fails (exit 1)** on the current lock: 20 unresolved advisory entries across five packages. The five existing chromadb advisory entries remain covered by the unchanged exact exceptions. No dependency version, exception, scanner setting, or shared environment was changed in this task. These findings were previously hidden behind the earlier gitleaks checkout failure; they are separate from that initial CI failure.

`pyproject.toml`, `uv.lock`, `config/audit-exceptions.json`, and `scripts/audit_python_dependencies.sh` match HEAD. Their SHA-256 values and Git comparisons are captured in `.omo/evidence/ci-dependencies-20261004/unchanged-source-manifest.json`.

The audit used the script's default real `uvx --from pip-audit==2.10.1 pip-audit` command, with no injected auditor or exception override. A direct JSON audit independently reproduced the findings. Both use frozen exports; neither synchronizes the shared virtual environment.

## Verified release candidates, not applied changes

| Package | Current | Verified candidate | Advisory evidence |
| --- | --- | --- | --- |
| anyio | 4.13.0 | 4.14.2 | PYSEC-2026-4024 and 4025 name 4.14.2 as fixed. |
| pyjwt | 2.13.0 | 2.15.0 | PYSEC-2026-4141 requires 2.15.0; eleven other entries name 2.14.0. PYSEC-2026-4146 uses `last_affected: 2.13.0`, without a fixed-version field; see the runtime verification below. |
| oauthlib | 3.3.1 | 4.0.0 | PYSEC-2026-4114 names 4.0.0. This is a major version with documented breaking changes; compatibility work is required before adopting it. |
| sentence-transformers | 5.5.1 | 5.6.0 | PYSEC-2026-4164 names 5.6.0. |
| urllib3 | 2.7.0 | 2.8.0 | PYSEC-2026-4175, 4176, and 4177 name 2.8.0. |

All five candidate versions have published, non-yanked files and no vulnerability entries in their live PyPI version JSON at verification time. This metadata is not a complete security or product compatibility guarantee. Captures: `pypi-before-<package>.json` and `pypi-fix-<package>.json` in the evidence directory.

The complete set of 20 primary advisory URLs is preserved in `advisory-sources.json`, with each raw PyPA advisory captured as `<PYSEC-ID>.yaml`. Representative primary sources: [AnyIO](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/anyio/PYSEC-2026-4025.yaml), [PyJWT required 2.15.0 release](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/pyjwt/PYSEC-2026-4141.yaml), [OAuthLib](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/oauthlib/PYSEC-2026-4114.yaml), [sentence-transformers](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/sentence-transformers/PYSEC-2026-4164.yaml), [urllib3](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/urllib3/PYSEC-2026-4177.yaml).

### PyJWT advisory metadata caveat

[The maintainer advisory GHSA-gvp8-978c-rx2q](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-gvp8-978c-rx2q) still lists no patched version and discusses release planning. [PyPA's corresponding record](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/pyjwt/PYSEC-2026-4146.yaml) limits its known affected range to 2.11.0–2.13.0. An empty `fix_versions` field therefore must not be interpreted as an unbounded affected range or proof that 2.15.0 contains a fix.

The advisory's actual failure was tested in isolated `uv run --no-project --with pyjwt==...` environments: decode an expired token with signature verification disabled using a mutable options mapping, restore signature verification in that same mapping, and decode the expired token again. On 2.13.0, the mapping was mutated and the expired token was accepted (probe exit 1). On 2.15.0, the mapping remained unchanged and the expired token raised `ExpiredSignatureError` (probe exit 0). Captured installed source shows `dict(options)` before defaults are applied. This directly verifies that specific regression in the candidate; it is not application authentication compatibility coverage or evidence that the current lock is fixed.

### OAuthLib release discrepancy and compatibility boundary

[The maintainer advisory](https://github.com/oauthlib/oauthlib/security/advisories/GHSA-xpv3-w29h-x7cv) names 3.3.2, but the live PyPI release inventory contains no 3.3.2 release. PyPA names 4.0.0, and the [4.0.0 changelog](https://raw.githubusercontent.com/oauthlib/oauthlib/v4.0.0/CHANGELOG.rst) contains the PKCE comparison repair alongside breaking JSONP removal and OAuth grant validation changes. Captures: `oauthlib-maintainer-advisory.html`, `oauthlib-releases.json`, and `oauthlib-4-changelog.rst`.

The locked parent `requests-oauthlib==2.0.0` declares `oauthlib>=3.0.0` without an upper bound, verified from its published PyPI metadata (`requests-oauthlib-metadata.json`). A resolver dry run accepts all five exact candidates and changes exactly those five packages. That is dependency resolution evidence only; it does not prove runtime compatibility. No OAuthLib major upgrade was applied. Application reachability or exploitability of each advisory was not established; the conservative existing gate remains unchanged.

## Reproducible observations and artifacts

All paths below are relative to `.omo/evidence/ci-dependencies-20261004/` unless otherwise stated.

| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Real current base + shipped Docker extras gate | `AGK_AUDIT_RECORD="$PWD/.omo/evidence/ci-dependencies-20261004/current-inputs.json" bash scripts/audit_python_dependencies.sh` | Exit **1**; `unresolved` length **20**, `excepted` length **5**, `expired` empty. | `current-gate.log`, `current-gate.exit`, `current-inputs.json` |
| Independent real auditor JSON | `uv export --frozen --no-dev --no-editable --no-emit-project --extra rag --output-file .omo/evidence/ci-dependencies-20261004/before-requirements.txt`; `uvx --from pip-audit==2.10.1 pip-audit --strict --desc --disable-pip --requirement .omo/evidence/ci-dependencies-20261004/before-requirements.txt --format json` | Exit **1**; **128** audited packages, **25** advisory entries, **6** affected packages. | `before-requirements.txt`, `before-audit.json`, `before-audit.stderr` |
| Candidate resolution without writing lock | `uv lock --dry-run --upgrade-package anyio==4.14.2 --upgrade-package pyjwt==2.15.0 --upgrade-package oauthlib==4.0.0 --upgrade-package sentence-transformers==5.6.0 --upgrade-package urllib3==2.8.0` | Exit **0**; exactly five package updates. | `lock-dry-run.log` |
| PyJWT advisory regression on current version | `uv run --no-project --python 3.12 --with pyjwt==2.13.0 python .omo/evidence/ci-dependencies-20261004/pyjwt_options_probe.py` | Exit **1**; `options_unchanged=false`, `expired_token_rejected=false`. | `pyjwt_options_probe.py`, `pyjwt-options-before.json`, `pyjwt-options-before.exit` |
| Same regression on candidate version | `uv run --no-project --python 3.12 --with pyjwt==2.15.0 python .omo/evidence/ci-dependencies-20261004/pyjwt_options_probe.py` | Exit **0**; `options_unchanged=true`, `expired_token_rejected=true`. | `pyjwt-options-regression.json`, `pyjwt-options-after.exit` |
| Preserve existing lock and policies | `git diff --exit-code HEAD -- pyproject.toml uv.lock config/audit-exceptions.json scripts/audit_python_dependencies.sh` | Exit **0**, all four files match HEAD. | `unchanged-source-manifest.json` |

Frozen input records show base **71**, rag **149**, union **149** locked package entries. The auditor evaluates host markers, auditing **128** packages on this macOS Python 3.12 environment. Linux/container execution has not been claimed. No candidate full-suite run, candidate lock audit, application authentication compatibility run, container build, commit, push, or green CI rerun is claimed.

A future dependency repair can use the verified versions above, then perform the affected runtime tests and repeat the real base-plus-shipped-extras audit on the resulting lock. Existing exceptions must remain exact and must not be broadened to hide these findings.
