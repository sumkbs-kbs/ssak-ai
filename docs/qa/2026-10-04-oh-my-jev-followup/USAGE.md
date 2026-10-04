---
title: SSAK-AI decision diagnostics usage
date: 2026-10-04
tags: [usage, benchmark, decision, uncertainty]
---

기존 확률 평가 명령에 정확도 구간과 태그별 진단이 추가되었다. 이 명령은
입력에 제공된 확률을 계산하며 LLM을 호출하지 않는다.

프로젝트 루트에서 활성 환경의 실제 명령으로 실행한다:

```sh
.venv/bin/agk decision-eval docs/qa/2026-10-04-oh-my-jev-followup/manual-cases.json
.venv/bin/agk decision-eval --help
```

QA에서는 개인 설정/저장소 접근을 분리한 기존 launcher로 같은 Typer 명령을
직접 실행했다. 일반 실행과 QA launcher의 구분은 RESULT.md에 기록한다.

기존 보호 API는 `POST /api/benchmarks/decisions/evaluate`이며 인증된 bearer
토큰이 필요하다. PIN이나 토큰을 평가 JSON 안에 넣지 않는다.

입력 사례의 기존 `probabilities`, `expected_key`, `underdetermined` 필드는
유지한다. 예측과 오류 사례 모두 선택적인 `tags` 문자열 배열을 받을 수 있다.
태그는 사례당 최대16개, 중복 없이 각각1~128자이며 공백만으로 구성될 수 없다.
생략하거나 `[]`로 보낸 태그는 기존 입력 fingerprint를 유지한다.

출력 `metrics.accuracy_interval`은 `method`, `confidence_level`, `z`, `n`,
`successes`, `lower`, `upper`를 담는다. 채점 가능한 사례가 없으면 null이다.
예시6건 중 확률 합 오류1건, 오류 응답1건, 무라벨1건, 선택지에 없는 정답1건은
정확도 채점에서 제외되므로 n=2이다. 1건 정답으로 정확도는50%지만 Wilson
95% 구간은 약9.45~90.55%이다. 표본이 작다는 한계를 함께 볼 수 있다.

`tag_diagnostics.groups`의 각 태그는 같은 집계 규칙을 사용하는 독립적인
보기이다. 전체 태그 수와 생략 수를 표시하고, 사례 수가 큰 순서 및 태그 이름
순서로 최대25개 그룹을 반환한다. 소수 표본과 모든 사례에 붙인 태그도 남긴다.

전체 예시와 `routing` 태그는 채점한2건이 같아 정확도/ECE/Brier/NLL/구간이
같다. 그러나 그룹의 유효률·오류율은 그 그룹의 사례 수를 분모로 삼아 전체와
다를 수 있다. 태그가 겹치므로 그룹별 건수를 더해 전체 표본 수로 쓰지 않는다.

이 결과는 제공된 표본의 관측치다. 모델 보정 상태는 계속 `unverified`이며,
독립 holdout 측정·미래 성능 보장·다중 비교 보정·도구 실행 승인을 의미하지
않는다. 실제 Qwen 답변의 정확도를 측정하려면 먼저 해당 모델의 확률과 정답
라벨을 안전하게 수집하는 별도 계약과 평가 데이터가 필요하다.
