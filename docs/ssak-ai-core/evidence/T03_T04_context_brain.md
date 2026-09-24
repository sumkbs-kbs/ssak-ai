---
title: "T03/T04 — Context reconstruction·Brain adapter 증거"
date: 2026-09-22
status: verified-module
owner: Brain/context 담당(P04)
---

# T03 Context / T04 Brain 교체 (P04)

```yaml
check_id: T03
status: PASS (module-level)
owner: context
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
command: .venv/bin/python -m pytest tests/cognitive -q  /  ruff  /  mypy
exit_code: 0
observed_behavior: L0 보존, 예산 초과 명시·handle 제공, project scope 격리, 만료/digest/권한 handle 구분, applicability 기록, projection replay
artifact:
  - src/antigravity_k/engine/cognitive/context.py (sha256 0e506935…)
  - tests/cognitive/test_context.py (sha256 1a1dd559…, 13 시험)
limitations: token 추정은 문자 기반 결정적 추정이며 정확한 tokenizer가 아니다(계약상 v1 허용). 실제 Brain context window 대비 검증은 P08/P10에서 관찰한다.
verified_at: 2026-09-22T03:36:23Z
```

```yaml
check_id: T04
status: PASS (module-level)
owner: brain-adapter
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
command: .venv/bin/python -m pytest tests/cognitive -q  /  ruff  /  mypy
exit_code: 0
observed_behavior: provider A/B가 같은 canonical record를 읽음, malformed repair 1회 제한, plain-text 판단 승격 0, rethink supersedes append, fallback 동일 frozen context·새 ID
artifact:
  - src/antigravity_k/engine/cognitive/brain.py (sha256 d6e3e45c…)
  - tests/cognitive/test_brain.py (sha256 2781dbc1…, 17 시험)
limitations: 실제 provider SDK·model_router 연결은 adapter 주입 지점만 제공한다(P08/P11에서 실제 router로 연결). timeout 완료 timing 실측은 미수행.
verified_at: 2026-09-22T03:36:23Z
```

## T03 Context 구현

- **L0 보존**: `ContextPackagePayload.l0_constraints`는 project의 `protected_constraints`(ConstitutionRule)로 구성되며 `L0_SIGNAL` disclosure로 고정된다. L0 token이 예산을 넘으면 조용히 버리지 않고 `ContextBuildError(L0_OVER_BUDGET)`로 실패한다(`test_l0_over_budget_fails_loudly`).
- **필수 항목 없음 처리**: goal record가 없거나 다른 project면 `integrity=INCOMPLETE` + `missing_ids`로 반환하고 빈 context로 성공하지 않는다. project record 자체가 없으면 `PROJECT_NOT_FOUND`로 중단한다.
- **계층 구성**: L1 = goal + open/reopened Decision + MATERIAL/BLOCKING Unknown + judgment, L2 = Experience/Pattern/Strategy/Principle(RETIRED 제외), L3 = 선택된 record가 참조한 Evidence + project Evidence. 각 항목에 `reason_selected`, `token_estimate`, `disclosure_level`, `applicability`를 기록한다.
- **예산**: `ContextBudget(token_budget, tokens_used, l0_reserved_tokens)`에 실제 사용량을 반영하고, 남은 예산을 넘는 항목은 `ContextExclusion(reason="BUDGET: …")`과 `handle`로 남긴다. 상한 초과 항목도 이유와 함께 제외된다.
- **project/owner 격리**: 다른 project record는 어떤 layer에도 주입되지 않고(시험에서 확인), owner scope가 허용되지 않으면 `OWNER_SCOPE` 사유로 제외된다.
- **handle 권한**: `resolve_handle`이 `OK/EXPIRED/NOT_FOUND(→DELETED)/FORBIDDEN/DIGEST_MISMATCH/TOO_LARGE`를 구분한다. handle 보유 자체는 권한이 아니며 매 조회마다 principal project·owner scope·disclosure 상한·digest를 다시 확인한다(`test_handle_resolution_checks_permission_expiry_and_digest`).
- **projection**: `ProjectionState(projection_version, last_event_sequence)`로 stale 여부를 표시하고, stale이면 `refresh_projection`이 index를 canonical manifest에서 rebuild한다(replay).

## T04 Brain 구현

- **provider 독립**: `BrainAdapter` 프로토콜(`name`, `capabilities`, `respond`). `StructuredBrainClient`가 검증·record 생성·reference 구성을 담당하므로 provider를 바꿔도 같은 canonical record를 읽고 쓴다(`test_different_providers_read_the_same_records`).
- **구조 검증**: structured 응답이 아니면(plain text) 판단으로 승격하지 않고 `BRAIN_PROTOCOL_ERROR`다. grounds/assumptions/unknowns는 canonical ID 접두사(`evidence:`/`assumption:`/`unknown:`)를 요구해 알 수 없는 enum·잘못된 ID를 거부한다. `context_digest` 없음·oversize 응답·context project 불일치·`structured_output` 미지원도 각각 거부한다.
- **repair 제한**: 형식 오류는 정확히 1회 repair하며(호출 2회) 두 번째도 실패하면 `repair_attempts=1`로 종료한다. repair 호출에는 `repair_of` 컨텍스트가 전달된다.
- **rethink**: canonical `brain_judgment:` ID만 허용하며, 결과는 **새 record**이고 `supersedes` reference로 이전 판단을 가리킨다. 이전 record/payload는 수정되지 않는다.
- **fallback**: `BrainDirector.think_with_fallback`은 실패한 primary와 **같은 frozen context 객체**를 fallback adapter에 전달하고 새 judgment ID를 만든다.
- **Secondary**: `engage_secondary`는 governance 승인 ID가 없으면 거부하고, 승인된 경우에도 결과는 `MODEL_JUDGMENT` Evidence record이며 `has_authority == False`다(다수결·최종 통합 권한 없음). Secondary evidence는 `REL_JUDGMENT` reference로 요청한 primary judgment에 연결된다.

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                       → 132 passed (context 13 + brain 17 추가)
.venv/bin/python -m pytest tests/test_agent_runtime.py tests/test_context_shaper.py tests/test_tool_executor.py \
    tests/test_tool_sandbox_coverage.py tests/test_ws02_tool_root.py tests/test_persistent_agency.py -q → 143 passed, 1 failed(기존 red)
ruff check / ruff format --check / mypy                              → clean
```

## 기존 red (분리 기록)

- `tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for` — `tools/ssak_bundle_store.py`가 ALLOWLIST 미등록(HEAD 상태와 동일). T01b 증거와 같은 기존 red이며 내 변경과 무관하다.

  > **2026-09-23 정정.** 이 시험은 이후 샌드박스 ALLOWLIST에 `FIXED_ARGV` 로 등록되면서 **green 이 됐다**(`ARCHITECTURE_REVIEW.md` §1.5). 위 문장은 그 시점의 관찰로 남기되, "기존 red" 는 지금 기준으로 낡았다.

## 남은 것 (다음 카드)

- P05: governance disposition/feedback을 실제 tool gate 흐름에 연결하고 authority grant를 context 요청 승인에 반영한다.
- P06: `DecisionAssurance` 9 check를 순수 함수로 구현한다(현재 payload 계약만 존재).
- P08: 이 builder/adapter를 실제 운영 루프(`runtime.py`)에 연결하고 `context_shaper`/`model_router` 경계에서 hook한다.

## 2026-09-24 v1.1 철학 시나리오 — T03-A~D / T04-A~C (module-level)

v1.1 추가 인수(체크리스트 §4의 T03-A~D·T04-A~C)를 현재 트리에서 구현·시험으로 닫은 회차다.
무관 이력 미주입(T03-A)과 시간·비용 제한(T04-B)·복수 Secondary(T04-C)는 구현이 없어서 이 회차에 새로 들어갔다.

```yaml
check_id: T03-A~D / T04-A~C
status: PASS (module-level)
owner: Brain/context 담당(P04)
source_head: 29a72e75139832e1 (dirty — 본 회차 4파일: context.py·brain.py·두 시험 파일)
command: .venv/bin/python -m pytest tests/cognitive/test_context.py tests/cognitive/test_brain.py -q
exit_code: 0
observed_behavior: 40 passed (context 16 · brain 24) — 아래 시나리오 매핑 참조
artifact:
  - src/antigravity_k/engine/cognitive/context.py — L2 RELEVANCE 제외(applicability goal_match=MISMATCH) + detail handle
  - src/antigravity_k/engine/cognitive/brain.py — TIMEOUT 강제·시도 합산 비용 계상·engage_secondaries(복수 Secondary)
  - tests/cognitive/test_context.py (16 시험)
  - tests/cognitive/test_brain.py (24 시험)
limitations: 실제 provider context window 대비 확인(T03-D)과 실제 router 연결은 P11 이월(NOT_RUN). timeout 강제는 client 수준의 경과 검사다 — adapter 스스로의 중단은 provider adapter의 몫이고, 여기서는 선언된 능력(timeout_seconds)을 넘은 응답을 받지 않는다.
verified_at: 2026-09-24T12:44:07Z
```

### 시나리오 매핑

- **T03-A 최소 주입** — `test_irrelevant_history_is_not_injected_even_with_budget_left`: 예산이 넉넉해도(100_000) applicability가 `goal_match=MISMATCH`를 선언한 이력은 L2에 주입되지 않고 `RELEVANCE:` 사유 제외 + detail handle로만 남는다. applicability를 선언하지 않은 이력은 advisory로 그대로 주입된다(무관하다고 단정하지 않는다).
  **무관성의 기계적 신호를 applicability 계약으로만 잡은 이유**: 참조 도달성(goal 참조 그래프)로 정의하면 성장 데모의 전제가 깨진다 — growth fixture의 goal은 일부러 evidence를 참조하지 않는다("어떤 evidence가 필요한지는 축적된 경험이 안다", `growth.py goal_record`). 그 이상의 의미적 무관성 판단은 Brain의 몫이라 계약이 정한 경계를 넘지 않는다.
- **T03-B 선택적 확장** — `test_selective_handle_expansion_returns_only_that_record`: 제외된 무관 이력 둘 중 하나의 handle만 확장하면 그 기록의 원문만 돌아오고 다른 무관 이력은 content에 없다(전체 이력 재주입이 없다). 권한·만료·digest 재확인은 기존 `test_handle_resolution_checks_permission_expiry_and_digest`가 지킨다.
- **T03-C 현재 우선** — `test_past_conclusion_with_context_mismatch_stays_advisory`: 높은 confidence(0.9 프로필) + `context_match=MISMATCH` 원칙은 L2 advisory 항목으로만 오고(항목의 `applicability=MISMATCH`가 그대로 보인다) L0/L1(현재 상태)에 들어가지 않으며, confidence는 레코드 payload 안에만 있다 — `ContextItem`에는 confidence 필드가 없다(confidence/applicability/assurance 미혼합).
- **T03-D 제약 보존** — module 반쪽은 기존 시험이 이미 지킨다: `test_l0_over_budget_fails_loudly`(L0 초과는 조용히 버리지 않고 실패)·`test_budget_overflow_is_explicit_with_handle`(예산 초과 명시 + handle)·`test_missing_required_id_reports_incomplete`(불완전 상태 처리). **실제 provider context window 대비 확인은 P11 이월(NOT_RUN).**
- **T04-A 연속성** — `test_brain_swap_keeps_records_and_does_not_force_previous_conclusion`: 같은 canonical store에서 provider A의 판단을 commit하고 context를 다시 짓면 이전 판단은 L1 "recent judgment" **이력 항목**으로만 온다. process restart 뒤 새 client/director(provider B)가 같은 기록 위에서 **다른 결론**을 내려도 유효하다 — 새 judgment ID, `supersedes` 없음(think는 rethink가 아니다), 원본 판단 digest 불변.
- **T04-B protocol** — `test_elapsed_over_declared_timeout_is_rejected`: adapter가 선언한 `timeout_seconds`(30)을 넘은 유효 응답은 `TIMEOUT`으로 거부된다(선언된 능력 밖의 응답은 쓰지 않는다). `test_repair_cost_is_accounted_on_the_judgment`: repair 시도의 token 비용도 합쳐 judgment에 계상된다(prompt 10+7=17, completion 5+3=8). repair 1회 제한·fallback 동일 frozen context·plain-text 승격 금지는 기존 시험 세트가 지킨다.
- **T04-C 의미 권한** — `test_multiple_secondaries_are_delivered_verbatim_without_majority`: 반대 의견("찬성"/"반대")을 낸 두 Secondary가 각자의 MODEL_JUDGMENT evidence로 **그대로** 남는다(claim 변형 없음, independence_group 별개), 최종 결론은 두 evidence를 grounds로 참조한 **Primary의 새 판단 기록**이다. `test_unanimous_secondaries_are_not_collapsed`: 같은 의견도 하나의 'consensus' 기록으로 합쳐지지 않는다. `test_secondary_set_requires_governance_approval`: governance 승인 없이 복수 Secondary도 거부된다. `test_secondary_set_fails_closed_when_one_member_fails`: 하나가 실패하면 부분 결과를 내지 않는다 — 일부 의견만 남은 자료는 "여럿이 다수로 말했다"로 읽히므로 전체 실패다(fail-closed).

### 구현 노트

- `ContextBuilder.build`는 L2 후보를 `_l2_candidates`로 모은 뒤 `_goal_mismatch`(레코드 payload의 applicability profile `goal_match`)인 항목을 제외·handle 발급하고 `_build_layer`에는 관련 이력만 넘긴다. L3(project-scope evidence fallback)은 그대로다 — evidence는 현재 자료이고 무관 주입은 pollution metric(growth)이 관찰·보고하는 대상이지, Body가 의미적으로 걸러낼 수 있는 것이 아니다.
- `StructuredBrainClient`는 `timer`(기본 `time.monotonic`)로 경과를 재고, 검증을 통과했어도 선언 `timeout_seconds` 초과면 `TIMEOUT` 실패를 낸다. token 비용은 시도(repair 포함)를 합산해 `BrainJudgment.prompt_tokens/completion_tokens/elapsed_seconds`에 기록한다.
- `BrainDirector.engage_secondaries`는 복수 Secondary를 같은 frozen context로 호출해 각각 `SecondaryEngagement`(독립 evidence)로 돌려준다. 기존 단일 `engage_secondary`는 동작·오류 문장 그대로 유지된다.
