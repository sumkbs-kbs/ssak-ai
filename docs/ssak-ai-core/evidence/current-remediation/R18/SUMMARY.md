# R18 report — live trial adapter (model→action→experience path)

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R18-V not claimed.

## Before

Only `LiveTrialPort` stub / fixture GrowthRunner existed. No adapter wired model choice through real ToolExecutor/store without canned FixtureThink success.

## After

- NEW `live_trial_adapter.py`: `LiveTrialAdapter` + `ScriptedModelPort` / `ModelPort`
- Append bytes come from `ModelChoice` only (wrong model → file has WRONG:…, success=False)
- `PolicyGateState` + `run_train_validation`: VALIDATION fail → no promote → FINAL Mature `policy=None`
- Separate `fresh/` vs `mature/` roots; digests diverge when mature has policy marker
- Workspace jail refuses outside targets (tool_calls=0); harness timeout → NOT_COMPLETE + partial ledger

## Acceptance

| ID | Result |
|----|--------|
| R18-A1 | PASS |
| R18-A2 | PASS |
| R18-A3 | PASS |
| R18-A4 | PASS |
| R18-E | PASS |
| R18-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_live_trial_adapter.py tests/cognitive/test_live_pilot.py -q -p no:cacheprovider
```

## Limits

- ScriptedModelPort is a contract double, not a paid/local LLM smoke. Real provider smoke remains optional/NOT_RUN unless environment is registered.
- Self-review ≠ release GO / CR-14.
- Experience/learning ledger depth beyond policy gate markers is deepened in R19.
