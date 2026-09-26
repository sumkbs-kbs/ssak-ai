# R23 report — knowledge mypy + CLI invalid-input contract

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R23-V not claimed.

## Before

- Scoped mypy on `wiki_graph.py` / `obsidian_links.py` / `wiki.py` reported 5 errors (tuple chunk reuse, tags tuple width, Row|None assign, mirrors_to_remove redef).
- `scripts/benchmark_cognitive_growth.py --manifest /missing` raised `FileNotFoundError` traceback.

## After

- `wiki_graph.py`: separate `node_chunk` / `link_chunk` (no shared `chunk` type collision).
- `obsidian_links.py`: annotate `tags: tuple[str, ...]`.
- `wiki.py`: `expanded_row` for Optional `.get`; drop unused early `mirrors_to_remove` so the population site is the sole definition.
- CLI `load_spec`: missing file / OSError / JSONDecodeError / non-dict / missing `spec` → `GrowthBenchmarkError` with Korean diagnosis; main already maps to EXIT_USAGE (2). No provider/trial path on invalid input.
- Tests: `test_r23_a2_*`, `test_r23_a3_*` in `tests/cognitive/test_growth.py`.

No `# type: ignore` / `Any` added to paper over the five errors.

## Acceptance

| ID | Result |
|----|--------|
| R23-A1 | PASS — mypy Success on 3 files; before log had 5 errors |
| R23-A2 | PASS — missing/malformed → `spec 오류:` + exit 2, no Traceback; store-root not created |
| R23-A3 | PASS — help text retains `--manifest`; demo mode exit 0 with comparison payload |
| R23-E | PASS — mypy before/after, pytest, cli-surface, diff in this folder |
| R23-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m mypy --show-error-codes \
  src/antigravity_k/knowledge/wiki_graph.py \
  src/antigravity_k/knowledge/obsidian_links.py \
  src/antigravity_k/knowledge/wiki.py
.venv/bin/python -m pytest tests/cognitive/test_growth.py -q -p no:cacheprovider
.venv/bin/python scripts/benchmark_cognitive_growth.py --manifest /no/such/manifest.json --mode demo
```

## Limits

- Full-repo mypy not claimed clean — only the three imported knowledge files + this CLI contract.
- Self-review ≠ CR-14 / release GO.
- R20/R21/R22 remain OPEN.
