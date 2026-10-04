---
title: SSAK-AI 선택지 확률 평가 사용법
date: 2026-10-03
tags: [usage, benchmark, calibration]
---

## CLI

저장소 루트에서 설치된 CLI로 실행한다.

```sh
.venv/bin/python .venv/bin/agk decision-eval --help
.venv/bin/python .venv/bin/agk decision-eval docs/qa/2026-10-03-oh-my-jev-upgrade/sample-input.json
```

성공하면 stdout에 JSON report를 출력한다. 파일은 UTF-8 JSON, 최대 2MiB다.
읽기·형식·스키마 오류는 안전한 stderr 메시지와 종료 코드 2를 반환한다. 사용자
저장소를 쓰지 않는 검증 실행은 `isolated_entry.py cli decision-eval INPUT.json`을
기존 `.venv/bin/python`으로 실행할 수 있다.

## HTTP

생산 API는 `POST /api/benchmarks/decisions/evaluate`다. 기존 로그인으로 발급된
bearer를 사용한다. 토큰을 보고서·채팅·저장소에 기록하지 않는다. request/response
스키마는 실행 앱의 `/docs`에서 benchmarks 태그로 확인할 수 있다. JSON body는
CLI와 같고 인증 없음은401, 잘못된 입력은 원문 없이422, 정상 입력은200이다.

## 입력과 해석

[sample-input.json](sample-input.json)은 합성 수계산 예시이며 모델 결과가 아니다.
각 prediction은 고유 case_id, status=prediction, 2..64개 고유 options key,
같은 개수의 probabilities를 넣는다. 확률은 유한한 숫자 0..1이어야 한다.
expected_key는 정답 key다. 선택지에 없는 정답과 정답이 없는 사례는 공통 평가
분모에 들어가지 않으며 카운트로 구분한다. 실행 오류는 status=error와
error_code(provider_error/timeout/invalid_response)로 기록한다.

underdetermined=true는 정답이 확정되지 않은 사례이며 expected_key와 함께
쓸 수 없다. 이 사례의 큰 confidence는 정확도 실패로 조작하지 않고 별도
과신 진단으로 보여준다. 요청은 최대1,000사례, key/식별자는 최대128문자다.
model_id/dataset_id는 요청자가 제공한 식별 정보이지 서버가 검증한 attestation이 아니다.

| 출력 | 의미 |
| --- | --- |
| accuracy | 공통 scored 집합의 top-label 정확도 |
| ece, ece_bins | 15개 confidence 구간의 정확도-확신 차이와 실제 표본 수 |
| brier | 사례별 multiclass 제곱 오차 합의 평균; 선택지 수로 나누지 않음 |
| nll | 정답 확률의 평균 음의 자연로그; 0확률 floor=1e-15 |
| strict_valid_rate / lenient_valid_rate | predictions 분모; 합계 오차1e-3/2e-2. lenient는 진단용 |
| selective_coverage | 동일 confidence를 묶은 cutoff의 경험적 risk·선택 수·coverage |
| underdetermined | strict-valid 정보 부족 사례의 최대 확률·0.9이상 비율·균등 대비 편차 |
| input_sha256 | 기본값을 포함한 정규 JSON 입력의 SHA256; 서식 차이를 제거한 재현 식별자 |

빈 평가의 점수는 null이다. 같은 확률 동률은 key 사전순으로 결정되고 카운트에
표시된다. coverage는 요청 데이터에서 측정한 값이며 미래 정확성이나 도구 실행
승인을 보장하지 않는다. 출력은 항상 provided_probabilities / unverified이고
모델 선택·승격·학습·기존 task 성공률에 자동 적용되지 않는다.

## 재현

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q tests/test_decision_evaluation.py tests/test_decision_evaluation_surfaces.py
```

전체 실행 목록과 조건은 [RESULTS.md](RESULTS.md), 인수 항목은
[CHECKLIST.md](CHECKLIST.md)에 기록한다. 새 데이터로 모델 보정을 주장하려면
별도 holdout·provider 확률 계약·provenance 검증이 추가로 필요하다.
