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
- 2026-09-23 보강 보고(P12 T14 digest 재확인): 6 시험 추가(리뷰 39 → 41, cognitive 422 → 428). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · evidence/digest_reverification.json · scripts/digest_drift.py. 앞선 회차가 “21개 pin 이 현재 파일과 다르다”로 이월한 것을 **계약 시험 수준에서 닫았다** — 증거가 인용한 시험 파일을 현재 트리에서 재실행해 전부 통과했고(test_models 58 · test_store 17 · test_legacy_adapter 8 · test_context 13 · test_governance 32 · test_readiness 28 · test_actions 17 · test_episode 21 · test_learning 29 · test_surface 20 · test_growth 17 · test_live_pilot 12 · test_protection 19), 선언 수치는 대부분 그대로였다(유일한 증가는 test_governance 31 → 32) — 파일 크기만 스냅샷 이후 조금씩 늘었다(learning.py 1221→1230 · cognitive_surface.py 647→681 등). 재확인은 `--record <문서> --method "..."` 로만 기록되고, `--method` 없이는 거부되며, 그 문서에서 **지금 움직인 pin** 만 박는다(낡은·과장된 재확인 금지). 재확인 뒤에 파일이 **또** 바뀌면 그 재확인은 무효(`stale_reverification`)가 되어 게이트가 실패하므로 면죄부가 아니다. 재확인 중 증거 문장 하나가 낡은 것도 드러났다 — `T01b_protection.md` 가 "기존 red" 로 적은 sandbox coverage 시험은 §1.5 의 등록으로 이미 green 이었고, 그 문장에 정정을 붙였다(역사는 지우지 않았다). 검증: architecture_review **11 checks PASS**(digest pin 50 · 그대로 29 · 재확인 21 · 미확인 0 · 재확인 무효 0 · marker 19종 일치) · tests/cognitive 428 passed · digest_drift --gate 0 · ruff clean · mypy clean. **미완:** 실모델·실 vault·사람 승인 표면에서의 재확인 · 중단 회차 원인 · 다른 레인 QA 산출물 커밋 여부 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 카나리아 종료 코드 계약): 7 시험 추가(cognitive 512 → 519). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/harness_canary.py · tests/cognitive/test_harness_canary.py · tests/cognitive/test_architecture_review.py. 앞 회차가 “카나리아가 스스로 실패하면 리뷰가 어느 harness 인지 잃는다” 고 적은 의심은 **반은 틀렸고 반은 맞았다** — 코드를 확인해 보니 `--emit-json` 이 **결과와 무관하게 exit 0** 이었다(하한이 장식이어도 성공을 알렸다). 즉 진단이 사라지는 게 아니라, **JSON 을 내는 실행이 실패를 신고할 방법이 없었다** — 읽는 쪽(리뷰·CI)은 “돌았는데 통과” 와 “돌았지만 아무것도 못 막았다” 를 종료 코드로 구분할 수 없었고, `measure_canary` 의 종료 코드 검사는 그 경로에서 죽은 코드였다. 이제 장식 하한이 하나라도 있으면 **`--emit-json` 도 exit 1**(JSON 은 stdout 에 그대로 — 판정과 진단이 함께 나온다)이고, 리뷰 쪽은 ① 종료 코드가 0 이 아니어도 **JSON 이 읽히면 그대로 쓴다**(어느 harness 가 못 물었는지 이름을 잃지 않는다) ② 종료 코드를 보고에 실어 **모순**(보고는 전부 통과라는데 스스로 실패했다고 말함)을 실패로 잡고 ③ **종료 코드 없는 보고**·**합계가 항목과 다른 보고**도 실패로 잡는다. 시험은 카나리아 쪽 1건(`--emit-json` 이 장식 하한에서 exit 1 + 진단 유지)과 리뷰 쪽 6건(종료 코드 없는 보고 · 모순 · exit 1 이어도 진단이 남는지 · 합계 불일치 · 실패해도 JSON 을 쓰는지 · JSON 이 아니면 None)이다. 검증: architecture_review **13 checks PASS** · tests/cognitive 519 collected(518 passed · 1 skipped) · canary --gate/--emit-json 둘 다 0(정상 저장소) · ruff · mypy clean. **미완:** 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 red 리허설 — 위반 0건인 감사에 red 를 심다): 21 시험 추가(리허설 계약 12 · 리뷰 계약 9, cognitive 579 → 601). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/red_rehearsal.py · scripts/audit_enum_identity.py · scripts/audit_test_namespace_purge.py · tests/cognitive/test_red_rehearsal.py · tests/cognitive/test_architecture_review.py. 두 감사(`audit_enum_identity`·`audit_test_namespace_purge`)의 green 은 이 체크아웃에서 **관찰이 아니라 미관찰일 수 있었다** — 위반이 0건이라 “다 봤는데 깨끗하다” 와 “한 번도 빨간을 본 적이 없다” 가 실행으로 갈리지 않았다(그동안 코드 경로를 읽어 확인했고, 그것을 미완으로 적어 두었다). 이번 회차는 그 자리를 **실측으로** 닫았다: ① 두 감사에 `--root`(감사 대상 트리, 기본은 지금까지처럼 저장소 루트)를 열어 저장소 밖 트리를 돌릴 수 있게 하고(하한도 함께 바뀐다 — 저장소 밖 트리에 저장소 하한 10을 들이대면 오탐이고, 하한 1은 “위반 0건” 과 “아무것도 못 봄” 을 가른다) ② `scripts/red_rehearsal.py` 가 임시 트리에 **진짜 파일로** 위반을 심어 감사를 subprocess 로 돌린다. 실측: `audit_enum_identity` — 심은 트리 exit 1 + 심은 파일 1행을 `[is] status is RiskLevel.HIGH` 로 지목(보고에 심은 파일 이름이 그대로 남는다) · 대조군(같은 자리에 `==`) exit 0 · 없는 트리 exit 1. `audit_test_namespace_purge` — 같은 형태(수집 단계 purge 심음)로 exit 1 + 지목 · 대조군(환경변수 가드 형태) exit 0 · 없는 트리 exit 1. ③ 판정 규칙을 여섯 가지 실패로 고정했다 — 심은 위반을 **못 봄** · **exit 0**(red 를 못 냄) · 봤지만 **심은 파일을 지목하지 않음**(JSON 또는 사람이 보는 출력에 없음) · **대조군이 빨간**(그 리허설은 심은 위반이 아니라 트리 모양을 본 것이다) · **빈 트리를 통과**(“위반 0건” 과 “못 봄” 을 구분하지 못한다) · **traceback 으로 사고**(사고는 판정이 아니다). ④ 리허설되지 않는 층은 **이유와 함께 선언**하고(`DECLARED` — 각 층의 red 재현 경로를 문장으로 적는다), 게이트 자기시험이 그 회계를 stage·카나리아 roster 와 대조해서 **red 재현 경로가 없는 층**이 조용히 생기지 않게 했다. 리허설 자신도 카나리아 여덟 번째 대상이 되었고(하한 “리허설 대상 2≥2” 이 장식인지 확인), 리뷰는 15번째 검사(`red_rehearsal`)로 보고를 읽는다(못 봄 · 오탐 · 빈 트리 통과 · 종료 코드 부재 · 모순 · 합계 불일치를 이름으로 지목). 한 계약은 리허설 자신에게도 적용된다: 심는 자리는 트리 안이어야 하고(`..`·절대 경로 거부) 저장소 스캔은 심은 뒤에도 그대로 깨끗하다 — 시험이 그 둘을 확인한다. 검증: architecture_review **15 checks PASS** · evidence_gate --tier full 9/9 PASS(리허설 stage 포함) · canary 8 harness · red_rehearsal --gate/--emit-json 0 · tests/cognitive 601 collected(600 passed · 1 skipped) · ruff · mypy clean. **미완:** 리허설은 **심은 종류의 위반**만 증명한다(그 층이 볼 수 있는 다른 위반 형태까지 증명하지 않는다) · 대조군은 같은 경로에 허용 형태를 넣은 것뿐이라 그 층의 allow-list 전체를 증명하지 않는다 · 나머지 층의 red 재현 경로는 **시험·기록으로 선언**돼 있을 뿐 같은 방식의 실물 재현은 아니다(그 이유를 `DECLARED` 에 적었다) · 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 증거 게이트 CI 배선 — 문서 변경과 요약): 4 시험 추가(cognitive 575 → 579). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · .github/workflows/evidence.yml · .github/workflows/ci.yml · scripts/evidence_gate.py · tests/cognitive/test_evidence_gate.py. 앞 회차가 남긴 **알려진 한계 두 개를 닫았다**. ① **문서만 바꾼 PR 은 게이트를 건너뛰었다** — `ci.yml` 이 `paths-ignore: docs/**, **.md` 이므로 그 워크플로의 `evidence-gate` job 이 안 돌았고, 그런데 게이트가 주로 보는 것이 문서·증거라 그 구멍은 실질적이었다. 새 `evidence.yml` 이 그 **여집합**(`docs/**`·`**.md`)을 같은 명령(`--tier fast`)으로 맡는다 — 둘을 합치면 모든 변경이 덮인다(코드+문서를 함께 바꾼 PR 은 둘 다 돌지만 각자 30초 안쪽이고 판정은 같은 명령이다). ② **결과가 artifact 로만 남아** “어느 층이 얇아졌나” 를 보려면 내려받아 열어야 했다. 이제 게이트가 `--summary` 로 markdown 요약을 내고(층별 표·보지 않은 층·기준 대비 움직임·문제 목록·`verdict: PASS|FAIL`), 두 워크플로가 그걸 `$GITHUB_STEP_SUMMARY` 에 붙이며 PR 에는 같은 댓글을 갱신하고(문서 워크플로) artifact 2종(JSON·md)을 올린다. **빨간 실행도 요약을 남긴다**(`if: always()`): 요약이 사라지면 리뷰어는 다시 돌려야 하고 그 사이에 트리가 바뀌면 같은 것을 못 본다. 배선은 시험 2건이 **txt 수준으로** 본다 — 두 워크플로가 같은 명령과 `--summary`·`GITHUB_STEP_SUMMARY` 를 쓰는가, 한쪽이 문서를 무시하는 전제(`paths-ignore`)가 아직 살아 있는가(그 전제가 바뀌면 여집합 워크플로의 이유도 바뀌므로 시험이 먼저 말한다). 나머지 2건은 요약 자체의 계약이다(층·보지 않은 층·문제를 담는가, CLI 가 JSON 과 md 를 함께 쓰는가). **미완:** 두 워크플로는 이 체크아웃에서 **실행되지 않았다**(YAML 문법은 파싱해 확인했고, 게이트 명령은 같은 argv 로 직접 돌려 확인 — GitHub Actions 런타임에서의 첫 실행은 이월) · PR 댓글 권한(`pull-requests: write`)은 저장소 설정에 의존한다 · 기준 파일은 자동 갱신되지 않는다(사람의 커밋) · 수치 감소의 원인 분류는 사람 몫 · 이 체크아웃에 위반 0건인 두 감사의 red 미재현 · 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 층별 수치 추이 — 기준 대비): 19 시험 추가(게이트 계약 12 → 28, 리뷰 계약 5). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/evidence_gate.py · evidence/evidence_gate_baseline.json · tests/cognitive/{test_evidence_gate,test_architecture_review}.py. 앞 회차가 이음매를 닫아 **한 번의 실행으로 판정과 수치를 함께** 낼 수 있게 된 것을 실제로 썼다 — 게이트가 층마다 JSON 으로 수치를 받아(`--emit-json`·`--json`·`--output`, stage 가 지목한 키만: `counts`·`coverage`·`measured`·`count`, 목록은 길이) 이번 실행의 **65개 수치**를 저장소의 기준(`evidence/evidence_gate_baseline.json`, 사람이 마지막으로 승인한 상태)과 대조해 **줄어든 수를 먼저** 보여 주고 그대로인 수는 접는다(안 움직인 60줄 사이에 답이 묻힌다). 실제로 잡힌 움직임: `review · measured.cognitive_tests 558 → 574 ▲`(시험을 더한 회차에 기준의 수치가 따라오지 못한 것을 게이트가 지목했다 — 그래서 회차 끝에 기준을 다시 기록했다). 계약을 정하면서 세 가지를 못 박았다: ① **이동은 판정이 아니다**(하한을 깨는 감소는 그 층의 자체 게이트가 실패시킨다) ② 실패로 보는 것은 **수치를 읽지 못한 층**·**못 돌린 층**·**깨진 기준 파일**이다(수가 안 보이는 층의 추이는 증거가 아니고, 읽지 못한 기준을 “기준 없음” 으로 삼키면 그 뒤 추이가 거짓말한다) ③ 기준은 `--record-baseline --method` 로만 갱신되고(무엇을 보고 승인했는지 없이는 거부, `recorded_on`·`method`·수치를 함께 기록) 게이트는 기준을 **읽기만** 한다(돌리는 것만으로 승인 기록이 바뀌면 추이가 거짓말한다). 첫 실행은 “기준 없음” 이라고 말하고, `--tier fast` 는 기준에 있는 회귀 원장을 “이번 실행이 수치를 내지 않았다” 로 적는다(초록으로 덮지 않는다). 리뷰의 14번째 검사가 **기준 파일의 존재·가독성·`method`·`recorded_on`** 까지 보고, 게이트 자기시험이 40건으로 늘었다(수치 추출·불리언 배제·움직임 6종·그대로 접기·기준 없음). 자기시험이 즉시 잡은 결함 하나: `run()` 이 임시 자리를 주지 않으면 파일로 수치를 내는 층이 전부 “수치를 읽지 못했다” 로 빨간이 됐다 — 부르는 쪽이 자리를 주지 않으면 게이트가 만든다. 검증: architecture_review **14 checks PASS**(evidence_gate: stage 8 · 자기시험 40건 · 기준 8개 층 2026-09-23 승인) · evidence_gate --tier full 8/8 PASS · tests/cognitive 575 collected(574 passed · 1 skipped) · ruff · mypy clean. 이 과정에서 부산물 하나를 더 잡았다: 파일로 수치를 내는 층에 자리를 주지 않고 돌리면 그 층이 저장소 뿌리에 `{report}` 라는 이름의 파일을 쓴다(시험 실행이 실제로 그 파일을 남겼고, 지웠다) — 이제 `stage_argv` 가 자리 없이 돌리는 것을 **거부**한다. **미완:** 기준 파일은 이 회차의 상태를 기록한 것이라 그 뒤로 자동 갱신되지 않는다(사람의 커밋) · 수치 감소의 원인 분류는 사람 몫 · 이 체크아웃에 위반 0건인 두 감사의 red 미재현 · 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 JSON 경로의 종료 코드 — 이음매 전수): 9 시험 추가(리뷰 계약 7 · digest 1 · 상태 주장 1, cognitive 549 → 558). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/digest_drift.py · scripts/audit_state_claims.py · scripts/architecture_review.py · tests/cognitive/{test_digest_drift,test_state_claims,test_architecture_review}.py. 앞 회차가 카나리아에서 고친 이음매(`--emit-json` 이 결과와 무관하게 exit 0)가 **그 층만의 문제인지 전수 확인**했고, 두 층이 같은 병을 앓고 있음이 드러났다 — 실측: `digest_drift --gate --artifact <없는 파일>` 은 exit 1 과 "artifact 가 없거나 읽히지 않는다" 를 내는데, **같은 store** 에서 `--emit-json --artifact <같은 파일>` 은 exit 0 을 내며 JSON 17KB 를 그대로 냈다. `audit_state_claims` 도 `--emit-json` 이 무조건 exit 0 이었다(그래서 리뷰의 `returncode != 0` 검사는 두 자리에서 죽은 코드였고, 층이 스스로 빨간 것을 읽는 쪽이 종료 코드로 받지 못했다). 이제 두 경로가 `--gate` 와 **같은 판정**을 쓰고 JSON 은 stdout 에 그대로 남으며, 리뷰는 세 층(카나리아·digest·상태 주장)을 같은 규칙으로 읽는다 — `measure_*` 는 exit 0 이 아니어도 **JSON 이 읽히면 그대로 쓰고** 종료 코드를 보고에 싣는다(진단을 이음매에서 뭉개지 않는다). 검사 쪽 새 실패 두 종류: **종료 코드 없는 보고**(스스로 실패했는지 알 수 없는 보고는 판정이 아니다) · **모순**(보고서는 문제 없다는데 실행이 스스로 실패했다고 말함 — 단 같은 결함이 이미 지목됐을 때는 모순으로 두 번 세지 않는다). `digest_drift --emit-json` 은 이제 판정을 말하므로, artifact 를 가리키지 않은 호출(저장본 없음)은 exit 1 이 된다 — 기존 시험 하나가 그 사실을 기대값으로 고정하도록 고쳐 썬다. 검증: architecture_review **14 checks PASS** · evidence_gate --tier full 8/8 PASS · tests/cognitive 558 collected(557 passed · 1 skipped) · ruff · mypy clean. **전수의 범위:** "쓰고 나서 판정" 하는 나머지 두 경로는 실패 상태를 실제로 재현해 확인했다 — `measure_cognitive_surface --output` 은 하한 미달(빈 source root)에서 exit 1 을 내면서 artifact 3.5KB 를 그대로 쓰고, `architecture_review --output` 도 같은 형태로 verdict 를 종료 코드로 낸다. **미완:** 이 체크아웃에 위반이 0건인 두 감사(`audit_enum_identity`·`audit_test_namespace_purge`)는 **red 상태를 재현해** 확인하지 못했다(코드 경로를 읽어 판정이 반환되는 것만 확인) · 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 증거 게이트 — 여섯 층을 한 번에): 32 시험 추가(게이트 계약 17 · 리뷰 계약 15, cognitive 519 → 549). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/evidence_gate.py · tests/cognitive/test_evidence_gate.py · tests/cognitive/test_architecture_review.py. 앞선 회차까지 여섯 harness 가 **각자** 게이트(자기시험 + 하한 + 카나리아)를 갖췄지만, 그것을 **도는 자리**는 사람의 기억뿐이었다 — CI 는 이 게이트를 하나도 돌리지 않았고(워크플로 grep 0건), 어디가 얇은지 보려면 여덟 개 명령을 손으로 쳐야 했다. `scripts/evidence_gate.py` 가 그 자리를 하나로 묶는다: stage 마다 **독립 process** 로 돌리고(한 층의 예외·중단이 다른 층을 가리지 않는다) 종료 코드·소요 시간·**첫 실패 문장**을 모아 어느 층이 빨간지 이름으로 말한다(fast 7 stage 8초 · full 8 stage 17초). 이 도구 자신도 같은 병을 앓을 수 있으므로(stage 목록이 비거나, 스크립트 이름이 틀려 아무것도 실행되지 않는데 “문제 없음” 이 되는 것) 여섯 harness 에 올린 규율을 그대로 적용했다 — **없는 스크립트 · 없는 산출물 · 제한 시간 초과는 `unrun`(실패)** 이고 `exit_code` 가 없는 결과는 판정이 아니며, stage 수에 하한(`8`)과 **근거(`why`)** 가 있고(하한은 값만 남기면 나중에 내려도 되는지 판단할 수 없다), 자기시험 **25건**이 종류 구분(pass 만 통과다)·tier 필터(full ⊇ fast · fast 는 로컬 전용 층을 돌지 않는다)·roster 정합·판정 문장을 매 실행 다시 물어본다. 자기시험이 즉시 잡은 결함 둘: ① stage 이름과 카나리아가 아는 harness 이름이 달라(`state_claims` vs `audit_state_claims` 등) 네 층이 “사라진” 것으로 보고됐다 — 게이트 stage 이름을 harness 이름에 맞춰 통일했다. ② 판정 문장(`describe`)에 `Outcome` 대신 `Stage` 를 넘겨 자기시험이 예외로 죽었고, 자기시험 예외를 **실패로 바꾸는** 경로가 그 사실을 그대로 보고했다(사고를 판정으로 세지 않는다). **tier 는 숨김이 아니다:** 회귀 원장의 회차 산출물(`.regression-ledger/`)은 커밋되지 않으므로 깨끗한 체크아웃에서는 그 층을 돌릴 수 없다 — `--tier fast`(기본)는 그 층을 **“이 실행이 보지 않은 층”** 으로 적고(통과로 세지 않는다), `--tier full`(로컬)은 전체 roster 를 요구하며 산출물이 없으면 왜 못 돌리는지 말하며 `unrun` 으로 실패한다. **게이트도 카나리아가 본다:** 게이트는 stage 수에 하한을 들고 있으므로 그 하한이 장식인지도 확인해야 한다 — 카나리아 roster 에 `evidence_gate` 를 일곱 번째로 넣어 눈멀게 한 사본(`observed=0`)이 막히는지 본다(카나리아가 7 harness 를 본다 · marker `canary_harnesses` 7 · `canary_ok` 7). 게이트 자신을 stage 로 넣으면 재귀라 그 하한을 보는 자리는 카나리아뿐이고, 이 예외는 코드에 이유와 함께 상수로 남으며 그 목록이 늘어나면 게이트 자기시험이 실패한다. **리뷰는 게이트를 돌리지 않고 명세만 읽는다**(14번째 검사 `evidence_gate`) — stage 스크립트 실재 · tier 유효 · fast tier 비어 있지 않음 · 자기시험 존재와 통과 · 하한 근거 기록 · 카나리아 roster 와의 정합. 겸사겸사 리뷰 §1 표와 마커 표의 낡은 서술을 바로잡았다(검사 13 → **14**, cognitive 442 → **547**, digest_reverified 21 → 22, canary 6 → 7). 리뷰가 `--quiet` 로 돌아도 **실패한 검사의 이름과 이유는 stderr 에 남는다**(`failure_lines`) — 한 명령으로 여섯 층을 도는 게이트가 그 출력에서 실패 이유를 읽으므로, 조용한 실행이 `exit 1` 만 남기면 그 층을 다시 돌려야 한다. 검증: architecture_review **14 checks PASS** · evidence_gate --tier full 0(fast 7 · full 8 stage 전부 PASS) · audit/카나리아 게이트 0 · tests/cognitive 549 collected(548 passed · 1 skipped) · ruff · mypy clean. **CI 배선:** ci.yml 에 `evidence-gate` job(시간 제한 15분, `--tier fast` + artifact 업로드)과 `make evidence-gate`/`evidence-gate-full` 을 추가했다 — 이제 이 명령이 사람의 기억이 아니라 파이프라인에서 돈다. **알려진 한계:** 그 워크플로의 `paths-ignore: docs/**` 때문에 문서만 바꾼 PR 은 이 job 을 건너뛴다(증거 게이트가 주로 보는 것이 문서·증거라 이 빈틈은 실질적이다 — 별도 회차의 대상으로 남긴다). **미완:** `--tier fast` 는 회귀 원장을 보지 않는다(로컬 `--tier full` 필요) · 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 카나리아 검사의 이빨): 7 시험 추가(cognitive 505 → 512). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/harness_canary.py · tests/cognitive/test_architecture_review.py. 앞 회차가 카나리아를 리뷰의 **13번째 검사**로 올렸지만, 그 검사 자체에는 다른 검사들이 가진 이빨이 없었다 — 결함 상태를 재현해 **실패를 확인하는 리뷰 쪽 시험**이 없었고, 그래서 "카나리아가 harness 를 못 보면 어떻게 되나"·"하나가 장식이면 어떻게 되나" 는 코드를 읽어야만 알 수 있었다. 이제 다섯 가지 변형을 각각 재현한다: 카나리아를 못 돌린 경우(통과 아님) · 눈멀게 한 사본을 막지 못한 하한("장식이다", 이름을 문장에 남김) · 정상 측정을 막는 하한(오탐도 탐지력이 아니다) · 실패 문장에 근거를 싣지 않은 하한 · harness 를 하나도 보지 않은 보고. 여기에 `canary_measured` 가 두 값을 보고에서 세는지(장식 하나면 `canary_ok` 가 줄어든다)와 **저장소 카나리아가 여섯 harness 전부에서 무는지**를 더해 7건이다. 겸사겸사 리뷰 §1 표의 낡은 수치를 바로잡았다(검사 12 → **13**, cognitive 442 → **511 passed(수집 512)**, 체크리스트의 artifact 161 → 163 · link 161 → 167 · evidence 15 → 16문서 · 수집 358 → 512). 검증: architecture_review **13 checks PASS** · tests/cognitive 512 collected(511 passed · 1 skipped) · canary --gate 0 · ruff · mypy clean. **미완:** 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 하한 카나리아): 10 시험 추가(cognitive 495 → 505). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/harness_canary.py · tests/cognitive/test_harness_canary.py. 하한을 기록하고 검사하는 장치가 다 갖춰져도 **하나가 남았다** — 하한이 장식일 수 있다(`minimum=0` 이거나 비교가 뒤집혀 있으면 “기록도 있고 자기시험도 통과” 하는데 아무것도 막지 못한다). 카나리아가 각 harness 의 하한을 **일부러 눈멀게 한 사본**(`observed=0`)으로 평가해 세 가지를 본다: ① 정상 측정은 막지 않고(하한이 난폭하면 게이트가 늘 빨개져 무시된다) ② 사본은 막으며 ③ 실패 문장이 **기록된 근거를 함께 낸다**. 여섯 전부 통과하고 리뷰의 13번째 검사(`harness_canary`)가 이를 매 실행 확인한다(marker `canary_harnesses` 6 · `canary_ok` 6). 기준 출처도 명시했다 — `digest_drift`·`regression_ledger`·`audit_state_claims` 는 **기록 artifact**(리뷰가 읽는 것과 같은 자리), 나머지 셋은 저장소 직접 측정. 카나리아 첫 실행이 제 오류를 잡았다: 원장을 **빈 원장**으로 기준 삼아 “정상 측정을 막는다” 는 오탐을 냈고(회차 산출물이 있어야 관측값이 나온다), 저장본 기준으로 바로잡았다. 카나리아 자신도 시험 10건에 물려 있다 — 시험용 하한으로 `minimum=0`(장식) · 정상 측정을 막는 하한 · 근거 없는 하한 · 하한 없는 harness · harness 예외를 모두 재현해 잡히는지 본다. 그 시험이 카나리아의 실제 버그를 하나 더 잡았다(근거 빈 하한을 문제로 적고도 `ok` 가 참으로 남는 모순 — 빈 목록 `all()` 함정). 검증: architecture_review **13 checks PASS** · tests/cognitive 505 collected(504 passed · 1 skipped) · canary --gate 0 · digest/ledger gate 0 · ruff · mypy clean. **미완:** 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 여섯 하한의 근거 기록): 9 시험 추가(자기시험 계약 28, cognitive 486 → 495). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/harness_contract.py · 각 harness artifact·tests/cognitive/test_harness_self_probes.py. 앞선 회차가 상태 주장 감사 하나에만 붙였던 하한 근거 기록을 **다섯 harness 에도** 올렸다 — 각 하한이 `why`(하한을 정한 시점의 관측)와 `margin`(관측−하한)을 들고 artifact 의 `floors` 로 실린다: digest_drift(`pin 50≥1 여유 49` · `문서 13≥1` · “증거 문서 13개가 digest 를 박은 pin 50개(그대로 28 · 재확인 22)”) · regression_ledger(`회차 21≥1 여유 20` · `scope 9≥1 여유 8`) · audit_enum_identity(`스캔 파일 21≥10 여유 11`) · audit_test_namespace_purge(`시험 파일 537≥1 여유 536`) · measure_cognitive_surface(`entrypoint 9≥1` · `실재 9≥1`). 하한을 1로 둔 이유도 문장으로 남겼다 — 잡으려는 것은 ’얼마나 많이 보나’ 가 아니라 ‘보는 능력이 0이 됐나’ 이며, 증거가 정말 주장을 그만두거나 경로가 바뀌면 그 문장을 고쳐 내린다. 리뷰는 이제 **기록이 없는 하한 · 근거가 빈 하한 · 저장본이 낙은 경우(`floors` 까지 비교)** 를 모두 실패로 본다. 이 과정에서 여섯 층이 즉시 일했다: 스크립트를 고치자 T11 이 못 박은 pin 이 무효(STALE)가 되어 재확인을 요구했고(표면 표 legacy 7/9 · core 2/9 재현), digest artifact 가 `floors` 를 갖기 전 저장본은 ’최신이 아니다’ 로 막혔다. 이빨은 `test_harness_self_probes.py` 의 parametrized 계약(여섯 harness 가 모두 하한을 들고 있고 `why` 에 관측 시점이 있는가) + artifact 최신성 시험 4건이다. 검증: architecture_review **12 checks PASS** · tests/cognitive 495 collected(494 passed · 1 skipped) · digest_drift --gate 0 · regression_ledger --gate 0 · ruff · mypy clean. **미완:** 하한을 내리는 판단은 사람 몫 · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 하한 근거 기록): 10 시험 추가(상태 주장 계약 22 · 리뷰 50, cognitive 478 → 486). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/audit_state_claims.py · evidence/state_claims.json · tests/cognitive/test_state_claims.py. 앞선 회차가 “감사자의 탐지력에 하한을 두라” 로 남긴 것을 **하한이 스스로를 설명하게** 만들어 닫았다 — 하한은 판단이므로 **값만 남기면 나중에 누구도 그것을 낮춰도 되는지 판단할 수 없다**. `harness_contract.Floor` 가 `why`(언제 무엇을 몇 개 봤나)와 `margin`(관측−하한)을 값과 함께 갖고, 상태 주장 감사가 그 기록을 artifact `evidence/state_claims.json`(`floors` + `coverage` + `probe` + `claims`) 으로 남긴다 — 현재 값은 **node 지목 산문 6≥1(여유 5) · 상태 주장 4≥1(여유 3)** 이며, 근거 문장은 “2026-09-23 기준 관측: 증거 문서 16개 중 node 지목 산문 6줄 / 주장 4건” 을 담는다(하한이 잡으려는 것은 ‘얼마나 많이 보나’ 가 아니라 ‘보는 능력이 0이 됐나’). 리뷰는 이제 저장본과 새 측정을 `counts`·`coverage`·`floors`·`claims` 로 대조하고, **하한 미기록 · 근거(`why`) 없는 하한 · 저장본 낙음**을 모두 실패로 본다. 실패 메시지도 감사가 기록한 근거를 그대로 인용한다(값만 옮겨 적지 않는다). 자기시험·하한은 감사자만의 것이 아니므로 공통 계약을 그대로 쓰도록 옮겼다(감사 안의 중복 `Probe` 제거). 검증: architecture_review **12 checks PASS**(state_claims: 주장 4 · 정정 4 · 하한 2종 여유 5·3 · 자기시험 17건 · marker 24종) · tests/cognitive 486 collected(485 passed · 1 skipped) · ruff clean · mypy clean. **미완:** 하한을 내리는 판단은 여전히 사람 몫(정말 주장이 사라지면 근거를 적고 내린다) · 실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 harness 공통 계약): 24 시험 추가(공통 계약 파일 20 · 리뷰 검사 4, cognitive 454 → 478). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/harness_contract.py · tests/cognitive/test_harness_self_probes.py. 상태 주장 감사에 붙인 자기시험·하한을 **공통 계약**으로 올렸다 — 측정 harness 의 같은 병은 **볼 수 없는데 통과하는 것**이다(pin 을 못 찾으면 “pin 0 · 움직임 0”, junit 을 못 읽으면 “결정적 0 · drift 0”, 인용 패턴이 죽으면 “인용 0건 모두 추적됨”). `scripts/harness_contract.py` 가 `Probe`/`Cases`(자기시험)와 `Floor`(탐지력 하한)를 제공하고, 여섯 harness 가 이를 쓴다(마지막 하나인 `measure_cognitive_surface` 는 **게이트가 아예 없어** 빈 entrypoint 표를 내도 exit 0 이었고, 이제 자기시험 6건·하한(entrypoint 9 · 실재 9)을 갖는다): `digest_drift` **9건**(경로+digest 판독·경로 없는 sha256 배제·경로 해석·상태 4종) · `regression_ledger` **11건**(junit 판독·testsuite 없으면 예외·회차 0개면 예외·결정적 판정) · `audit_state_claims` 17건 · `audit_enum_identity` **5건**(identity 2건·값 비교 제외·리터럴 제외·제외 목록) · `audit_test_namespace_purge` **6건**(미가드 purge · del 형태 · 트리 override 허용 · 함수 본문 제외 · 무관 mapping). 하한은 “찾은 것 없음” 과 “볼 수 없음” 을 가르는 값이라 낮게 잡았고(하한 1 · enum 스캔 10), 하한을 내리는 것은 근거와 함께 사람이 하는 결정이라는 문장을 상수 옆에 두었다. 리뷰는 자기시험 **부재**·실패·하한 미달을 모두 실패로 보며(digest_report · regression_ledger · citation_tracking), 인용 추적 하한은 저장소 기본 범위에만 걸리게 해 부분 범위(시험 합성 문서)는 호출자가 하한을 소유한다고 적었다. 각 harness 에 `--self-test`(측정·기록 없이 자기시험만)를 추가했고, artifact 에 `probe`·`coverage` 를 실었다. 이빨 `tests/cognitive/test_harness_self_probes.py` **20건**은 정상 통과와 **판독력 망가짐**(패턴 파괴 · 빈 결과 · 전부 위반으로 보는 경우 · 빈 원장/빈 측정)을 양방향으로 고정한다. 검증: architecture_review **12 checks PASS**(자기시험 9·17건 · marker 24종 일치) · tests/cognitive 476 passed · digest_drift --gate 0 · regression_ledger --gate 0 · enum/namespace 감사 0건 · ruff clean · mypy clean. **미완:** 각 harness 의 실측 재검토(실모델·실 vault)·주장하지 않는 문장의 참·거짓 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 감사자 자기시험): 8 시험 추가(상태 주장 계약 18건, cognitive 442 → 454). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/audit_state_claims.py · tests/cognitive/test_state_claims.py. 문장을 읽는 기계는 **자기 눈이 머는 것**이 가장 위험한 실패다 — 어휘를 지우거나 문서 형식이 바뀌면 주장 0건이 되어 조용히 통과한다. 그래서 감사자에게 두 장치를 달았다. ① **운영 자기시험**(`--self-test` 로도 단독 실행): 매 실행마다 어휘 분류·펜스 처리·정정 창(가까운 표기만 인정)·상태 계산을 합성 입력 **17건**으로 다시 물어보고, 어휘를 통째로 비우거나 단어 하나(`green`)를 지우면 그 실행이 바로 실패한다 — 상수를 쓸어보기만 하면 지워진 단어가 안 보이므로 **요구 어휘를 따로 고정**했다. ② **탐지력 하한**: 주장 수(4)뿐 아니라 **node 를 지목한 산문 줄 수**(mention 6 — 상태 어휘가 없어도 세는 상한 집합)를 함께 세고, 하한(1·1) 아래로 가면 게이트가 실패한다(“눈이 멀었을 수 있다”). 하한 상수는 증거 문서가 정말 주장을 그만두면 근거와 함께 사람이 내린다. 자기시험 실패는 **판정 결과와 무관하게 그 실행을 실패**로 만들고, 리뷰의 `state_claims` 검사도 자기시험 부재·실패·mention 미달을 모두 실패로 잡는다(이빨 시험 8건: 비운 어휘·지운 단어·자기시험 부재/실패·mention 0줄·펜스 제외·JSON 노출·`--self-test` 무실행). 검증: architecture_review **12 checks PASS**(marker 24종 일치 · 자기시험 17건 · mention 6 · 주장 4) · tests/cognitive 454 passed · ruff clean · mypy 2 files clean. **미완:** 주장하지 않는 문장의 참·거짓·실모델·실 vault 재확인 · 중단 회차 원인 · wheel/sdist build(NOT_RUN) · 사람 승인.
- 2026-09-23 보강 보고(P12 T14 상태 주장 감사): 12 시험 추가(리뷰 harness 41 → 51, cognitive 428 → 442). 증거: docs/ssak-ai-core/ARCHITECTURE_REVIEW.md §1.4 · scripts/audit_state_claims.py · tests/cognitive/test_state_claims.py. 앞선 회차가 재확인 중 발견한 낡은 문장 하나(`T01b_protection.md` 의 "기존 red")가 우연이 아니라 **류**임을 기계로 재판정했다 — 증거 문서에는 시점 기록(낡아도 역사)과 **지금 트리에 대한 주장**(낡으면 틀린 문장)이 섞여 있다. 새 감사는 뒤엣것만 본다: 산문에서 **test node 를 지목한 문장**(`파일::시험`)에 같은 줄 상태 어휘(red·실패·failed ↔ green·통과·passed)가 있을 때만 주장으로 세고, 펜스 안은 그때 돌린 명령·출력의 **기록**이라 보지 않는다. 실제로 돌려 보니 **주장 4건이 전부 낡았다**(T01b · T03/T04 · T06 · T07 이 같은 sandbox coverage 시험을 "기존 red"·"실패는 그대로" 로 적었지만 §1.5 의 등록 뒤 green). 문장을 지우지 않고 `> **2026-09-23 정정.**` 인용문을 붙였고, 감사는 정정 표기가 **그 줄 가까이(date 필수)** 있을 때만 `FIXED` 로 보고 통과시킨다 — 정정 없이 실제와 어긋나는 주장이 하나라도 있으면 리뷰가 실패한다. 감사 범위는 의도적으로 좁게 잡았다: 처음에는 리뷰 문서까지 봤는데 낡은 문장을 **인용해 해설**하는 줄이 주장으로 잡혀 5건으로 세었다 — 관찰을 주장하는 자리는 증거 문서이므로 범위를 좁히고 그 이유도 docstring 에 남겼다(자기 해설로 오탐이 나는 것을 문서화). 검증: architecture_review **12 checks PASS**(인용 232건 전부 실재·추적 · digest 미확인 움직임 0 · 상태 주장 낡음 0 · marker 22종 일치) · tests/cognitive 442 passed · digest_drift --gate 0 · ruff clean · mypy clean(530 sources). **미완:** 주장하지 않는 문장의 참·거짓(조건문·유보 표현) · 실모델·실 vault 재확인 · 중단 회차 원인 · 다른 레인 QA 산출물 커밋 여부 · wheel/sdist build(NOT_RUN) · 사람 승인.
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
