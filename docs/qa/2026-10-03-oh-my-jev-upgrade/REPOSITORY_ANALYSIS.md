---
title: oh-my-jev 실제 코드 비교와 SSAK-AI 적용 판단
date: 2026-10-03
tags: [external-research, architecture, benchmark, calibration]
---

## 비교 기준과 결론

외부 소스는 [iamupd/oh-my-jev](https://github.com/iamupd/oh-my-jev/tree/c03c182013b64223a9b3a15095e85ef17c002b56)의
`c03c182013b64223a9b3a15095e85ef17c002b56`을 clone하고 그래프 인덱싱한 뒤
gateway·backend·benchmark·calibration·training·시험을 나누어 읽었다. README의
기능 주장만으로 SSAK-AI 모델 성능 개선을 판정하지 않았다. SSAK-AI 기준은 현재
공유 작업 파일과 full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`이다.

이 프로젝트는 선택지별 확률을 반환하는 판단 도구다. 핵심 이식 대상은 판단의
정확성과 확률의 과신을 구분해 측정하는 평가 방식이다. SSAK-AI의 기존 작업
benchmark는 실행 성공·도구 정확도·복구·비용을 측정한다. 자체 confidence 추정은
선택지별 확률과 정답을 가진 데이터셋의 보정 결과가 아니다. 따라서 기존 점수를
확률처럼 변환하지 않고, 실제 확률 분포를 제공받는 별도 benchmark를 연결한다.

## 기능별 검토

| 외부 코드 | 실제 구현과 SSAK-AI 차이 | 이번 반영 |
| --- | --- | --- |
| [bench/metrics.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/metrics.py) | 합계 허용 오차, ECE, multiclass Brier, NLL, selective coverage, 정보 부족 과신 진단을 계산한다. SSAK-AI 작업 report에는 대응 확률/정답 필드가 없다. | typed 확률 평가기와 동일 계산기를 사용하는 API·CLI 추가 |
| [backends/base.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/backends/base.py) | RawAnswer는 logits/probs 배타성·길이·yes/no key 순서를 검사하지만 유한성·음수·중복 key 전체를 검증하지 않는다. | 유한 숫자·범위·일대일 길이·중복 ID/key를 입력 경계에서 검사 |
| [gateway/app.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/gateway/app.py), [gateway/calibration.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/gateway/calibration.py) | backend가 logits를 제공하면 온도 보정을 적용한다. 이미 확률인 출력은 임의 역산하지 않는다. calibrated flag/metadata가 전체 검증 근거를 대신하지는 않는다. | caller 확률 출처·입력 SHA256·unverified 상태를 report에 보존. 자동 보정·승격하지 않음 |
| [backends/mock.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/backends/mock.py) | state와 선택지의 토큰 겹침을 logits로 만든 시험용 backend다. | 알고리즘 시험은 합성 입력으로 검증하되 모델 정확도 향상으로 보고하지 않음 |
| [backends/semif.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/backends/semif.py) | 선택지에 대응하는 단일 토큰 label과 마지막 위치 logits를 이용한다. 현재 SSAK-AI Qwen/Ollama 호출 계약과 플랫폼 조건이 다르다. | 추론 backend를 복사하거나 현재 모델을 교체하지 않음 |
| [bench/temperature.py](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/temperature.py), training, benchmark order·KO/EN pair | 별도 fit/eval 분리와 순서·언어 민감도 평가의 방향은 유용하다. 실제 모델 logits와 독립 holdout·provenance가 있어야 적용 의미가 있다. | 후속 도입 조건만 문서화; 이번 결과를 학습·보정 성능 판정으로 사용하지 않음 |

## 원본의 약점을 그대로 옮기지 않은 부분

원본 metrics의 accuracy/ECE는 expected가 존재하는 행을 사용하지만 Brier/NLL은
expected key가 실제 선택지에 없으면 건너뛴다. 이 경우 분모가 달라질 수 있다.
이번 계산기는 정확도·ECE·Brier·NLL에 같은 scored 집합을 사용하고 빠진 truth를
별도 집계한다. 실행 오류, 정답 없는 사례, 합계 불일치는 각각 카운트로 노출한다.

원본 selective coverage는 동일 confidence 안에서 개별 행 순서에 따라 prefix를
선택할 수 있다. 이번 구현은 같은 confidence 전체를 묶어 cutoff를 평가한다.
argmax 동률도 선택지 순서 대신 key의 사전순으로 결정하고 동률 건수를 표시한다.
빈 집합의 평가 점수는 null이며 ‘오차 0’ 또는 ‘100% 검증됨’으로 표현하지 않는다.

허용 오차 strict 1e-3 / lenient 2e-2, ECE 15구간, NLL floor 1e-15를 명시한다.
lenient-valid는 진단용이고 점수에는 strict-valid만 사용한다. 합계가 잘못된
분포를 균등 분포로 바꾸거나 normalize하여 성공 기록으로 만들지 않는다.
검증 오류 응답은 입력 원문·provider 오류·자격증명을 되돌려주지 않는다.

[README의 제한](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/README.md#known-limitations)도
직접 확인했다. 로컬 추론은 CUDA 조건으로 macOS를 지원하지 않으며, training의
혼합 question 종류는 choice 온도를 공유한다. compare의 근사 표시는 통계적
유의성 검정이 아니고, 번들 reference 수치도 특정 시점의 결과다. 따라서 현재
Apple Silicon·Qwen/Ollama 환경에 모델 실행·학습 경로를 그대로 통합하지 않았다.

## 라이선스와 도입 범위

[LICENSE](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/LICENSE)는 Apache-2.0이며,
[THIRD-PARTY.md](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/THIRD-PARTY.md)는
데이터셋·모델 조건을 별도로 명시한다. 이번 코드는 수학적 지표를 SSAK-AI의
Pydantic·표준 라이브러리로 독립 구현한다. 외부 코드·데이터셋·모델 가중치나
의존성 전체를 vendoring하거나 재배포하지 않는다.

## 후속 도입 조건

실제 provider의 선택지별 logits/probabilities 계약, 모델·tokenizer·backend·버전
식별, fit/eval 데이터의 중복 없는 분리, 데이터 사용 조건, 독립 holdout 검증이
준비되면 온도 보정과 한/영·선택지 순서 민감도 평가를 추가할 수 있다. 그 전에는
측정된 경험적 risk를 승인 보장으로 해석하지 않는다. 현재 Qwen 대화 품질 향상이나
학습 완료는 이 변경의 검증 대상이 아니다.
