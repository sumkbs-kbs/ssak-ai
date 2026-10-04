---
title: Root가 직접 사용한 CLI·HTTP 실행 기록
date: 2026-10-03
tags: [manual-qa, cli, http]
---

Full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, 최종 source manifest
SHA256 `0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa`.

CLI는 실제 생산 Typer app을 임시 홈으로 격리하여 별도 process로 실행했다.
`isolated_entry.py cli decision-eval --help` 종료0, sample-input 정상 종료0,
존재하지 않는 파일 입력 종료2를 직접 관찰했다. 오류 stdout은 비었으며 stderr는
generic 메시지만 포함했다. 출력 파일은 root-cli-help/report/error.*에 보존했다.

별도8018서버는 최종 생산 FastAPI app을 실제 uvicorn/socket으로 실행했다.
기존 인증 middleware·최종 router를 사용했고 lifespan은 끄고 임시 홈의 합성
TokenService bearer를 사용했다. 아래 요청은 실제 curl로 실행했다. Authorization은
0600 임시 header 파일로 전달했으며 문서나 명령 출력에 bearer를 표시하지 않았다.

| 요청 | 관찰 상태 | body artifact |
| --- | --- | --- |
| 인증+sample-input | 200 | root-http-report.json |
| 인증 없음+sample-input | 401 | root-http-unauth.json |
| 인증+NaN 확률, private marker 합성 ID | 422 | root-http-nonfinite.json |
| 인증+JSON 아닌 private marker 합성 문자열 | 422 | root-http-malformed.json |
| 인증+cases 빈 배열 | 200 | root-http-empty.json |

NaN/잘못된 JSON은 `Invalid decision evaluation input` 한 줄 detail만 반환했고
입력 marker를 포함하지 않았다. 빈 결과의 metrics 전부null 검사와 CLI/HTTP 전체
JSON 비교는 각각 jq true였다. sample 수계산 결과는 RESULTS.md에 기록했다.

실행 중이던 제가 만든 PID32914 서버를 명령까지 확인한 뒤 정상 종료하고 같은
localhost8000 명령으로 실행했다. OpenAPI 계약 오류 수정 반영 때 제가 실행한
PID56771의 명령도 확인한 뒤 같은 명령으로 재시작했다. 최종 PID64370의 startup complete와
실제 health200을 확인했다. OpenAPI의 새 request schema ref 검사 true,
새endpoint 인증 없음401도 확인했다. 오류 OpenAPI의 schema ref는
DecisionEvaluationInputError이고 detail은 필수string인 것을 실제 HTTP로 확인했다.
현재 서버는 유지하고 임시8018서버는 종료했다.
이 검증에서는 모델 질문이나 대화 품질 개선을 주장하지 않는다.
