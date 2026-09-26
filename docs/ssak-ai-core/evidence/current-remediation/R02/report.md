# R02 report — 권한 위임 수명·취소와 승인 결박

- 실행: 2026-09-26 21:32 KST (digest-bound residual close)
- tip before: `c2e88477`
- reviewer: 마뱀 (self-review limitation)

## Before / after (residual)

- Before: `reuse_approval` skipped digest check when `action_digest=""`; `authorize_execution` skipped when `action_digest is None`; ToolGovernanceAdapter admit path omitted digest.
- After:
  1. Missing/empty digest on reuse → `DIGEST_MISMATCH`.
  2. Missing digest on authorize_execution → deny ("실행 직전 action digest 결박이 없다").
  3. Adapter passes `reauthorized.action_digest` into authorize_execution.

## R02-A*

Prior A1–A4 still green. Residual tests in `test_r02_digest_bound.py`.

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_r02_digest_bound.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_governance.py -q -p no:cacheprovider
# 38 passed
```

## Limits

- Implementer/secondary attack dry-run (2026-09-27): [V_ATTACK_DRYRUN_2026-09-27.md](./V_ATTACK_DRYRUN_2026-09-27.md) — **NOT Independent R02-V**.
- Independent R02-V open. Cross-process grant cache still out of scope.
- Ops/CR-14 still NO-GO.
