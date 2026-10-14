---
title: TOOL-03 실제 인증 제품 스트림 독립 검수
tags: [ssak-ai, imp-09, independent-review, luna]
date: 2026-10-10
task_id: CODEX_REVIEW_IMP-09-B-TOOL-03-UVICORN-AUTH
verdict: APPROVED_SCOPED_LIVE
---

# 검수 결과

**APPROVED_SCOPED_LIVE**. `PASS_SCOPED_UVICORN_AUTH_LIFESPAN_OFF` 판정을 승인한다. 이 실행의 승인에 필요한 추가 수정은 없다. 실제 요청과 하네스를 재실행하지 않고 저장된 원문, 전송 기록, 실행 소스 및 영수증만 대조했다. [기계 판정](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-review-2026-10-10-tool03-live/review.json), [독립 대조 결과](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-review-2026-10-10-tool03-live/verification.json).

| 검수 경계 | 확인 결과 |
| --- | --- |
| 실제 전송 | 인증 제품 POST 1회 → 실제 Ollama `/api/chat` inference 1회. metadata 5회, Ollama 전체 HTTP 6회. 제품 내부 capability show는 0회이며 횟수를 맞추려고 호출하지 않음 |
| HTTP·SSE | 제품 200 / `text/event-stream`, upstream 200 / `application/x-ndjson`. 원문 28 frame, text/tool 블록 2개가 각각 정상 종료. message_start/delta/stop 각 1회 |
| 도구 의미 | JSON 조립 입력 `{"name":"bolts"}`, `lookup_part`, 비어 있지 않은 tool id, stop_reason=tool_use. upstream 텍스트와 제품 text delta가 일치하며 JSON fence에서 tool_use를 생성한 경로 |
| 실제 옵션 | model=qwen3.8, stream=true, think=false, num_predict=512, temperature=0. keep_alive=30m 원문 유지 |
| 호출 예산 | 예약·wire 진입·응답을 각각 대조. product/inference 각각 1회, retry·redirect·거부·추가 inference 없음 |
| 종료·정리 | 외부 launcher가 subprocess returncode 0을 관측. worker 0, 소유 Uvicorn 정상 종료 및 임시 auth 제거 확인. 내부 receipt의 null / NOT_OBSERVED는 보존 |
| 원문 무결성 | manifest 75개 크기·SHA 일치, 현재 source 28개 및 보호 파일 14개 일치. 독립 대조 65항목 통과 |
| 승인 소스 연결 | 승인 parent와 실행 사본은 task/run 출력 메타데이터를 정규화하면 AST 동일. task-binding.patch를 임시 폴더에서 재구성한 bytes도 실행 사본과 일치 |

실행 전 acceptance 동결 시각은 실제 제품·inference wire 진입보다 이르다. 보존된 self-check, Ruff, format, basedpyright, 메모리 compile 영수증은 실제 실행 harness SHA와 연결되며 모두 exit 0이다. 최초 format 실패 원문도 남아 있다. 기존 오프라인 회귀와 실제 모델 요청은 검수 중 반복하지 않았다.

# 완료 범위와 미완료

이번 TOOL-03의 인증된 외부 loopback HTTP, 실제 provider 연결, SSE lifecycle, 옵션 전달 및 tool bridge 계약은 검수 완료다. 과거 원문과 PENDING 기록은 덮어쓰지 않고 이 독립 검수 문서를 후속 판정으로 추가했다.

`lifespan=off`이며 worker에서 실제 auth/manager를 초기화한 범위다. native tool calling, 도구 실행, full lifespan, 외부 익명 요청의 거부, 로그인 flow, 일반 모델 품질 및 모든 설치 모델의 capability matrix는 이번 승인 범위에 없다. 익명 거부는 worker의 실제 인증 함수 사전 검사로 확인했다. upstream에는 native tool_calls가 없으므로 native 도구 지원을 검증했다고 기록하지 않는다.

전체 IMP-09=PARTIAL, ledger=NOT_RECOVERED, 역사적 TOOL-01/02·EM-01=FAIL은 유지한다. 미복구 원장을 이유로 완료된 TOOL-03을 다시 실행할 필요는 없다.

# 다음 작업

**IMP-09-C-MESSAGES-IMAGE-CONTRACT-01**: `/v1/messages`가 이미지 블록을 조용히 누락하는 경로를 오프라인 route 회귀로 재현하고, 추론 전에 typed HTTP 400으로 거절한다. 현재 [메시지 변환](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/messages_api.py:75)은 content를 문자열로 평탄화한다. [평탄화 함수](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/anthropic_tool_bridge.py:113)에는 image 분기가 없고, tool_result의 중첩 이미지도 text만 취한다. 이 근거는 정적 관찰이며, 새 API 실패는 다음 작업의 수정 전 테스트로 입증해야 한다.

이번 다음 작업은 Messages route의 지원 범위를 명확히 만드는 작은 수정이다. 전체 vision 모델 지원이나 이미지 인식 품질 판정을 포함하지 않는다. 제품에서 이미지가 지원되는 별도 표면은 별도 capability 항목으로 남는다.

[GPT-6 Luna 실행 프롬프트](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/ssak-ai-core/GPT6_LUNA_MESSAGES_IMAGE_CONTRACT_2026-10-10.md). 제품 소스·config·공용 원장·기존 증거는 이번 검수에서 수정하지 않았고 commit/push하지 않았다.
