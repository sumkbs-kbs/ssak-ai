# R01 report — 보호 파일을 실제 실행 경계에서 강제

- 실행: 2026-09-26 19:59 KST
- HEAD: `2862584ea8f79641fefd9a78de9c145851ea515b` (+ dirty working tree)
- reviewer: 마뱀 (self-review limitation)

## Before / after

- Before: seatbelt가 project root 전체 write를 허용해 `Path.write_bytes`가 임시 헌법을 승인 없이 변경 (F01 REPRODUCED).
- After:
  1. `SandboxRunner`가 `default_protected_roots` 경로에 `file-write*` deny, 부모 디렉터리에 `file-write-unlink` deny를 **넓은 /var/folders allow 이후**에 적용.
  2. `evaluate_shell_command`가 보호 경로+interpreter/변이 징후(`write_bytes`, `os.rename` 등)면 토큰 목록 없이도 거절. 순수 `cat` 읽기는 유지.
  3. `require_sandbox` + disabled → fail-closed (기존).

## R01-A*

| ID | 관측 | 결과 |
|---|---|---|
| A1 | write_bytes / os.replace / parent rename / symlink write → digest 불변 | PASS |
| A2 | 일반 ok.txt + sibling NOTES.md 쓰기 성공 | PASS |
| A3 | 승인 digest 일치만 ALLOW, content 변경 DENY | PASS |
| A4 | enabled=False+require_sandbox → refused, 실행 0 | PASS |
| E | evidence/current-remediation/R01/ | PASS |
| V | self-review | PASS w/ limitation |

## Commands

```
.venv/bin/python -m pytest tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_protection_boundaries.py tests/cognitive/test_protection.py tests/test_sandbox_isolation.py -q -p no:cacheprovider
# 58 passed
```

## Limits

- Docker readonly mount for protected paths not added in this card (macOS seatbelt primary).
- Independent human reviewer slot open.
- Card ≠ release / ops activation.
