---
title: "T10 — Experience가 미래 행동을 바꾸는 경로 증거"
date: 2026-09-22
status: verified-module-and-canonical-store-surface
owner: 학습 담당 카드(P09) / 주 에이전트 구현
---

# T10 학습 lifecycle (P09)

```yaml
check_id: T10
status: PASS (module + 실제 CanonicalStore 표면) — T10-A~E
owner: p09-learning
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/learning.py (sha256 d6b9234b66d421d9…, 신규 1221 lines)
  - src/antigravity_k/engine/cognitive/policy_store.py (sha256 869458c3bd958d39…, 신규 756 lines)
  - tests/cognitive/test_learning.py (sha256 0b8e81c6c2934c83…, 신규 29 시험)
command: |
  .venv/bin/python -m pytest tests/cognitive/test_learning.py -q
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_plan_guard.py tests/test_cr04_shell_api_boundary.py tests/test_fr02_shell_execution_boundary.py tests/test_persistent_agency.py tests/test_cognitive_loop_events.py tests/test_cognitive_recovery.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive/test_learning.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive/test_learning.py
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive
exit_code: 0 (모든 명령)
observed_behavior: 검증 없는 승격은 등록 단계에서 거부되고, active version은 CAS promotion으로만 바뀐다.
  독립 episode 2건 미만·중복 원자료·trigger 단독 후보는 검증되지 않는다. 결과 실패는 판단 실패로 자동
  치환되지 않으며, applicability MISMATCH는 confidence와 무관하게 적용이 보류된다. candidate → report →
  activation → 다음 task의 shadow/실제 선택 차이 → outcome 연결이 BehaviorChangeTrace로 이어질 때만 성장
  근거가 만들어진다. policy activation은 authority dimension 판정을 바꾸지 않는다.
artifact:
  - docs/ssak-ai-core/evidence/T10_learning.md (이 문서)
  - tests/cognitive/test_learning.py (29 시험: T10-A 10 / B 5 / C 2 / D 5 / E 5, §경계 2)
limitations: 실제 provider·실제 미래 task 분포에서의 성장 효과는 이 카드가 주장하지 않는다(P10의 사전 등록
  BenchmarkSpec·ablation 범위). validation은 fixture split으로 수행했고 live model snapshot은 없다.
  engine runtime/agent_runtime/CLI·API 표면 연결은 P11, migration·최종 인수는 P12다. VALIDATION_REPORT의
  평가 주체는 Body(기계 집계)이고, 의미 해석은 Primary/human-assisted 경로만 사용하도록 경계를 고정했다.
verified_at: 2026-09-22T06:12:30Z
```

## 구현 경계

| 인터페이스 | 구현 | 계약 |
|---|---|---|
| Experience Evaluator | `ExperienceEvaluator.aggregate` (기계 집계) / `.interpret` (Primary/human 경로) | 의미 해석 호출 0을 aggregate에서 고정 |
| Pattern Candidate Builder | `CandidateProposer.propose` → `LearningCandidate` | typed candidate, active 변경 경로 없음 |
| Policy Candidate Store | `CandidateStore` (append-only) | 실패 report도 보존, 기준 완화 대신 새 experiment ID |
| Validation Interface | `HeldOutValidator.validate` → `ValidationReport` | 학습/검증 task 분리, 계약 위반은 예외 |
| Policy Versioning / Promotion | `PolicyStore.register` / `.promote` | 검증 필수 + CAS |
| Policy Rollback / Retirement | `PolicyStore.rollback` / `.retire` | append event, 과거 기록 불변 |
| Behavior Change Trace | `PolicyStore.record_behavior_change` / `.growth_evidence` | 선택 변화 + outcome 연결 필요 |

## T10 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A | 실패 1건 후보 | `InsufficientEvidenceError` — 독립 episode 1 < 2 |
| A | 같은 원자료 2건 | `observation_count=2`, `independent_episode_count=1` → 검증 거부 |
| A | grade/cooldown trigger만 | trigger는 계기일 뿐이라는 사유로 거부 |
| A | Brain 해석 trigger만 | 동일하게 거부 |
| A | 결과 실패 + 당시 판단 합리 | `outcome_failures=2`, `decision_failures=0`, `unattributable_failures=2`. FAILURE 계기 후보는 거부되지만, 환경 변화 계기로 다시 세운 같은 관측은 검증을 통과한다 |
| A | 주장한 근거 집계 조작 | `EvidenceMismatchError` |
| A | split 재사용/겹침 | 학습 split 사용·task 겹침 각각 `ValidationBypassRefused` |
| A | 검증 없는 promotion | `PromotionRefused`, `active_version=None`, 실패 report는 보존 |
| A | 등록만 한 상태 | active는 여전히 `None`, `growth_evidence=None`, stale expectation은 `PolicyCasConflict` |
| A | human-assisted | 독립 episode 1건이면 같은 오류로 거부, 2건 + 검증 통과 시에만 등록. 우회 경로 없음 |
| B | 기계 집계 | spy interpreter 호출 0 (`interpret_calls == 0`), 명시 호출 시에만 1회 + request에 summary digest 결박 |
| B | 해석 주체 | Body author는 `SemanticAuthorityError`(평가기·proposer 양쪽), 미연결 상태도 거부 |
| B | 의미 → Principle | Evidence 없는 의미 후보는 narrower/broader report가 있어도 `NotPromotableError` |
| B | causal claim | 검증 전에는 HYPOTHESIS(CANDIDATE)로만 남고, 검증 후 STRATEGY(SUPPORTED)로 승격 |
| B | Principle | broader validation 없이는 `ValidationBypassRefused`, 통과 시 Principle record + report ref |
| C | confidence 0.99 + MISMATCH | `WITHHOLD`(자동 적용 0), reason에 confidence가 판정 근거가 아님을 기록 |
| C | 전 축 MATCH / PARTIAL·UNKNOWN | `APPLY` / `APPLY_WITH_SCOPE` + unknown field 기록 |
| C | challenged→retired | append revision 2건, `supersedes` 체인, 원본 lifecycle(CANDIDATE)과 record digest 불변. SUPPORTED 상향은 `NotPromotableError` |
| D | candidate→report→activation | activation이 report ID를 참조, 등록 직후 `growth_evidence=None` |
| D | trace 기록 | shadow(`context:l1#a`) → 실제(`context:l1#a, context:l2#b`) 차이가 diff에 남고 growth evidence 생성 |
| D | outcome 없는 trace | 변화는 남지만 성장 근거로는 세지 않음 |
| D | canonical store | 후보·report·policy·activation·trace record를 commit → read-back, `verify_digests` 통과 |
| D | CAS 동시 promotion | 두 번째 `expected_active_version=None`은 `PolicyCasConflict`, active는 승자 유지 |
| D | rollback | `ROLLBACK` event append, active 복원, 과거 activation digest 불변, pin 선택도 이전 version |
| D | 실행 중 pin | promotion 뒤에도 pin은 시작 version 유지, `revoke_authority` 직후 resolve는 `AuthorityRevokedError` |
| D | retire | retired lifecycle 기록·유지, active는 이전 version으로 복귀(ROLLBACK event), 재활성화는 거부 |
| E | 두 운영 target | CONTEXT_SELECTION·TOOL_SELECTION이 서로 다른 policy로 독립 활성화 |
| E | 권한 확대 파라미터 | `new_grant`·`max_autonomy`·허용 목록 밖 위임 파라미터 모두 `AuthorityWideningRefused` |
| E | 기존 grant 안 위임 조정 | `selection_order` 같은 선택 파라미터만 등록 가능 |
| E | protected 참조 | 헌법 경로를 rule에 넣으면 proposer에서 `PolicyTargetRefused`, guard 없이 만든 후보도 등록에서 거부 |
| E | authority 불변 | activation 전후 `dimension_view` 동일, grant 발급은 `AuthorityViolation`, ceiling 상향은 사람 결정으로만 남음, store에 grant/ceiling API 없음 |

## 검증 명령과 결과

```sh
.venv/bin/python -m pytest tests/cognitive/test_learning.py -q      # 29 passed
.venv/bin/python -m pytest tests/cognitive -q                       # 258 passed
.venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_plan_guard.py \
    tests/test_cr04_shell_api_boundary.py tests/test_fr02_shell_execution_boundary.py \
    tests/test_persistent_agency.py tests/test_cognitive_loop_events.py tests/test_cognitive_recovery.py -q
                                                                    # 400 passed
.venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive/test_learning.py
                                                                    # All checks passed
.venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive/test_learning.py
                                                                    # clean
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive           # Success: 17 source files
```

## 성장 영역 확장 계약 (P09 v1.1 요구)

「Experience가 개선해야 할 영역」 14개를 모두 같은 경로로 확장한다. 새 target을 추가할 때 필요한 것은 넷이다.

| 단계 | 계약 |
|---|---|
| target | `PolicyTarget` enum에 운영 knob을 추가한다. 헌법·authority·premise는 여기에 들어오지 않으며, allowlist 밖 target은 `PolicyTargetRefused`/`AuthorityWideningRefused`로 거부된다 |
| scope | `CandidateRequest.scope` + `PolicyVersion.compatibility`에 goal·environment 같은 적용 경계를 적는다. 현재 applicability는 `KnowledgeLedger.reassess_applicability`로 재평가한다 |
| validation | 학습에 쓴 split과 task가 겹치지 않는 frozen split을 `ValidationRole.VALIDATION`(그리고 Principle이면 `BROADER`)로 사전 등록하고, `ValidationCriterion`을 실행 전에 고정한다 |
| trace | `PolicyStore.record_behavior_change`로 policy 없이 같은 입력에 대한 shadow 선택과 실제 선택 차이·outcome ref를 남긴다. trace가 없으면 `growth_evidence`는 생성되지 않는다 |

권한 관련 영역은 별도 경로다. `AUTHORITY_DELEGATION` target에서 policy가 할 수 있는 것은 기존 grant 안의 선택·위임
조정(`preferred_subject`, `preferred_dimension`, `selection_order`, `fallback`, `max_parallel`)뿐이다. 새 grant 발급과
human ceiling 상향은 `PolicyTarget`이 아니라 사람 결정 경로(`AuthorityProfile.issue_grant(actor_kind=HUMAN)`,
`propose_ceiling_change`)로만 가능하다.

## 이월 조건

- **P10:** 사전 등록 BenchmarkSpec·frozen final held-out·ablation 6종에서 실제 성장 효과를 측정한다. fixture
  통과는 일반 성능 우위의 근거가 아니다.
- **P11:** runtime·agent_runtime·CLI/API/stream/background 표면에서 policy 선택과 pin·revoke를 연결한다.
- **P12:** migration·rebuild·brain 교체 시 policy version·trace 계보의 보존을 확인한다.
