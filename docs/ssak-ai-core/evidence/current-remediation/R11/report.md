# R11 report — operational record + selected Experience persistence

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R11-V not claimed.

## Before

- `STOPPED_NO_DELTA` skipped `_record_experience` → no operational trail.
- `form_experience_core` never called from episode completion.
- Surface built a fresh in-memory `ExperienceLedger` each run.
- No provider-neutral ingest/restart path for selected cores.

## After

- Every terminal `_episode` path records operational + selection; `STOPPED_NO_DELTA` forced to `OPERATIONAL_ONLY` (no Experience).
- `EXPERIENCE` selection calls `form_experience_core` with canonical lineage refs only.
- Ledger `pending_sink_records` / `mark_sunk` + runtime `_flush_experience_records` push to `record_sink` without re-commit on shared ledger.
- Surface shares one `ExperienceLedger` across runs; `restore_experience_records` / `ingest_core_record` for restart.
- Idempotent `form_experience` when same episode+digest already stored.

## Acceptance

| ID | Result |
|----|--------|
| R11-A1 | PASS — `test_r11_a1_*` |
| R11-A2 | PASS — `test_r11_a2_*` |
| R11-A3 | PASS — `test_r11_a3_*` |
| R11-A4 | PASS — `test_r11_a4_*` |
| R11-A5 | PASS — `test_r11_a5_*` |
| R11-A6 | PASS — `test_r11_a6_*` |
| R11-E | PASS — this evidence tree |
| R11-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_episode.py tests/cognitive/test_surface.py -q -p no:cacheprovider
# 59 passed
.venv/bin/python -m pytest tests/cognitive/test_episode.py -q -p no:cacheprovider -k r11
# 6 passed
```

## Limits

- Self-review ≠ release GO / CR-14.
- Surface shorthand `context:1` refs are omitted from Reference edges (canonical IDs only).
- Episode reference on ingest still passed explicitly (payload has no dedicated episode field).
