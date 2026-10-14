# Backend failure recheck

Date: 2026-10-04. Read-only product/test lane; only backend-recheck-* evidence written. No installation, Git mutation, user-store use, authentication-store use, real message, or root-server interaction.

## Result

All **88 historical browser failures now PASS**, mapped individually in `backend-recheck-browser-mapping.json`. The complete six-file rerun produced **186 passed, 1 skipped, 20 deselected**, exit **0**, in **106.29s**. The skipped live-model case is explicitly NOT verified; it was not one of the 88 historical failures. Voice/memory-recall modules were imported during collection and their 20 tests deselected, exercising the repaired collection boundary without claiming those assertions ran.

| Browser module | Historical failures now passing | Current whole-file passes | Skipped |
|---|---:|---:|---:|
| actions | 28 | 33 | 0 |
| adversarial | 25 | 26 | 0 |
| approval | 20 | 37 | 0 |
| benchmark | 6 | 14 | 0 |
| loop | 6 | 32 | 1 |
| recovery | 3 | 44 | 0 |

The independent search benchmark remains **2 failed, 16 passed, 11 errors**, exit **1**. First rerun: 3.44s; after concurrent source edits were detected, a second run with unchanged relevant before/after hashes reproduced the same counts in **11.68s**. This is not caused by missing Chromium: the legacy provider arm returns empty results on all ten fixture cases, failing `legacy:non_empty_results` and `legacy:authority_required`; the integrated arm produces nDCG 0.7373 and valid-source ratio 0.9600. A standalone cache assertion also reports `error='empty_result'`, `cache_supported=False` and `warm_provider_requests=8`.

The two failing selectors are:
- `tests/test_ssak_search_benchmark.py::test_anchor_can_only_be_refreshed_with_a_recorded_reason`
- `tests/test_ssak_search_benchmark.py::test_legacy_arm_really_observes_the_cache`

All eleven setup-error selectors and exact full traces are in `backend-recheck-remaining-failures.json`. They share `slice_anchor` -> `_run(..., expect=0)` at test lines 87/62, which receives exit 1. Their adversarial bodies did not run; none is counted as passed. Root cause below the legacy empty-result observation is not asserted by this lane.

## Historical baseline remains historical

The original run was **113 failed, 7846 passed, 19 skipped, 20 xfailed, 11 errors, 25 deselected**. Source/HEAD drift prevents subtracting the 88 repaired browser cases from that run and calling the remainder a current full-suite result. The original browser breakdown was 78 direct cache-launch errors and ten downstream consequences. This current check covers every one of those selectors, not a representative sample. Other non-browser baseline failure groups remain outside this delegated lane and require their owners' verification.

## Invocation and isolation

Exact argv, unique cwd, environment overrides, timestamps, timeout bounds and exit codes are saved in `backend-recheck-browser-command.json`, `backend-recheck-search-command.json`, and `backend-recheck-search-stable-command.json`.

Existing `isolated_entry.py` patched `Path.home()` and set AGK storage/auth paths before product imports, with `sitecustomize.py` propagation into Python children. The actual HOME environment variable was preserved so already-installed Playwright Chromium cache lookup remained valid. Unique temporary cwd and TMPDIR enclosed test and pytest storage; a cwd `src` symlink permitted the existing source-reading contract without altering it. Benchmark subprocesses use their existing repository cwd, with temporary explicit output/storage paths. No test was edited, weakened, or newly skipped.

## Source and cleanup

Historical reported HEAD sequence was `0b1aca -> 28f021 -> 02b9cde`; this run started and ended at `02b9cde7fb0e890330ddebfec5ff8ad9ddc50435`. Initial 1494 tracked source/test/script/vendor SHA256 hashes are recorded. During the broader check, other agents changed `tool_loop.py`, `web_search_tool.py`, and `test_citation_source_links.py`; exact hashes are in `backend-recheck-source-after.json`. Browser contract source was unchanged. The search rerun records unchanged hashes for its test, benchmark script, web-search tool and tool-loop source. These are working-tree results, not an immutable clean-commit certification.

All three unique temporary roots were removed. Process comparison found no newly remaining Chromium, Playwright driver, or browser-task child. Root port 8000 remained on PID **46399** before and after. Existing processes were not stopped. Cleanup artifacts retain the process/listener proof.

## Evidence boundary

`backend-recheck-manual-qa.md` contains the required `manualQa` fields, all 88 selector-level passes, all reproduced search failures, rejected live-model coverage, adversarial mappings, exact invocations, and artifact references. This is an automated CLI/production-browser contract recheck. It does not claim separate dashboard GUI/manual screenshot coverage. Every PASS is backed by non-empty log/XML artifacts.
