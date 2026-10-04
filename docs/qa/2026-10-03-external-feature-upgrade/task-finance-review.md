---
title: Task-runner claim and financial numeric upgrade code review
tags: [code-review, task-runner, sqlite, financial-numeric, external-feature-upgrade]
date: 2026-10-03
---

# Code quality review — CLEAR

## Candidate and scope

- Final full HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Baseline: `/private/tmp/ssak-external-baseline.JAxkH3` (flattened file snapshot).
- Reviewed production files: `src/antigravity_k/engine/task_runner.py`, `src/antigravity_k/engine/data_extractor.py`, `src/antigravity_k/engine/financial_numbers.py`, and `src/antigravity_k/api/routes/system_api.py`.
- Reviewed tests: `tests/test_task_runner_claim.py`, `tests/test_financial_numbers.py`, and `tests/test_search_numeric_contract.py`, with related task-state/resume/outcome, data-extractor, and search-extract tests consulted.
- Graph discovery could not run because graph MCP tools were not exposed. I used the bounded known-file fallback only and did not re-index the project.

## Independent final checks

`HOME=/private/tmp/ssak-review-home-task-finance-canonical-20261003 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_financial_numbers.py tests/test_search_numeric_contract.py`

Result: `20 passed, 1 warning in 2.35s`; the sole warning is the existing Starlette `TestClient` deprecation warning. Ruff passed for `financial_numbers.py` and the two changed finance tests; `git diff --check` passed.

Direct adapter checks confirm the formerly failing values are canonical and consistent:

- `1조 0.0000000000000000000000000001만` → `value == normalized_value == "1000000000000.000000000000000000000001"`.
- `123456789012345678901234567890원`, `USD 0.12345678901234567890123456789`, and `123456789012345678901234567890조원` retain every digit, and unsafe values use the same exact string in both fields.
- The actual HTTP contract tests cover safe-integer overflow and long scaled serialization through `POST /api/search/extract` with only `WebSearchTool.execute` replaced.

The previous Decimal context and lexical-value findings are fixed: `_canonical_decimal` provides the one canonical textual representation, and `json_compatible_value` now returns it whenever a float would be inexact. The focused regression additions are behavior-bearing and distinguish the prior bug.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Task-claim assessment

The task-claim files remain frozen at their prior reviewed hashes. The durable claim precedes worktree, snapshot, orchestrator, checkpoint, and outcome work; pending starts claim `pending -> running`, and resumes claim `resuming -> running`. The real-SQLite race tests distinguish one executor from one loser with no competing orchestration, checkpoint, or outcome. I found no task-claim regression.

## Evidence assessment

`docs/qa/2026-10-03-external-feature-upgrade/financial-validation.md` and `.omo/evidence/financial-numeric-verification.md` correctly mark pre-final artifacts as historical. The final exactness manifest predates this last lexical-only repair, so it is not reused as final proof for the current parser/test hashes. This review records the current hashes below and its independent green result above.

## Skill-perspective check

This check ran after loading `omo:programming` and `omo:remove-ai-slops`.

- `remove-ai-slops`: no deletion-only, removal-only, prose/prompt, tautological, implementation-constant, or mock-only test was added. Real temporary SQLite covers the claim race; financial tests assert concrete parser, adapter, and HTTP behavior.
- `programming`: the CAS change remains a narrow boundary. The financial representation preserves exact Decimal semantics through parser, adapter, and serialized contract without needless abstraction, untyped escape hatches, brittle prompt assertions, or unrequired validation.

## Source identity (SHA-256)

```text
5cf8c52389295e52d97888dcd4ddde38c8adcbe6f1751f1586add9276c2c79e1  src/antigravity_k/engine/task_runner.py
4031fc7512626fd7c0c54a5071d4d9a833d8fec69f4751336c39aa1fb85a2868  tests/test_task_runner_claim.py
593d0b2e3a5b9a178dc20b446afe6db56c4887870b120bde51b20b5c1fc4a316  src/antigravity_k/engine/data_extractor.py
5289fe93e19de50035123086a0778c2235f0631c697fc40231e1a3006d8d5eb5  src/antigravity_k/engine/financial_numbers.py
2cfcf47487039bb0ecce66c5a6f2ade0fc3b277ddb1a3f33080daba90b1179e1  src/antigravity_k/api/routes/system_api.py
d1c7a4673f3a0be23a563fdcb426592d458216843cd9dccab86b7432f226e219  tests/test_financial_numbers.py
8dcf0f7c0037a78c9b01b11317d8fef7110a732cda196bd9365c11fbe3269d38  tests/test_search_numeric_contract.py
```

## Decision

- `codeQualityStatus`: **CLEAR**
- `recommendation`: **APPROVE**
- `reportPath`: `docs/qa/2026-10-03-external-feature-upgrade/task-finance-review.md`
- `blockers`: None.
