---
title: oh-my-jev 비교 기반 확률 판단·검증 개선 실행 계획
date: 2026-10-03
completed: 2026-10-04
tags: [architecture, calibration, decision, benchmark, external-research]
---

# 방침과 비교 기준

현재 SSAK-AI 작업 폴더의 최신 파일을 기준으로 비교한다. 기존 Constitution,
Brain/Body 책임, Files-first·Git-first, 인증·사용자 데이터·qwen3.8 27.3B 선택과
모델 승격·도구 승인 정책을 유지한다. 외부 제품이나 모델을 자동 설치하지 않는다.

외부 코드 기준은 `iamupd/oh-my-jev`의
`c03c182013b64223a9b3a15095e85ef17c002b56`이다. 공개 소스를 임시 clone으로 읽고
지식 그래프에 인덱싱했다. 코드 Apache-2.0과 데이터셋·모델 조건을 분리한다.
SSAK-AI full HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`이며 기존 shared
수정이 있으므로 최종 판정은 실제 파일 해시로 함께 식별한다.

## 이번 실행 단계

| 단계 | 상태 | 인수 조건 |
| --- | --- | --- |
| 외부 소스·라이선스와 현재 확률/benchmark 경로 비교 | completed | 실제 함수·시험·고정 소스 근거로 이식 가능한 대상과 제한 확정 |
| 최소 개선을 기존 경로에 연결하고 실패→통과 회귀 확인 | completed | 확률과 휴리스틱 구분, 정확한 분모·근거, 기존 승인/승격 정책 보존 |
| 실행 표면 직접 QA와 관련 회귀 | completed | Root CLI/실제 HTTP 성공·오류·오류 OpenAPI 일치, 관련160회귀, 현재8000앱 반영 |
| 독립 검토·최종 분석·인수 체크리스트 확정 | completed | 같은 후보 해시의 독립2검토CLEAR; 문서·인수24항목 최종 교차 확인 |

분석 담당자는 외부 gateway/inference와 calibration/evaluation을 나누어 읽고,
현재 기능 지도 담당자는 기존 runtime·benchmark의 실제 호출 경로를 확인한다.
주 에이전트는 적용 대상 선택·통합·직접 QA와 최종 판정을 맡는다. 구현 담당자는
선정 후 지정한 파일만 소유하고 다른 담당자의 변경을 되돌리지 않는다.

증거 디렉터리: `docs/qa/2026-10-03-oh-my-jev-upgrade/`.
어떤 점수도 outcome-backed 측정 없이 보정된 확률로 표시하지 않는다. 확률 분포가
없는 기존 작업 기록은 calibration의 성공·실패 분모에 임의로 포함하지 않는다.

## 확정한 구현

외부 확률 판단의 평가 방식을 독립적인 typed benchmark로 도입한다. 기존 task
benchmark는 작업 실행·도구 성공을 측정하므로 해당 기록을 확률 입력으로 변환하지
않는다. 새 계산기는 인증된 `POST /api/benchmarks/decisions/evaluate`와
`agk decision-eval INPUT.json`에서 공통 사용한다. 자동 모델 호출·설치·학습·승격은
없으며, 결과의 calibration_status는 항상 unverified이다.

구현 계약과 담당 파일은 [IMPLEMENTATION_CONTRACT.md](../qa/2026-10-03-oh-my-jev-upgrade/IMPLEMENTATION_CONTRACT.md)에 기록한다.
주 에이전트는 분석 문서·통합 QA·독립 판정, 구현 담당 A는 모델·계산기·수치 경계
시험, 구현 담당 B는 API·CLI 연결과 경계 시험을 소유한다. 기존 파일 수정은
라우터 등록과 CLI 등록에 한정하며 수정 전 사본을 임시 디렉터리에 보존했다.
