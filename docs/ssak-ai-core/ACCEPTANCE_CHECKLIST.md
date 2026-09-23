---
title: "SSAK-AI 실행·인수 체크리스트"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# SSAK-AI 실행·인수 체크리스트

## 1. 판정 기준

Constitution과 Architecture Invariants가 최상위 기준이다. [Roadmap](IMPLEMENTATION_ROADMAP.md)의 공통 의미 계약과 P00~P12를 함께 적용한다. 파일 존재·schema 통과·모듈 시험 성공만으로 실제 사용자 경로의 인수를 선언하지 않는다.

v1.1의 전체 인수 체크는 모두 미체크로 시작한다. 이는 기존 성공 기록을 취소하거나 구현이 없다는 뜻이 아니다. 기존 보고와 신규 조건을 구분하고 현재 source/digest에 적용 가능한 증거를 재연결하기 위한 상태다. 재사용할 수 있는 증거는 다시 실행할 필요 없이 정확한 시험 범위와 source 동일성을 확인해 연결한다. 변경·누락·불확실한 범위만 추가 검증한다.

체크 완료 조건: 해당 항목의 필수 하위 시나리오 충족, 실제 관찰 결과와 기대 결과 일치, 근거의 source SHA+dirty digests 확인, 이월 통합 조건 해소. SKIP/NOT_RUN/NOT_AVAILABLE은 PASS가 아니다. N_A는 사유와 상위 요구 충족 방법이 있어야 한다.

## 2. 기존 증거 기록

아래 결과는 기존 증거 문서에서 보고한 내용이며 이번 문서 편집에서 재실행한 결과가 아니다.

| 항목 | 기존 보고 범위 | 제한 / 추가 조건 |
|---|---|---|
| T00 | [기준선](evidence/T00_baseline.md): 일부 경계·회귀 PASS | 전체 entrypoint 실호출, 별도 data root, T00b는 별도 확인 |
| T01a | [모델](evidence/T01a_typed_model.md): 30종 entity, module PASS | 현재 schema·선별 기록 계약 대조 |
| T01b | [보호](evidence/T01b_protection.md): module/tool gate/store PASS | migration/evolution hook·승인 발급 미완료로 보고됨 |
| T02 | [저장](evidence/T02_canonical_store.md): module PASS | 실제 Vault writer 동시성·사용자 표면 통합 필요 |
| T03/T04 | [Context·Brain](evidence/T03_T04_context_brain.md): module PASS | 실제 provider/router·Context window, 신규 철학 시험 확인 |
| T05 | [Governance](evidence/T05_governance.md): module + tool_executor surface PASS (31 시험) | CLI/API/stream/background 연결, 사람 승인 발급 주체 검증은 P11 이월 |
| T06 | [COMMIT](evidence/T06_commit.md): module + canonical store PASS (28 시험) | loop(P08)·사용자 표면(P11) 실행 경로 연결 이월 |
| T07 | [Action](evidence/T07_actions.md): module + ToolExecutor·CanonicalStore 표면 PASS (17 시험) | task_state_store 재시작 복구, OBSERVE 경험 형성은 P08/P11 이월 |
| T08/T09 | [Loop·Experience](evidence/T08_T09_episode.md): module + ToolExecutor·CanonicalStore 표면 PASS (21 시험) | production 대화 경로 opt-in(P11), Knowledge/Policy 승격(P09) 이월 |
| T10 | [Learning lifecycle](evidence/T10_learning.md): module + CanonicalStore 표면 PASS (29 시험) | 실제 미래 행동 변화 성능 비교(P10), 사용자 표면·runtime 연결(P11) 이월 |
| T13 | [성장·ablation](evidence/T13_growth.md): deterministic fixture PASS (17 시험 + CLI artifact) | live pilot NOT_RUN(exit 2), 작은 표본·실측 latency 없음, 사용자 표면 연결(P11) 이월 |
| T13 (live) | [live pilot harness](evidence/T13_live_pilot.md): harness·분리 계약 PASS (12 시험) | 실제 provider 실행 NOT_RUN, 확증 표본 미등록 — 사람 결정 필요 |
| T11 | [사용자 표면 opt-in](evidence/T11_surface.md): 실측 + adapter + read-only CLI/API(SSE 포함) + feature-off 회귀 PASS (36 시험) | 대화 스트림/background 배선·실모델 QA·ACTIVE 실검증 이월 (체크박스 미완) |
| T12 | [migration dry-run](evidence/T12_migration.md): source read-only·별도 root·mapping·index·rollback rehearsal PASS (14 시험) | destructive 변환 NOT_RUN(사람 결정), 실사용 DB 대상 dry-run 이월 |

기존 문서가 보고한 `test_all_process_execution_paths_are_accounted_for` 실패는 별도 기존 이슈 기록으로 유지한다. 현재도 같은 원인인지 재확인 없이 단정하거나 이번 신규 실패를 그 항목에 섞지 않는다.

## 3. 전체 인수 목록

- [ ] **T00a 현재 기준선** — P00. 최신 source/digests·entrypoint→runtime→gate 근거, 실제 회귀 명령과 기존 실패 분리. 전체 사용자 표면은 P11에서 완료.
- [ ] **T00b 초기 benchmark** — P00/P01. 사전 metric/split/manifest 및 실행 가능한 skeleton. T00b-A/B 충족.
- [ ] **T01a 모델·계보** — P01. roundtrip, enum/time/ref/type/project 오류 거부, 관찰·해석 분리, 선별 기록·당시 Context 계보.
- [ ] **T01b 헌법·보호 권한** — P03/P05/P07/P11. 신뢰 가능한 승인 발급·검증, 실제 우회 경로 차단, 취소·scope·digest·만료 검증. hook 미연결 상태는 전체 PASS 불가.
- [ ] **T02 불변 저장·복구** — P02/P11/P12. 동시 write·중복 ID·write/commit/publish crash, 미완료 노출 0, 실제 Vault writer 통합, 원본 보존.
- [ ] **T03 Context** — P04/P08/P11. L0·필수 항목·권한·handle·최소충분·선택적 확장·현재 applicability. T03-A~D 충족.
- [ ] **T04 Brain 교체·의미 권한** — P04/P08/P11. A/B provider와 state 연속성, repair 제한, Secondary 무권한, Primary 최종 통합. T04-A~C 충족.
- [x] **T05 Governance** — P05. 5 dispositions, feedback, reshape, 다차원 grant·delegation·취소·승인 재사용. T05-A~D 충족. 증거: [T05_governance.md](evidence/T05_governance.md) — module + tool_executor surface PASS(31 시험). CLI/API 사용자 표면과 승인 발급 검증은 P11 이월 조건으로 남긴다.
- [x] **T06 COMMIT·Decision** — P06. 9 readiness checks, 3 outcomes, semantic judge 0, freshness·append reopen. T06-A~D 충족. 증거: [T06_commit.md](evidence/T06_commit.md) — module + canonical store 표면 PASS(28 시험). loop(P08)·사용자 표면(P11) 연결은 이월 조건.
- [x] **T07 Action** — P07. 요청 EXECUTE와 최종 ACTION 양쪽의 권한·receipt·idempotency, crash after effect, UNKNOWN, 취소·회수. 증거: [T07_actions.md](evidence/T07_actions.md) — module + 실제 ToolExecutor·CanonicalStore 표면 PASS(17 시험). task_state_store 재시작 복구와 loop 연결은 P08/P11 이월.
- [x] **T08 운영 루프** — P08. simple/expanded cycle, targeted rethink, material delta stop, stop≠READY. T08-A~D 충족. 증거: [T08_T09_episode.md](evidence/T08_T09_episode.md) — module + 실제 ToolExecutor·CanonicalStore 표면 PASS(21 시험). 사용자 경로 연결은 P11 이월(ADR-0004).
- [x] **T09 Experience** — P08. 선별·세 평가·원본 보존·지연 관찰·해석 versioning. T09-A~E 충족. 증거: [T08_T09_episode.md](evidence/T08_T09_episode.md) — 선별·세 평가·해석 versioning PASS. Knowledge/Policy 승격은 P09 범위로 분리 기록.
- [x] **T10 학습** — P09. 후보→검증→승격→trace, 의미 해석 책임, 현재 applicability, rollback/retire/CAS. T10-A~E 충족. 증거: [T10_learning.md](evidence/T10_learning.md) — module + 실제 CanonicalStore 표면 PASS(29 시험). 실제 미래 행동 변화의 성능 비교는 P10, 사용자 표면 연결은 P11 이월.
- [ ] **T11 사용자 표면** — P11. 실제 CLI/API/stream/background의 정상·오류·resume·cancel, 임시 파일 action, Brain/process 교체 복원, feature off 회귀와 이월 인수.
  - 진행 보고: [T11_surface.md](evidence/T11_surface.md) — 진입 실측(legacy 7/9 · core 2/9; core 도달은 추가한 조회 표면뿐이고 실행 경로는 0), opt-in adapter(OFF fail-closed / SHADOW action 0 / ACTIVE 사람 승인 필수), read-only CLI(`cognitive status`, `cognitive surface`)와 read-only API(`GET /api/cognitive/surface/status|reach`, 실측 캐시·`?refresh=true`)와 read-only SSE(`GET /api/cognitive/surface/stream`, `limit`회 snapshot 후 `done` 종료·범위 밖 422) PASS(36 시험, 기존 SSE 계약 회귀 0). feature-off 회귀 실측: 실제 legacy `CognitiveLoop` transcript가 `absent`/`disabled_explicit`/`shadow_enabled` 세 설정에서 동일 digest이고, shadow는 workspace 파일을 만들지 않았다(dispatch 0). **미완:** 대화 스트림·background 실행 경로에 core 상태를 얹는 배선, 실모델 대화 1건의 응답·도구 호출 비교, resume/cancel QA, ACTIVE 실검증.
- [x] **T12 migration/index** — P12. 별도 root dry-run, source 불변·ID mapping, index rebuild, feature rollback, 과거 기록 보존.
  증거: [T12_migration.md](evidence/T12_migration.md) — dry-run PASS(14 시험): source는 `mode=ro`로만 열리고 실행 전후 digest·counts가 동일하며, 같은 store 재실행은 record를 늘리지 않는다(idempotent replay). index rebuild·digest 검증 5/5, rollback rehearsal은 dry-run 출력을 보존한다. 옮길 수 없는 legacy 값은 errors로 남고 exit 1이다. **미완/이월:** destructive in-place 변환은 NOT_RUN(사람 결정), 실사용 vault DB·vector index 대상 dry-run은 별도 실행.
- [x] **T13 성장·ablation** — P10. frozen splits, Fresh/Mature paired comparison, 실제 행동 변화, negative transfer, 6 ablations 및 실험 한계. 증거: [T13_growth.md](evidence/T13_growth.md) — deterministic fixture PASS(17 시험 + CLI artifact): FINAL 18 task에서 retry 39 → 15, success 1.0 유지, negative-transfer 감소 0, 6 ablation 전부 MEASURED(미사용 mechanism은 NOT_RUN). live pilot harness와 분리 계약은 [T13_live_pilot.md](evidence/T13_live_pilot.md) — port 미주입·fixture spec·최소 trial 미달은 거부되고 fixture/live artifact는 병합 불가. 실제 provider 실행은 NOT_RUN이며 확증 표본 등록은 사람 결정으로 이월.
- [ ] **T14 회귀·최종 Architecture Review** — P12. 기존 test/lint/type/build, 실제 표면 QA, 헌법 24원칙·원문 §63별 근거, 관련 문서 정합성.
  - 진행 보고: [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) — 헌법 24원칙(covered 15 · partial 9 · gap 0), 원문 §63 질문 12개, §52 drift 질문 10개(triggered 0)를 카드·시험·증거·module에 매핑하고 질문별 근거·한계를 기록했다. 이 매핑은 `scripts/architecture_review.py`가 8개 검사로 기계 검증한다: artifact 존재(161 참조), 문서 상대 link 161건 해석, 체크리스트 17항목 전부 최소 한 원칙에 매핑, `evidence/` 15문서 고아 없음, 리뷰 문서가 24원칙·§63·§52를 모두 포함, `measured` 마커가 실제 측정값과 일치, source 정렬(헌법 24·§63 12·§52 10), tests/cognitive 수집 358건.
  - 회귀 관찰: pytest 전체(fast)를 **네 번** 쟀고 순서가 달랐다 — ① 7723 수집(수정 전 · random) **94 failed / 7571 passed / 14 skipped / 20 xfailed**(26:31, 변경 전 95 failed와 목록 동일) ② 7726 수집(random) **10 failed / 7660 passed** ③ **고정 순서**(`-p no:randomly`, 7726 수집/7702 selected) **7 failed / 7663 passed / 14 skipped / 24 deselected / 20 xfailed**(21:21) ④ **고정 순서 · 정리 뒤** **5 failed / 7666 passed**(20:13). 차이는 수정 효과가 아니라 **순서 artifact**이며, 네 회귀의 실패는 전부 cognitive core 밖의 기존 항목이다. ③의 7건은 git 이력 기반 cr14 fence/지문 2건, dashboard skip 마커 1건, 번들 config 기본값 1건, nx07 기존 문서 기준선 2건, 샌드박스 ALLOWLIST 1건이고, 해당 5개 파일을 단독 실행해도 같은 7건이 재현된다(86 passed / 7 failed). 그중 **둘을 등록으로 닫았다**(§1.3): `tools/ssak_bundle_store.py` 를 `FIXED_ARGV` 로 등록(신뢰 루트·sha256·arch 통과 뒤 고정 argv selftest)하고, `dashboard/e2e/ssak-web-integration.spec.ts` 의 조건부 skip 을 조건 토큰·owner·재검토 기한과 함께 등록해 tripwire 를 양방향(미등록 마커·낡은 등록 모두 실패)으로 만들었다 — 재실행 89 passed / 5 failed. ②의 cognitive 실패 3건은 이 작업이 만든 문서 `measured` 마커 미갱신이었고 갱신 뒤 0이다 — `tests/cognitive -q` **358 passed**(③·④에서도 cognitive 실패 0). ruff check/format clean · mypy clean · record schema up to date · `scripts/architecture_review.py` 10 checks PASS(이후 검사가 둘 늘었다 — 회귀 원장 계약·인용 추적).
  - **문서가 인용한 파일이 실재하고 git 에 추적되는지 검사한다** — `evidence/T11_surface.md` 가 `tests/test_cognitive_surface_api.py` 를 sha256·11 시험과 함께 근거로 인용하면서 그 파일이 추적되지 않는 상태를 발견했다(내용은 digest 와 일치했고 11 시험 통과). 실재만 보는 검사로는 이 상태가 통과하므로, 문장으로 인용한 저장소 경로를 축약 표기까지 해석해 실재 + 추적을 요구하는 검사를 붙였고, 등록이 필요한 미추적·미실재 인용 여섯 건은 이유·소유자·재검토 기한과 함께 코드에 남겼다(등록된 경로가 추적되거나 기한이 지나면 실패한다). 이빨은 시험 여섯 건으로 고정했고 현재 인용 214건이 모두 실재·추적된다 — `ARCHITECTURE_REVIEW.md` §1.3.
  - 회귀가 찾아낸 결함을 고쳤다: (1) `AuthorityProfile.evaluate`가 dimension을 **class identity**로 비교해, 같은 이름·값의 enum이 두 번 로드되면 유효한 grant가 NOT_GRANTED→DEFER로 떨어졌다(권한 판정이 조용히 약해지는 부류). (2) 해당 시험이 경로 문자열 patch에 의존해 중복 module 상황에서 옛 객체를 patch했다 — adapter `admit.__globals__`를 직접 patch하도록 고쳤다. (3) 같은 부류를 전수 점검해 `models.same_enum`(정의 module·class 이름·값 비교)을 도입하고 cognitive core의 raw enum identity 비교 **95곳**을 이 helper로 통일했으며, 재발을 막는 감사(`scripts/audit_enum_identity.py`, 위반 0건)와 계약 시험(`tests/cognitive/test_enum_identity.py`, 8건)을 추가했다. pydantic 검증이 중복 class를 canonical enum으로 정규화하는 것도 시험으로 고정했다. (4) **오염원 자체를 제거했다** — `tests/test_flush_budget_contract.py`가 import 시점에 `sys.modules`의 `antigravity_k.*`를 조건 없이 지우고 있었고(승격되어 일반 suite가 함께 수집), 그 결과 먼저 import된 시험은 옛 class 객체를, 뒤에 import되는 module은 같은 이름의 새 객체를 잡아 **판정이 실행 순서에 따라** 달라졌다. 미러 리허설(`NX10_FLUSH_TREE` 지정)에서만 비우도록 조건화하고, 승격본·staged 쌍둥이·fsync2(F2)를 같은 형태로 맞췄다. 재발 방지는 감사(`scripts/audit_test_namespace_purge.py`, 위반 0건)와 계약 시험(`tests/cognitive/test_module_namespace_isolation.py`, 5건)이며, 미러 리허설은 그대로 돈다(**PASS 17 · FAIL 0**). 재현·수정·관찰은 [T14_namespace_isolation.md](evidence/T14_namespace_isolation.md).
  - **회귀 수치를 원장에서만 인용하도록 바꿨다** — 회차마다 `N failed` 가 달랐던 이유(트리 변화· 수집 오염·다른 선택)를 서술로 추정하지 않고, 같은 scope 를 **variant** 를 바꿔(seed 101·202, 일부는 수집 순서를 뒤집은 `rev-seed-101` 도) 돌려 교집합(결정적)/대칭차(variant 민감)를 계산하는 harness(`scripts/regression_ledger.py`)를 만들었다. 502 파일을 8구간 + subdir 로 나눠 **21회** 측정했고(순서 뒤집기 3회 포함), **결정적 11건 · variant 민감 0건**이다 — 즉 이 체크아웃에서 seed 를 바꿔도, 순서를 뒤집어도 빨간 집합이 움직이지 않는다. 이전 회차의 “순서 artifact” 서술은 그 측정으로 대체했다(중단된 회차는 판정에서 제외한다). 방법·관찰·이빨·한계는 [T14_regression_ledger.md](evidence/T14_regression_ledger.md).
  - **미완:** 실모델 대화 QA·resume/cancel·ACTIVE 실검증은 P11 이월이고, wheel/sdist build는 릴리스 CI 소관으로 이 체크아웃에서 실행하지 않았다(NOT_RUN). 전체 회귀의 실패는 기존 이슈로 분리했으며 PASS로 바꾸지 않았다. 원장이 분리한 결정적 11건은 모두 소유자(레인)가 지정돼 있고 **무소유 0건**이다 — cr14 울타리 2 · nx07 문서 기준선 2 · model_registry 1 · ws01 대화 저장소 상태 5 · trn02 학습 API 1. 그중 ws01·trn02 6건은 이전 기준선에 없던 항목이며 단독 실행으로도 재현된다(다른 레인·이 체크아웃 상태 소관). 이 리뷰 자체의 사람 승인(Architecture Review)이 남아 체크박스는 미완이다.

## 4. 철학을 관찰 가능한 행동으로 확인하는 시나리오

### T00b — 개발 초기에 측정 기반 확보

- **A / P00:** Task Success, Context Size/Pollution, Brain/Tool Calls, Retry, Token, Latency, Verification, Reopen, Recovery, Risk Shaping, Experience Reuse, Negative Transfer의 정의·분모·측정 구간과 train/validation/final split 규칙을 등록한다. source/brain/prompt/policy/hardware/task/cache/seed manifest 필드를 정한다.
- **B / P01:** 최소 fixture로 skeleton 정상 실행·잘못된 입력·help를 확인하고 실제 관측값과 manifest를 출력한다. 미구현 성장·ablation은 NOT_AVAILABLE/NOT_RUN이다. 데이터 오염 없는 Fresh baseline을 보존한다.

### T03 — Minimum Sufficient Context

- **A 최소 주입:** 같은 현재 과제에 무관한 과거 기록을 대량 추가한다. 여유 token budget이 있어도 무관한 원문이 기본 Context에 유입되지 않는다. 필수 Goal/state/constraints/evidence/material unknown은 유지되고 선택·제외 이유가 남는다.
- **B 선택적 확장:** 특정 근거가 부족한 경우 해당 handle만 확장한다. 전체 이력 재주입·관련 없는 L3 확장은 없다. 권한·digest·만료를 다시 확인한다.
- **C 현재 우선:** 높은 과거 confidence와 현재 환경의 mismatch를 함께 제공한다. 과거 결론은 advisory이며 현재 결론으로 강제되지 않는다. confidence/applicability/assurance가 혼합되지 않는다.
- **D 제약 보존:** 필수 L0 또는 Context가 예산을 넘으면 명시적으로 축소 요청/지원 모델 선택/불완전 상태를 처리한다. 조용한 삭제는 없다. 실제 provider context window에서도 확인한다.

최소충분은 무조건 가장 짧은 Context를 뜻하지 않는다. 현재 판단에 필요한 충분성을 보존하면서 불필요한 주입을 줄였는지 평가한다.

### T04 — Brain은 교체 가능하고 Primary가 의미를 통합

- **A 연속성:** 같은 Body record로 A→B Brain 및 process restart를 수행한다. State/Memory/Experience/Decision/Knowledge/Governance/Authority/Human Partnership의 ID·이력·범위가 유지된다. 이전 Brain 결론을 강제하지 않는다.
- **B protocol:** malformed repair 횟수·시간·비용 제한, fallback의 동일 frozen Context·새 judgment ID, plain text의 FACT/READY 자동 승격 금지를 확인한다.
- **C 의미 권한:** Secondary 여러 개가 반대하거나 같은 의견을 낸다. Body는 MODEL_JUDGMENT로 전달하고 Primary의 통합 응답을 받는다. Body 다수결·semantic merge·응답 치환으로 최종 결론을 생성하지 않는다. Secondary 사용은 trigger와 Governance 승인으로 설명된다.

### T05 — Governance는 사고의 정답을 심사하지 않음

- **A feedback:** APPROVE/APPROVE_WITH_LIMITS/RESHAPE/DEFER/DENY 각각에서 원래 요청·변경·이유·남은 제약·대안을 기록하고 Primary에 전달한다. 변경된 args는 재권한 검사한다.
- **B Risk Shaping:** 기존 grant 안에서 위험한 광범위 쓰기를 isolated scope+checkpoint+verification으로 줄인 실행을 관찰한다. 고위험이라는 이유만으로 자동 인간 이관하지 않는다. human-only action은 reshape로 우회하지 않는다.
- **C Unknown:** ACCEPTABLE/MATERIAL Unknown은 일괄 차단하지 않는다. BLOCKING Unknown은 관련 action만 차단한다. 새 제한 action에서 residual risk가 관리 가능해졌는지 Primary의 판단과 readiness 근거를 연결한다.
- **D 권한:** dimension별 grant·scope·만료·취소·parent subset delegation을 확인한다. 같은 유효 승인 범위는 불필요하게 재질문하지 않는다. 단일 autonomy score나 Brain 결론의 의미적 선호로 승인하지 않는다.

### T06 — COMMIT은 readiness만 검사

9 checks: Ground exists; Evidence provenance linked; Material Unknown explicit; Hard constraints satisfied; Residual risk manageable; Authority sufficient; Verification sufficient; Rollback sufficient where necessary; Action scope clear.

- **A 의미 재심사 금지:** provider spy로 LLM 호출 0을 확인한다. readiness 입력을 고정하고 의미적 결론 문구만 바꾼 fixture에서 규칙/점수/모델로 결론 선호를 판정하지 않음을 trace·경계 검사로 확인한다. action/근거/제약이 달라진 경우 다른 readiness 결과는 허용된다.
- **B 결과·Unknown:** READY/READY_WITH_GUARDS/NOT_READY를 재현한다. 각 check는 PASS/FAIL/UNKNOWN/N_A와 reference를 가진다. N_A에는 이유가 필요하다. ACCEPTABLE Unknown 하나만으로 NOT_READY가 되지 않는다.
- **C 실행 요건:** guard는 실제 executor에서 강제된다. action digest·authority/state/policy/decision revision 변경 시 재확인하며 문자열 rollback 약속만으로 통과하지 않는다. 의미적 해석이 더 필요하면 Primary로 돌려보내고 gate 내부에서 해석하지 않는다.
- **D Closure/Reopen:** material trigger로 정당화된 최소 범위를 reopen하고 새 event/판단을 append한다. 원래 DecisionTrace는 불변이다. 단순 불안·표현 변경만으로 반복 reopen하지 않는다. Human reopen을 허용하고 이미 발생한 action은 별도로 다룬다.

### T08 — Simple to Start / Sparse Activation

- **A simple:** 추가 인지가 필요 없는 과제를 PREPARE→THINK→COMMIT→ACTION으로 실행한다. 불필요한 Secondary·전체 재사고·추가 verifier가 없다. 필수 권한·readiness·가벼운/비동기 관찰은 유지한다.
- **B targeted:** 하나의 ground에 새 evidence를 제공한다. 해당 범위와 delta만 rethink하고 기존 judgment를 append 계보로 보존한다.
- **C stop:** 새로운 ID만 생기고 material cognitive delta는 없는 반복 요청을 입력한다. Primary의 delta 설명과 Body의 signature/revision/budget 검사로 유한 종료한다. 새로운 ID를 새로운 의미로 간주하지 않는다.
- **D stop≠READY:** 확장 예산이 소진됐으나 readiness가 부족한 상황에서 BLOCKED/DEFER 또는 재평가된 안전한 축소 action으로 끝난다. 자동 READY나 무한 재평가는 없다.

### T09 — Operational Record와 Experience 구분

- **A 선별:** 재사용 가치 없는 정상 읽기는 OPERATIONAL_ONLY, 재사용 가치 있는 실패·회복은 EXPERIENCE, 판단이 어려우면 DEFERRED로 기록한다. reason/evidence/producer/정책 버전이 남고 어느 경우도 원본을 지우지 않는다.
- **B 예상 일치:** 중요한 새로운 환경에서 기존 가정을 독립 재검증한 성공 사례는 expected=observed여도 Experience가 될 수 있다. 단순 수치 차이 유무만으로 선별하지 않는다.
- **C 세 평가:** 당시 근거로 합리적 판단이었으나 나중에 예상 불가능한 실패가 발생한 fixture에서 OutcomeEvaluation과 DecisionEvaluation을 동일 실패로 자동 치환하지 않는다. ExecutionEvaluation도 별도다.
- **D 지연·불명:** PENDING/UNKNOWN을 성공으로 학습하지 않는다. 후속 관찰은 supplement/reference로 append한다. 원인 UNKNOWN이어도 남은 unknown을 명시하고 기록을 닫을 수 있다.
- **E 해석·역사:** Body의 기계 비교와 Primary/human의 의미 해석 주체를 구분한다. 재해석·교정은 새 version/record이고 기존 core digest는 동일하다. 유사 경험의 제시는 묶을 수 있지만 별개의 과거 사건을 삭제·덮어쓰지 않는다.

### T10 — Experience Must Change Future Behavior

- **A 승격 경계:** 한 실패·한 Brain 해석·grade/cooldown trigger만으로 active policy가 바뀌지 않는다. source independence와 별도 validation을 확인한다. human-assisted 후보도 같은 검증을 거친다.
- **B 해석 주체:** Evaluator/PatternBuilder의 기계 집계와 의미 해석을 분리한다. 의미 해석은 Primary 또는 명시된 human-assisted 경로를 사용한다. 근거 없는 causal claim을 FACT나 검증된 Principle로 승격하지 않는다.
- **C 적용과 수정:** 높은 Knowledge confidence라도 현재 applicability가 MISMATCH이면 자동 적용하지 않는다. 환경 변화와 반증을 받아 challenged/scoped/revised/retired로 관리하고 원본을 보존한다.
- **D 실제 변화·복구:** 후보→ValidationReport→PolicyActivation→다음 task의 실제 선택→outcome을 BehaviorChangeTrace로 연결한다. CAS 충돌을 처리하고 rollback 후 선택이 복원된다. 기록 생성만으로 성장 통과가 아니다.
- **E 성장 범위·권한:** 초기 한 target 외에 다른 운영 target을 추가할 수 있는 계약을 확인한다. 기존 grant 안의 선택·위임 조정과 신규 grant/ceiling 발급을 구분한다. learned policy가 인간의 보호 권한을 바꾸지 못한다.

## 5. T13 성장 평가·Ablation

동일 Brain/code/hardware/task distribution, 분리된 저장 root, frozen train/validation/final splits, 동일 cache·seed 정책으로 Fresh/Mature를 비교한다. live model snapshot 고정이 불가능하면 제한을 보고한다.

실제 Context/운영 선택의 변화, outcome quality, 반복 실패, calls/retries/tokens/latency 등을 함께 제시한다. 더 많이 계산했다는 사실만으로 성장이라고 하지 않는다. 기본 fixture 합격 제안은 success 비열등, 사전 지정 retry 또는 tool-call metric 개선, 사전 등록된 negative-transfer fixture에서 success 감소 0이다. 숫자·표본 크기·비열등성 폭은 실행 전 BenchmarkSpec에 고정하고 작은 표본의 결과를 일반 성능 보장으로 확대하지 않는다.

6개 ablation: Without Context Builder / Experience Advisory / Targeted Re-reasoning / Experience / Risk Shaping / Governance Learning. 한 번에 해당 mechanism만 바꾸며 policy·task·code·hardware 조건을 기록한다. Constitution·권한 보호·기본 safety boundary는 끄지 않는다. 비활성화한 mechanism이 실제 사용됐던 비교인지 확인한다. 사용되지 않은 기능의 no-op 비교를 유효성 증거로 삼지 않는다.

정답 문자열·final 평가 결과를 학습 저장소에 주입하는 데모는 무효다. deterministic fixture와 live pilot 결과는 분리 보고한다. 개선이 없으면 그대로 기록하고 해당 복잡성을 Core로 승격하지 않는다.

## 6. 최종 Definition of Done

| 영역 | 필수 인수 |
|---|---|
| Documentation | 헌법 보존, 상위 계약·Protocol·schema·Roadmap·Gap·Checklist 연결, 헌법 24원칙별 근거 |
| Runtime | simple/expanded 경로, feedback, targeted rethink, readiness, action, observation, Experience 선별 |
| Continuity | Brain/process 교체, 같은 canonical 기록·권한·인간 관계, rebuild와 rollback |
| Learning | 검증 후 정책 활성화, 실제 미래 행동 변화, applicability 재평가, retirement/rollback |
| Governance | 실제 보호 경로, 권한 provenance, Risk Shaping, semantic 재심사 없는 COMMIT |
| Validation | 초기 baseline, 회귀, 실제 사용자 표면, 성장 비교, ablation, limitation 명시 |

최종 리뷰는 원문 §63과 SELF_IMPROVEMENT_POLICY의 drift 질문을 항목별로 답한다. 특히 Body의 semantic Brain화, history 의존, 경험의 결론 강제, Human Authority 우회, 무한 루프, COMMIT 의미 재심사, 검증 없는 복잡성, 성장 경로 차단, 역사 삭제가 없는지 증거로 확인한다.

## 7. 증거 기록과 실행 명령

```yaml
check_id: T09-A
specification_version: "1.1"
status: NOT_RUN
scope: integrated
owner: integration
source_head: null
working_tree_manifest: null
scenario: null
expected_behavior: null
observed_behavior: null
command: null
exit_code: null
artifact: null
reused_evidence: null
limitations: null
verified_at: null
```

기존 evidence의 요약 hash만으로 현 source와 동일하다고 단정하지 않는다. 실행 시 전체 digest manifest를 남긴다. PASS는 exit 0만으로 충분하지 않으며 기대와 실제를 비교한다. 이월된 인수에는 owner/check ID/완료 조건을 붙인다.

실행 명령은 P00에서 현재 Makefile/CI/환경을 확인한다. 기존 증거의 typing 도구는 mypy이므로 도구 전환 근거 없이 다른 검사기를 강제하지 않는다. 다음은 해당 파일과 환경이 확인된 뒤 사용할 예시다.

```sh
.venv/bin/python -m pytest tests/cognitive -q
.venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive
.venv/bin/python scripts/generate_record_schema.py --check
.venv/bin/python scripts/benchmark_cognitive_growth.py --help
```

Benchmark CLI는 `--output`, `--seed`, `--mode fresh|mature|ablation`, `--manifest`, `--store-root` 계약을 P01 skeleton부터 마련하고 P10에서 완성한다. 미지원 mode는 명시적으로 미구현 처리한다. production vault/data 대신 격리 fixture root를 사용하며 정상·잘못된 입력·help를 직접 확인한다.
