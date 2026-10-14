# IMP-03-NATIVE-STREAM-TERMINAL-01 인계

상태: COMPLETE_OFFLINE / 독립 검수 PENDING. worker는 실제 HTTP·Ollama·모델 추론·서버 실행 및 commit/stage/push를 하지 않았습니다. root의 별도 controlled NDJSON 관측은 이 실행의 증거와 구분합니다.

## 구현 범위

native stream에서 error 키, JSON/UTF-8 해독 실패, done:true 없는 EOF는 NativeProtocolError로 실패합니다. pending native tool call은 완료 전 방출하지 않으며 tools가 있는 요청의 모든 content는 terminal까지 보류합니다. XML fallback에서도 원래 tools schema를 유지하여 불완전한 XML content가 ToolLoop로 먼저 전달되지 않습니다. done:true는 실제 boolean True로 판단합니다.

native stream은 safe_urlopen(max_retries=0)을 사용합니다. tools 없는 재전송은 opener가 genuine HTTP400이며 JSON error 문자열에 명시적 도구 미지원 문구가 있을 때만 1회 허용합니다. 해당 분기를 response 소비 앞에 한정했습니다. HTTP500/timeout/NDJSON 오류 및 EOF는 자동 fallback하지 않습니다. transport 예외는 기존 mutable NativeTransportError를 재사용합니다.

direct Chat SSE는 typed error event 후 return하며 [DONE]과 assistant 저장을 하지 않습니다. Messages SSE도 typed error event 후 return하여 오류 텍스트를 정상 message_stop으로 승격하지 않습니다. 정상 terminal의 응답은 유지합니다. ModelManager/ToolLoop 소스는 수정하지 않았으며 기존 실패 usage/실패 outcome 동작을 재사용합니다.

소유6파일: inference_providers.py, transport_errors.py, chat.py, messages_api.py, test_inference_providers.py, 새 test_native_stream_terminal_contract.py. 기존 provider tool-rejection 회귀는 RuntimeError 가짜 opener를 HTTPError400+JSON error body로 교정했으며 도구 제거 fallback/성공 XML 단언을 유지했습니다.

## 검증과 재현

실행 명령: `.venv/bin/python <이 폴더>/verify.py final-v3`. 실제 argv/cwd/종료 코드/시작·종료 소스 SHA는 final-v3/checks.json에 있습니다. 실행 소스6개는 final-v3/source/에 보존했습니다.

- final-v3/junit.xml: 101 passed, 실패/오류/skip0. 새 stream19 + 기존 direct21 + provider10 + structured36 + Messages streaming15.
- final-v3/focused.stdout/stderr: 원문. Starlette TestClient deprecation 경고1건을 유지했습니다.
- lint/format/types/compile stdout/stderr: 4개 검사 exit0. 타입 검사는 --level error이며 실제 출력 errors/warnings/notes 모두0.
- final-v3/socket-attempts.json: import 전에 connect/connect_ex/create_connection/bind/listen을 막은 cold 프로세스에서 물리 socket 시도0.
- final-v3/stream-captures/: 19개 사례의 원본 요청, upstream NDJSON hex 또는 예외 종류, usage, persistence, sleep 계수. 합계 counts.json. 공통 safe_urlopen은 실제 코드이고 urllib.request.urlopen 최종 sink만 mock입니다. fixture 메타데이터 조회는 별도 mock이며 추론 계수에 섞지 않습니다.
- ToolLoop4사례는 실제 ToolLoop→manager→provider→safe_urlopen을 통과합니다. incomplete native toolcall EOF는 read dispatch0, 완료 read1 이후 protocol error/timeout은 read 재실행0·총 provider2·실패 outcome을 단언합니다. read는 소유 tmp_path sentinel을 읽는 실제 함수이며 파일 내용은 그대로 유지합니다. 주변 orchestrator context/guardrail은 기존 mock fixture이며 실제 운영 lifecycle 검증은 아닙니다.
- task-only.patch는 시작 dirty preimage5개+신규test 기준입니다. patch-reconstruction.json은6개 파일을 재구성하여 현재 바이트/SHA 일치를 확인합니다. 기존 direct evidence/테스트 파일은 수정하지 않았습니다.

## 과거 실패와 한계

red-junit.xml: 12 failed/1 passed. 초기 Messages2건은 max_tokens 누락으로 route 검증400에서 멈췄으므로 provider 실패 재현으로 계산하지 않습니다. 나머지10개는 목표 실패 경계를 드러냈습니다. 초기test 별도 source snapshot은 없으며 최종test와 동일 source-bound red라고 주장하지 않습니다. production 시작 preimage는 보존했습니다.

candidate-v1-junit.xml:19 passed/6 failed. response contextmanager의 __enter__ 결과 사용 누락4건과 Messages max_tokens fixture 누락2건을 수정했습니다. candidate-v2-junit.xml은27 passed였으며 이후 정상 SSE 및 캡처를 보강한 최종 source는 final-v3입니다. 실패 원문은 보존했고 최종 성공 검사는 추가 반복하지 않았습니다.

일반 non-tool stream은 실패 전 일부 텍스트가 전달될 수 있으나 성공 종료/저장은 하지 않습니다. 모든 provider·모든 에이전트 UI의 오류 이벤트를 통일하는 작업, 전체 suite, 실제 auth/lifespan 및 실제 모델 품질은 범위 밖입니다. 모의 ToolLoop의 실패 outcome은 실제 전체 agent SSE 운영 검증과 구분합니다.
