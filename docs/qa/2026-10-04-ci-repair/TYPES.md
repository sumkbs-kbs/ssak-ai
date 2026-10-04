# Strict optional CI type repair

Baseline commit: `0b1aca2d990e08235c784c94f94585ec0c688ac5`.
These results cover the working tree patch below, not a remote Actions run.

## Confirmed cause

The CI typecheck executes `mypy src/` with `strict_optional = true` from
`pyproject.toml`. The separate pre-commit parity gate passes
`--no-strict-optional`, so its success did not establish the stricter CI contract.
Running `.venv/bin/python -m mypy src/` before the patch reproduced exit 1:
two errors in two files, with 573 source files checked.

- `financial_numbers.py:201`: `candidate` was first inferred as
  `_FinancialMatch`, then reused for `_scaled_match()`, whose result may be `None`.
- `cognitive/growth.py:1852`: `pin_of()` returns `PolicyPin | None`.
  Checking one call for `None` cannot narrow the result of a second call.

## Change

- Use `scaled_candidate` for the optional parse result and explicitly require
  a non-null result before overlap detection and append.
- Read `observed_pin` once, then reject either a missing pin or a changed
  policy version. The existing rejection exception remains in place.

No checker settings, test expectations, policy activation rules, or authority
checks were weakened. Both changes model the existing behavior accurately.

## Verification

Local interpreter: Python 3.13.12. CI uses Python 3.12; the parent task must
observe the new remote run before claiming the CI job passes.

| Command | Observed result |
| --- | --- |
| `.venv/bin/python -m mypy src/` | Exit 0; no issues in 573 source files |
| `.venv/bin/python -m basedpyright src/antigravity_k/engine/sandbox.py src/antigravity_k/tools/search_benchmark.py` | Exit 0; 0 errors, 0 warnings, 0 notes |
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -B docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_financial_numbers.py tests/cognitive/test_growth.py -q` | 40 passed in 11.60 seconds |
| `.venv/bin/python -m ruff check src/antigravity_k/engine/financial_numbers.py src/antigravity_k/engine/cognitive/growth.py` | All checks passed |
| `.venv/bin/python -m ruff format --check src/antigravity_k/engine/financial_numbers.py src/antigravity_k/engine/cognitive/growth.py` | 2 files already formatted |

The `basedpyright` executable in this existing local environment still has an
old checkout path in its shebang. Running the module with the current Python
interpreter avoids that launcher issue without changing the environment.

A separate direct library driver patched `Path.home()` to a temporary directory
before any project import and directed config/storage paths there. It observed:

- `3억 2만원`, `4.2%`, and `25bp` normalize respectively to `300020000 KRW`,
  `4.2 percent`, and `25 basis_point` in source order.
- Malformed tokens `-$-5, 1,23원, 1.2.3%` return no financial numbers.
- A default deterministic growth fixture completed validation, produced two
  behavior traces for two training episodes, and retained the expected pinned
  policy version. This does not establish live-model growth quality.

Initial manual-driver assertions used unsupported compound wording and an
incorrect expectation that an invalid scaled compound forbids every independently
recognized currency suffix. Those assertions were corrected to the parser's
existing documented/tested scope; no parser behavior was changed to fit them.

## Patch identity and review

SHA-256 of the reviewed source files:

- `financial_numbers.py`: `68e0911c9418bbdd2215b4b87e88ed9db4281ef9cd53306edd66279bb6a3f561`
- `cognitive/growth.py`: `e10ece4427945efaa40a052c62d84a1231bdbe37a43d422ca9fc044f2db66c5d`

The financial parser remains responsible for explicit financial quantities;
growth remains responsible for deterministic growth evaluation. No new helper,
union escape hatch, exception handler, or public input boundary was introduced.
The parser is 188 nonblank, noncomment lines; the pre-existing growth module is
1842 and this patch removes two lines. A broad module split is outside this
repair. Existing behavior tests remain unchanged; the strict checker is the
failing-before/passing-after contract for this static typing defect.

Temporary homes were removed by their context managers. The temporary mypy
output file was removed after recording the results here. No debugger probes,
ports, global environment overrides, or commits were created by this lane.
