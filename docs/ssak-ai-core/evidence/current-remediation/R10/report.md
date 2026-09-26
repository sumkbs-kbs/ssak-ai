# R10 report — UNKNOWN 실행의 관찰·reconciliation·재시작

## Status
PASS (self-review limitation)

## Changes
- `action_journal.py`: observation_digest / observation_record_id / projection_revision; `attach_observation`; pending_reason
- `ActionDispatcher.submit_observation`: reconstruct from canonical IDs, CAS on expected_receipt_id, idempotent digest replay, never redispatches
- `CognitiveSurfaceAdapter.list_pending_actions` / `submit_observation`
- ACTIVE API: `GET /active/pending`, `POST /active/observe`
- Refusals: UNKNOWN_ACTION / PROJECT_MISMATCH / STALE_RECEIPT_REVISION / MALFORMED_OBSERVATION

## Acceptance
| ID | Result | Observation |
|----|--------|-------------|
| R10-A1 | PASS | `test_r10_a1` — effect then restart observe; dispatch count stays 1 |
| R10-A2 | PASS | `test_r10_a2` + HTTP replay — same observation_record_id / receipt_id |
| R10-A3 | PASS | stale receipt → STALE; foreign project → UNKNOWN; HTTP 409/404 |
| R10-A4 | PASS | timeout does not clear claim; pending_reason queryable |
| R10-E | PASS | evidence/R10/ |
| R10-V | OPEN (self-review) | independent reviewer pending; PASS ≠ release GO |

## Commands
```
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -q -p no:cacheprovider
# 23 passed
.venv/bin/python -m pytest tests/cognitive/test_action_safety.py tests/cognitive/test_active_api.py -k r10 -q -p no:cacheprovider
```

## Limits
Self-review only. HTTP observe requires activate+owned prepared project. Late older observations not yet stored as non-downgrading history rows (only CAS reject / digest idempotency). PASS ≠ CR-14 GO.
