# R17 report — live pilot input contract · raw trial ledger

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R17-V not claimed.

## Before

Harness validated min trials / fixture kind / snapshot limits, but had no public pre-registration schema, no append-only raw trial ledger, no NOT_COMPLETE on timeout, safety only checked the Mature arm, and primary metric improvement was hard-wired to retries. Aggregation could not be replayed from raw events alone.

## After

- `PilotPreRegistration` + `validate_live_pilot_inputs` (overlap IDs, TRAIN content leak, order/metric allowlists, nonnegative/finite budgets) refuse **before** provider calls.
- `RawTrialLedger` / `TrialLedgerEntry` record STARTED → COMPLETED|TIMEOUT|FAILED|BUDGET_EXHAUSTED.
- Timeout/exception/budget → `LivePilotStatus.NOT_COMPLETE` with partial ledger preserved.
- Safety and duplicate checks cover **both** Fresh and Mature arms.
- Verdict uses registered `primary_improvement_metric` via `PRIMARY_METRIC_FIELDS`.
- Mechanisms/seed/`trial_uid` are passed on `LiveTrialRequest`.
- `aggregate_from_ledger` independently recomputes arm summaries and verdict.

## Acceptance

| ID | Result |
|----|--------|
| R17-A1 | PASS — overlap / negative budget / unsupported order·metric refuse with provider call 0 |
| R17-A2 | PASS — fresh or mature safety fails whole verdict |
| R17-A3 | PASS — 5th trial timeout keeps 4 completions + TIMEOUT + NOT_COMPLETE |
| R17-A4 | PASS — aggregate_from_ledger matches harness means/verdict |
| R17-E | PASS — this evidence tree |
| R17-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_live_pilot.py -q -p no:cacheprovider
# 16 passed
```

## Limits

- Self-review ≠ release GO / CR-14.
- Live/real provider smoke is still R18; this card is input contract + ledger only.
- Family leakage uses task `category` + content digest; not a separate family taxonomy.
