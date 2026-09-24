---
title: "SSAK-AI Cognitive Core 개발·인수 기준"
date: 2026-09-22
version: "1.1"
status: implementation-spec
tags: [ssak-ai, cognitive-core, architecture]
---

# SSAK-AI Cognitive Core 개발·인수 기준

SSAK-AI는 교체 가능한 Neural Brain을 활용하는 Persistent Adaptive Cognitive System이며, Human Partner에게는 Persistent Adaptive Cognitive Partner다. Brain이 의미를 판단하고, SSAK-AI Body는 상태·Context·근거·권한·실행·경험의 연속성을 소유한다.

이 문서는 Constitution을 변경하지 않고 개발계획과 인수 조건을 구체화한 v1.1이다. 문서 완성과 runtime 완성은 별개다. 원본 저장소의 파일을 덮어쓰지 않은 배포용 완성본이며, 함께 제공된 상위·참고 문서는 작성 시점의 읽기용 사본이다.

## 1. 문서 권위와 읽기 순서

1. [Constitution](SSAK_AI_CONSTITUTION.md): 최상위 원칙, 인간의 보호 권한, 헌법 변경 절차.
2. [Architecture Specification](SSAK_AI_ARCHITECTURE_SPEC_V1.md): 시스템 경계와 Architecture Invariants.
3. 해당 작업의 세부 Protocol: 아래 목록에서 선택한다.
4. [Gap Analysis](SSAK_AI_GAP_ANALYSIS_V1.md): 현재 근거, 미확인 사항, 변경 이유.
5. [Implementation Roadmap](IMPLEMENTATION_ROADMAP.md): P00~P12 구현 계약과 선행 조건.
6. [Acceptance Checklist](ACCEPTANCE_CHECKLIST.md): 시험 시나리오와 증거를 통한 완료 판정.

하위 문서, 현재 코드, 구현 편의, 성능 최적화는 상위 원칙을 변경할 근거가 될 수 없다. 충돌하면 상위 계약을 유지하고 Architecture Conflict를 기록한다. 헌법 의미·Human Authority·Protected Authority·Project Premise 변경은 명시적인 인간 결정이 필요하다. 그 밖의 구현 세부사항은 상위 계약 안에서 진행한다.

각 카드는 `상위 원칙 → Gap 근거 → 구현 → 실제 표면 검증 → 인수 증거 → 다음 카드` 순서로 닫는다. 다른 문서의 짧은 설명을 근거로 이 패키지의 상세 인수 조건을 생략하지 않는다.

## 2. 반드시 보존할 설계 경계

| 영역 | 구현 계약 | 담당 카드 / 인수 |
|---|---|---|
| Brain 교체·연속성 | State/Memory/Experience/Decision/Knowledge/Governance/Authority/Human Partnership은 특정 provider session에 종속되지 않음 | P01/P02/P04/P11, T04/T11/T12 |
| Brain/Body | 의미 해석·가설·최종 semantic integration은 Primary Brain. Body는 구조화·비교·provenance·권한·실행을 담당 | P04/P05/P08/P09, T04/T05/T08/T10 |
| Context | 현재 상태에서 재구성. 최소충분 주입, handle 기반 선택적 확장, 과거 결론 강제 금지 | P04, T03 |
| Governance | 요청 변경을 숨기지 않음. 다차원 권한과 Risk Shaping, protected boundary 유지 | P03/P05/P07, T01b/T05/T07 |
| COMMIT | 9개 readiness 조건만 검사. LLM·규칙·점수 어느 방식으로도 결론의 의미적 정답을 재심사하지 않음 | P06, T06 |
| Stop·Closure | 의미 변화가 없으면 확장 중단. Stop은 READY가 아니며 Material Trigger로 최소 범위 reopen | P06/P08, T06/T08 |
| Experience | 운영 기록과 선별된 Experience 구분. 관찰·평가·해석 분리. 과거 원본 보존 | P08, T09 |
| 성장 | Experience→Evaluation→Candidate→Validation→Versioned Policy→실제 Future Behavior Change | P09/P10, T10/T13 |
| 복잡성 | Simple to start, designed to mature. 조건부 기능은 필요할 때만 활성화, 새 복잡성은 증거로 정당화 | P00/P08/P10, T00b/T08/T13 |
| 인간과의 관계 | Human Partner가 최종 Value/Authority Owner. 기존 승인 범위는 존중하며 불필요한 승인 반복 금지 | P03/P05/P12, T01b/T05/T14 |

헌법 24개 원칙 전체가 적용된다. 이 표는 헌법을 대체하는 축약 헌법이 아니라 구현·검증 위치를 찾기 위한 안내다.

## 3. 영구 설계 문서

- [운영 루프](COGNITIVE_OPERATING_LOOP.md), [데이터 모델](COGNITIVE_DATA_MODEL.md).
- [Brain Engagement](BRAIN_ENGAGEMENT_PROTOCOL.md), [Context·Memory](CONTEXT_AND_MEMORY.md).
- [Evidence·Unknown](EVIDENCE_AND_UNCERTAINTY.md), [Decision·COMMIT](DECISION_AND_COMMIT.md).
- [Governance·Authority](GOVERNANCE_AND_AUTHORITY.md), [Experience·Learning](EXPERIENCE_AND_LEARNING.md).
- [Self-improvement](SELF_IMPROVEMENT_POLICY.md), [Benchmark·Ablation](BENCHMARK_AND_ABLATION.md).
- ADR: [Primary/COMMIT](ARCHITECTURE_DECISIONS/ADR-0001-primary-brain-authority.md), [Context](ARCHITECTURE_DECISIONS/ADR-0002-context-reconstruction.md), [Experience](ARCHITECTURE_DECISIONS/ADR-0003-experience-ownership.md), [Loop ownership](ARCHITECTURE_DECISIONS/ADR-0004-cognitive-loop-ownership.md).

세부 Protocol의 추가 보완은 Roadmap §공통 의미 계약과 해당 카드에 명시했다. Protocol·schema·구현이 이 계약과 어긋나면 담당 카드에서 함께 정합화하고 변경 근거를 남긴다. Constitution의 문구를 자동 수정하는 방법으로 해결하지 않는다.

## 4. 구현 선택과 불변조건의 구분

v1은 Canonical Markdown + explicit references, Git persistence, rebuild 가능한 index, versioned policy activation을 사용한다. 저장 형식·CAS 방식·예산·표본 수·namespace는 구현 선택이며 헌법 그 자체가 아니다. 현재 Architecture Spec의 계약으로서는 준수하고, 변경하려면 ADR·관련 명세·migration 및 검증 근거를 함께 갱신한다.

초기 rule-based 구현과 human-assisted candidate 작성은 허용한다. 그러나 경험이 쌓여도 행동이 바뀔 수 없는 구조, 검증 없이 정책을 적용하는 구조, Context 학습만 가능하도록 나머지 성장 경로를 영구 차단하는 구조는 허용하지 않는다.

## 5. 현재 상태와 증거 사용법

아래는 기존 증거 문서의 보고 내용이다. 이번 v1.1 문서 편집에서 코드·시험을 재실행했다는 뜻이 아니다. source SHA뿐 아니라 dirty-file digest, 시험 범위, limitation을 대조해야 한다.

| 영역 | 기존 보고 | 남은 인수 |
|---|---|---|
| P00 | [기준선](evidence/T00_baseline.md): 일부 경계·회귀 기록 | 전체 entrypoint 기준선, T00b 초기 계측 |
| P01 | [Typed model](evidence/T01a_typed_model.md): 모듈 시험 PASS | 현재 소스 재대조, v1.1 선별·계보 계약과 schema 정합화 |
| P02 | [Canonical store](evidence/T02_canonical_store.md): 모듈 시험 PASS | 실제 Vault 동시성·사용자 경로 통합 |
| P03 | [보호 경계](evidence/T01b_protection.md): 모듈/tool gate/store PASS | migration/evolution 실제 hook, 승인 발급·검증 |
| P04 | [Context·Brain](evidence/T03_T04_context_brain.md): 모듈 시험 PASS | 최소충분 Context·의미 경계 추가 시험, 실제 provider/router 통합 |
| P05 | [Governance](evidence/T05_governance.md): module + tool_executor surface PASS (31 시험) | CLI/API/stream/background 연결, 승인 발급 주체 검증은 P11 이월 |
| P06 | [COMMIT](evidence/T06_commit.md): module + canonical store 표면 PASS (28 시험) | loop(P08)·사용자 표면(P11) 실행 경로 연결 이월 |
| P07 | [Action](evidence/T07_actions.md): module + ToolExecutor·CanonicalStore 표면 PASS (17 시험) | task_state_store 재시작 복구, OBSERVE 경험 형성은 P08/P11 이월 |
| P08 | [Loop·Experience](evidence/T08_T09_episode.md): module + ToolExecutor·CanonicalStore 표면 PASS (21 시험) | production 대화 경로 opt-in(P11), Knowledge/Policy 승격(P09) 이월 |
| P09 | [Learning lifecycle](evidence/T10_learning.md): module + CanonicalStore 표면 PASS (29 시험) | 실제 성장 효과 계측(P10), runtime·사용자 표면 연결(P11) |
| P10 | [성장·ablation](evidence/T13_growth.md): deterministic fixture PASS (17 시험 + CLI artifact) | live pilot NOT_RUN, 실제 provider·표본 확대·실측 latency 이월 |
| P10 (live) | [live pilot harness](evidence/T13_live_pilot.md): harness·분리 계약 PASS (12 시험) | 실제 provider·확증 표본 등록은 사람 결정 필요 |
| P11 (부분) | [사용자 표면 opt-in](evidence/T11_surface.md): 실측 + adapter + read-only CLI/API(SSE 포함) + feature-off 회귀 PASS (36 시험) | 대화 스트림/background 배선, 실모델 QA, ACTIVE 실검증 이월 |
| P12 (부분) | [migration dry-run](evidence/T12_migration.md): source read-only·별도 root·mapping·index·rollback PASS (14 시험) | destructive 변환 NOT_RUN, 실사용 DB dry-run 이월 |
| P12 (T14) | [최종 Architecture Review](ARCHITECTURE_REVIEW.md): 헌법 24원칙(covered 15·partial 9·gap 0)·§63 12질문·§52 10질문 매핑 + 기계 검증 16 checks PASS(인용의 실재·추적, 증거 digest 의 drift, 증거 산문의 상태 주장, 하한 원장까지 측정) · 고정 순서 전량 회귀 5 failed/7666 passed(cognitive 실패 0), 남은 5건은 커밋 이력·패키징·문서 기준선으로 분리 · 회귀가 찾은 enum identity 결함을 `same_enum`으로 95곳 통일 + 감사 위반 0 (8 시험) | 실표면 QA(P11)·사람 승인 이월 |
| P12 (T14 증거 digest) | [증거 digest drift](ARCHITECTURE_REVIEW.md): pin 50개를 실제 파일과 대조하는 harness(`scripts/digest_drift.py`) — 그대로 29 · **재확인 21** · 미확인 0 · 재확인 무효 0, 재확인은 `--method` 없이 기록 불가 (25 시험) | 실모델·실 vault 재확인은 이월 |
| P12 (T14 상태 주장) | [증거 산문의 상태 주장 재판정](ARCHITECTURE_REVIEW.md): “이 시험은 실패한다” 류 문장(test node 지정)을 현재 트리와 대조하는 감사(`scripts/audit_state_claims.py`) — 주장 4건 중 그대로 0 · **정정 붙임 4** · 낡음 0, 정정 없이 실제와 어긋나면 리뷰 실패 · 감사자 자신이 매 실행 **자기시험 17건**으로 자기 눈을 확인하고, 하한(mention 6≥1 여유 5 · 주장 4≥1 여유 3)을 **근거(`why`)·여유(`margin`)와 함께 artifact 로 기록**해 리뷰가 저장본과 새 측정을 대조 (이빨 22 시험 · 기계 검증 **14 checks PASS**) | 실모델·사람 승인 표면은 이월 |
| P12 (T14 harness 자기시험) | [공통 계약](ARCHITECTURE_REVIEW.md): 자기가 못 보면 조용히 통과하는 병을 여섯 harness 에서 공유 계약(`scripts/harness_contract.py`)으로 막는다 — 매 실행 자기 판독 재판정(digest 9 · 원장 11 · 상태 주장 17 · enum 5 · purge 6 · 표면 6건) + 탐지력 하한(여섯 harness 모두 **값 + 근거(`why`) + 여유(`margin`)** 를 artifact 에 기록) + **카나리아**가 각 하한을 눈멀게 한 사본으로 시험해 장식이 아님을 확인, 자기시험 부재·근거 없는 하한도 실패 (38 시험 · **14 checks PASS**) | 각 harness 의 실측 재검토는 이월 |
| P12 (T14 카나리아 종료 코드) | [판정과 진단을 함께 낸다](ARCHITECTURE_REVIEW.md): `--emit-json` 이 결과와 무관하게 exit 0 이던 이음매를 닫았다 — 장식 하한이 있으면 JSON 을 내면서도 exit 1, 리뷰는 0 이 아닌 종료 코드에서도 JSON 을 살려 **어느 harness 가 못 물었는지** 이름을 남기고, 모순(보고는 통과인데 스스로 실패)·종료 코드 없는 보고·합계 불일치를 실패로 잡는다 (7 시험 · **14 checks PASS**) | 하한을 내리는 판단은 사람 몫으로 이월 |
| P12 (T14 카나리아 이빨) | [카나리아를 리뷰가 지키게](ARCHITECTURE_REVIEW.md): “각 하한이 실제로 무는가” 를 보는 검사에 **스스로의 이빨**을 달았다 — 못 돌린 경우 · 장식 하한 · 정상 측정을 막는 하한 · 근거 없는 하한 · harness 0개 보기 · 마커 계산 · 저장소 카나리아 실물 확인 (7 시험 · **14 checks PASS**) | 하한을 내리는 판단은 사람 몫으로 이월 |
| P12 (T14 증거 게이트 CI 배선) | [판정·추이가 리뷰어에게 닿게](ARCHITECTURE_REVIEW.md): ① `ci.yml` 이 `docs/**`·`**.md` 를 무시해 **문서만 바꾼 PR 은 게이트를 건너뛰던 구멍**을 `evidence.yml` 이 그 여집합으로 맡아 닫았고(둘을 합치면 모든 변경이 덮인다) ② 게이트가 `--summary` 로 **markdown 요약**을 내면 두 워크플로가 `$GITHUB_STEP_SUMMARY` 와 PR 댓글(같은 댓글 갱신)로 보여 주고 artifact 2종을 올린다 — **빨간 실행도 요약을 남긴다**. 배선은 시험이 txt 수준으로 본다 (4 시험) | PR 댓글은 문서 변경 워크플로에서만 |
| P12 (T14 배포 산출물) | [`build` 를 NOT_RUN 에서 빼냈다](ARCHITECTURE_REVIEW.md): wheel·sdist 를 실제로 만들어(둘 다) **저장소 밖 신규 venv** 에 설치해 CLI·모듈·API·auth 를 돌리고, **sdist 왕복**(sdist 안에서 다시 빌드한 wheel 과 **이름+내용** 비교 — 664개 · 빠짐 0 · 내용 다름 0) · **내용 대조**(배포판 패키지 658개 바이트 = 빌드가 본 트리 · 다름 0 · `dist-info` 6개는 견줄 수 없음, 빌드가 내용을 바꿔 싣는 미니 프로젝트를 매 실행 둘 빌드해 그 눈이 무는지 확인) · **배포판 vs 추적 트리**(추적 656개가 모두 배포판에 있다 — `uv build` 는 wheel 을 sdist 에서 만들므로 sdist 가 잃은 파일은 소비자에게도 없다) · **재현 빌드**(`SOURCE_DATE_EPOCH` 를 고정하고 한 번 더 — **wheel 은 바이트가 같고 sdist 는 다르다**: 항목 중 pin 을 따르는 것 wheel 664/664 · sdist 0/1205. 그래서 sdist 는 **좁고 만료되는 예외**로 기록한다: 디렉터리·커밋되지 않은 생성물만 허용, 커밋된 파일·목록이 흔들리면 실패, sdist 가 **같아지면** “예외를 지워라” 로 실패) · **민감도 실물 재현**(같은 backend 의 미니 프로젝트를 매 실행 셋 빌드 — 같은 pin 은 같고 다른 pin 은 달라야 하며, 미니 sdist 도 같은 모양으로 달라지는지 본다) · **배포 경로 감사**(CI `build` job 이 같은 pin 을 걸었는지 읽어 대조) · **red 재현 셋**을 본다 — ‘빠진 배포판’(module 하나를 뺀 wheel)은 검증기가 막고, ‘빠진 sdist’와 ‘잃어버린 추적 파일’(작은 실물 프로젝트를 매 실행 빌드)은 **이름으로 지목**한다. red 재현이 없으면 “설치만 됐다” 와 구분할 수 없다. 게이트의 **로컬(`--tier full`) stage**(61초)이고 CI fast 는 이 층을 ‘보지 않은 층’ 으로 적는다(그 자리는 CI build job — 그 job 은 이제 같은 `SOURCE_DATE_EPOCH` 를 건다) (계약 시험 89 · **15 checks PASS**) | 카나리아는 이 층을 **기록으로** 본다(빌드로는 못 들어간다 — 아래 하한 기록 행) · 추적 대조는 커밋된 파일만 본다(미추적분은 보고) · 내용 대조는 **디스크** 트리와 견준다(커밋본이 아니다 — 미커밋 편집을 오탐으로 만들지 않기 위해서다) · **sdist 재현은 아직 안 된다**(backend 가 `SOURCE_DATE_EPOCH` 를 읽지 않는다 — 미니 프로젝트로 매 실행 확인) |
| P12 (T14 red 리허설) | [위반 0건인 감사에 red 를 심어 본다](ARCHITECTURE_REVIEW.md): 두 감사는 위반이 0건이라 green 이 “다 봤는데 깨끗하다” 인지 “한 번도 빨간을 본 적이 없다” 인지 실행으로 갈리지 않았다 — 저장소 밖 임시 트리에 **진짜 파일로 위반을 심고** 감사에 열린 `--root` 로 돌려 확인한다: 심은 트리 exit 1 + 파일 지목 · **경계 사례 8개를 같은 실행에 심어 오탐 0** · 대조군(허용 형태) 초록 · 없는 트리 차단. 리허설되지 않는 층은 **이유와 함께 선언**하고 게이트가 그 회계를 roster 와 대조한다 (이빨 14+11 시험 · **15 checks PASS**) | 경계 사례는 표본이라 allow-list 전체는 아님 |
| P12 (T14 층별 수치 추이) | [어제보다 얇아졌는가](ARCHITECTURE_REVIEW.md): 게이트가 층마다 **한 번의 실행으로 판정 + 수치**를 받아(이음매가 먼저 필요했다) 65개 수치를 저장소의 **기준**(사람이 마지막으로 승인한 파일)과 대조한다 — 줄어든 수를 먼저, 그대로인 수는 접어서. 이동은 판정이 아니고, 실패하는 것은 **수를 못 읽은 층**·**못 돌린 층**·**깨진 기준**이다. 기준은 `--record-baseline --method` 로만 갱신되고(날짜·무엇을 보고 승인했는지 함께) 게이트는 기준을 읽기만 한다 (이빨 19 시험) | 첫 실행은 “기준 없음” 이라고 말한다 |
| P12 (T14 이음매 전수) | [JSON 을 낸다고 통과는 아니다](ARCHITECTURE_REVIEW.md): 카나리아에서 고친 이음매(`--emit-json` 이 결과와 무관하게 exit 0)를 전수 확인해 **두 층이 같은 병을 앓고 있음**을 찾았다 — `digest_drift` 는 없는 artifact 에서 `--gate` exit 1 인데 `--emit-json` 은 exit 0(JSON 은 그대로 냈다), `audit_state_claims` 도 같다. 두 경로가 이제 같은 판정을 쓰고, 리뷰는 세 층(카나리아·digest·상태 주장)을 같은 규칙으로 읽는다 — 종료 코드 없는 보고는 판정이 아니고, 보고서는 통과인데 스스로 실패했다고 말하면 모순으로 실패한다 (이빨 9 시험) | — |
| P12 (T14 증거 게이트) | [층을 한 번에](ARCHITECTURE_REVIEW.md): 층마다 있는 게이트를 **도는 자리**가 사람의 기억뿐이었다 — `scripts/evidence_gate.py` 가 stage 마다 독립 process 로 돌려 종료 코드·소요 시간·**첫 실패 문장**을 모아 어느 층이 빨간지 이름으로 말한다(fast 9 stage · 34초 · full 11 stage · 96초). 없는 스크립트·없는 산출물·제한 시간 초과는 `unrun`(실패)이고, **tier 밖 층은 “보지 않은 층”** 으로 적는다(회귀 원장의 회차 산출물은 커밋되지 않는다). 게이트도 카나리아가 보고(하한이 장식이 아님을 확인), 리뷰는 검사 `evidence_gate` 로 stage roster·tier·자기시험 47건·하한 근거를 본다. 기준을 기록할 때 **게이트가 아직 도는 층을 빼는 기록은 거부**한다 — fast 로 기록하자 full 전용 둘이 기준에서 조용히 사라졌고(층 10 → 9) 다음 실행은 그것들을 “기준 없음” 으로 봤다: 승인은 자기가 본 것만 말해야 하고, **보지 않은 층의 승인을 지우는 것은 결정이 아니라 손실**이다(stage 목록에서 진짜 사라진 층은 빼도 된다) (이빨 36 시험 · **16 checks PASS**) | `--tier full` 은 로컬 회차 필요, CI 는 fast |
| P12 (T14 회귀 원장) | [회귀 원장](evidence/T14_regression_ledger.md): 502 파일을 9 scope 로 나눠 **variant(seed 101·202 + 순서 뒤집은 3회)** 로 측정 — 결정적 11 · variant 민감 0 · 무소유 0, 중단 회차는 자동 재시도하되 횟수·로그를 남김 (32 시험 + 리뷰 계약) | scope 사이 순서·중단 회차 원인은 이월 |
| P12 (T14 격리) | [namespace 오염 제거](evidence/T14_namespace_isolation.md): import 시점 `sys.modules` purge를 미러 리허설에서만 하도록 조건화 + 감사·계약 시험 (5 시험) · 미러 리허설 PASS 17/FAIL 0 | 남은 순서 민감성은 별도 분리 |
| P12 (T14 배포 산출물 만료) | [기록된 관측이 얼마나 움직여도 되는가](ARCHITECTURE_REVIEW.md): 하한 기록은 “이 하한은 관측에서 이만큼 떨어져 있다” 는 승인이므로, 관측이 그 허용 이상 **줄면** 기록이 현재를 과장한다 — 그래서 기록에 **허용 이동**(10% · 작은 관측(산출물 2)은 허용 0)을 함께 담고, 관측이 허용 이상 줄면 층이 실패하며(문장이 이름·수치를 남긴다) **늘어난 것은 보고만** 한다(기록이 현재를 과장하지 않으면 안전한 쪽으로 틀린 것이다). 허용을 넓히거나 손으로 고친 기록도 실패다 — 만료 규칙을 무력하게 만들면 “기록이 낡았는가” 라는 물음 자체가 사라진다. 실측: 664→598(허용 경계) 통과 · 664→597 만료 · 2→3 통과 · 2→1 즉시 만료 (이빨 3 시험 · 자기시험 76 → 84건) | 하한을 내리는 판단은 사람 몫 · 허용 비율의 근거가 낡으면(정상 이동이 커지면) 상수와 근거를 다시 고쳐 기록해야 한다 |
| P12 (T14 배포 산출물 하한 기록) | [하한이 무는지를 카나리아가 빌드 없이 본다](ARCHITECTURE_REVIEW.md): 이 층의 하한을 재려면 61초 빌드가 필요해 fast tier 의 카나리아에 들어갈 수 없었다 — 그래서 층이 `--record --method` 로 **하한 기록**(`evidence/release_artifacts.json`: 값·관측·근거·승인 문장)을 남기고, 카나리아가 그 기록으로 여섯 하한이 정상 관측을 막지 않고·눈멀게 한 사본은 막으며·근거를 함께 내는지 본다(harness **9개** · 기록 기준 넷). 기록은 그 층이 스스로 지킨다 — **판단**(하한 값·근거·개수)이 지금 코드와 다르면 게이트가 실패하고(낡은 기록 위의 초록은 거짓), **관측**이 움직인 것은 보고만 한다(파일이 늘면 “비교한 파일” 관측도 는다). 기록 없음·승인 문장 없음·날짜 없음도 실패이고, 장식 하한(`minimum=0`)을 심은 사본은 카나리아가 BLIND 로 지목한다 — 거부는 빌드 전에 나고 실패한 실행은 기록하지 않는다 (이빨 12 시험 · 자기시험 64 → **76건**) | 하한을 내리는 판단은 사람 몫 · 기록은 사람의 승인으로만 갱신 |
| P12 (T14 하한 원장) | [하한을 한 자리에서](ARCHITECTURE_REVIEW.md): “이 저장소에는 어떤 하한이 있고 **무엇을 보고** 누가 승인했는가” 를 묻는 자리가 사람의 기억뿐이었다 — 하한은 다섯 harness 의 코드 상수와 네 기록 artifact 에 흩어져 있었고, 값만 읽고서는 나중에 낮춰도 되는지 판단할 수 없다. `scripts/floor_ledger.py` 가 카나리아와 **같은 눈**(기록이 있으면 저장본, 없으면 직접 측정 — 두 번째 구현을 만들지 않는다)으로 읽어 한 표로 낸다: 층 **11** · 하한 **21**(기록 넷 12 + 직접 여섯 7 + 자기 2) · 다른 층에서 본 캔버스 19 ≥ 하한 15 · 고아 기록 0 · 4초. 행마다 관측·하한값·여유·근거와 **승인(날짜·누구·해시 — 기록 artifact 의 승인 문장, 없으면 그 근거 파일의 마지막 커밋)** 을 적는다. 실패는 여섯: 하한 없는 층 · 근거 없는 하한 · 못 읽는 기록 · **아무도 읽지 않는 기록**(`floors` 를 담았는데 어떤 harness 도 안 읽음 — 면죄부를 남기지 않는다) · 승인을 못 읽음 · 캔버스가 자기 하한 미만. 자기 자신도 같은 규칙으로 판정되는데 **자기 행은 캔버스에 안 든다**(자기를 세면 저절로 참이 된다) — 첫 구현이 자기 행을 루프 밖에서 만들어 **자기 승인 검사를 건너뛰던 결함**을 실제로 잡았다. **표 밖은 이제 침묵이 아니라 목록이다**: `scripts/*.py` 를 AST 로 읽어 하한처럼 생긴 **숫자 상수**(주석·문자열·``_WHY_*`` 근거 문자열 제외)를 세고, 그중 `Floor(..., minimum=…)` 에 실제로 넘겨진 것을 **그 하한을 드는 층에 이어** 배선으로 본다(잇는 자리는 코드의 배선이다 — 하한의 **라벨**은 `pin`·`회차` 처럼 사람이 쓴 이름이라 상수 이름으로 잇지 못하고, 라벨로 이으려 한 첫 구현은 합성 자기시험만 통과한 채 실제 저장소에서 **0건**을 이었다) — 배선도 선언(`OUTSIDE` — 근거·소유자·재검토 기한)도 아닌 후보는 **이름을 대며 실패**하고, 선언은 양방향이다(그 상수가 하한이 되거나 사라지면 낡은 선언으로 실패 — 면죄부는 다음 결함을 가린다). 실측 후보 32(배선 22 — 그 22개가 표의 층 11개에 **어느 층의 하한인지**까지 이어져 있다 · 선언 10) · 스캔 하한 24. **첫 승격은 스캔이 찾았다**: 리뷰의 인용 하한이 검사 함수 안에만 있어 어떤 하한 목록에도 안 실려 있었고, 이제 `coverage_floors` 로 나가 카나리아 `review` harness 가 된다(관측 = 인용 270). 배선: 게이트 fast stage(11번째) · 카나리아 열한째 harness(자기 하한도 눈멀게 하면 문다) · 리뷰 16번째 검사(표의 합계·고아 수·승인·근거·표 밖 상태·기록 상태·`verdict` 와 종료 코드의 정합) (계약 시험 38 + 자기시험 **147건** · **16 checks PASS** · marker 36종 — `ledger_wired` 22 · `ledger_late_reviews` 0). **하한을 내리는 판단이 남는 자리**: 표는 **사람이 승인한 기록**(`evidence/floor_ledger.json`, `--record --method`)과 대조한다 — 기록보다 **내려간 하한값**·**사라진 하한**·**기록에 없는 새 하한**·**값이 같아도 바뀐 근거**는 실패이고(이름·옛값·새값을 함께 낸다), **관측 이동·올라간 하한은 보고**다(관측은 각 층의 게이트가 판정한다 — 둘이 같은 것을 두 번 판정하면 기록이 잡음으로 낡는다). 그 이동은 **층 단위로 묶여** 말해진다 — 층이 통째로 빠지면 하한 개수만큼의 문장이 아니라 한 문장(몇 개가 함께 갔는지)이고, **그 층이 아직 roster 에 있으면 결정이 아니라 결함**(표가 그 층을 못 읽었다)으로 말한다. 하한 이름 집합이 그대로인 사라진 층과 새 층은 **“이름만 바뀐 것으로 보인다”** 고 짝과 근거를 한 문장으로 내되 단정하지 않는다(일부만 겹치면 쓰지 않고, roster 에 살아 있으면 결함이므로 덮지 않는다 — 판단은 사람 몫). 이름 변경은 **기록에 사실로 남는다**(`renames`: 옛 이름 → 새 이름 · 그대로 옮겨간 하한 이름들 · 승인 날짜) — `floors` 는 지금 이름만 담으므로 그것만 적으면 그 하한들이 처음부터 새 이름의 층에 있었던 것으로 읽히고 옛 이름은 다음 회차에 사라진다. 이력은 다음 기록으로 이어지고(`p → r → s`), 기록은 자기 이력과 모순될 수 없다(새 이름이 기록의 하한에 있어야 하고 · 옛 이름은 거기 있으면 안 되고 · 같은 새 이름으로 두 번 바뀌었거나 이름이 고리를 이루면 실패) · 기록이 승인한 옛 이름이 표에 돌아오면 다시 승인받는다. 그리고 **면제도 승인을 지난다**: 선언(`OUTSIDE`)은 “이 상수는 하한이 아니다” 라는 판단인데 기록에 **이름으로만** 실려 있었고(그 목록을 읽는 자리도 없었다), 그래서 면제를 만들어도 · 근거·소유자를 바꿔도 · **재검토 기한을 미뤄도** 표는 조용했다 — 날짜가 있으면 통과했기 때문이다(면죄부가 스스로 갱신되는 자리였다). 이제 기록은 면제를 **이름·근거·소유자·기한**까지 담고, 표는 그 기록과 대조한다: 기록에 없는 **새 면제** · 기록이 승인했는데 표에 없는 **거둔 면제** · **바뀐 근거·소유자** · **미룬 기한**은 실패고 **앞당긴 기한**은 보고다(더 자주 보는 쪽이 안전한 쪽이다). 옛 이름이 낡은 선언이고 새 이름이 실재하는 후보인데 약속이 토씨 하나 안 틀리고 같으면 사라짐·새 면제 대신 한 문장으로 **“이름만 바뀐 것으로 보인다”** 고 말하되(단정하지 않는다) 그 문장도 승인을 요구한다. 그리고 그 면제의 **기한은 확인일로부터의 창**이다: 날짜만 뒤로 미는 일은 검토가 아니므로 면제는 **확인일**(`reviewed_on` — 이 판단을 마지막으로 확인한 날)을 들고, 기한이 확인일보다 뒤인지·확인일이 미래가 아닌지·기한까지의 창이 한 번의 확인으로 줄 수 있는 크기(366일) 안인지를 묻는다(창이 없으면 한 번의 확인으로 면죄부를 두 해·세 해로 늘릴 수 있다). 창 자체도 판단이라 기록이 함께 승인하고(둘이 갈라지면 기록이 먼저 실패한다), 같은 사실을 두 사건으로 말한다 — **기한만 뒤로 가고 확인일이 그대로**면 “기한만 미뤘다(연장이 아니다)” 이고 **확인일까지 잡았으면** “기한을 미뤘다(결정이다)” 다. 기한을 당기거나 확인일만 새로 잡은 것은 보고고, 창을 넘는 기한은 표가 먼저 막는다(면제 10개의 확인일 2026-09-24 · 창 98일 ≤ 366일). 기한이 움직인 순간은 기록이 **사실로 이어 가고**(미룸 횟수는 주장이 아니라 계산이다), 확인일 없이 기한만 미룬 실행은 **기록을 거부한다**(그대로 쓰면 옛 기한이 덮여 그 사실이 사라지므로 파일을 손대지 않는다) — 재검토는 `--review` 가 기한이 가까운 순서로(남은 날·미룸 횟수) 낸다. 면제가 층이 되는 순간(**승격**)도 기록이 사실로 담고(`promoted` — 이름·층·그 층이 그 하한을 부르는 **이름**(라벨)·승인 날짜: 그 사실이 없으면 새 하한 하나가 늘어난 것과 구별되지 않고, 라벨이 없으면 기록이 “그 층에 그 하한이 실렸는가” 를 자기 안에서 확인할 수 없다), 승격은 셋이 다 되어야 끝나므로(그 층의 하한 목록에 싣고·선언을 지우고·기록한다) `--promote <이름>` 이 한 자리에서 남은 일을 내고 **끝났는지를 종료 코드로** 말한다. 승격 감지는 **배선으로 잇는다** — 잇지 못하는 승격(그 층에 기록에 없던 새 하한이 없거나, 한 회차에 둘이라 어느 것이 그 상수인지 모르는 경우)은 **기록을 거부한다**(추측을 사실처럼 적지 않는다: 그대로 쓰면 “그 도구가 층이 되었다” 는 사실이 지워진다). 하한을 **기록 artifact** 에서 드는 층은 코드에만 싣고 끝나지 않고(그 층의 artifact 도 같은 것을 말해야 한다 — 카나리아가 이름·값으로 대조한다) `--promote` 가 그 사실과 그 층이 지금 내는 하한을 함께 낸다. 그리고 이 저장소는 아직 승격이 일어난 적이 없어(선언 10개가 모두 면제) 이 절차가 **도는지**를 알 수 없었으므로 **클린 worktree 사본에서 실제 승격 왕복**을 돌렸고, 그 실험이 코드의 거짓말 셋을 찾아냈다: `--promote` 가 기록을 **보고**로 읽어 선언된 면제에게 “면제로 선언된 적이 없다” 고 말하던 자리 · artifact 층에 코드만 실어 끝난 것처럼 보이던 자리 · 승격 사실이 그 층의 **새 하한 라벨**을 모르던 자리. 실패한 실행은 기록하지 않고(기록은 통과의 승인), 기록 없이 도는 실행은 통과가 아니다. 그 이력이 담아야 하는 것은 **방향이 아니라 옛 기한·새 기한·그 이동을 받친 확인일**이라는 사실을 이번 회차가 실측으로 닫았다: 첫 구현은 기한이 앞으로만 가는 이력을 요구했고, 그래서 면제의 기한을 **앞당긴** 이동을 기록하면 그 다음 게이트가 그 이동을 “되돌아간 이동” 이라 부르며 실패했다(표는 초록인데 기록 때문에 빨간 상태이고, 실패한 실행은 기록되지 않으므로 손으로 기록을 고쳐 그 사실을 지우는 것 말고는 길이 없었다 — 자기시험은 그 잘못된 규칙을 **정답으로 못박고** 있었다). 이제 방향은 모순이 아니고(제자리 이동만 이동이 아니다 — 표도 앞당긴 기한을 보고로 내고 시트가 “당김” 으로 센다), 이동마다 그 검토를 받친 **확인일**이 함께 남는다: 승인 날짜(`on`)는 기록을 쓴 날이라 검토일이 아니고, 확인일이 없으면 “제때 봤다” 와 “넘겨서 봤다” 가 같은 줄로 읽힌다. 그 확인일이 **옛 기한보다 뒤면** 그 연장은 **늦은 검토**다 — 약속을 넘겨서 다시 본 것이므로 실패가 아니라 사실이고(막으면 그 면제는 영원히 닫히지 않는다), 원장이 `그중 늦은 검토 N회` 로, 시트가 면제마다 `늦음 N회` 로 세며, 기록을 지나기 전의 연장에는 “그 연장은 **늦은 검토**다(옛 기한 … 를 지나 … 에 검토)” 문장이 함께 나온다(그 사실도 기록에 남는다). 확인일은 이력에서도 문다: 그 이동이 준 기한보다 뒤일 수 없고(창의 규칙을 이력에도 묻는다), 이력의 마지막 검토가 지금 승인된 확인일보다 뒤일 수 없다. 늦은 검토가 생기면 문서의 수가 먼저 낡는다(marker `ledger_late_reviews` 0). 실측: 기록된 기한 이동 0회(그중 늦은 검토 0회). | 이름 패턴은 추측이라 다른 이름의 임계값이나 계산해서 넘긴 하한은 스캔이 못 본다 · 기록은 관측을 판정하지 않고 사람의 승인으로만 갱신된다(커밋되어야 남는다) · 층 이름 변경은 “보인다” 까지만 말한다(일부만 겹치는 경우와 진짜 새 층은 사람이 가르고, 기록이 담는 것은 승인된 사실이지 확인된 동일성이 아니다) · 승인으로 적힌 커밋은 그 하한을 바꾼 커밋이 아닐 수 있다 · 하한을 내리는 판단은 사람 몫 · 면제의 승인은 **“기록을 지나갔는가” 까지만** 말한다(그 결정이 옳았는지는 사람 몫이고, 면제의 근거를 다듬으면서 이름도 바꾸면 두 문장이 나온다) · 확인일도 원장은 **움직였는가** 만 본다(그 날 무엇을 보았는지는 묻지 못하고, 창의 크기 366일은 지금의 판단이다) · 미룬 횟수는 기록이 적은 이동에서 세므로 늦었는지는 알아도 **왜 늦었는지**는 묻지 못한다(세 번째·네 번째 미룸은 신호일 뿐 자동 승격이 아니고, 확인일이 없는 옛 기록의 이동은 “언제의 검토인지 말하지 못한다” 로 먼저 문다) · 승격도 원장은 “기록한 사실이 자기 모습과 표에서 맞는가” 까지만 보고(그 하한의 관측·근거가 맞는지는 그 층의 게이트와 사람의 몫이다) `--promote` 는 코드를 대신 고치지 않으므로 어느 층의 하한으로 세울지는 사람이 정한다 · **배선은 코드를 읽는 눈이라 침묵이 있다**: 상수를 다른 이름으로 넘기거나 계산해서 넘기면 그 층도 배선으로 안 잡히고(그 상수는 “선언도 배선도 아닌 후보” 로 남는다), 같은 이름의 상수가 여러 파일에 있으면 정의 파일이 그 층의 스크립트일 때만 이어지며, **한 회차에 하나씩만 승격할 수 있다**(그 층의 새 하한이 둘이면 잇지 않고 기록을 거부한다 — 어느 것이 그 상수인지 기계가 모르는 것을 사실처럼 적지 않는다) |

상세 상태는 Acceptance Checklist가 관리한다. 기존 module PASS는 보존하지만 새로운 시험이나 실제 사용자 경로 PASS로 확대하지 않는다. 참고 문서의 과거 완료 표현보다 시험 범위와 근거가 우선한다.

## 6. 실행 책임

P01/P03/P06/P12는 주 담당자, P00/P08/P11은 통합 담당자가 책임진다. 나머지 역할은 Roadmap에 명시한다. 역할 배정은 별도 에이전트가 실행됐다는 뜻이 아니다. 공유 runtime/tool/config 파일은 통합 담당 한 명이 수정한다.

완료 상태는 문서·모듈·통합·최종 인수를 분리한다. 신규 인수 항목은 미실행으로 시작하고 실제 증거를 얻은 뒤에만 체크한다. 원래 작업의 수정·데이터·검증 이력을 되돌리지 않는다.

## 7. 원문과 참고 기록

[Master Prompt 원문](MASTER_PROMPT_V2_SOURCE.md), [원문 digest](SOURCE_MANIFEST.json), [코드 기준선 manifest](CURRENT_TREE_MANIFEST.json), [Envelope schema](contracts/record-envelope.schema.json), [Payload schema](contracts/record-entities.schema.json).

[요구사항 추적표](REQUIREMENTS_TRACEABILITY.md), [기존 보완 분석](SUPPLEMENT_ANALYSIS.md), [기존 산출물 보고](IMPLEMENTATION_REPORT.md), [기존 문서 검증 결과](VALIDATION_REPORT.md)는 당시 기록이다. v1.1 신규 요구의 통과 증거로 자동 재사용하지 않는다.
