# R12 report — decision quality vs outcome separation

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R12-V not claimed.

## Before

Runtime always called `evaluate_decision(..., available_at_decision=True)`, so a known outcome became decision MATCH whenever readiness had passed. Decision quality and outcome were collapsed.

## After

- `DecisionAssessment` (Primary/Human explicit record) on `EpisodePlan`.
- `evaluate_decision` without assessment → `OutcomeStatus.UNKNOWN` (readiness ≠ semantic assessment).
- With assessment, decision status is independent of outcome (A1/A2).
- Learning already treats UNKNOWN decision as non-failure and does not score it as success.

## Acceptance

| ID | Result |
|----|--------|
| R12-A1 | PASS — `test_r12_a1_*` |
| R12-A2 | PASS — `test_r12_a2_*` |
| R12-A3 | PASS — `test_r12_a3_*` |
| R12-E | PASS — this evidence tree |
| R12-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_episode.py tests/cognitive/test_learning.py -q -p no:cacheprovider
# 64 passed
.venv/bin/python -m pytest tests/cognitive/test_episode.py -q -p no:cacheprovider -k r12
# 3 passed
```

## Limits

- Self-review ≠ release GO.
- Assessment must be supplied by Primary/Human path; Body does not invent one.
