---
title: Financial numeric extraction validation
tags: [qa, search, financial-evidence]
date: 2026-10-03
---

# Financial numeric extraction validation

## Current integrated candidate

The root retake subsequently fixed canonical text for inexact `value` as well as
`normalized_value`. Current parser SHA-256 is
`5289fe93e19de50035123086a0778c2235f0631c697fc40231e1a3006d8d5eb5`.
The authoritative current file manifest is [source.sha256](source.sha256), with
[independent final approval](task-finance-review.md). The two new adapter and
HTTP regressions first failed in [canonical-text-red.log](canonical-text-red.log)
and then passed with the 20-case finance suite in
[canonical-text-green.log](canonical-text-green.log). The root integrated suite
passed 357 cases before the later independent chat-routing repair; see the final
[RESULTS](RESULTS.md) for the complete final scope. The 18/135 counts and
`66a4547...` manifest below describe the earlier worker candidate only.

## Contract

- `normalized_value` is exact canonical Decimal text. Its `unit` is a normalized base: an explicit currency code, `percent`, `percentage_point`, `basis_point`, or `base` when no currency was supplied.
- `display_unit` retains source notation such as `조 억 원`, `억`, or `%p`.
- `value` is a legacy JSON scalar only when the Decimal is exactly representable as an IEEE-754 float; otherwise it is the same exact string as `normalized_value`.
- `raw_text` and `source_index` remain the evidence linkage. The parser does not infer a currency, an as-of date, or meaning for arbitrary unlabeled numbers.

## Historical evidence

The following artifacts are retained for audit history only; they are not final-candidate proof:

- `financial-red.log` records the missing-parser import before this implementation existed.
- `financial-scale-combination-red.log` records the former split-scale extraction.
- `financial-numeric-contract-red-current.log` records six earlier contract failures.
- `financial-numeric-contract-final-targeted.log`, `financial-numeric-contract-final-regression.log`, and `financial-numeric-contract-final.sha256` predate the long-Decimal correction and must not be used as final hashes or pass counts.

## Earlier worker RED → GREEN evidence

All current artifacts below are under the repository-root `.omo/evidence/` directory.

| Scenario | Invocation | Observable | Artifact |
| --- | --- | --- | --- |
| Baseline extractor and HTTP omission | isolated import of `/tmp/ssak-external-baseline.JAxkH3/data_extractor.py` plus its `system_api.py` router through `FastAPI` `TestClient` | Old extractor returned `value=[None, None]`, `unit=['', '']`; its HTTP 200 response omitted `extracted.numeric_data` | `financial-numeric-baseline-red.log` |
| Long Decimal formatting defect | `HOME=/private/tmp/ssak-financial-exactness-red PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_financial_numbers.py tests/test_search_numeric_contract.py` | Two failures: long USD decimal `normalized_value` rounded and long `조원` value rounded | `financial-numeric-exactness-red.log` |
| Large-whole plus fractional-minor precision defect | `HOME=/private/tmp/ssak-financial-fraction-red PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_financial_numbers.py tests/test_search_numeric_contract.py` | Two failures for `1조 0.12345678901234567890123456789만` and `1조 0.0000000000000000000000000001만` | `financial-numeric-fractional-precision-red.log` |
| Final parser and actual HTTP contract | `HOME=/private/tmp/ssak-financial-exactness-green PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_financial_numbers.py tests/test_search_numeric_contract.py` | `18 passed`; real route uses only a provider seam and serializes the long scaled amount as exact text | `financial-numeric-exactness-green.log` |
| Related extraction and search regression | `HOME=/private/tmp/ssak-financial-regression-green PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_financial_numbers.py tests/test_search_numeric_contract.py tests/test_data_extractor.py tests/test_search_extract_e2e.py` | `135 passed`; one Starlette/TestClient deprecation warning | `financial-numeric-exactness-regression.log` |
| Lint and parser type check | `.venv/bin/ruff check src/antigravity_k/engine/financial_numbers.py src/antigravity_k/engine/data_extractor.py src/antigravity_k/api/routes/system_api.py tests/test_financial_numbers.py tests/test_search_numeric_contract.py`; `.venv/bin/python -m basedpyright --level warning src/antigravity_k/engine/financial_numbers.py` | Ruff passed; `0 errors, 0 warnings, 0 notes` | `financial-numeric-exactness-ruff.log`, `financial-numeric-exactness-types.log` |
| LSP observation | `mcp__lsp__diagnostics` on the five owned files | New parser and its unit test have no diagnostics; unrelated route and third-party TestClient typing warnings are recorded without suppressions | `financial-numeric-exactness-lsp.md` |
| Integration compile and patch whitespace | `.venv/bin/python -m py_compile src/antigravity_k/engine/financial_numbers.py src/antigravity_k/engine/data_extractor.py src/antigravity_k/api/routes/system_api.py`; `git diff --check` | Both commands succeeded with empty output | `financial-numeric-exactness-compile.log`, `financial-numeric-exactness-diff-check.log` |

## Earlier worker source hashes

`financial-numeric-exactness-final.sha256` identifies that historical worker candidate:

| File | SHA-256 |
| --- | --- |
| `src/antigravity_k/engine/financial_numbers.py` | `66a4547d656a9f11959aaa64cf8fce9ed4d2a26c353ffd0a2b7d19d2edc1b0c5` |
| `src/antigravity_k/engine/data_extractor.py` | `593d0b2e3a5b9a178dc20b446afe6db56c4887870b120bde51b20b5c1fc4a316` |
| `src/antigravity_k/api/routes/system_api.py` | `2cfcf47487039bb0ecce66c5a6f2ade0fc3b277ddb1a3f33080daba90b1179e1` |
| `tests/test_financial_numbers.py` | `c8029f8530a8aeeeccc480ef1e0373f54f4af5706cf24d46e1468032e650a657` |
| `tests/test_search_numeric_contract.py` | `5192d81955cc91051a29b5ce641b7a8376d2065de0ff2f37840ecc7229dd8dca` |
