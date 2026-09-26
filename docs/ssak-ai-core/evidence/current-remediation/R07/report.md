# R07 report — 성공·실패 feedback bounded 사고 루프

## Status
PASS (self-review limitation)

## Changes
- `runtime.py` run loop: govern→execute→feedback→targeted rethink as a multi-round state machine
- Successful request feedback is also passed to Primary rethink (not failure-only)
- Rethink’s new request batch runs through the same governance/execute path next round
- `CognitiveRequestEnvelope.signature()` includes normalized action arguments
- Per-request repeat detection via signature; `EpisodeBudget.max_total_requests` caps batch size
- `ThinkOutcome.plan` optional override so COMMIT uses the latest plan after evidence integration

## Acceptance
R07-A1..A5 via `test_r07_*`; full `test_episode.py` green (see pytest_r07.txt)

## Limits
Self-review only; PASS ≠ release GO. Live surface/provider smoke not run in this card.
