# Evidence publication consistency repair

## Scope and temporary artifacts

This lane owns the public core document links and the measured digest artifact. It does not change any gate, test, coverage floor, or historical verdict. Raw local QA logs, source captures, and authentication records remain excluded from publication.

Temporary clean export and reports will be created under `/tmp/ssak-ci-evidence-20261004-agent` and removed after validation. The export is based on published commit `0b1aca2d990e08235c784c94f94585ec0c688ac5`; only the lane's approved document edits are overlaid. This deliberately excludes unrelated staged and untracked local evidence.

## Investigation

Hypotheses: public summaries link to local-only evidence; the measured digest artifact predates the published document set; or substantive source edits invalidated a previously recorded reverification. The unchanged gate will distinguish these cases in the clean export.

## Confirmed cause

The clean published checkout reproduced the unchanged fast gate with exit 1: seven of nine stages passed; `review` and `digest_drift` failed. There were 52 unresolved Markdown links across 15 public core documents. Every referenced raw artifact exists in the original local workspace, but none is in the published checkout. Local uncommitted evidence had hidden this publication inconsistency.

Separately, the stored digest report described 50 pins across 13 documents with 10 matches and 40 reverifications. Measurement of the published bytes found eight matches, 40 reverifications, one ordinary drift, and one stale reverification. The document and pin sets are unchanged; their per-status records differ because source bytes changed. The affected historical document is `T11_surface.md`:

| Referenced source | Observed state | SHA-256 of published bytes |
|---|---|---|
| `src/antigravity_k/api/routes/__init__.py` | drift without a current reverification | `90cab572c83a3b75e9d014a62cfbdd21b639795bd7b28f9e8a0e363af7b5f117` |
| `src/antigravity_k/cli.py` | stale reverification | `f88b31e943459ee3b1d8fde4cce5ce74e6fc996c6bcd641447ec8cbfc203b8af` |

## Repair and observed verification

The 52 unavailable public links now retain their exact filenames as explicit local-only archive references. Each affected document states that the raw evidence remains unpublished and that its historical results do not certify today's source. No historical PASS, FAIL, INCONCLUSIVE, NOT_COMPLETE, source hash, result count, or pilot limitation was changed. Raw evidence and private authentication records were not added.

The clean export was initialized as a separate Git repository at the published commit so citation tracking sees the same tracked file set as CI. Only the 15 Markdown edits were overlaid. An initial archive-only attempt lacked this Git context and is not used as evidence.

From the clean export, using the existing environment with `PYTHON_DOTENV_DISABLED=1` and `PYTHONPATH` pointing to the export's `src`:

```sh
.venv/bin/python -B scripts/evidence_gate.py --tier fast --json REPORT.json --summary REPORT.md
.venv/bin/python -B scripts/digest_drift.py --emit-json
.venv/bin/python -B -c 'import sys; sys.path.insert(0, "scripts"); import architecture_review; result = architecture_review.check_doc_links(); print(result); raise SystemExit(0 if result.passed else 1)'
```

| Check | Actual result |
|---|---|
| Published baseline fast gate | exit 1; seven PASS, two FAIL; broken links and stale/outdated digest |
| Link-only overlay fast gate | exit 1; seven PASS, two FAIL; remaining failure is stale/outdated digest |
| Link checker after overlay | exit 0; 381 relative links resolve; zero broken links |
| Historical-content reversal comparison | 15 documents equal the original nonblank text after reversing only availability annotations |
| `git diff --check` for the core documents | exit 0 |

Independent read-only documentation review returned **APPROVE, no blocking findings**, bound to baseline `0b1aca2d990e08235c784c94f94585ec0c688ac5` plus SHA-256 `8d1617629c0596f7c2ba1ecce7fb96bc9de21f406e84193b3d21ae60b0120995` of the 15-document unstaged diff. The reviewer independently confirmed the 52 exact local references, public absence, and unchanged historical bodies. Private raw contents were not opened. This approval covers documentation availability edits only, not current source behavior.

The link repair is complete. Digest renewal is handed to the integration owner: actually reverify the affected current CLI/surface behavior, record only that observed scope and its exact bytes, then regenerate the measured artifact after all source changes have landed. This lane does not relabel the stale source as reverified or claim the complete fast gate passed. Release-artifact and regression-ledger layers remain outside this fast-tier execution and are not counted as PASS.

## Cleanup

At the integration owner's explicit request, the temporary export and reports under `/tmp/ssak-ci-evidence-20261004-agent` are retained for final verification and handed to that owner for cleanup after completion. No debug instrumentation or user configuration was changed. Final integration evidence, including any later gate PASS and remote CI result, belongs to the integration owner's report.
