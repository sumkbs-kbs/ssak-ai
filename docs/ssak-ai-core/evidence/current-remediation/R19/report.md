# R19 report — registered Fresh/Mature experiment + independent recompute

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R19-V not claimed.

## Before

Live growth effect was NOT_RUN / fixture-only. No frozen registered manifest runner that refuses post-hoc task/metric edits, closes every trial_uid, and recomputes unfavorable verdicts from the raw ledger.

## After

- `freeze_registered_manifest` / `run_registered_live_experiment` / ledger closure + independent task analysis (not inflated reps)
- CLI `--mode registered-live` (NOT_RUN unless `SSAK_LIVE_SCRIPTED=1`)
- Ollama list probed fresh for environment note; **108-generation live smoke not run** — no promotion claim

## Acceptance

| ID | Result |
|----|--------|
| R19-A1 | PASS — task_ids/primary_metric unchanged after run |
| R19-A2 | PASS — ledger_gaps empty |
| R19-A3 | PASS — shared prereg settings; analysis_unit=task |
| R19-A4 | PASS — aggregate recomputes unfavorable; preserved |
| R19-E | PASS |
| R19-V | NOT independent — self-review only |

## Limits

- Scripted contract ≠ Ollama efficacy proof. Do not promote policy/Core from this card.
- Self-review ≠ CR-14 / release GO.
