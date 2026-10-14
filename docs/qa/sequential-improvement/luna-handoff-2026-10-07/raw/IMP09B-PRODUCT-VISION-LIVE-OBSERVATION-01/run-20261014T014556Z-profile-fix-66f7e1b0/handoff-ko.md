---
title: Product Vision 실제 관측 결과와 인계
date: 2026-10-14
tags: [qa, product-vision, live-observation, strict-output-failure]
---

현재 판정은 **COMPLETE_OBSERVATION_WITH_STRICT_OUTPUT_FAILURE / acceptance FAIL_SEMANTIC**입니다. 전체 IMP-09는 PARTIAL, 역사 원장은 NOT_RECOVERED입니다.

마지막 사례는 실제 인증 Uvicorn 제품 라우트에서 로컬 Ollama로 연결했습니다. 제품 및 provider가 HTTP 200을 반환했고 provider done=true, 옵션·입력·응답 lineage·assistant 원본 바이트 일치·worker 종료 및 reap이 모두 통과했습니다. 다만 모델은 다음 문자열을 반환했습니다.

~~~~text
```json
{"red_circles": 2, "blue_squares": 1}
```
~~~~

수량 2/1은 기대값과 일치하는 보조 관측입니다. 코드 fence 때문에 원문을 바로 JSON으로 해석할 수 없어 고정된 엄격 수락 기준은 실패했습니다. fence를 제거해 과거 판정을 PASS로 바꾸지 않았습니다. 실제 추론은 전체 1회이며 추가 추론을 하지 않았습니다.

| 사례 | 실제 제품 POST | 실제 provider 추론 | 원본 판정 / 원인 |
|---|---:|---:|---|
| 1 | 0 | 0 | INCONCLUSIVE_PREPARATION. 제가 계획 파일을 acceptance.json으로 먼저 만들어 하네스 불변 파일 생성과 충돌했습니다. 인증·metadata는 이미 실행됐습니다. |
| 2 | 1 | 0 | INCONCLUSIVE_MANDATORY_GATE_UNKNOWN. 프로젝트가 worker 허용 루트 밖이라 실제 403 project_root_invalid가 발생했습니다. |
| 3 | 1 | 0 | FAIL_MANDATORY_GATE. HTTP 200에 하네스 repeat_penalty 프로필 차이 오류가 일반 assistant 문자열로 담겼습니다. |
| 4 | 1 | 1 | FAIL_SEMANTIC. 전송 조건은 통과했지만 코드 fence가 엄격 JSON 조건을 위반했습니다. |

누적 실제 요청은 제품 POST 3회, 추론 1회, readiness GET 8회, metadata preflight 16회, postflight 3회입니다. 원장과 실제 http-open을 합산한 확인된 HTTP 요청은 31회입니다. 재시도·redirect·native 추론·도구 실행은 0회입니다. 최초 단일 제품 POST 및 단일 preflight 계획은 NOT_MET이며, 이를 사례별 예산 통과로 덮지 않습니다.

실행별 외부 supervisor 종료 코드는 모두 4입니다. 내부 supervisor 종료는 NOT_OBSERVED이며 외부 영수증과 구분합니다. 네 worker는 모두 종료 코드 0, OS 종료 관측·reap·핸들 해제와 cleanup PASS입니다. 초기 phase=cleanup_failed 문구는 실제 cleanup 실패를 뜻하는 근거로 사용하지 않습니다.

수정은 소유 QA 사본에 한정했습니다. parent HTTP의 절대 deadline 적용, 프로젝트를 runtime-state/workspace로 배치, 실제 비스트리밍 GENERAL의 repeat_penalty=1.3/min_p=0.05를 정확한 프로필로 고정했습니다. allowlist를 확대하거나 제품 소스를 바꾸지 않았습니다.

각 수정의 집중 회귀 최종 결과는 10/6/15 PASS이며 최종 정적 검사도 각각 종료 코드 0입니다. 새 프로필의 실제 ASGI→translator→manager→provider 경로는 terminal mock만 교체해 전체 payload를 비교했습니다. 이 오프라인 호출은 실제 HTTP/추론 계수에 포함하지 않습니다. 이전 45/22/18 selector 결과를 새 프로필의 검사 결과로 승격하지 않았습니다.

현재 보호 소스 24개, 구현 6개, 공용 상태 7개가 해시 기준과 일치합니다. 승인 부모의 1,922 파일 및 34 symlink도 그대로입니다. delivery-harness.patch는 승인 부모에서 두 구현 파일을 재구성해 최종 바이트와 일치합니다. 각 수정의 신규 테스트와 단계별 patch는 아래 기록에 있습니다.

- [최종 기계 판정](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/final-result.json)
- [현재 바인딩](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/execution-binding.json)
- [독립 소스 검수](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/current-source-review.json)
- [프로필 수정 및 전체 payload 회귀](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/offline-profile-fix/checks.json)
- [deadline 수정 기록](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T010347Z-codex-11484957-470575c0/offline-fix-attempts/deadline-checks.json)
- [workspace 수정 기록](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T013431Z-workspace-fix-8c6d1943/offline-workspace-fix/checks.json)
- [납품 패치](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/delivery-harness.patch)
- [패치 재구성](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/delivery-patch-verification.json)
- [보호 파일 대조](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/final-protection-verification.json)
- [원본 판정](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/runtime-cli-result.json)
- [원본 wire 원장](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/task-wire-journal.jsonl)
- [원본 실행 영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/launches/live-51f36c800a7646bcb47adbcb8127bbbf/launch-receipt.json)
- [후속 출력 계약 작업 명세](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-LIVE-OBSERVATION-01/run-20261014T014556Z-profile-fix-66f7e1b0/next-work.md)

lifespan은 off였습니다. full lifespan·광범위한 품질·반복 안정성·릴리스 기준은 검증하지 않았습니다. keep_alive=30m에 따라 모델이 postflight에서 메모리에 남은 원본 상태를 기록했고 강제 unload는 하지 않았습니다. pytest 설정 및 TestClient deprecation 경고, 초기 진단 일부의 원문 대신 전사 기록 한계도 보존했습니다. 커밋·푸시는 하지 않았습니다.
