# R01 report — 보호 파일을 실제 실행 경계에서 강제

- 실행: 2026-09-26 21:30 KST (residual close)
- tip before: `c21f0695`; this commit restores seatbelt deny + gate digest wiring
- reviewer: 마뱀 (self-review limitation)

## Before / after (residual)

- Before (tip): `sandbox_protected_write_denies` existed but was **not** wired into seatbelt; `protection_action_digest` missing → R01 tests ImportError; override could open protected writes; injected guard replaced.
- After:
  1. `SandboxRunner._protected_write_deny_section` after broad `/var/folders` allow (write + unlink parent denies).
  2. Docker path remounts protected host paths `:ro` over `/workspace`.
  3. Non-Darwin without Docker remains fail-closed when sandbox enabled.
  4. `protection_action_digest` restored; cognitive protection runs **before** tool overrides; injected guard root preserved.

## R01-A*

| ID | 관측 | 결과 |
|---|---|---|
| A1–A4 | Darwin suite + residual tests | PASS (self-review) |
| Residual order/Linux/Docker RO/digest | `test_r01_residual.py` | PASS |
| E | evidence/R01/ | PASS |
| V | independent | NOT claimed |

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_r01_residual.py tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_protection_boundaries.py tests/cognitive/test_protection.py tests/test_sandbox_isolation.py -q -p no:cacheprovider
# 62 passed
```

## Limits

- Live Docker RO mount not exercised against a real daemon in this run (cmd shape asserted).
- Independent human R01-V open. Ops/CR-14 still NO-GO.
