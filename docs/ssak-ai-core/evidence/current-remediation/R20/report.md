# R20 report — GBRAIN meaning / consumers / complexity promotion

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R20-V not claimed.

## Before

- Write-count decay/reward could be misread as task utility / maturity.
- Corrupt GraphML initialized as empty healthy graph (silent success).
- No clear record that production selection does not consume `reward_score`.

## After

- `GBrain.REWARD_SEMANTICS` / `REWARD_PROMOTION_STATUS=experimental_storage_metadata`
- `reward_implies_authority()` always False; `REWARD_SELECTION_CONSUMERS=()`
- Corrupt / malformed snapshot → `GBrainCorruptSnapshotError` (fail-closed)
- Policy doc updated; wiki `KGBinaryValidator` explicitly NOT a GBrain release gate (NOT_RUN)
- Tests: R20-A1..A4 in `tests/test_gbrain.py` — suite **35 passed**

## Acceptance

| ID | Result |
|----|--------|
| R20-A1 | PASS — high reward; no authority/confidence/maturity on node |
| R20-A2 | PASS — corrupt GraphML raises |
| R20-A3 | PASS — no reward selection consumers; search/related ignore reward |
| R20-A4 | PASS — fixed-scale write latency samples recorded |
| R20-E | PASS |
| R20-V | NOT independent — self-review only |

## Limits

- No new reward consumer invented to justify complexity.
- Reward has no separate enable/disable flag; absence of selection use is the control.
- Official KGBinaryValidator OK for GBrain GraphML: **NOT_RUN** (wrong owner — wiki SQLite).
- Self-review ≠ CR-14 / release GO.
