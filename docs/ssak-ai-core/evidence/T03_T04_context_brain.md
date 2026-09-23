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
