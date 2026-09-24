---
title: "T01a — typed cognitive model·계보 계약 증거"
date: 2026-09-22
status: verified-module
owner: 주 에이전트(P01)
---

# T01a 모델/계보 (P01)

```yaml
check_id: T01a
status: PASS (module-level)
owner: principal
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
command: .venv/bin/python -m pytest tests/cognitive -q  /  ruff check·format  /  mypy
exit_code: 0
observed_behavior: 30종 entity roundtrip 무손실, enum·naive time·cross-project ref·type 오류 거부, 83 passed
artifact:
  - src/antigravity_k/engine/cognitive/models.py (sha256 65abe58b…)
  - src/antigravity_k/engine/cognitive/references.py (sha256 f678df28…)
  - docs/ssak-ai-core/contracts/record-entities.schema.json (sha256 051d63e1…)
  - tests/cognitive/test_models.py (sha256 abe6237b…)
limitations: runtime(AgentRuntime/tool gate)에는 아직 연결하지 않았다. 이 시험은 계약 모듈 단독 검증이다.
verified_at: 2026-09-22T03:16:57Z
```

## 구현 내용

- **30종 discriminated union**: 원문 22 entity + 보완 8 entity를 `payload.entity_type` discriminator로 묶었다. `Record.entity_type`과 payload literal이 다르면 거부한다.
- **stable ID**: `<namespace>:<uuid4>` 강제. namespace는 entity type에 고정 매핑되며(`project`↔Project), namespace 불일치·비정규 ID는 거부한다. Project record는 `project_id == id`.
- **시간**: `UtcDatetime`(AwareDatetime + UTC 정규화). naive 시간은 거부, aware KST 입력은 UTC로 변환한다.
- **typed reference**: `relation/target_id/expected_type/target_revision?`. 저장 시 `validate_references`가 SELF_REFERENCE·UNRESOLVED·TYPE_MISMATCH·CROSS_PROJECT·REVISION_MISMATCH를 각각 구분해 거부한다. `shared_scope` relation만 다른 project 참조를 허용한다. `supersedes` 순환은 `assert_no_supersedes_cycle`이 거부한다.
- **관측/해석 분리**: `ObservationPayload`에는 meaning/interpretation 필드가 존재하지 않고 extra 필드도 거부한다. 해석은 `InterpretationPayload(experience_id, revision, supersedes, evidence_ids …)`로만 기록한다.
- **판단 근거**: `BrainJudgmentPayload.grounds`는 Evidence ID여야 하며, envelope references에 `ground → Evidence`가 없으면 거부한다(자유문 justification 거부).
- **단일 점수 금지**: `ConfidenceProfile` 5차원, `ApplicabilityProfile` 7차원, `RiskProfile` 10차원, `DecisionAssurance`는 9개 readiness check 결과 집합이며 scalar 합성이 없다. NOT_READY인데 FAIL/UNKNOWN이 없으면 거부한다.
- **Policy allowlist**: `PolicyTarget`은 §36 개선 영역 14종 운영 knob만 허용한다(헌법·authority 대상 없음). parameter key는 소문자 snake_case 형식만 통과한다.
- **schema 격리**: `from_wire`는 알 수 없는 major를 `UNSUPPORTED_SCHEMA`로 격리한다. `scripts/generate_record_schema.py`가 envelope 계약을 payload 수준 schema로 확장한 `record-entities.schema.json`을 생성/검증(`--check`)한다.
- **비의존**: `models.py`/`references.py`는 stdlib+pydantic만 import한다. cognitive namespace는 api·ui·tools·knowledge·agents·cli 계층을 import하지 않는 것을 시험으로 강제한다.

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q            → 83 passed
.venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive scripts/generate_record_schema.py → All checks passed
.venv/bin/python -m ruff format --check …                 → 11 files already formatted
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive scripts/generate_record_schema.py → Success: no issues found in 6 source files
.venv/bin/python scripts/generate_record_schema.py --check → schema up to date (2972 lines)
```

## 남은 것

- `docs/ssak-ai-core/contracts/record-envelope.schema.json`(envelope 전용)과 새 payload schema의 역할 구분을 P12 문서 갱신에서 명시한다.
- alias ID(legacy) 매핑은 P02 adapter가 담당하며 P01은 canonical ID만 발급한다.

## 2026-09-24 v1.1 정합화 회차 — 선별 기록 canonical 표현·당시 Context 계보

v1.1 추가 인수("선별 기록 roundtrip·provenance·타입 경계")를 닫은 회차다. P08이 만든 선별 기록
(`ExperienceSelection`)은 계약 필드를 전부 갖고 있었지만 **canonical 변환에서 사라졌다** —
`to_record`가 `EventPayload`에 disposition·reasons·evidence·policy_version을 싣지 않아 wire
roundtrip이 선별 판단의 본체를 복원할 수 없었고, "기존 Event로 충분한가?"라는 v1.1 물음의 답은
**불충분**이었다. 또한 `ExperienceCore.context_ref`(당시 Context 계보)가 타입 reference가 아니라
`historical_refs` 문자열로만 남았다.

```yaml
check_id: T01a-v1.1
status: PASS (module-level)
owner: principal
source_head: b019dc80 (dirty — 본 회차: models.py · experience.py · references.py · test_models.py · record-entities.schema.json)
command: .venv/bin/python -m pytest tests/cognitive/test_models.py -q  /  scripts/generate_record_schema.py --check  /  ruff  /  mypy
exit_code: 0
observed_behavior: test_models 61 passed(신규 3) — 아래 매핑
artifact:
  - src/antigravity_k/engine/cognitive/models.py — SelectionDisposition·SelectionReason enum + SelectionInfo + EventPayload.selection
  - src/antigravity_k/engine/cognitive/references.py — REL_CONTEXT("context")
  - src/antigravity_k/engine/cognitive/experience.py — 선별→Event 계약 필드 실림·core의 타입 context 계보(정합화)
  - tests/cognitive/test_models.py (61 시험)
  - docs/ssak-ai-core/contracts/record-entities.schema.json (재생성, +89행)
limitations: 선별 해석 주체 제한(Interpretation author ∈ {BRAIN, HUMAN})은 P08 게이트가 소유(test_episode). 별도 entity는 만들지 않았다 — 공통 의미 계약이 허용한 최소 확장이다.
verified_at: 2026-09-24T14:01:19Z
```

### 시나리오 매핑

- **선별 기록 roundtrip** — `test_selection_event_roundtrips_contract_fields`: `ExperienceSelection.to_record`
  → `to_wire` → `from_wire` 왕복에서 disposition·reasons·evidence_refs·policy_version·note가 그대로이고
  producer(선별 실행 주체)는 envelope이 보존한다. **기존 Event는 `selection=None`**이라 영향 0(전 entity
  roundtrip 시험 그대로 통과).
- **타입 경계** — `test_selection_payload_rejects_unknown_disposition_and_empty_reasons`: 모르는
  disposition/reason·빈 사유의 선별은 canonical로 들어오지 못한다(pydantic 거부).
- **당시 Context 계보** — `test_experience_core_carries_typed_context_lineage`: `context_ref`가
  `Reference(relation="context", expected_type=ContextPackage)`로 타입을 가진다(historical_refs에는
  그대로 남는다 — 문자열 메모가 아니라 계보). `context_ref=None`이면 reference도 없다.

### 설계 결정

- **enum 소유를 experience.py(models를 import하는 쪽)에서 models.py로 옮겼다** — payload 필드가
  enum을 요구하는데 experience에 두면 순환 import다. experience.py는 같은 이름을 re-export하므로
  기존 import 지점(test_episode 등)은 그대로 동작한다.
- **별도 entity를 만들지 않았다**: 공통 의미 계약이 "기존 Event로 충분하면 별도 entity를 추가하지
  않는다"고 했고, Event에 선택 필드 `selection`을 얹는 것으로 계약 최소 필드가 왕복한다 — 불충분했던
  것은 Event의 표현력이 아니라 변환이 필드를 버리던 것이었다.
- schema는 재생성했다(`generate_record_schema.py`), `--check` 초록.
