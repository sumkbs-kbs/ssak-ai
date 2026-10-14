---
title: 구조화 Product-Vision 단일 실관측 실행 범위
date: 2026-10-14
tags: [product-vision, structured-output, observation, source-bound]
---

작업 ID: IMP-09-B-PRODUCT-VISION-STRUCTURED-OBSERVATION-01.

직접 사용자 요청: "다음 이어서 진행해줘". 직전 인계의 후속 단계인 명시적 schema 요청의 실제 제품 관측을 진행한다. 과거 format 생략 사례의 실패를 재실행하거나 대체하지 않는다.

완료 조건은 현재 승인된 구조화 출력 소스를 보호하고 새 request/schema/image/source binding과 독립 준비 검수를 고정한 뒤, 인증된 외부 loopback Uvicorn 제품 POST를 최대 1회 수행해 결과·cleanup·호출 수를 원문 근거로 검수/인계하는 것이다. 실패/불명도 진실하게 기록하면 관측 작업은 종료하며 추가 요청은 보내지 않는다.

- 모델: qwen3.8:latest, 설치 digest 22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643. metadata가 다르면 INCONCLUSIVE로 중단.
- 고정 이전 이미지 bytes와 질문, 정답 red_circles2/blue_squares1. 새 schema 요청에는 키 두 개의 integer, required 모두, additionalProperties false.
- 제품 request: response_format json_schema envelope, stream false; max_tokens128, temperature0, direct mode. Native format은 정확한 schema object.
- 예상 native profile: model qwen3.8, think false, keep_alive30m, num_ctx32768, num_predict128, temperature0, repeat_penalty1.3, min_p0.05. 임의 범위 완화 금지.
- 이번 fresh run 제품 POST 최대1, Ollama chat inference 최대1. retry/redirect/native/direct-tool inference0. metadata 및 인증 readiness는 승인된 기존 adapter의 단계별 경계에서 계수하고 inference로 합산하지 않는다.
- localhost/127.0.0.1:11434 exact origin; product listener127.0.0.1 ephemeralport, worker1/reloadfalse/lifespanoff.
- 총 deadline120초, readiness15초, cleanup5초. 기존 shutdown/terminate/kill/wait/reap 구현을 재사용.
- 기존 stage97, 제품 소스/설정/원장/기존 증거는 변경하지 않는다. 새 owned run의 하네스와 계약, targeted offline fixture만 수정한다.
- 준비 확인은 새 schema 적합성 fixture에 한정한다. 이미 통과한36/50/45/18 과거 selector는 반복하지 않는다.
- 새 independent review와 소스에 바인딩한 local authorization descriptor를 생성한 후 기존 CLI live path를 root가 단1회 실행한다. 하위 에이전트는 live 실행 금지.

판정은 transport, strict JSON/schema, 정확한 수량, provider/product content 일치, 호출계수 및 OS cleanup을 각각 기록한다. fence stripping/사후 출력 수정/성공 가정 금지. 과거 FAIL_SEMANTIC, 전체 IMP-09 PARTIAL, ledger NOT_RECOVERED는 유지한다.

구조화 구현 부모: ../IMP09C-PRODUCT-VISION-OUTPUT-CONTRACT-01/run-20261014T021626Z-codex-4f8b80cb (검수APPROVED).
하네스 재사용 부모: ../IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0 (과거FAIL_SEMANTIC).
