---
title: 확률 판단 평가 API 오류 계약 실행 감사
date: 2026-10-04
tags: [debugging, runtime-audit, openapi, qa]
full_head: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
source_manifest_sha256: 0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa
verdict: PASS
---

## 관찰한 오류와 원인

Root가 실제 실행 중인 생산 app의 `/openapi.json`을 읽었을 때 새 평가 API의
422 문서는 `#/components/schemas/HTTPValidationError`를 참조했다. 이 기본
모델의 detail은 배열이지만 실제 잘못된 JSON/NaN 요청에는
`{"detail":"Invalid decision evaluation input"}`라는 문자열 detail이 반환됐다.
실행 오류를 안전하게 처리하는 endpoint 전용 handler에 명시적 응답 모델이 없어
FastAPI의 기본 오류 문서가 남은 것이 원인이다. 수정 전 문서는
[root-main-openapi-before-fix.json](root-main-openapi-before-fix.json)에 보존했다.

검토한 가설은 세 가지다. 명시적 오류 모델 누락은 공개 문서와 실제 응답의
불일치로 확인했다. 오래된 서버 가설은 수정 전에도 새 소스로 재시작한 서버였고
정상 요청/report 모델이 최신 코드와 일치하여 원인에서 제외했다. 중복 라우터나
전역 handler 가설은 생산 경로의 단일 등록과 endpoint 전용 오류 처리, 동일 경로를
통과하는 회귀 시험으로 제외했다. 인증·PIN·provider·사용자 데이터의 문제로
해석하지 않았다.

## 최소 수정과 실패→통과

불변 `DecisionEvaluationInputError` 모델에 필수 문자열 detail을 선언하고 새
endpoint의 `responses[422]`에 연결했다. 오류 handler는 같은 모델을 직렬화한다.
기존 422 상태와 generic 메시지는 유지하며 입력 원문을 반환하지 않는다.
전역 오류 handler나 기존 라우터의 응답 계약은 변경하지 않았다.

- 수정 전 공개 계약 회귀: [worker-b-openapi-red.txt](worker-b-openapi-red.txt),
  오류 모델 불일치로 1실패.
- 수정 후 표면 회귀: [worker-b-openapi-green.txt](worker-b-openapi-green.txt),
  같은 공개 계약 회귀를 포함해 21통과.
- 최종 관련 합본: [root-openapi-final-regression.log](root-openapi-final-regression.log),
  새71개와 기존89개, 총160통과·실패0.

이 근거는 먼저 실패한 시험과 수정 후 통과의 비교다. 수정 코드를 다시 되돌리는
세 번째 실행은 하지 않았으며 그런 재현을 수행했다고 주장하지 않는다.
시험의 기존 12경고는 Starlette/httpx 경고1개와 다른 라우트의 중복 operation ID
11개이며 이번 수정 범위 밖이다.

## 실제 실행 표면과 정적·독립 검토

Root는 최종 소스로 실제 uvicorn/socket의 생산 app을 임시 localhost8018에서
실행하고 합성 bearer 인증을 사용했다. 정상200·인증 없음401·NaN422·잘못된
JSON422·빈 입력200을 직접 관찰했다. 최종 오류 문서는
`#/components/schemas/DecisionEvaluationInputError`를 참조하며 detail은 필수
string이다. 실제 문서의 ref/type/required 검사는 jq true였다. 현재8000 앱에서도
같은 오류 스키마와 health200·인증 없음401을 확인했다.

근거: [root-http-openapi.json](root-http-openapi.json),
[root-main-openapi.json](root-main-openapi.json),
[root-manual-qa.md](root-manual-qa.md). CLI 성공 report와 HTTP report의 JSON 전체
비교도 jq true였다. 임시 서버는 lifespan을 끄고 모델·배경 저장소를 시작하지 않았다.
OpenAPI JSON 증거는 전체 앱 문서에서 평가 route와 오류 schema만 추출한 것으로,
최상위 `evaluation_route`와 `error_schema` 필드를 사용한다.

Ruff는 [root-frozen-ruff.log](root-frozen-ruff.log)에서 통과했으며 무필터 타입 검사는
[root-frozen-types.log](root-frozen-types.log)에 0오류·0경고·0note로 기록됐다.
변경8파일 LSP error 진단은 [root-lsp.md](root-lsp.md)에서 모두 없음이다.
같은 full HEAD와 최종 소스 manifest에 바인딩된 독립 engine/표면 검토는 각각
CLEAR / APPROVE다. 정확한 보고서 해시와 판정은
[EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md)에 기록했다.

## 정리와 판정 범위

Root 소유 임시8018 서버는 해당 실행 session의 Ctrl-C로 정상 종료했고 0600
합성 인증 header 파일은 제거 후 존재하지 않음을 확인했다. 현재 앱 PID64370은
127.0.0.1:8000에서 유지한다. 이 진단을 위해 만든 `.debug-journal.md`의 가설과
결과는 이 감사 문서로 보존하고 임시 journal만 제거했다.

breakpoint·debugpy·pdb·trace·임시 debug flag는 추가하지 않았다. 새 생산4모듈의
debug marker 검색은 일치 항목이 없었다. raw 앱 로그나 실제 JWT/PIN은 출력하거나
증거에 복사하지 않았다. Git HEAD와 기존 공유 수정은 보존했고 staging·commit·
branch·`.git/info/exclude`를 변경하지 않았다.

PASS는 명시한 소스 후보의 오류 응답/문서 계약, 경계 회귀와 직접 실행에 한정한다.
실제 모델의 정확도 상승이나 보정 완료를 의미하지 않는다.
