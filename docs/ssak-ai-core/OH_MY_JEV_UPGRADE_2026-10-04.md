---
title: oh-my-jev 후속 분석과 평가 해석 개선 계획
date: 2026-10-04
tags: [architecture, decision, benchmark, uncertainty, external-research]
---

## 기준과 방침

오늘 공개 Git remote와 임시 clone에서 확인한 upstream HEAD는
`c03c182013b64223a9b3a15095e85ef17c002b56`으로 이전 분석과 같다.
SSAK-AI는 현재 공유 작업 폴더를 기준으로 하며 기존 Constitution·Brain/Body,
Files-first·Git-first·인증·모델 선택·도구 승인·모델 승격 정책을 유지한다.
이전 완료된 typed decision-eval 기능과 검증 문서는 수정해서 재사용하지 않는다.

원본의 Wilson 정확도 구간과 태그별 진단을 참고하여 기존 평가기를 보완한다.
실제 Qwen의 logits/probabilities 계약과 독립 labeled holdout이 없는 상태에서
추론 backend·학습·온도 보정·자동 승인 연동을 추가하지 않는다. 외부 코드·데이터·
모델·패키지를 설치하거나 복사하지 않고 수학적 지표를 독립 구현한다.

## 실행 단계

| 단계 | 상태 | 결과 및 인수 조건 |
| --- | --- | --- |
| upstream 최신 SHA와 기존 반영 범위 확인 | completed | 이전 커밋 동일; 원본 통계·태그·confidence 의미 및 한계 조사 |
| typed 신뢰구간·태그 진단 계약과 계산기 구현 | completed | engine 87시험 통과; Wilson·공통 그룹 집계·기존 fingerprint 회귀 유지 |
| 기존 API·CLI의 새 응답과 입력 경계 확인 | completed | 표면 신규29시험 통과; 무필터 타입 경고 해결; 기존 인증/안전한 오류/OpenAPI 유지 |
| Root 직접 CLI 사용·품질 검증·독립 검토 | completed | 직접CLI 성공·입력오류·help; 최종137시험·타입·lint 통과; 독립 검토2PASS 및 서버 재실행 |

Root는 방향·계약·통합 검증과 최종 판정을 맡는다. 계산기 담당은 engine의
decision_evaluation 모델·계산기·통계 helper·전용 시험을 소유한다. 표면 담당은
API/CLI 관련 시험만 소유한다. 담당자는 다른 shared 변경을 되돌리지 않는다.

구현 계약과 이번 증거는 `docs/qa/2026-10-04-oh-my-jev-followup/`에 기록한다.
95% Wilson 구간은 독립 Bernoulli 관측의 비율을 설명하는 구간이며, 데이터의
독립성이나 미래 성능을 인증하지 않는다. 태그별 집합은 겹칠 수 있고 다중 비교
보정은 하지 않는다. empirical selective risk·calibration_status=unverified를
유지하며 어떤 구간도 승인/승격의 안전 보장으로 사용하지 않는다.

최종 체크리스트·한계·재현 증거는
`docs/qa/2026-10-04-oh-my-jev-followup/RESULT.md`, 사용법은 같은 폴더의
`USAGE.md`에 있다. 이 요청 범위는 완료되었으며 전체 프로그램·실제 모델
품질·차단된 브라우저 검증의 완료 판정으로 확대하지 않는다.
