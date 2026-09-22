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
