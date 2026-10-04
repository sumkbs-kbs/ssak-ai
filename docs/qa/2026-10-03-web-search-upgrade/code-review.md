# Web-search upgrade: independent code review

## Verdict

- **codeQualityStatus:** CLEAR
- **recommendation:** APPROVE
- **blockers:** None.

This review is bound to the requested candidate state, not the repository-wide
working tree:

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` (matches `head.txt`)
- `candidate.sha256` SHA-256:
  `09acd657a0cae397ee555d8c37f44603c60fb8ccb601395d7c7203e5a831d443`
- Every entry in `candidate.sha256` matched the candidate file bytes at review
  time, including the production modules, tests, dependency files, and manual
  driver.

## Scope reviewed

The review compared the supplied baseline copies for the pre-existing engine,
tool, dependency manifest, and lock file; it inspected the three new modules
and their new tests in full. It also inspected the two modified regression
tests and the supplied evidence artifacts.

Checked production files:

- `src/antigravity_k/tools/web_html.py`
- `src/antigravity_k/tools/web_search_html.py`
- `src/antigravity_k/tools/web_reader.py`
- `src/antigravity_k/tools/web_search_engine.py`
- `src/antigravity_k/tools/web_search_tool.py`
- `pyproject.toml`, `uv.lock`

Checked tests and evidence:

- `tests/test_web_html.py`, `tests/test_web_search_html.py`,
  `tests/test_web_reader.py`, `tests/test_web_search.py`, and
  `tests/test_web_search_quality.py`
- `regression.log`, `regression-expanded.log`, `reader-red.log`,
  `reader-green.log`, `fallback-test.log`, `lint.log`, `typecheck.log`,
  `lock.log`, `install.log`, `routing-recheck.log`, and `manual-live.jsonl`

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

The parser change removes position-based title/snippet pairing and binds a
snippet to its owning DDG result container, with an isolated-node fallback.
The tests exercise both HTML and Lite adapters, class/attribute drift, entity
handling, challenge controls, invalid and private targets, DDG redirect
unwrapping, and the no-snippet-first-result regression. The result URL remains
subject to the existing public-HTTP policy before it enters either adapter.

The reader change streams both synchronous Jina and asynchronous scraper
responses, rejects non-text content and detected challenge pages, and caps
decoded stream bytes. The private-redirect test now uses the actual streaming
client path, so it would fail if the second redirect target were fetched before
the public-address check. Its coverage is behavior-facing rather than an
implementation mirror.

The HTML extractor's semantic-root selection, body fallback, hidden-subtree
exclusion, malformed markup recovery, whitespace/code/table handling, and
nonpositive cap are all directly exercised. `Selector(..., adaptive=False,
huge_tree=False)` is explicit at `web_html.py:117`; the new dependency is
pinned consistently in `pyproject.toml` and `uv.lock`.

## Required skill-perspective check

The `omo:programming` and `omo:remove-ai-slops` skills were loaded and applied
before judging maintainability and tests. The Python reference was also
consulted for typed errors, async resource ownership, and HTTP use.

- **Programming perspective:** no new `Any`, `cast`, type-ignore, broad
  exception catch, speculative abstraction, or prompt/prose assertion was
  introduced. The mutable parser accumulator is a documented parser state
  object; the public result value is frozen and slotted. The direct
  `basedpyright` binary could not be run because its virtual-environment
  interpreter target is missing; the candidate's supplied `typecheck.log`
  records `0 errors, 0 warnings`. This is a local verifier limitation, not
  evidence of a candidate failure.
- **Remove-AI-slops perspective:** no deletion-only or tautological tests were
  found. The added tests distinguish real externally visible behavior and
  would fail for the named regressions. The parser and bounded-reader modules
  serve concrete shared seams used by all three DDG adapters or both response
  paths; there is no needless extraction, parsing, normalization, or
  single-use abstraction in scope. No violation found.

The repository's codebase-memory graph tools were not exposed in this review
session, so graph-first discovery was unavailable. The supplied scoped file
list and baseline artifacts were read directly; this is limited to the stated
candidate scope.

## Verification

- `.venv/bin/pytest -q tests/test_web_html.py tests/test_web_search_html.py
  tests/test_web_reader.py tests/test_web_search.py tests/test_web_search_quality.py`
  → **189 passed** (19 pre-existing/dependency deprecation warnings from lxml).
- `.venv/bin/pytest -q tests/test_web_reader.py -x` → **10 passed**.
- `.venv/bin/ruff check` for all candidate production and test files → **All
  checks passed**.
- `git diff --check` for the candidate scope → clean.
- Supplied full/expanded regression logs each contain one unrelated routing
  circuit-timing failure (`tests/test_ssak_search_routing.py`), reproduced in
  `routing-recheck.log`; it is outside the candidate files and not treated as
  a web-search-upgrade regression. The supplied `manual-live.jsonl` records
  successful private-URL blocking, live Python documentation reading, and a
  cited production search.

## Final candidate stamp (formatter follow-up)

**Approved: CLEAR / APPROVE** for the refreshed candidate manifest.

- HEAD remains `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Refreshed `candidate.sha256` digest:
  `9e2409a8d5109cc92521f41bf78c4943121f33c353c2d1579de0a592b65fdb6c`.
- A complete `sha256sum -c candidate.sha256` pass succeeded for all 13
  candidate entries after the formatter run.
- Re-inspection of the two changed production files found only the reported
  formatter layout changes: an empty-line adjustment, the harmless spacing in
  `text[: max(0, max_chars)]` at `web_search_engine.py:460`, and wrapping of
  the existing list-comprehension return at `web_search_tool.py:679-681`.
  No expression, branch, argument, import, or output behavior changed.
- `regression-final.log` records the full candidate suite passing: **247
  passed**. `routing-before-task.log` shows the same isolated circuit-timing
  failure as `routing-recheck.log`, proving it predates this task and remains
  outside candidate scope.

## Final freeze stamp: MIME boundary and late challenge marker

**Approved: CLEAR / APPROVE** for the frozen candidate.

- HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Final `candidate.sha256` digest:
  `c96c377d16045c9104d0ead35a7ab61c72adcec51cba195d267e5be02a9612d9`.
- A complete final `sha256sum -c candidate.sha256` pass succeeded for all 13
  candidate entries.

The MIME boundary correctly preserves the literal, capped body for all allowed
non-HTML `text/*` responses, including `text/plain` and `text/markdown`, at
`web_search_engine.py:796-799`. Only `text/html` and `application/xhtml+xml`
reach DOM text extraction. This fixes the demonstrated loss of explanatory
literal `<main>` and `<article>` strings without widening accepted media types
or bypassing the bounded reader.

Challenge classification still requires a recognized title in the first 4 KiB;
only after that inexpensive title decision does it scan the already bounded
(at most 5 MiB) decoded body for a provider-specific marker
(`web_reader.py:15-34`). This catches a late Cloudflare marker while retaining
the prior safeguard against ordinary pages that merely discuss CAPTCHA. The
test is behavior-facing: its supplied red proof failed before the MIME fix for
both wire types, and the late-marker case would fail if either the full bounded
body scan or provider-marker condition were removed.

Verification after this frozen candidate:

- Independent scoped run: **192 passed**,
  `tests/test_web_html.py tests/test_web_search_html.py tests/test_web_reader.py
  tests/test_web_search.py tests/test_web_search_quality.py` (19 lxml
  dependency deprecation warnings).
- Supplied `reader-final.log`: **13 passed**; supplied `typecheck-final.log`:
  **0 errors, 0 warnings**.
- Supplied `regression-final.log`: **247 passed**. The pre-existing routing
  circuit-timing failure is still proved identical before task work in
  `routing-before-task.log`; it is not a candidate regression.
