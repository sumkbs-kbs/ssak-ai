# R02 report — 권한 위임 수명·취소와 승인 결박

## Status
PASS (self-review limitation; R02-V는 독립 인간 검토 대기)

## Files / symbols
- `src/antigravity_k/engine/cognitive/authority.py`
  - `delegate`: 자식 `expires_at=None` → 부모 ceiling 상속
  - `revoke`: `granted_by` 후손 고정점까지 전파
  - `evaluate` + `_ancestor_failure`: 조상 revoked/expired/dangling/cycle 거절
  - `reuse_approval(..., action_digest=)`: DIGEST_MISMATCH
- `src/antigravity_k/engine/cognitive/governance.py`
  - `_reusable_human_decision`: 현재 `action.digest()` 결박
- `tests/cognitive/test_r02_authority_lifecycle.py` (R02-A1..A4)
- `tests/cognitive/test_governance.py`: human-only 승인에 digest 필수

## Before / after
- Before: 위임 시 만료 생략 → 자식이 부모보다 오래 살 수 있음; 손자 revoke 누락; governance가 digest 없이 승인 재사용.
- After: 상속·조상 검사·후손 전체 revoke·digest 일치 시에만 재사용.

## Acceptance observations
- R02-A1: 생략 만료=부모 ceiling; 이른 만료 유지; 부모 만료 후 자식/레거시 None 거절 (EXPIRED).
- R02-A2: root→mid→leaf revoke 전파, independent grant 유지.
- R02-A3: digest mismatch human-only → APPROVE 아님 (DENY).
- R02-A4: 축소 위임 성공 + matching digest REUSED / mismatch DIGEST_MISMATCH.

## Commands
```
.venv/bin/python -m pytest tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_governance.py -q
→ 36 passed
.venv/bin/ruff check …authority.py …governance.py …test_r02… → All checks passed
```

## Limits
- 독립 검토자(R02-V) 미실시.
- Docker/프로세스 간 권한 복제 경로는 이 카드 범위 밖.
- 이 카드 PASS ≠ release GO.
