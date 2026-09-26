# R09 report — durable episode·decision·receipt 계보

## Status
PASS (self-review limitation)

## Changes
- `action_journal.py`: claim-only → projection with `action_record_id`, `status`, `receipt_id`, `list_pending`, `attach_receipt`, schema migrate-on-open
- `ActionReceipt.to_record`: `record_id=receipt_id` (ExecutionReceipt ID pattern); `REL_ACTION` reference to action
- `new_receipt_id()`: durable `execution_receipt:…` IDs replace `receipt:key:n` strings
- `actions._finish`: journal `attach_receipt` (PENDING/SETTLED); `pending_claims(project_id)` for restart
- `action_lifecycle.reconcile`: append new receipt + `REL_SUPERSEDES` prior; prior canonical bytes untouched
- Fail-closed persist-before-effect unchanged (A2 covered by raise-before-dispatch)

## Acceptance
| ID | Result | Observation |
|----|--------|-------------|
| R09-A1 | PASS | `test_r09_a1` — store.read(receipt_id)==receipt; action reverse-link; republish same id |
| R09-A2 | PASS | `test_r09_a2` — sink OSError → tool calls == [] |
| R09-A3 | PASS | `test_r09_a3` — new dispatcher + same journal lists pending with original action/receipt IDs |
| R09-A4 | PASS | `test_r09_a4` — prior model_dump_json bytes identical; new row supersedes |
| R09-E | PASS | evidence/R09/ (manifest + pytest logs) |
| R09-V | OPEN (self-review) | independent reviewer not yet; PASS ≠ release GO |

## Commands
```
.venv/bin/python -m pytest tests/cognitive/test_actions.py tests/cognitive/test_store.py tests/cognitive/test_episode.py -q -p no:cacheprovider
# 72 passed
.venv/bin/python -m pytest tests/cognitive/test_actions.py -k r09 -q -p no:cacheprovider
# 4 passed
```

## Limits
Self-review only. No live surface/provider smoke. Episode→decision writer wiring beyond action/receipt journal is deferred to R10/R11 consumers of this contract. PASS ≠ CR-14 GO / release.
