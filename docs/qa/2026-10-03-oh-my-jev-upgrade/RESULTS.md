---
title: oh-my-jev 분석 기반 확률 판단 평가 개선 최종 결과
date: 2026-10-03
completed: 2026-10-04
tags: [qa, benchmark, calibration, release-evidence]
---

## 적용 결과

선택지별 확률의 정확도와 과신을 측정하는 기능을 SSAK-AI에 추가했다. 동일한
typed 계산기를 `agk decision-eval INPUT.json`과 인증된
`POST /api/benchmarks/decisions/evaluate`에서 사용한다. 기존 root CLI와 실제
생산 API router에 등록했으며 `/docs`의 benchmarks 태그에서도 발견할 수 있다.

새 report는 정확도, ECE와 15개 reliability bin, multiclass Brier, NLL,
경험적 risk별 selective coverage, 정보 부족 사례의 과신 진단을 제공한다.
정답이 없는 사례·선택지 밖 정답·실행 오류·합계 불일치를 구분하고 모든 scored
지표의 분모를 통일했다. 동일 confidence는 묶어서 cutoff를 결정하며 argmax
동률은 key 사전순으로 처리한다. 확률이 아닌 휴리스틱 점수를 자동 변환하지 않는다.

유한성·숫자 범위·길이·중복·입력 크기를 검사한다. 오류에는 입력 원문이나
provider 오류를 반사하지 않는다. report의 출처는 provided_probabilities,
보정 상태는 unverified이며 입력 SHA256과 요청자가 제공한 모델/데이터 식별자를
남긴다. 기존 Constitution·Brain/Body·승격·도구 승인·Qwen 선택 정책은 변경하지 않았다.

## 코드와 후보 식별

외부 분석 기준: `iamupd/oh-my-jev`
`c03c182013b64223a9b3a15095e85ef17c002b56`.
SSAK-AI full HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
공유 미커밋 변경을 보존했으며 Git commit/staging/branch 조작은 하지 않았다.
최종 소스8파일 manifest [source.sha256](source.sha256)의 SHA256은
`0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa`다.

| 파일 | 역할 |
| --- | --- |
| engine/decision_evaluation_models.py | bounded 불변 request/report와 prediction/error union |
| engine/decision_evaluation.py | 공통 수치 계산과 근거 집계 |
| decision_evaluation_cli.py | 2MiB bounded JSON 입력·출력·안전한 오류 |
| api/routes/decision_evaluation_api.py | typed API와 endpoint 한정422 경계·명시적 오류 OpenAPI 계약 |
| cli.py, api/routes/__init__.py | 기존 파일에 각각 import와 등록2줄 추가 |
| tests/test_decision_evaluation.py, tests/test_decision_evaluation_surfaces.py | 새 기능71개 검증 |

이전 후보와 초기 검사 이력은 [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md)에 구분했다.

## 검증 결과

| 실행 | 결과 | 근거 |
| --- | --- | --- |
| 새 계산기 경계·수치 검증 | 50통과 | worker-a-green.txt |
| 실제 등록 API·CLI 표면 검증 | 21통과 | worker-b-openapi-green.txt |
| Root 최종 관련 합본 회귀 | 160통과, 실패0 | root-openapi-final-regression.log |
| Ruff: 변경 소스·시험·QA helper10파일 | 통과 | root-frozen-ruff.log |
| 무필터 basedpyright: 새4모듈·새2시험·QA2helper | 오류0, 경고0 | root-frozen-types.log |
| LSP: 변경 소스·시험8파일 error 진단 | 모두 없음 | root-lsp.md |
| 독립 계산기 검토 / API·CLI 검토 | 둘 다 CLEAR / APPROVE | engine-review.md, surface-review.md |
| Root CLI 직접 사용 | help0 / 정상0 / 읽기 오류2 | root-cli-help.txt, root-cli-report.json, root-cli-error.*.txt |
| Root 최종 실제 HTTP | 정상200 / 인증 없음401 / NaN422 / 잘못된 JSON422 / 빈 입력200 | root-http-*.json, root-manual-qa.md |
| OpenAPI 오류 계약 | 실제422 필수string detail와 문서 모델 일치 | worker-b-openapi-red/green.txt, root-http-openapi.json, root-main-openapi.json |
| 현재8000앱 | 재시작·health200·새typed route등록·인증 없음401 | root-main-*.json |

합본 목록은 decision_evaluation 두 시험 외에 model_calibration,
runtime_benchmark_binding, benchmark_metrics, confidence_evaluator,
finetune_evaluation_gate, cli_smoke, auth_policy_truth_table이다.
실행 명령은 `isolated_entry.py pytest -q` 뒤에 각 `tests/test_*.py`를 지정한다.
Path.home을 collection 전에 격리하고 CLI subprocess도 임시 sitecustomize로
격리했다. 기존 CLI의 Ollama 발견 시험은 로컬 접속 허용이 필요했다. 초기
샌드박스 제한은 재실행으로 해소했고 제품 코드나 시험 기대값을 약화하지 않았다.
새 공개 OpenAPI 회귀가 기존의 다른 라우트 operation ID 중복 경고11건을
드러냈다. 기존 Starlette/httpx 도구 폐기 예정 경고1건을 합쳐12경고이며 실패는
없다. 이 변경과 무관한 기존 라우트의 중복 operation ID는 수정하지 않았다.

## 직접 수계산과 실행

[sample-input.json](sample-input.json)의7개 합성 사례는 scored2, 정답 없음2,
선택지 밖 정답1, 합계 오류1, 실행 오류1로 나뉜다. 정확도0.5,
ECE0.4, Brier0.4, NLL0.5697171415941824다. risk_budget0.05에서
선택 수1·confidence cutoff0.8·coverage0.5·경험적 risk0이다.
정보 부족 사례는0.95 confidence로 별도 과신 진단에 집계된다.
CLI와 HTTP의 JSON report 전체가 동일한지 `jq -e -s '.[0] == .[1]'`로 확인했다.
빈 입력은 모든 평가 점수null, 잘못된 입력은 generic422를 반환했다.

최종 임시 HTTP는 생산 app·라우팅·bearer 인증을 실제 socket으로 사용했다.
lifespan은 끄고 모델·배경 작업을 시작하지 않았다. 합성 인증 파일은 임시 홈에
0600으로 만들고 검증 서버 종료 후 제거했다. 현재 앱은 PID64370,
127.0.0.1:8000에서 정상 실행 중이다. 사용자 인증이나 모델 설정은 변경하지 않았다.

## 범위와 제한

이번 검증은 평가 기능의 수학·입력 경계·실행 연결을 확인한 것이다. 실제 Qwen
정확도 개선이나 모델 보정 학습 완료를 의미하지 않는다. 외부 추론/학습 backend는
CUDA·provider 계약·데이터 조건이 달라 이식하지 않았다. 독립 holdout과 실제
선택지별 확률 계약이 마련되면 추가 보정을 검토할 수 있다. API 입력 식별 정보도
서버가 모델 실행 여부를 인증한 근거가 아니다. 전체 저장소의 모든 기존 기능을
이번에 다시 시험했다고 주장하지 않는다.

사용법: [USAGE.md](USAGE.md). 정밀 분석: [REPOSITORY_ANALYSIS.md](REPOSITORY_ANALYSIS.md).
발견한 API 문서 계약 오류의 실패→통과와 직접 실행·정리 근거는
[openapi-runtime-audit.md](openapi-runtime-audit.md)에 기록했다.
인수 항목: [CHECKLIST.md](CHECKLIST.md). 단계 계획:
[OH_MY_JEV_UPGRADE_2026-10-03.md](../../ssak-ai-core/OH_MY_JEV_UPGRADE_2026-10-03.md).
