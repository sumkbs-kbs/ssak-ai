---
title: "Detailed Implementation Roadmap and Agent Handoff"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# Detailed Implementation Roadmap and Agent Handoff

## 작업 범위와 완료 상태

Constitution → Architecture Specification → 관련 Protocol → Gap Analysis → 본 Roadmap → Acceptance Checklist 순서로 읽는다. 헌법과 Architecture Invariants가 하위 구현 계획보다 우선한다.

이 문서는 P00~P12 전체 구현 계약이다. v1.1에서 Experience 선별, 의미 판단 책임, 초기 benchmark, 철학 검증 시나리오를 보완했다. 각 카드의 기존 상태는 인계 문서에 보고된 범위를 보존한 것으로, 이번 문서 편집에서 구현을 재검증한 결과가 아니다. 추가 조건과 현재 source/digest를 대조하기 전에는 전체 카드 완료로 확대하지 않는다.

`신규`로 표시된 소유 경로는 원래 계획의 분류다. 일부는 이미 구현 보고가 있으므로 작업 시작 시 존재 여부와 현 내용을 확인하고 중복 생성하지 않는다. 모든 소스 경로는 repository root 기준이며 `engine/` 등은 `src/antigravity_k/` 아래를 뜻한다. `scripts/`, `tests/`, `docs/`는 repository root 아래다.

## 공통 의미 계약

### Brain/Body 책임

Body는 ID·시간·버전·측정값·차이·반복·권한·scope·형식·provenance를 확인한다. 의미적 해석, 인과 가설, 대안 생성, 판단 근거의 의미적 타당성, Secondary 의견의 최종 통합은 Primary Brain이 맡는다. human-assisted 학습도 가능하며 해석 주체를 기록한다.

Evaluator와 PatternBuilder가 Body에 있다는 이유로 독립 semantic judge가 되어서는 안 된다. 기계적 집계는 직접 수행하되 의미 해석이 필요하면 권한·예산 안에서 Primary Brain에 요청하고 MODEL_JUDGMENT/INFERENCE/HYPOTHESIS 등으로 기록한다. Brain 판단을 FACT·실행 권한·검증 통과로 자동 승격하지 않는다.

### Experience 선별과 보존

1. 필요한 Operational Record와 Observation을 먼저 보존하고 provenance를 연결한다.
2. Expected↔Observed 비교와 현재 근거를 바탕으로 미래 판단에 재사용 가치가 있는지 평가한다.
3. 가치가 없으면 Operational Record로 유지한다. 있다고 판단하면 근거와 해석 주체를 남겨 Experience를 형성한다. 불명확하면 선별을 보류하고 후속 관찰과 연결할 수 있다.
4. 이후 의미 있는 근거가 생기면 기존 기록을 참조한 새 Experience를 추가한다. 원래 기록은 덮어쓰지 않는다.

선별 사유에는 의미 있는 예상/관측 차이, 중요한 가정의 검증·반증, Unknown의 변화, Failure/Recovery/Risk Shaping/Rollback, 환경 차이, 중요한 Human feedback·권한 변화가 포함된다. 예상과 일치한 결과도 중요한 독립 재검증이면 Experience가 될 수 있다. 고정된 원시 delta 임계값만으로 의미적 가치를 단정하지 않는다.

선별 기록은 최소 episode reference, disposition(OPERATIONAL_ONLY/EXPERIENCE/DEFERRED), reason, evidence references, producer, recorded_at, policy version을 가진다. 이는 v1 구현 표현이며 새 헌법 원칙이 아니다. 기존 Event로 충분하면 별도 entity를 추가하지 않는다. schema/Protocol 정합화는 P01/P08이 책임진다.

OutcomeEvaluation은 결과, DecisionEvaluation은 당시 이용 가능했던 정보에 비춘 판단, ExecutionEvaluation은 실행 품질을 다룬다. 나중에 얻은 지식으로 과거 판단을 자동 오판 처리하지 않는다. 원인 불명 상태도 기록·종료할 수 있다. Experience 선별과 Knowledge/Policy 승격은 서로 다른 절차다.

### 성장과 권한

초기 한 영역의 성장 데모로 시작하되 Context, Brain engagement, Governance, Closure, Risk Shaping, Retrieval, Tool/Verification, Authority Delegation으로 확장 가능한 후보·검증·version·trace 경로를 유지한다. 모든 영역의 자동 학습을 v1에서 구현할 필요는 없다.

검증된 정책은 기존 grant와 human ceiling 안에서 운영 선택·위임 범위를 조정할 수 있다. 새로운 권한을 스스로 발급하거나 protected boundary를 높일 수 없다. 권한 확대가 필요하면 근거를 제안하고 해당 인간 결정 절차를 거친다.

### 초기 계측과 문서 동기화

P00에서 metric·baseline·split·실행 manifest 계약을 정의하고, P01에서 실행 가능한 최소 benchmark skeleton을 만든다. 아직 없는 mechanism은 NOT_AVAILABLE/NOT_RUN으로 표시하며 결과를 만들지 않는다. P10은 초기 skeleton을 실제 성장·ablation 평가로 완성한다.

새 Cognitive Entity, Governance Mode, Authority Boundary, Experience/Decision Lifecycle, Brain Responsibility, Learning Path 변경은 담당 Protocol·schema·traceability·인수시험을 함께 갱신해야 완료다. 인간 승인이 필요한 원칙 변경과 일상적인 구현 상세 결정을 구분한다.

## 순서와 병렬화 경계

```text
P00a 경계·기준선 + P00b 계측 명세
  → P01 모델·계보 + benchmark skeleton
    → P02 저장
      ├→ P03 보호 → P05 Governance → P06 COMMIT → P07 Action
      └→ P04 Context·Brain
P04 + P06 + P07 → P08 운영 루프·Experience
P08 → P09 학습 → P10 성장 평가 → P11 사용자 경로 통합 → P12 최종 인수
```

P04는 P03~P07과 소유 파일이 겹치지 않을 때 병렬 가능하다. 공유 model/store API는 필요한 module 계약 인수 후 고정한다. 후속 통합 인수가 남아 있으면 정확한 범위와 이월 카드·시험을 기록한다. P00 전체 entrypoint 인수가 남아 있어도 확인된 범위의 모듈 개발은 가능하지만 production 승격은 불가하다.
기존 `agent_runtime.py`, `tool_executor.py`, `config` 수정은 통합 담당 한 명만 반영한다. 다른 담당은 adapter와 필요한 hook 명세를 전달한다.
각 카드 1개를 하나의 검증 가능한 변경 단위로 취급한다. 일정 추정은 P00 기준선과 작업량 확인 후 정하며 근거 없는 완료 날짜를 확정하지 않는다.

## 공통 완료 규칙

- 작업 시작 전에 현재 디스크 파일을 다시 읽고 담당 파일·입출력 계약·선행 evidence를 확인한다.
- 타 작업의 수정·vault_data·NX QA 기록을 revert/stash/delete하지 않는다.
- 새 .py 구현은 저장소 typing/lint 관례와 해당 AGENTS/skill 지침을 따른다.
- 단위 시험뿐 아니라 해당 runtime 표면에서 한 번 실제 작동을 관찰한다.
- evidence는 command, exit, observed behavior, timestamp, source SHA와 dirty digests, artifact path를 포함한다.
- 기존 red는 별도 기록하며 신규 red를 섞어서 허용하지 않는다. mock 성공을 실제 외부 action 성공으로 보고하지 않는다.
- 상태는 NOT_STARTED/IN_PROGRESS/BLOCKED/IMPLEMENTED_UNVERIFIED/VERIFIED이며 반드시 scope와 specification_version을 붙인다. module VERIFIED와 integrated VERIFIED를 구분한다. 전체 카드 체크는 해당 버전의 모든 필수 조건과 명시된 이월 통합 조건이 충족됐을 때만 한다.
- 기존 evidence는 역사로 보존한다. 신규 조건은 NOT_RUN으로 시작하고 현재 source SHA+dirty digests에 대한 재사용 가능 범위를 판정한다.

## 실행 카드

### P00 — 현재 경계 재검증·기준선

- 기존 보고 상태: 부분 완료(증거: evidence/T00_baseline.md): hash drift 0, entrypoint 표, 핵심 회귀 127 passed. 전체 entrypoint 실호출/별도 data root 기준선은 미실행
- 담당: 통합 담당
- 선행 조건: 없음
- 소유 파일: docs/ssak-ai-core/CURRENT_TREE_MANIFEST.json 및 GAP 문서 (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: manifest hash를 현재 파일과 대조하고 변경 시 해당 함수·호출부를 재탐색한다. CLI/API/stream/background/MAX/secondary/self-evolution별 실행 진입과 권한 경계를 표로 확정한다. 기존 테스트 명령을 Makefile/CI에서 확인하고 별도 임시 data root에서 기준선을 수집한다.
- 인수 기준: T00a: 각 entrypoint→runtime→tool gate 경로의 파일·symbol 근거와 기존 실패 목록; 그래프가 없으면 index 후 탐색.
- 복구: 소스 변화 없음. 기존 dirty 파일을 baseline으로 보존.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: T00a는 현재 경계·기존 실패를 재확인한다. T00b는 metric 정의·분모·측정 구간·Fresh baseline·train/validation/final held-out 분리·source/brain/code/hardware/task/policy manifest를 P01 이전에 고정한다. 기존 결과를 새 측정 결과로 주장하지 않는다.
- 추가 소유: docs/ssak-ai-core/evidence/benchmark_spec.md. 이 경로는 신규 산출물의 목표이며 아직 생성됐다는 뜻이 아니다.
- 추가 인수: T00b-A에서 spec과 비중복 split/metric 계약 확인. 초기 회귀 근거 없이 현재 코드가 정상이라고 단정하지 않는다.


### P01 — Typed Cognitive Model·계보 계약

- 기존 보고 상태: VERIFIED(module-level, 증거: evidence/T01a_typed_model.md): models.py/references.py 구현, tests/cognitive/test_models.py 57 시험, contracts/record-entities.schema.json 생성기 추가. runtime 연결은 P08/P11
- 담당: 주 에이전트 직접
- 선행 조건: P00
- 소유 파일: 신규 engine/cognitive/models.py, references.py; tests/cognitive/test_models.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 22개 entity와 supplemental entity를 discriminated union으로 정의한다. envelope JSON schema를 payload별 schema로 확장한다. stable ID, timezone-aware 시간, enum, provenance, typed ref, observation/interpretation 분리를 구현한다. Core 모델은 provider/UI를 import하지 않는다.
- 인수 기준: T01a: unknown enum/naive time/cross-project ref/잘못된 type 거부; roundtrip 손실 0.
- 복구: 새 namespace만 추가. 기존 runtime 연결 없음.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: Operational Record와 Experience 선별 기록·해석 주체·당시 Context reference를 기존 Event/Experience 모델로 표현 가능한지 확인한다. 불충분한 계약만 확장하고 Protocol/schema를 동기화한다.
- 추가 소유: scripts/benchmark_cognitive_growth.py의 최소 skeleton, tests/cognitive의 계측 fixture. P10으로 ownership을 인계한다.
- 추가 인수: T00b-B에서 skeleton 정상 입력·잘못된 입력·help 및 manifest 출력을 직접 확인한다. 출력은 관측한 baseline만 포함하며 미구현 mechanism을 성공으로 표시하지 않는다. T01a는 선별 기록 roundtrip·provenance·타입 경계를 포함한다.


### P02 — Canonical store와 legacy adapter

- 기존 보고 상태: VERIFIED(module-level, 증거: evidence/T02_canonical_store.md): store.py/legacy_adapter.py 구현, tests/cognitive/test_store.py 17 + test_legacy_adapter.py 9 시험. VaultEngine과 같은 lock file 사용, legacy SQLite read-only 확인
- 담당: 저장 담당
- 선행 조건: P01
- 소유 파일: 신규 engine/cognitive/store.py, legacy_adapter.py; tests/cognitive/test_store.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: create-only record·transaction manifest·Git persistence를 구현한다. Vault lock 재사용 가능성을 확인하고 별도 중복 lock 순서를 만들지 않는다. PersistentAgency event/task IDs를 origin reference로 연결한다. commit 실패·동시 writer·index rebuild를 시험한다.
- 인수 기준: T02: duplicate ID 거부, write/commit/publish 각 crash 복구, 원본 digest 불변, 미완료 transaction 비노출.
- 복구: feature off, 기존 DB 불변; 신규 store root 보존. backfill은 dry-run 전용.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T02/T09에서 OPERATIONAL_ONLY 기록도 보존하며, 뒤늦은 Experience 형성이 원본을 변경하지 않음을 확인한다. 실제 Vault writer와의 동시성은 P11/P12에서 연결 시험하고 그 전에는 module 결과로만 표시한다.


### P03 — 헌법·보호 권한 enforcement

- 기존 보고 상태: VERIFIED(module + tool gate + store, 증거: evidence/T01b_protection.md): protected_targets.py, permission_gate.py 연결, store write_guard, tests/cognitive/test_protection.py 19 시험. migration/evolution hook과 승인 발급은 P05/P06/P11
- 담당: 주 에이전트 직접
- 선행 조건: P01, P02
- 소유 파일: 신규 engine/cognitive/protected_targets.py; 기존 tool gate/evolution 연결점; tests/cognitive/test_protection.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 헌법과 protected authority 경로에 write allowlist를 강제한다. canonical path·symlink·shell·plugin·migration·policy target 우회를 모두 검사한다. 신뢰 가능한 human 승인 record에 action digest와 범위를 결박한다.
- 인수 기준: T01b: learned policy와 runtime actor의 직접/간접 헌법 변경 거부; 승인 없는 protected ceiling 변경 0. hash 검사만으로 완료 금지.
- 복구: flag off; 기존 보호를 낮추지 않는다. 경계 누락이면 승격 중단.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T01b는 guard 함수 시험과 실제 shell/plugin/migration/evolution 진입 경로 시험을 분리한다. 호출부 hook 누락이 있으면 전체 보호 PASS가 아니다. 인간 승인 발급 주체의 진위·scope·digest·만료·취소 검증을 P05/P07/P11과 연결한다.


### P04 — Context reconstruction·Brain adapter

- 기존 보고 상태: VERIFIED(module-level, 증거: evidence/T03_T04_context_brain.md): context.py(L0~L3·예산·handle 권한·projection replay), brain.py(structured 검증·repair 1회·rethink supersedes·fallback·secondary 무권한), tests/cognitive/test_context.py 13 + test_brain.py 17 시험. 실제 router/provider 연결은 P08/P11
- 담당: Brain/context 담당
- 선행 조건: P01, P02
- 소유 파일: 신규 engine/cognitive/context.py, brain.py; 기존 context_shaper/model routing adapter; tests/cognitive/test_context.py, test_brain.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: L0~L3와 handle permission을 구현한다. 현재 state revision을 pin한다. think/rethink structured 응답을 검증하고 제한 repair를 구현한다. 기존 router를 재사용하되 Primary와 conditional Secondary를 구분한다.
- 인수 기준: T03/T04: 제약 예산 초과 명시, stale/타project handle 거부, schema invalid 응답 실행 0, provider A/B 동일 기록 읽기.
- 복구: 새 adapter flag off; plain-text legacy를 FACT로 승격하지 않음.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: 관련성이 없는 이력을 예산이 남는다는 이유로 주입하지 않는다. 현재 Goal/state/constraints/evidence/unknown이 기본이며 경험은 작은 advisory와 detail handle로 시작한다. 결론 유도 문구를 생성하지 않는다.
- 추가 인수: T03-A~D로 최소충분·선택적 확장·과거 결론 비강제·L0 보존을 검증한다. T04-A~C로 Brain 교체와 Primary의 최종 semantic integration을 검증한다. Secondary 다수결·Body 합성은 최종 판단 권한이 아니다.


### P05 — 요청 Governance와 다차원 Authority

- 기존 보고 상태: 미착수
- 2026-09-22 구현 보고(P05): module + tool_executor surface PASS, 31 시험, source head 79582ccd. 증거: evidence/T05_governance.md. CLI/API 사용자 표면 연결과 사람 승인 발급 주체 검증은 이월 조건(P11)이다.
- 2026-09-22 보강 보고(T14 회귀 발견): 32 시험. `AuthorityProfile.evaluate`의 dimension 비교를 `is`에서 `models.same_enum`(정의 module·class 이름·값)으로 바꾸고, cognitive core의 raw enum identity 비교 95곳을 같은 helper로 통일했다. 중복 로드된 같은 이름·값의 enum은 매칭되고, 정의 module이 다른 enum(예: cognitive `RiskLevel` vs 도구 `RiskLevel`)은 매칭되지 않는다. 재발 감사: scripts/audit_enum_identity.py(위반 0건), 시험: tests/cognitive/test_enum_identity.py(8건).
- 담당: 권한 담당
- 선행 조건: P01, P03
- 소유 파일: 신규 engine/cognitive/governance.py, authority.py; 기존 tool_executor adapter; tests/cognitive/test_governance.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: APPROVE/limits/reshape/defer/deny 결과와 No Silent Governance feedback을 구현한다. grant scope/expiry/revocation을 검사하고 parent delegation을 부분집합으로 제한한다. 위험 재구성은 실행 가능한 guard로 구체화한다.
- 인수 기준: T05: 모든 disposition fixture, reshape args 재검사, 승인 재사용 범위 일치, 취소 즉시 반영, 단일 score 판정 없음.
- 복구: 기존 gate를 유지하며 adapter만 disable. 권한이 더 넓어지는 fallback 금지.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T05-A~D에서 DENY/DEFER/RESHAPE feedback, 위험 재구성 후 허용된 제한 행동, ACCEPTABLE Unknown 허용, 승인 범위 재사용을 시험한다. reshape는 grant·human-only boundary를 우회하지 않는다. Body가 Brain 결론을 의미적으로 마음에 들지 않는다는 이유로 요청을 거부하지 않는지 확인한다.


### P06 — COMMIT·Decision lifecycle

- 기존 보고 상태: 미착수
- 2026-09-22 구현 보고(P06): module + canonical store 표면 PASS, 28 시험, source head 79582ccd. 증거: evidence/T06_commit.md. loop(P08)·사용자 표면(P11) 연결과 decision_revision 증가 트리거는 이월 조건이다.
- 담당: 주 에이전트 직접
- 선행 조건: P01, P05
- 소유 파일: 신규 engine/cognitive/readiness.py, decisions.py; tests/cognitive/test_readiness.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 원문 9개 readiness check와 READY/READY_WITH_GUARDS/NOT_READY를 구현한다. blocked unknown·evidence ref·guard receipt·authority revision을 검사한다. closure/reopen/reassessment를 append한다.
- 인수 기준: T06: provider fake가 호출 시 실패하도록 해도 gate 성공; 부실 rollback/권한변경 차단; reopen은 옛 trace digest 불변.
- 복구: 연결 전 pure module로 시험. semantic verifier를 재사용하지 않는다.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T06-A~D에서 LLM 호출 0뿐 아니라 규칙/점수 기반 semantic 재심사도 금지한다. readiness 입력이 같고 의미 결론만 다른 경우 결론 선호를 이유로 결과가 바뀌지 않아야 한다. action/constraints/evidence/authority가 달라지면 readiness가 달라질 수 있다. ACCEPTABLE Unknown 허용, guard 강제, freshness, material reopen을 검증한다.


### P07 — Action receipt·복구 연결

- 기존 보고 상태: 미착수
- 2026-09-22 구현 보고(P07): module + 실제 ToolExecutor·CanonicalStore 표면 PASS, 17 시험, source head 79582ccd. 증거: evidence/T07_actions.md. task_state_store 재시작 복구 배선과 OBSERVE 경험 형성은 P08, 사용자 표면 노출은 P11 이월 조건이다.
- 담당: 실행 담당
- 선행 조건: P02, P05, P06
- 소유 파일: 신규 engine/cognitive/actions.py; 기존 tool_executor/task_state_store adapter; tests/cognitive/test_actions.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: persist intent→권한 freshness→기존 ToolExecutor→receipt→관찰 순서. 제출 idempotency와 action idempotency를 분리한다. crash 후 outcome 조회와 reconciliation을 우선한다.
- 인수 기준: T07: 동일 action key 2회 중복 effect 0; effect 후 crash·취소·timeout→UNKNOWN; 비idempotent 재dispatch 금지.
- 복구: 신규 dispatch 경로 off; 이미 발생한 action은 receipt로 복구, 자동 삭제/취소 선언 금지.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T07은 Cognitive Request EXECUTE와 최종 ACTION 양쪽의 side effect에 권한·중복 방지·receipt 경계를 적용한다. 단순 read도 network/cost/privacy 권한 검사를 생략하지 않는다. 외부 결과 UNKNOWN을 임의 성공으로 바꾸지 않는다.


### P08 — 최소 운영 루프와 Experience 형성

- 기존 보고 상태: 미착수
- 2026-09-22 구현 보고(P08): module + 실제 ToolExecutor·CanonicalStore 표면 PASS, 21 시험, source head 79582ccd. 증거: evidence/T08_T09_episode.md. ownership는 ADR-0004-cognitive-loop-ownership.md로 확정했다(legacy CognitiveLoop는 production 경로 유지, 신규 runtime은 opt-in). engine/agent_runtime.py 연결과 사용자 표면 opt-in, decision/context record 제공자 연결은 P11 이월 조건이다.
- 담당: 통합 담당
- 선행 조건: P04, P06, P07
- 소유 파일: 신규 engine/cognitive/runtime.py, experience.py; engine/agent_runtime.py 최소 연결; tests/cognitive/test_episode.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 기존 CognitiveLoop와의 ownership를 ADR로 확정한다. Simple/expanded loop, feedback, targeted rethink, stop budget, deferred observation을 연결한다. 성공/실패/불명 episode를 형성한다.
- 인수 기준: T08/T09: temporary file action으로 한 바퀴 실제 완주; repeated request bounded; interpretation append 후 역사 동일.
- 복구: opt-in flag off로 legacy 복귀. 새 history 유지.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: 공통 의미 계약의 Experience 선별을 구현한다. Operational Record→선별→Experience와 Experience→Knowledge/Policy 승격을 구분한다. 평가의 의미 해석은 Primary 또는 명시된 human-assisted 경로로 수행한다.
- 추가 인수: T08-A~D에서 simple 경로의 불필요한 Secondary/재사고/검증 0, targeted rethink, material delta 종료, stop≠READY를 관찰한다. T09-A~E에서 선별·예상 일치 재검증·세 평가 분리·불명 결과·후속 관찰 append를 확인한다. module 결과와 실제 loop 인수를 분리한다.


### P09 — 후보·검증·정책 lifecycle

- 기존 보고 상태: 미착수
- 2026-09-22 구현 보고(P09): module + 실제 CanonicalStore 표면 PASS, 29 시험, source head 79582ccd. 증거: evidence/T10_learning.md. learning.py(Evaluator/PatternBuilder/Validator, typed candidate, applicability·lifecycle) + policy_store.py(CAS activation, pin, rollback, retire, behavior change trace, 권한 ceiling 불변)를 구현했다. 실제 미래 행동 변화의 성능 비교는 P10, runtime·사용자 표면 연결은 P11 이월 조건이다.
- 담당: 학습 담당
- 선행 조건: P02, P08
- 소유 파일: 신규 engine/cognitive/learning.py, policy_store.py; tests/cognitive/test_learning.py (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: Evaluator/PatternBuilder/Validator interface와 typed candidate 구현. source independence와 split을 확인한다. CAS activation, version pin, rollback, retirement, behavior trace 저장.
- 인수 기준: T10: 검증 없는 promotion 거부, 단일 실패로 active 변경 없음, 동시 promotion 1개, rollback 후 선택 복원.
- 복구: 이전 policy activation을 새 event로 지정. 후보·실패 report 보존.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: Evaluator/PatternBuilder의 기계 처리와 의미 해석 호출을 구분하고 producer/provenance를 남긴다. human-assisted 후보를 허용하되 검증·승격을 우회하지 않는다. Context 이외 성장 영역의 target/scope/validation/trace 확장 계약을 문서화한다.
- 추가 인수: T10-A~E에서 결과 실패를 판단 실패로 자동 치환하지 않음, Brain 해석을 FACT로 승격하지 않음, 현재 applicability 재평가, 정책 철회·rollback, 권한 ceiling 불변을 검증한다.


### P10 — Growth demonstration·paired benchmark

- 기존 보고 상태: 미착수
- 담당: 평가 담당
- 선행 조건: P09
- 소유 파일: 신규 scripts/benchmark_cognitive_growth.py; tests/cognitive/fixtures; docs/ssak-ai-core/evidence/ (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: Benchmark 명세의 corpus/splits/metric을 사전 등록한다. 실제 runtime에 fixture Brain을 연결해 fresh/mature를 독립 root에서 실행한다. adapter live pilot와 deterministic demo를 분리한다. ablation 6개 결과를 기록한다.
- 인수 기준: T13: 같은 brain/code/hardware/task manifest, 실제 future selection 변화, success 비열등·선택 metric 개선·negative transfer 0.
- 복구: policy 기본 비활성. 개선 없으면 실패로 기록하고 복잡성을 core로 승격하지 않음.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 구현: P00/P01의 skeleton을 인계받아 frozen final held-out으로 평가한다. 결과를 본 뒤 성공 기준을 바꾸지 않는다. 필요 변경은 새 experiment ID로 분리한다.
- 추가 인수: T13에서 같은 Brain/code/hardware/task distribution을 비교하고 실제 정책·선택·행동 변화를 연결한다. deterministic demo와 live pilot를 구분하며 fixture 통과를 일반 성능 우위로 주장하지 않는다. negative transfer 0은 사전 등록된 fixture의 관측 조건이다. 권한·헌법 보호는 ablation하지 않는다.
- 2026-09-22 구현 보고(P10): deterministic fixture 표면 PASS — 17 시험, CLI artifact, source head 79582ccd. 증거: evidence/T13_growth.md. growth.py(spec 사전 등록·frozen splits·Fresh/Mature paired·성장 사슬·6 ablation·NOT_RUN) + scripts/benchmark_cognitive_growth.py(--output/--seed/--mode/--manifest/--store-root/--mechanism) + engine/growth_fixture_tools.py(도구 결선은 adapter 계층 — cognitive 패키지의 architecture guard 유지). FINAL 18 task에서 retry 39 → 15, success 1.0 유지, negative-transfer 감소 0, duplicate dispatch·safety violation 0, 6 ablation 전부 MEASURED. live pilot은 NOT_RUN(exit 2)이며 실제 provider·표본 확대·실측 latency는 이월 조건이다.
- 2026-09-22 추가 구현 보고(P10 live 부속): live pilot harness와 분리 계약 — 12 시험, 증거: evidence/T13_live_pilot.md. engine/cognitive/live_pilot.py(LiveTrialPort, ProviderAttestation, 최소 3 paired trial, 평균·중앙값·p95·분포, 순서 효과, claim scope, NOT_RUN/INVALID) + CLI `--mode live-pilot` NOT_RUN artifact(exit 2). fixture spec으로 live 시작 불가, port 미주입은 수치 없이 NOT_RUN, fixture·live artifact 병합은 FixtureLiveMixError로 거부. 실제 provider 실행과 확증 표본 크기 등록은 사람 결정으로 이월한다.


### P11 — 기존 사용자 경로 opt-in 통합

- 기존 보고 상태: 미착수
- 담당: 통합 담당
- 선행 조건: P08, P10
- 소유 파일: engine/agent_runtime.py 및 발견된 API/CLI adapter; 기존 config; 관련 테스트 (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 기존 CLI/API/stream/background task에서 동일 core를 호출한다. shadow 모드는 action 0. dashboard command palette에 상태·decision trace·policy version 조회를 기존 방식으로 연결한다. UI 변경 시 별도 실제 브라우저 QA.
- 인수 기준: T11/T14: CLI/API 실제 happy/bad input/resume/cancel, feature off 회귀, stream terminal 상태 일치.
- 복구: project 단위 flag off. legacy API shape 유지.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: T11 및 이월된 T01b/T02/T03/T04를 실제 CLI/API/stream/background 경로에서 닫는다. 새로운 보호·Context·Brain·Experience 경로가 legacy 우회 없이 연결되는지 관찰하고 feature off의 기존 동작도 확인한다.
- 2026-09-22 부분 구현 보고(P11): 27 시험, source head 79582ccd. 증거: evidence/T11_surface.md. ① 진입 실측(scripts/measure_cognitive_surface.py) — 9 entrypoint 중 7개가 legacy `engine.cognitive_loop`에 도달하고, core 도달은 추가한 조회 표면 2건(CLI·API 라우터)뿐이며 실행 경로(chat/SSE/engine_context/tool_loop)는 0이다(상대 import 해석을 추가해 재측정). ② engine/cognitive_surface.py — 설정 fail-closed(OFF 기본), SHADOW는 실제 dispatcher(port=None)로 episode를 돌리되 dispatch 0, ACTIVE는 사람 승인 + dispatch port + governance gate + canonical project id가 모두 필요. readiness가 다른 action에 결박된 경우도 거부. ③ CLI `cognitive status`/`cognitive surface` read-only 명령 추가(+70 lines, config.yaml 미변경). - 2026-09-22 추가 구현 보고(P11 API 표면): 7 시험. api/routes/cognitive_surface_api.py — read-only `GET /api/cognitive/surface/status`(legacy/core·mode·승인 상태·dispatch 0)와 `GET /api/cognitive/surface/reach`(정적 실측, 프로세스당 1회 캐시·`?refresh=true`)를 라우터만 추가로 등록해 기존 경로·응답을 바꾸지 않았다. 전체 app 라우트 275건 유지, 새 경로 2건. 증거: evidence/T11_surface.md(API 관찰표 추가).
- 2026-09-22 추가 구현 보고(P11 feature-off 회귀): 5 시험. scripts/measure_feature_off_regression.py — 실제 legacy `CognitiveLoop`(verify→reflect→adapt) transcript와 workspace 파일 상태를 `absent`·`disabled_explicit`·`shadow_enabled` 세 설정에서 비교해 digest 동일(sha256:6a9a4142…)·workspace 불변·would-be write 파일 미생성·shadow dispatch 0을 관찰했다. `enabled=false`+`mode=active` 조합은 OFF로 fail-closed 되어 실행이 켜지지 않는다. 증거: evidence/T11_surface.md §1b. - 2026-09-22 추가 구현 보고(P11 read-only SSE): 4 시험. `GET /api/cognitive/surface/stream` — 표면 상태를 SSE로 보내되 `limit`(1~10)회 snapshot 후 `done`으로 끝나는 유한 스트림이다(무한 폴링·자동 갱신 없음, 범위 밖 422). 스트림이 상태를 바꾸지 않음을 고정했다(반복 호출 payload 동일, `last_episode_id=null`, `dispatched_actions=0`). 기존 chat/agent 스트림 계약은 regress 0(test_nx05_sse_live_revocation·test_messages_api·test_api_server·stream 계열 48 시험 통과). 증거: evidence/T11_surface.md §3. **미완:** 대화 스트림·background 실행 경로에 core 상태를 얹는 배선, 실모델 대화 1건의 응답·도구 호출 수 비교, resume/cancel QA, ACTIVE 실도구 검증은 이월 조건이다(체크박스 미완).


### P12 — migration·최종 인수

- 기존 보고 상태: 미착수
- 담당: 주 에이전트 직접
- 선행 조건: P00~P11
- 소유 파일: docs/ssak-ai-core/evidence 및 IMPLEMENTATION_REPORT.md; migration adapter (경로·존재 여부는 본문 작업 범위 규칙에 따라 확인)
- 구현: 원본/target hash·count·ID mapping dry-run, 기존 regression+architecture tests+manual QA+brain swap+rebuild를 수행한다. 원문 §63 질문에 증거로 답한다. destructive migration은 실행하지 않고 인간 결정으로 분리한다.
- 인수 기준: T12/T14와 전체 checklist 증거 완료. NOT_RUN을 PASS로 바꾸지 않는다.
- 복구: snapshot 복귀/flag off rehearsal 확인. default 활성화는 결과와 scope를 검토 후 결정.
- 인계 산출물: 변경 파일 목록, API/schema diff, 검증 evidence, 미해결 제약, 다음 카드 진입 가능 여부.
- v1.1 추가 인수: 헌법 24개 원칙 각각을 담당 카드·시험·증거와 연결한다. README의 불변조건 표와 T00b/T03-A~D/T04-A~C/T05-A~D/T06-A~D/T08-A~D/T09-A~E/T10-A~E를 전부 점검한다. 기존 PASS를 신규 조건 PASS로 자동 이월하지 않는다.
- 문서 정합화: 관련 Protocol, REQUIREMENTS_TRACEABILITY, IMPLEMENTATION_REPORT, VALIDATION_REPORT의 현재 상태와 본 v1.1을 맞춘다. 기존 기록은 날짜·검증 범위를 보존하며 역사 결과를 덮어쓰지 않는다.
- 2026-09-22 추가 구현 보고(P12 T14 최종 Architecture Review): 18 시험, source head 79582ccd. 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md · scripts/architecture_review.py · tests/cognitive/test_architecture_review.py. 헌법 24원칙을 담당 카드·시험·증거·module에 매핑하고(covered 15 · partial 9 · gap 0, gap 0 자체를 검사), 원문 §63 질문 12개와 SELF_IMPROVEMENT_POLICY §52 drift 질문 10개(triggered 0)에 근거·한계를 붙였다. 검사기 8종: artifact 존재(159 참조) · 문서 상대 link 158건 해석 · 인수 항목 17개 전부 매핑 · `evidence/` 14문서 고아 없음 · 리뷰 문서가 24원칙·§63·§52를 모두 담음 · `measured` 마커가 실제값과 일치(principles 24/covered 15/partial 9/gap 0, §63 12, §52 10, evidence 14, cognitive_tests 353) · source 정렬 · tests/cognitive 수집. 회귀: pytest 전체(fast, 7723 수집/7699 selected) exit 1 — 94 failed/7571 passed/14 skipped/20 xfailed이며 실패 94건은 전부 cognitive core 밖(브라우저 stub fallback·API 인증 설정·ctx/cr 게이트·`/private/var` 경로 allowlist·nx07 기존 문서 기준선 등)으로 변경 전 회귀(95 failed)와 목록이 동일하다. `tests/cognitive -q`는 353 passed이고 전체 회귀에서 cognitive 실패는 0이다. ruff check/format clean(1162 files), mypy 29 source files clean(scripts/benchmark_cognitive_growth.py의 Mapping 인자 오류 1건을 발견해 고쳤다), record schema up to date. 회귀가 찾아낸 결함을 고쳤다: ① `AuthorityProfile.evaluate`가 dimension을 class identity로 비교해 중복 enum class 상황에서 유효한 grant를 NOT_GRANTED→DEFER로 떨어뜨렸다 — `models.same_enum`(정의 module·class 이름·값 비교)으로 고정하고 중복 class 재현 시험(`test_dimension_equality_survives_a_duplicate_enum_class`)을 추가했다. ② 해당 시험이 경로 문자열 patch에 의존해 중복 module에서 옛 객체를 patch했다 — adapter `admit.__globals__`를 직접 patch하도록 고쳤다. ③ 같은 부류를 전수 점검해 cognitive core의 raw enum identity 비교 95곳(`X is Enum.MEMBER`/`is not`)을 모두 `same_enum`으로 통일하고, 재발 감사 `scripts/audit_enum_identity.py`(위반 0건)와 계약·감사 시험 `tests/cognitive/test_enum_identity.py`(8건)를 추가했다. `same_enum`은 module 중복 로드에는 관대하고(같은 module·class 이름·값), 정의 module이 다른 enum에는 엄격하다(예: cognitive `RiskLevel` vs 도구 `RiskLevel`). pydantic 검증이 중복 class를 canonical enum으로 정규화한다는 사실도 시험으로 고정했다. 오염원 `tests/test_flush_budget_contract.py`의 import 시점 `sys.modules` purge는 다른 카드 소관으로 기록만 남겼다. **미완:** 실모델 대화 QA·resume/cancel·ACTIVE 실검증(P11 이월), wheel/sdist build는 릴리스 CI 소관(NOT_RUN), 이 리뷰의 사람 승인 — 체크박스는 미완 유지.
- 2026-09-22 보강 보고(T14 격리 · namespace 오염 제거): 5 시험, source head 79582ccd. 증거: docs/ssak-ai-core/evidence/T14_namespace_isolation.md · scripts/audit_test_namespace_purge.py · tests/cognitive/test_module_namespace_isolation.py. 이전 회차가 "오염원(기록만)"으로 남긴 `tests/test_flush_budget_contract.py`의 import 시점 `sys.modules` purge를 재현·수정했다 — 승격된 그 파일은 일반 suite가 함께 수집하므로, 먼저 import된 시험 파일은 옛 class 객체를, 뒤에 import되는 module은 같은 이름의 새 객체를 잡아 **판정이 실행 순서에 따라** 달라진다(임시 진단으로 RED 재현 → 조건화 뒤 GREEN). purge를 미러 리허설(`NX10_FLUSH_TREE` 지정)에서만 하도록 조건화하고, 승격본과 staged 쌍둥이(docs/qa/.../fsync/)·아직 승격되지 않은 fsync2(F2)를 같은 형태로 맞췄다. 재발 감사 `scripts/audit_test_namespace_purge.py`(수집 대상 시험 파일의 조건 없는 import 시점 purge = 위반 · 현재 0건)와 계약 시험 5건(순서에 기대지 않는 행위 확인 포함)을 추가했다. **미러 리허설 무회귀:** `rehearse_flush.sh` PASS 17 · FAIL 0(P1 적용 전 3 failed로 이빨이 물고, P2 적용 뒤 9 passed, P3 기존 70 passed). 전체 회귀는 네 번 측정했고 순서에 민감하다 — ① 94 failed/7571 passed(수정 전) ② 10 failed/7660 passed(random) ③ 고정 순서 7 failed/7663 passed ④ 고정 순서·정리 뒤 5 failed/7666 passed이며 차이는 수정 효과가 아니라 순서 artifact다(가장 보수적인 값은 ④의 5건이고 모두 이 작업 밖 항목이다). ③의 7건 중 둘은 등록으로 닫았다 — `tools/ssak_bundle_store.py` 를 샌드박스 ALLOWLIST에 `FIXED_ARGV`로 등록(신뢰 루트·sha256·arch 통과 뒤 고정 argv selftest)하고, `dashboard/e2e/ssak-web-integration.spec.ts` 의 조건부 skip 을 조건 토큰·owner·재검토 기한과 함께 등록해 소스 마커 tripwire 를 양방향으로 만들었다(ARCHITECTURE_REVIEW §1.3). 고정 순서 첫 시도가 fd 오류로 중단된 원인도 추적해, fd 손실이 pytest capture 자원 1건뿐이고 제품 code 결함이 아니라는 것을 확인했다(중단은 재현되지 않았고 같은 실행을 두 번 더 돌려 정상 종료). `tests/cognitive`는 358 passed, review 8 checks PASS.
- 2026-09-23 추가 구현 보고(P12 T14 전량 회귀 원장): 27 시험. 증거: docs/ssak-ai-core/evidence/T14_regression_ledger.md · evidence/regression_ledger.json · scripts/regression_ledger.py · tests/cognitive/test_regression_ledger.py. 회귀 수치를 서술이 아니라 **측정 산출물**로만 인용하도록 바꿨다 — 같은 scope 를 두 hash seed(101·202)로 돌려 junit XML 만 읽고, **교집합=결정적 실패 / 대칭차=variant 민감 실패** 로 분리한다(로그 문자열 파싱 0). 502개 파일을 8구간 + subdir = **9 scope · 21 회차**(순서 뒤집기 3회 포함)로 나눠 측정: **결정적 11건 · variant 민감 0건 · 무소유 0건**(회차별 failed 수까지 seed 쌍마다 동일). 결정적 11건은 전부 소유자(레인)를 지정했다 — cr14 fence 2(커밋 이력) · nx07 2(EX-05 대장 행 두 단계 분리) · config.yaml 1 · ws01 5(대화 저장소 v2 마이그레이션 전, 단독 재현) · trn02 1(학습 job cancel API, 단독 재현). 즉 이 체크아웃에서 **seed 를 바꿔도, 수집 순서를 뒤집어도 빨간 집합이 움직이지 않는다**(순서 뒤집기 회차를 3 scope 에 넣어 확인: 0·2·5 빨강 모두 동일) — 이전 회차의 “순서 artifact” 서술(94/10/7/5)은 seed 효과를 가른 측정이 아니었으므로 원장으로 대체했다. 계약: 분류표에 없는 결정적 실패는 unowned 로 남고 게이트가 실패하며, 한 회차뿐인 scope 는 판정하지 않고, **중단된 회차는 판정에서 제외**한다(실측 1회 — 시험이 stdout fd 를 닫아 종료 시 `sys.stdout.flush()` 가 OSError 9 로 죽었고 수집 1860 중 1078 만 기록됐다; 임시 plugin 으로 60파일을 뒤졌으나 원인 시험은 특정하지 못했고 제품 코드 결함 증거는 없다). 리뷰 하니스에 9번째 계약을 추가해 원장 artifact·scope 회차 수·소유자 유무를 검사하고, measured 마커 5종(scope 9·회차 21·결정적 11·drift 0·무소유 0)을 실제 값과 대조한다. **미완:** scope 사이의 순서 효과는 재지 않았다(순서 뒤집기는 9 scope 중 3개에만 넣었다) · 중단 회차 원인 시험 · wheel/sdist build(NOT_RUN) · 이 리뷰의 사람 승인 — 체크박스는 미완 유지.
- 2026-09-23 보강 보고(P12 T14 증거 digest drift): 19 시험 추가(리뷰 harness 34 → 39, cognitive 403 → 422). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · evidence/digest_drift.json · scripts/digest_drift.py · tests/cognitive/test_digest_drift.py. 증거 문서가 파일에 못 박은 sha256 을 추정하지 않고 측정했다 — **pin 50개 중 그대로 29 · 움직임 21 · 깨짐 0**. 움직임은 그 파일이 그 뒤에 바뀌었다는 뜻이고(예: 이 카드의 회귀가 고친 `authority.py`·`actions.py`, T11 배선이 들어간 `cognitive_surface.py`), 그 증거가 현재 내용에 대해 다시 확인되지 않았음을 뜻한다 — 13개 증거 문서에 퍼져 있고 그 재확인을 §5 의 이월 항목으로 남겼다. harness 는 digest 를 현재 값으로 **갱신하지 않는다**: 갱신은 “다시 확인했다” 는 주장이라 사람이 그 내용을 읽어야 한다. 대신 저장본이 썩지 않게 했다 — 파일을 고치면 리뷰의 11번째 검사(`digest_report`)가 저장본과 방금 잰 값을 대조해 실패하고 다시 재게 만든다(재생성은 변경 인정일 뿐 재확인이 아니라는 문장을 artifact 에 함께 남긴다). 계약 시험은 판독(관행 형태·산문의 sha256 제외)·판정(match/drift/missing·기록 보존)·축약 해석·결정성·게이트(저장본 없음/낡음/깨진 pin)·`--emit-json` 무쓰기를 고정한다. 검증: architecture_review **11 checks PASS**(marker 17종 일치) · tests/cognitive 422 passed · digest_drift --gate 0 · ruff clean · mypy clean. **미완:** 21개 pin 의 재확인(각 카드 레인) · 다른 레인 QA 산출물 커밋 여부 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 인용 추적): 6 시험 추가(리뷰 harness 28 → 34, cognitive 397 → 403). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.3 · scripts/architecture_review.py · tests/cognitive/test_architecture_review.py. 리뷰가 증거를 “실재하는가”로만 보던 자리를 “**실재하고 git 에 추적되는가**” 로 넓혔다 — `evidence/T11_surface.md` 가 `tests/test_cognitive_surface_api.py` 를 sha256(2cccfed8d5f499c1…)·11 시험과 함께 인용하면서 그 파일이 추적되지 않아, 이 체크아웃을 잃으면 근거가 사라지는 상태였다(내용은 인용된 digest 와 정확히 일치했고 11 시험 통과 — 그래서 커밋만으로 닫았다). 새 검사는 문서가 문장으로 인용한 저장소 경로(`tests`·`scripts`·`src`·`dashboard`·`tools`·`config`·`data` 아래 파일)를 축약 표기까지 해석해(`tools/ssak_bundle_store.py` → `src/antigravity_k/tools/ssak_bundle_store.py`) 실재 + 추적을 요구하고, glob·생략 표기는 패턴으로 제외한다. 등록이 필요한 인용은 여섯 건이며 성격을 코드에 구분해 적었다 — 아직 만들지 않은 목표 산출물(`evidence/benchmark_spec.md`) · T01b symlink **예시** 경로(`src/innocent.md`) · 재현용 임시 진단(`tests/test_aa_purge_probe.py`) · 다른 레인의 미추적 QA 산출물 3건(`docs/qa/.../nx10/fsync{,2}/*`). 등록은 면죄부가 아니다: 등록된 경로가 추적되면 낡은 등록으로 실패하고 재검토 기한(2026-12-31)이 지나도 실패한다. 검증: architecture_review **10 checks PASS**(인용 214건 전부 실재·추적 · marker 14종 일치) · tests/cognitive 403 passed · ruff clean · mypy clean. **미완:** 다른 레인 QA 산출물의 커밋 여부는 그 레인 결정 · scope 사이 순서 효과 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 원장 중단 재시도): 32 시험(원장 계약 27 → 32). 증거: docs/ssak-ai-core/evidence/T14_regression_ledger.md · scripts/regression_ledger.py · tests/cognitive/test_regression_ledger.py. 위 회차가 “수십 분짜리 회차를 통째로 잃는다”로 남긴 한계를 닫았다 — 회차가 중단되면 같은 조건으로 **한 번 자동 재실행**하되(`--retry-aborted`, 기본 1 · 0이면 끔), 재시도는 조용하지 않다: 회차 기록에 `attempts`·`aborted_attempts` 를 남기고 중단된 시도의 로그를 `<scope>__<variant>.retry<n>.log` 로 보존하며 원장 요약·JSON 에 `retried`(scope·variant 별 중단 횟수)를 싣는다. **재시도를 다 써도 중단이면 `aborted` 로 남아 게이트가 실패한다** — 재시도는 회차를 잃지 않게 해 줄 뿐 증거를 만들어내지 않는다. 초록 회차는 재시도하지 않으므로 회귀 시간은 늘지 않는다. 계약 시험 5건 추가(중단→재시도 기록·상한·0회 끄기·초록 회차 미재시도·원장 요약 노출), 리뷰 marker cognitive_tests 392 → 397 갱신. 검증: architecture_review 9 checks PASS(9 scope · 회차 21 · 결정적 11 · variant 민감 0 · 무소유 0 · marker 14종 일치) · tests/cognitive 397 passed · ruff clean · mypy clean. **미완:** 중단 원인 시험 자체는 여전히 특정하지 못했다(재시도는 완충일 뿐 원인 제거가 아니다) · scope 사이 순서 효과 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-22 부분 구현 보고(P12 migration dry-run): 14 시험, source head 79582ccd. 증거: evidence/T12_migration.md. engine/cognitive/migration.py — legacy SQLite를 `mode=ro`로만 열고(쓰기 시도는 sqlite3가 거부), target overlap guard, `mode=apply`는 `DestructiveMigrationRefused`, 같은 store 재실행은 record를 늘리지 않며(idempotent replay), `CanonicalStore.rebuild_index()`·`verify_digests()` 5/5, rollback rehearsal은 전용 scratch에서만 수행해 dry-run 출력을 보존한다. scripts/migrate_legacy_to_canonical.py — dry-run report artifact(exit 0)·`--apply` 거부(exit 2)·incomplete 시 exit 1. ID mapping 계약: canonical project ID는 최초 매핑 시 발급되는 random ID이므로 root를 옮길 때 mapping manifest를 함께 이관해야 identity가 유지된다(미이관 시 warning). **미완:** destructive in-place 변환은 NOT_RUN(사람 결정), 실사용 vault DB·vector index dry-run, T14 회귀·최종 Architecture Review(헌법 24원칙·§63 근거, 문서 정합성)는 이월 조건이다.


## 후속 에이전트 시작 프롬프트

```text
현재 폴더의 최신 파일과 미커밋 변경분을 기준으로 작업한다.
SSAK_AI_CONSTITUTION.md → SSAK_AI_ARCHITECTURE_SPEC_V1.md → 관련 Protocol →
SSAK_AI_GAP_ANALYSIS_V1.md → IMPLEMENTATION_ROADMAP.md → ACCEPTANCE_CHECKLIST.md 순서로 읽는다.
P00의 미완료 기준선·T00b 초기 계측과 기존 증거의 source/digest를 먼저 대조한다. 이후 선행조건이 충족된 가장 앞 카드를 맡는다.
CURRENT_TREE_MANIFEST.json의 hash가 달라졌으면 관련 근거를 다시 읽고 gap 분석을 갱신한다.
본인 카드의 파일만 수정한다. 같은 코드베이스에 다른 작업자가 있으므로 그들의 변경을 되돌리지 않는다.
헌법·Human authority·기본 철학은 변경하지 않는다. 구현 세부사항은 명세 안에서 결정한다.
모델이 아니라 Body가 canonical state/experience를 소유해야 한다.
COMMIT은 readiness만 검사하고, learned policy는 protected authority를 바꿀 수 없다.
Operational Record와 Experience 선별을 구분하고 의미 해석은 Primary에 맡긴다.
새 인수 항목을 기존 module PASS로 통과 처리하지 않는다.
하나의 카드 완료 시 실제 표면 QA와 테스트 evidence를 남기고 checklist를 갱신한다.
형식 구현 완료와 runtime 인수 통과를 구분한다. NOT_RUN을 PASS로 쓰지 않는다.
주 에이전트 담당 P01/P03/P06/P12는 해당 책임자에게 인계하되 다른 선행 작업은 계속한다.
```
