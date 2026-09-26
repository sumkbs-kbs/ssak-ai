# R13 report — real policy consumption / BehaviorChangeTrace

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R13-V not claimed.

## Before

`growth_phase` built `BehaviorChangeTrace.actual_selection` by concatenating train `selected_evidence` with `advisory_refs` (synthetic). That was not a real post-policy `ContextBuilder` / selector observation. Negative-transfer tasks could still receive mature depth limits.

## After

- `_observe_selection(store, task, policy_version, limits)` runs `ContextBuilder` / `build_context_once` and returns L3 evidence IDs.
- After promote: commit advisory, **pin** episode to active policy version, observe shadow (baseline / no policy) vs actual (pinned policy + mature limits), `record_behavior_change` with observed IDs and optional `outcome_ref`.
- `_policy_limits_for_task`: `negative_transfer` → baseline limits and `policy_version=None` (no mature depth).
- Acceptance nodes `test_r13_a1`…`a5` in `tests/cognitive/test_growth.py`.

## Acceptance

| ID | Result |
|----|--------|
| R13-A1 | PASS — re-observe on frozen growth-train store matches trace / phase fields |
| R13-A2 | PASS — negative_transfer keeps baseline limits / no policy version |
| R13-A3 | PASS — rollback restores active version; new pin resolves to rolled-back version |
| R13-A4 | PASS — mid-episode pin stays on pre-promotion version after later promote |
| R13-A5 | PASS — failed validation `register` raises `PromotionRefused` |
| R13-E | PASS — this evidence tree |
| R13-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_learning.py tests/cognitive/test_growth.py tests/cognitive/test_context.py -q -p no:cacheprovider
# 75 passed
.venv/bin/python -m pytest tests/cognitive/test_growth.py -q -p no:cacheprovider -k r13
# 5 passed
```

## Limits

- Self-review ≠ release GO / CR-14.
- Growth demo path wires observe+pin; broader runtime/Context policy pin beyond growth is still owned by R14/R15 consumers.
- R13-A4 “restart” covered via durable pin object identity across promote, not full process restart (PolicyStore in-memory pin freeze).
