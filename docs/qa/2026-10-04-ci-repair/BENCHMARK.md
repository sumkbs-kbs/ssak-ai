# Benchmark investigation and bounded optimization

Date: 2026-10-04. Published baseline: `0b1aca2d990e08235c784c94f94585ec0c688ac5`.

## Actual failure

GitHub run `37167151612`, job `111332347410` reported `context_enrich latency 1261.4ms exceeds threshold 500ms`. This measures a fresh index of the entire repository, keyword search, and the rule-based summary. It does not measure an LLM response or a paid network request.

The existing 500ms workflow limit and all existing benchmark tests remain unchanged.

## Investigation

A clean `git archive` of the published commit avoids including private, untracked workspace caches. The shared workspace initially scanned 27,380 files; the clean export scanned 2,855 candidates and indexed 2,837 files. Timing the dirty workspace would therefore describe a different workload.

The clean Python 3.13 profile attributed 685ms to building the tree, including 453ms of symbol extraction, and less than 1ms to summarization. A clean, unprofiled Python 3.12 reproduction failed at 694.9ms with the unchanged 500ms limit.

Two avoidable costs were confirmed:

- Python extraction scanned each entire source three times. A combined scan produced identical function, class, and import lists for all 1,411 Python files in the clean archive, with the isolated extraction probe changing from 189.7ms to 90.0ms.
- Common language expressions repeatedly scanned blank lines after an unsuccessful match. The new regression fixture failed with the original JavaScript expression at 1760.8ms. A nonblank-line guard removes that repeated scan. The OO expression uses horizontal leading whitespace instead, because a stricter guard would lose the historical `SomeType` followed by `run(` capture.

The secondary read-only probe checked 519 non-Python source files: the alternative prefixes and required-keyword guards preserved capture lists. A deliberately unusual OO multiline fixture is also retained as a regression test.

## Changes

- `code_tree_symbol_extractor.py`: combine Python scans; count newlines without allocating a list of every line; skip expressions whose required literal keyword is absent; avoid repeated leading blank-line scans while retaining OO multiline discovery.
- `code_tree_indexer.py`: calculate relative directories once, and avoid constructing a `Path` for every filename extension. File selection, hashing, cache behavior, ranking, and summaries retain their existing contracts.
- `test_code_tree_symbol_extractor_performance.py`: preserve Python category order and deduplication, OO multiline discovery, and the blank-line performance regression.

No new exclusion, truncation limit, result cache, or benchmark retry was introduced.

## Verification and limits

The same-process original/optimized library driver produced these full-pipeline wall times in milliseconds:

| Trial | Original | Optimized |
| --- | ---: | ---: |
| 1 | 999.7 | 423.4 |
| 2 | 660.1 | 507.7 |
| 3 | 633.8 | 403.2 |

Every pair produced identical tree bytes, statistics, ranked search results, and summary text. These measurements demonstrate reduced work; they do not establish that every clean checkout meets the 500ms wall-clock limit.

Focused indexer, summarizer, and new regression tests: **43 passed**. Ruff passed. Mypy reported no issues in the two changed source files. Pure-line counts were 250 for the existing indexer, 196 for the extractor, and 30 for the new test module.

The strict combined benchmark invocation still reported **1 failed, 13 passed, 3 skipped, 2 deselected**, with total context enrichment at **1117.4ms**. The skips cover unavailable optional RAG dependencies in the dedicated locked-dev environment. A process snapshot during investigation showed five codebase-memory server processes consuming approximately 790% aggregate CPU plus several Python jobs consuming approximately 300%. Timing on this machine was therefore variable, even though semantic results were stable.

**Status: the bounded optimization is verified; the strict full-repository performance acceptance criterion remains unproven locally and requires the matching new GitHub Actions result.** Do not present the local semantic pass or the blank-line regression pass as a complete benchmark CI pass.

Representative reproduction, with a clean export's source and a dedicated Python 3.12 environment:

```bash
PYTHON_DOTENV_DISABLED=1 \
BENCHMARK_THRESHOLD_CONTEXT_ENRICH=500 \
BENCHMARK_THRESHOLD_CODE_REVIEW=1000 \
BENCHMARK_THRESHOLD_MAX_ENGINE=50 \
PYTHONPATH="$SSAK_CLEAN_EXPORT/src" \
"$SSAK_TEST_PYTHON" -B \
"$SSAK_CLEAN_EXPORT/docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py" \
pytest "$SSAK_CLEAN_EXPORT/tests/test_benchmark_performance.py" \
"$SSAK_CLEAN_EXPORT/tests/test_code_tree_symbol_extractor_performance.py" \
-m benchmark -q --tb=short
```

The temporary home launcher isolates authentication and user storage. Full-program, browser, model inference, and optional RAG performance were outside this benchmark lane.
