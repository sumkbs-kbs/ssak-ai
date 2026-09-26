# R06 report — 관련성·최신 revision·직렬화 예산

## Status
PASS (self-review limitation)

## Changes
- `context.py`: L1은 현재 goal만, superseded judgment는 SUPERSEDED exclusion + handle
- L3 injection은 selected/goal reference evidence만 (project-wide dump 제거)
- handle/exclusion bounded page (`DEFAULT_HANDLE_PAGE`/`DEFAULT_EXCLUSION_PAGE`) + omitted counts
- `tokens_used`는 content와 serialized package(메타 포함) 추정의 max; 예산 초과 시 metadata trim
- `models.py`: `ContextPackagePayload.omitted_handle_count` / `omitted_exclusion_count` (C01 전송 예산 계약)

## Acceptance
- R06-A1..A4: `test_r06_*` in `tests/cognitive/test_context.py`
- Full file suite: 24 passed (see pytest_r06.txt)

## Limits
- Token estimate remains conservative char-based (`TOKENS_PER_CHAR`), not provider tokenizer
- R06-V is self-review, not independent human; PASS ≠ release GO
- Schema fields added on ContextPackagePayload; consumers ignoring unknown fields are fine (explicit fields)

## Rollback
Revert context.py / models omitted_* / test_context R06 blocks; prior L3 project-scope dump returns.
