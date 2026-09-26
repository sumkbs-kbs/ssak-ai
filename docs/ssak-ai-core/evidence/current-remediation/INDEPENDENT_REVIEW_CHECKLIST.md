# Independent R*-V review checklist (not yet executed)

Generated: 2026-09-26 KST · tip `531a5de3` (`531a5de3989229da5182c8b8e38271a5afcaa01e`)
Purpose: give a **separate** human/reviewer a concrete punch-list.
**This file does not itself satisfy any R*-V checkbox.**

## How to use

1. Reviewer is not the implementer of the card under review.
2. For each card: read `tasks/Rxx.md` + `evidence/Rxx/report.md` + linked pytest/logs.
3. Mark V as PASS only with dated initials and a one-line method; otherwise leave open.
4. Authority/concurrency cards (R01–R04, R08, R10, R15) need failure-model review, not suite green alone.

## Priority queue

| Card | Why first | Evidence folder | Suggested focus |
|------|-----------|-----------------|-----------------|
| R01 | protected file enforcement at execution boundary | evidence/R01 | sandbox + permission_gate fail-closed paths |
| R02 | authority lifetime / cancel / approval binding | evidence/R02 | revoke + stale approval refusals |
| R03 | staged transaction identity | evidence/R03 | conflict / identity immutability |
| R04 | WAL + snapshot lineage | evidence/R04 | lineage digests, not just dry-run |
| R08 | pre-dispatch current revision check | evidence/R08 | race between plan and execute |
| R10 | UNKNOWN observe/reconcile/restart | evidence/R10 | never promote UNKNOWN to success |
| R15 | trusted ACTIVE composition / single owner | evidence/R15 | OFF default + single executor owner |
| R21 | current-bytes migration rehearsal | evidence/R21 | dry-run only; no --apply without Human |
| R22 | integration / ops judgment | evidence/R22 | keep ops NO-GO until Human authorize |
| R20 | GBRAIN reward semantics | evidence/R20 | no silent reward→authority promotion |

## Remaining cards (self-review only so far)

R00, R05–R07, R09, R11–R14, R16–R19, R23 — suite evidence present; V still open unless reviewer signs.

## Explicit non-goals for V pass

- Do not treat architecture_review green as release GO.
- Do not treat R19 scripted harness as live LLM growth efficacy.
- Do not authorize destructive migration or production ACTIVE default from this checklist.

## Implementer failure-model re-scan (2026-09-26 21:15 KST)

See [FAILURE_MODEL_RESIDUAL_REVIEW.md](FAILURE_MODEL_RESIDUAL_REVIEW.md) (tip ).
This scan **does not** check any R*-V box. Highest residual: R15 defaults, R01 non-macOS/seatbelt order, R08 TOCTOU, R03 cross-process stage race.
