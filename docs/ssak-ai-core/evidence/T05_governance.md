---
title: "T05 — Governance·다차원 Authority 증거"
date: 2026-09-22
status: verified-module-and-tool-executor-surface
owner: 권한 담당 카드(P05) / 주 에이전트 구현
---

# T05 Governance (P05)

```yaml
check_id: T05
status: PASS (module + tool_executor surface) — T05-A/B/C/D
owner: p05-authority
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/authority.py (sha256 3c36ad73a365752d…, 신규)
  - src/antigravity_k/engine/cognitive/governance.py (sha256 ec4f7ff6d35433b5…, 신규)
  - src/antigravity_k/engine/tool_executor.py (sha256 8de05c5fb47e26cd…, 수정: opt-in governance hook)
  - tests/cognitive/test_governance.py (sha256 07f0b4a8b504f8e7…, 신규 31 시험)
command: |
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive/test_governance.py -q
  .venv/bin/python -m pytest tests/test_tool_executor.py tests/test_ws02_tool_root.py tests/test_failure_classifier.py tests/test_context_artifact_tool.py -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_ws02_tool_root.py tests/test_tool_contracts.py tests/test_claw_integration.py tests/test_plan_guard.py tests/test_command_execution_boundary.py tests/test_fr02_shell_execution_boundary.py tests/test_autonomous_capabilities.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive src/antigravity_k/engine/tool_executor.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive src/antigravity_k/engine/tool_executor.py
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/tool_executor.py
exit_code: 0 (모든 명령)
observed_behavior: 5 disposition과 feedback, reshape 재권한, unknown 구분, dimension별 권한·delegation·취소·
  승인 재사용이 기대대로 동작하고, 실제 ToolExecutor 호출에서 승인 실행·회수 차단·guard receipt 요구를 관찰했다.
artifact:
  - docs/ssak-ai-core/evidence/T05_governance.md (이 문서)
  - tests/cognitive/test_governance.py (31 시험: T05-A 8 / B 4 / C 3 / D 9 / 통합 4 + 기타)
limitations: CLI/API/stream/background 사용자 표면 연결은 P11이다. guard의 실제 집행(체크포인트 생성, isolated
  worktree 실체화)은 adapter가 주입하는 guard_runner가 담당하며, 이번 카드에서는 호출 계약과 거부 경로만
  고정했다. 사람 승인 record의 발급·서명 체계는 P03 승인 객체를 그대로 사용하므로 발급 주체 검증 확장은
  P05/P07/P11 이월 조건이다. risk_profile_for는 도구 이름 기반 구조 분류이며 의미 해석이 아니다.
verified_at: 2026-09-22T04:59:23Z
```

## 구현 표면

| 모듈 | 역할 | 판정 성질 |
|---|---|---|
| `engine/cognitive/authority.py` | grant 집합·human ceiling·delegation·revocation·승인 재사용 | 순수 판정, 부작용 없음, scalar score 없음 |
| `engine/cognitive/governance.py` | 요청 수용 판정(5 disposition), Risk Shaping, unknown 구분, feedback | 순수 판정 + 실행 직전 `authorize_execution` |
| `engine/tool_executor.py` | opt-in hook(`set_governance_gate`) | adapter 미연결 시 기존 동작 그대로 |

판정 순서는 `GOVERNANCE_AND_AUTHORITY.md` 순서를 따른다: human-only boundary → 명시적 deny/revocation →
유효 grant → limits → 부족 범위 승인 요청. 권한 부족은 무조건 사람 이관이 아니라 `DEFER`/`DENY` +
대안이며, grant 밖으로 나가는 재구성은 `DENY`다.

## T05 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A | 5 disposition 각각의 feedback | 모든 결과가 `feedback.original_request_digest == action.digest()`, `why_changed` 보유. APPROVE 계열은 변경 0, DENY/DEFER는 남은 제약 또는 대안 필수(위반 시 `GovernanceError`) |
| A | reshape args 재권한 | RESHAPE 결과는 재권한 전 `authorize_execution`이 거부되고, `reauthorize` 후 guard receipt가 완전해야 실행 허용. digest 불일치는 거부 |
| B | Risk Shaping | blast radius·data loss·verification·cost·privacy 고위험 요청이 `ISOLATED_SCOPE`·`NARROWED_SCOPE`·`CHECKPOINT`·`DRY_RUN`·`VERIFICATION`·`DIFF_INSPECTION`·`BUDGET_LIMIT` guard로 재구성되고, 고위험이라는 이유만으로 human escalation하지 않음(`human_decision_required == False`) |
| B | human-only 우회 금지 | `change_human_ceiling`·`grant_authority`·`constitution_change`·`CONSTITUTIONAL` dimension은 reshape 없이 `DENY`이며, 재사용 가능한 사람 승인이 있을 때만 APPROVE |
| C | Unknown | ACCEPTABLE은 그대로 APPROVE, MATERIAL은 limit을 남긴 APPROVE_WITH_LIMITS, BLOCKING은 해당 action만 DENY(`blocked_unknowns` 기록, 다른 action은 계속) |
| D | 다차원 권한 | dimension·scope·만료·취소·operation·constraint별 verdict 분리. `dimension_view`는 dimension→verdict mapping이며 합산 점수 없음 |
| D | delegation | scope·operation·만료·constraint 중 하나라도 parent를 넘으면 `DELEGATION_NOT_SUBSET`, 부분집합은 `granted_by=parent`로 발급 |
| D | revocation | 회수는 새 revision에 기록되고 원래 profile은 불변. parent 회수는 위임 child에 전파 |
| D | 승인 재사용 | principal·scope·operation·유효기간이 모두 같아야 `REUSED`, 불일치는 4종 verdict로 구분 |
| D | 권한 발급 주체 | 사람이 아닌 actor의 `issue_grant`는 `AuthorityViolation`, ceiling 상향은 제안만 가능 |
| — | Brain 결론 의미 심사 금지 | 동의하지 않는다는 `advisory_notes`를 넣어도 disposition·limits가 동일하고 `semantic_review_performed`는 False로 강제 |

## 실제 tool_executor 표면 관찰

`tests/cognitive/test_governance.py`의 통합 시험은 MockPermissionGate가 아니라 실제 `ToolRegistry` +
실제 `PermissionGate` + 실제 `ToolExecutor`에 adapter를 연결해 다음을 관찰했다.

1. `fake_write` 도구가 grant 안에서 실제 파일을 생성하고 결과 문자열과 판정 disposition을 함께 기록한다.
2. 같은 도구·같은 scope지만 grant가 회수된 요청은 `[GOVERNANCE DENY]`로 차단되고 파일이 생성되지 않는다.
3. 고위험으로 분류된 요청은 `RESHAPE`로 반환되어 guard_runner가 없으면 실행되지 않고, guard receipt를
   채운 뒤 재권한된 요청만 실행된다(테스트에서 실제 파일 내용 `guarded` 확인).

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                        → 163 passed (governance 31 포함)
.venv/bin/python -m pytest tests/cognitive/test_governance.py -q     → 31 passed
.venv/bin/python -m pytest tests/test_tool_executor.py tests/test_ws02_tool_root.py \
    tests/test_failure_classifier.py tests/test_context_artifact_tool.py -q → 91 passed
.venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_ws02_tool_root.py \
    tests/test_tool_contracts.py tests/test_claw_integration.py tests/test_plan_guard.py \
    tests/test_command_execution_boundary.py tests/test_fr02_shell_execution_boundary.py \
    tests/test_autonomous_capabilities.py -q                     → 328 passed (영향 영역 회귀)
.venv/bin/python -m ruff check / ruff format --check                 → clean
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive          → Success: no issues found in 10 source files
.venv/bin/python -m mypy src/antigravity_k/engine/tool_executor.py   → Success
```

문서만 hash 검사하는 방식은 사용하지 않았다. 보호 경계는 P03의 `ProtectedWriteGuard`가 담당하고, 이 카드는
그 판정을 governance 결과와 연결하는 위치만 정의한다.

## 기존 red (분리 기록, 이번 변경과 무관)

기존 증거가 보고한 `tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for`
실패는 이번 변경으로 재검증하지 않았다. 이 카드의 파일은 해당 ALLOWLIST를 수정하지 않았고, `tool_executor.py`
수정은 governance hook과 setter 추가뿐이다. 신규 red는 만들지 않았다.

## 남은 것 (다음 카드)

- P06: readiness 9 checks가 이 gate 결과(guards·limits·authority revision)를 입력으로 받는다. semantic 재심사는 없다.
- P07: guard receipt와 action receipt를 같은 idempotency/digest 체계로 묶어 체크포인트 실체화를 강제한다.
- P11: CLI/API/stream/background 경로에 adapter를 opt-in으로 연결하고 feature off 회귀를 확인한다.
- 사람 승인 발급 주체 검증(진위·scope·digest·취소)은 P05/P07/P11 이월 조건으로 남는다.
