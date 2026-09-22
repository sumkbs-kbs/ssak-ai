---
title: "T06 — COMMIT readiness·Decision lifecycle 증거"
date: 2026-09-22
status: verified-module-and-canonical-store
owner: 주 에이전트 카드(P06)
---

# T06 COMMIT·Decision lifecycle (P06)

```yaml
check_id: T06
status: PASS (module + canonical store 표면) — T06-A/B/C/D
owner: principal
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/readiness.py (sha256 ddbc74bd21874212…, 신규)
  - src/antigravity_k/engine/cognitive/decisions.py (sha256 444bf04c7b67edbd…, 신규)
  - tests/cognitive/test_readiness.py (sha256 f0efa9bbbda0f43d…, 신규 28 시험)
  - src/antigravity_k/engine/cognitive/governance.py (P05 산출물, 이번 카드에서 수정하지 않음)
command: |
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive/test_readiness.py -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_ws02_tool_root.py tests/test_tool_contracts.py tests/test_claw_integration.py tests/test_plan_guard.py tests/test_command_execution_boundary.py tests/test_fr02_shell_execution_boundary.py tests/test_autonomous_capabilities.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive src/antigravity_k/engine/tool_executor.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive
exit_code: 0 (모든 명령)
observed_behavior: 9 readiness check가 PASS/FAIL/UNKNOWN/N_A와 이유를 반환하고, READY/READY_WITH_GUARDS/
  NOT_READY가 재현된다. semantic judge 호출 0, 문자열 rollback 약속 거부, freshness 재확인, material trigger만
  reopen하며 옛 trace digest가 불변임을 관찰했다. readiness assurance가 Decision record로 canonical store에
  commit·read-back·digest 검증까지 통과한다.
artifact:
  - docs/ssak-ai-core/evidence/T06_commit.md (이 문서)
  - tests/cognitive/test_readiness.py (28 시험: A 5 / B 7 / C 7 / D 6 / P05 연계 2 / store 1)
limitations: loop(P08)와 사용자 표면(P11) 연결 전이므로 COMMIT gate를 실제 orchestrator 흐름에서 실행하지 않았다.
  guard를 실제로 집행하는 주체는 여전히 executor(P07)이며, 이 카드는 guard receipt가 없으면 readiness가
  통과하지 않는다는 계약만 고정한다. UNKNOWN은 Primary/사람 판단이 필요하다는 뜻으로 NOT_READY로 처리했다.
  의미 해석 자체는 이 모듈이 하지 않는다. decision_revision 증가·재평가 트리거 연결은 P08 이월 조건이다.
verified_at: 2026-09-22T05:10:30Z
```

## 구현 표면

| 모듈 | 역할 | 성질 |
|---|---|---|
| `engine/cognitive/readiness.py` | 9개 readiness check, 3 verdict, freshness binding | 순수 함수, provider 미호출, 외부 쓰기 없음 |
| `engine/cognitive/decisions.py` | DecisionTrace, closure/reopen/reassessment append ledger | append-only, 원본 digest 보존, semantic 재심사 없음 |

`semantic_judge` 파라미터는 **호출되지 않아야 하는 hook**이며 시험에서 호출 0을 고정한다(`_ForbiddenJudge`가
호출되면 AssertionError). 의미적 불확실성(예: 기계 검증도 human attestation도 없는 constraint)은 `UNKNOWN`으로
표시하고 `needs_primary_judgment=True`로 Primary에 돌려보낸다.

## T06 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A | LLM 호출 0 | 호출 시 실패하는 judge를 주입해도 gate가 성공하고 호출 횟수는 0 |
| A | 의미 결론만 다른 fixture | `advisory_notes`가 반대여도 verdict·check 상태·freshness digest가 동일 |
| A | 구조가 달라진 fixture | action scope/digest, constraint, evidence provenance, authority 중 하나만 달라져도 verdict/check가 바뀜 |
| A | 승인 후 args 변경 | `ACTION_SCOPE_CLEAR`가 FAIL이며 "재승인" 사유를 반환 |
| B | 9 checks | 항상 9개가 모두 보고되고 각 항목에 reason이 있다. N_A도 사유를 갖는다 |
| B | verdict 3종 | READY / READY_WITH_GUARDS(guard receipt·limit·risk acceptance 존재) / NOT_READY |
| B | ACCEPTABLE Unknown | 단독으로는 NOT_READY가 되지 않고 `MATERIAL_UNKNOWN_EXPLICIT` PASS |
| B | BLOCKING Unknown | NOT_READY + blocking condition 문자열 반환 |
| C | guard 강제 | `enforced=False`·빈 receipt digest의 guard는 receipt로 인정되지 않아 `RESIDUAL_RISK_MANAGEABLE` FAIL |
| C | rollback | mechanism·checkpoint reference 없는 약속은 FAIL("문자열 rollback 약속은 충족이 아니다") |
| C | verification | required requirement가 receipt 없이 satisfied 상태면 FAIL |
| C | freshness | state/authority/policy/decision revision이 달라지면 `revalidate`가 stale로 판정하고 `assert_fresh`가 거부 |
| D | material reopen | trigger evidence + smallest scope + rationale이 모두 있어야 reopen. 없으면 `ReopenRefused` |
| D | 중복 reopen | 같은 trigger·evidence 조합은 거부되고 옛 trace digest는 그대로 |
| D | Human reopen | evidence 없이 허용, actor 종류와 이미 발생한 action을 기록 |
| D | 행동 되돌림 가정 | `claims_effects_reverted=True`는 거부(`assumes_effects_reverted`는 항상 False) |
| D | reassessment | 새 decision ID로 연결하고 원래 trace digest는 digest history에 그대로 남음 |
| 연계 | P05 → P06 | APPROVE_WITH_LIMITS의 limit이 `READY_WITH_GUARDS`로 이어지고, DENY(REVOKED)는 authority FAIL 유지 |
| 연계 | P06 → P02 | readiness assurance가 Decision record로 commit·read-back·`verify_digests` 통과 |

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                        → 191 passed (readiness 28 포함)
.venv/bin/python -m pytest tests/cognitive/test_readiness.py -q      → 28 passed
.venv/bin/python -m pytest (cognitive + executor/registry/plan_guard/shell 경계 9 suite) -q → 356 passed
.venv/bin/python -m ruff check / ruff format --check                 → clean
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive          → Success: no issues found in 12 source files
```

## 기존 red (분리 기록, 이번 변경과 무관)

이번 카드는 기존 파일을 수정하지 않았다(신규 2 모듈 + 신규 시험 1 파일). 기존 증거가 보고한
`tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for` 실패는 그대로 남아
있으며 이 카드의 변경으로 새로 생긴 실패는 없다.

## 남은 것 (다음 카드)

- P07: readiness가 요구한 guard receipt를 실제 executor/ToolExecutor 경로에서 생성·검증하고, action receipt와
  같은 idempotency·digest 체계로 묶는다.
- P08: 운영 루프에서 decision_revision 증가, stop 판정, reassessment event를 실제 loop 상태와 연결한다.
- P11: CLI/API/stream/background 표면에서 COMMIT·reopen을 opt-in으로 노출하고 feature off 회귀를 확인한다.
