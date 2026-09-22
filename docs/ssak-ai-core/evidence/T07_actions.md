---
title: "T07 — Action receipt·idempotency·복구 증거"
date: 2026-09-22
status: verified-module-and-tool-executor-surface
owner: 실행 담당 카드(P07) / 주 에이전트 구현
---

# T07 Action receipt·복구 (P07)

```yaml
check_id: T07
status: PASS (module + 실제 ToolExecutor·CanonicalStore 표면)
owner: p07-action
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/actions.py (sha256 894ea5abc6c72426…, 신규)
  - tests/cognitive/test_actions.py (sha256 17a26582fe953c2a…, 신규 17 시험)
  - src/antigravity_k/engine/tool_executor.py (P05 hook 포함, 이번 카드에서 수정하지 않음)
command: |
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive/test_actions.py -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_ws02_tool_root.py tests/test_tool_contracts.py tests/test_claw_integration.py tests/test_plan_guard.py tests/test_command_execution_boundary.py tests/test_fr02_shell_execution_boundary.py tests/test_autonomous_capabilities.py tests/test_persistent_agency.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive src/antigravity_k/engine/tool_executor.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive
exit_code: 0 (모든 명령)
observed_behavior: 같은 action key의 두 번째 제출은 receipt를 재사용하며 executor 호출이 1회로 유지된다.
  effect 후 crash는 UNKNOWN receipt로 남고 관측 없이는 성공으로 승격되지 않는다. non-idempotent 재dispatch는
  거부되며, 읽기 도구도 clearance·dimension 검사를 받고 network/cost/privacy는 별도 허가를 요구한다.
  intent/receipt가 canonical Action·ExecutionReceipt record로 실제 store에 commit·read-back됐다.
artifact:
  - docs/ssak-ai-core/evidence/T07_actions.md (이 문서)
  - tests/cognitive/test_actions.py (17 시험: idempotency 2 / UNKNOWN·복구 3 / 권한·정책 3 / freshness·guard 1 /
    feature off 1 / 취소 2 / store 1 / 실제 ToolExecutor 2 / P05 연계 1 / 문구 검사 1)
limitations: 실제 CLI/API/stream/background 연결은 P11이다. task_state_store를 통한 process 재시작 복구는
  dispatcher의 ``pending_reconciliation()`` 계약만 제공하고 실제 배선은 P08/P11이 담당한다. guard를 실행 시점에
  강제하는 주체는 여전히 executor이며 이 카드는 receipt가 없으면 dispatch하지 않는다는 경계만 고정한다.
  OBSERVE 단계의 경험 형성은 P08 범위다.
verified_at: 2026-09-22T05:14:08Z
```

## 구현 표면

| 요소 | 역할 |
|---|---|
| `ActionIntent` | 실행 의도. args digest·dimension·guard 의무·readiness·clearance를 담는다 |
| `PolicyClearance` | P05 governance가 허용한 실행 허가 + network/cost/privacy 한도 |
| `ActionDispatcher.execute` | `intent persist → 권한·freshness → guard receipt → executor → receipt` 순서 강제 |
| `ActionDispatcher.reconcile` | 관측으로만 UNKNOWN을 확정. 관측 실패는 UNKNOWN 유지 |
| `ActionDispatcher.cancel` | dispatch 전 취소만 종결. 이미 나간 action은 되돌림을 주장하지 않는다 |
| `ActionDispatcher.pending_reconciliation` | crash 후 미확정 receipt 목록(복구 우선순위) |
| `ToolExecutorPort` | 기존 `ToolExecutor.execute` adapter. 실패 판정 predicate를 주입받는다 |

## 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| idempotency | 같은 action key 2회 | 두 번째는 `DUPLICATE_ACTION`이며 executor 호출은 1회, receipt는 재사용 |
| idempotency | submission/action 분리 | 같은 submission 재제출은 "같은 submission", 다른 submission·같은 action key는 "중복 effect를 만들지 않는다", 같은 submission·다른 action key는 정상 dispatch |
| UNKNOWN | effect 후 TimeoutError | 파일 effect는 실제로 발생했고 receipt는 `UNKNOWN`, `effects_observed=None`, `reconciliation_required=True` |
| 복구 | 관측 실패 | `UNKNOWN` 유지, 문구에 "성공으로 승격하지 않는다" 기록 |
| 복구 | 관측 성공 | `COMPLETED` + `effects_observed=True`로 확정, 이후 `pending_reconciliation()` 비어 있음 |
| 재dispatch | non-idempotent + retry_authorized | `NON_IDEMPOTENT_REDISPATCH`로 거부되고 호출 수 그대로 |
| 재dispatch | idempotent + retry_authorized | 새 attempt(dispatch_attempt=2)로 실행, 이전 UNKNOWN receipt는 보존 |
| 권한 | 읽기 도구 + clearance 없음 | `NOT_AUTHORIZED` (읽기도 검사 대상) |
| 권한 | dimension 불일치 | `DIMENSION_MISMATCH` |
| 정책 | network/cost/privacy | 허가 없으면 `POLICY_CLEARANCE_MISSING`/`COST_EXCEEDS_CLEARANCE`, 허가가 있으면 dispatch |
| freshness | readiness 없음·digest 불일치 | `STALE_READINESS` |
| guard | receipt 없는 의무 | `GUARD_RECEIPTS_MISSING`, receipt가 있으면 dispatch |
| feature off | port 없음 | `NO_DISPATCH_PORT`, 기록 0 |
| 취소 | dispatch 전 | `CANCELLED` receipt, `effects_observed=False` |
| 취소 | dispatch 후 | 상태 유지 + `cancellation_requested`, 문구에 되돌림 주장 없음(`claims_reversal` False), reconciliation 요구 |
| store | intent·receipt canonical record | `Action` + `ExecutionReceipt` 2건 commit, `verify_digests()==2`, read-back 일치 |
| 실제 표면 | P05→P06→P07→ToolExecutor | governance APPROVE → readiness → dispatcher → 실제 파일 append 1회, 중복 제출은 파일에 남지 않음 |
| 실제 표면 | executor 실패 | 실패 문자열을 `FAILED` + `effects_observed=False`로 기록, 파일 미생성 |

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                        → 208 passed (actions 17 포함)
.venv/bin/python -m pytest tests/cognitive/test_actions.py -q        → 17 passed
.venv/bin/python -m pytest (영향 영역 10 suite, persistent_agency 포함) -q → 382 passed
.venv/bin/python -m ruff check / ruff format --check                 → clean
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive          → Success: no issues found in 13 source files
```

## 기존 red (분리 기록, 이번 변경과 무관)

신규 모듈·신규 시험만 추가했고 기존 파일은 수정하지 않았다. 기존 증거가 보고한
`tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for` 실패는 그대로이며
이번 카드로 새로 생긴 실패는 없다.

## 남은 것 (다음 카드)

- P08: 운영 루프에서 EXECUTE→FEEDBACK→OBSERVE를 이어 붙이고, `pending_reconciliation()`을
  task_state_store 재시작 복구와 연결한다. Experience 형성도 같은 카드다.
- P09~P10: receipt·outcome을 Experience/학습 입력으로 쓰고 정책 승격·rollback을 연결한다.
- P11: CLI/API/stream/background에서 dispatch 경로를 opt-in으로 노출하고 feature off 회귀를 확인한다.
