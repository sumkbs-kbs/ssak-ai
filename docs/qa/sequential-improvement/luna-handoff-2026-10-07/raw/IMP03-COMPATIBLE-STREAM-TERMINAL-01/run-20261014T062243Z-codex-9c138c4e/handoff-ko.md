# IMP-03-COMPATIBLE-STREAM-TERMINAL-01 인계

판정: **COMPLETE_OFFLINE / 독립 검수 PENDING**. 실제 HTTP·모델·Ollama·Uvicorn 실행은 worker 범위에서 0회이며, parent가 소유하는 별도 controlled-wire 관측과 합산하지 않는다.

## 변경과 경계

`inference_providers.py`의 공통 OpenRouter/LMStudio SSE 경계에서 Pydantic strict 모델로 소비할 content·tool delta를 파싱한다. 오류 프레임과 `finish_reason:error`는 `upstream_stream_error`, JSON/UTF-8/소비 필드 위반은 `invalid_stream`, `[DONE]` 없는 EOF는 `incomplete_stream`으로 기존 `NativeProtocolError`를 전파한다. nullable content, 문자열 도구 인자 조각, 주석, 여러 data 줄에 걸친 JSON, 반복 finish_reason usage 프레임은 유지한다. 기존 fixture 및 호환 endpoint의 빈 줄 없는 완성 JSON data 줄도 계속 허용한다.

tools가 제공된 호출은 텍스트/XML도 `[DONE]`까지 보류한다. native tool delta는 문자열 조각으로 모으고 tool_calls finish와 DONE 확인 뒤 인자를 JSON 객체로 검증한 후 방출한다. 오류나 불완전 EOF에 따른 자동 재시도는 없다. 정상 `[API Error]` 문자 답변은 그대로 정상 답변이다.

`chat.py`와 `messages_api.py`에는 direct nonstream `NativeProtocolError`의 안전한 typed 502 매핑만 각각 2줄 추가했다. 기존 dirty API refactor는 preimage에 보존했으며 이번 task-only patch에 섞지 않았다. 기존 manager 실패 usage 기록과 SSE typed catch를 재사용했다.

OpenAI-compatible 공통 메서드를 상속하는 기타 provider에는 같은 구현이 적용되지만 이번 제품 fixture는 등록된 LMStudio/OpenRouter에 한정한다. Nim/Gemini 등의 별도 override, Anthropic SDK, MLX, Ollama compatible nonstream JSON 의미 검증, combo의 기존 문자열 heuristic은 이번 검증 범위 밖이다. Ollama native NDJSON 계약은 별도 구현 그대로 두고 인접 회귀로만 확인했다.

## 실행·검증 근거

재현 및 후보의 정확한 subprocess argv/cwd/exit는 각 `checks.json`, 원문은 `focused.stdout`/`focused.stderr`와 `junit.xml`, 실행 전 소스는 `source/`에 있다. 테스트 도중 소스 SHA는 시작·종료 동일하다.

- `red-v1/`: 수정 전 40 실패/115 통과. 오류 프레임의 성공 승격, 잘못된 필드, 불완전 EOF 및 ToolLoop dispatch 문제를 재현했다. 초기 lint/format 실패도 보존했다.
- `final-v1/`: 최초 수정 155 통과와 정적 검사 통과. 이후 추가 경계 사례 때문에 최종 근거로는 아래 v3를 사용한다.
- `final-v2/`: malformed tool 구조 및 textual XML 보류 추가 후 175 통과.
- `direct-red-v1/`: 새 direct nonstream mapping만 `FOCUSED_K=nonstream_protocol`로 선택해 12 실패/175 deselected. 이 환경값은 `selector-environment.json`에 별도로 기록했다. API 변경 전 HTTP 500/529였던 응답 원문을 보존했다.
- **`final-v3/`: 187 passed, 실패/오류/skip 0.** 새 계약 78개와 기존 compatible transport/native stream/native direct/provider 회귀 109개다. Ruff lint/format, basedpyright 오류 수준, 메모리 compile 모두 exit 0. pytest 기존 asyncio_mode 설정 경고 1개는 그대로 남았다.

최종 호출 명령은 저장소 cwd에서 `.venv/bin/python <이 실행 폴더>/verify.py final-v3`였다. 이 폴더는 이미 존재하므로 재실행 대상으로 사용하지 않는다. cold wrapper는 production import 전에 물리 socket connect/bind/listen을 차단하고 pytest_asyncio 플러그인을 명시한다. 이전 성공 검사의 반복 실행이 아니라 후보별 변경에 대한 검증이다.

## 시나리오별 관측

| 시나리오 | 관측 | 아티팩트 |
|---|---|---|
| 두 제품 SSE route × LMStudio/OpenRouter × 오류/잘못된 입력/EOF 36개 | provider_protocol_error, 성공 DONE/message_stop 없음, failed usage 1, persistence 0, sink 1 | final-v3/junit.xml 및 compatible-stream-captures 각 nodeid의 upstream_hex/response/usage/wire |
| nullable/multiline/comment/repeated usage 4개 | 정상 literal 답변 및 성공 terminal, success usage 1 | 같은 캡처의 정상 response |
| real ToolLoop 4개 | incomplete tool dispatch 0; 정상 read 이후 실패는 read 1, 재실행 0, failed outcome | 캡처 dispatch/outcome_success; owned sentinel 내용 유지 단언 |
| fragmented tool 2개 | 유효 인자 조각을 합친 read_file XML 1개 | 캡처 chunks |
| malformed tool 16개, textual XML 후 실패 4개 | NativeProtocolError 및 방출 내용 0, failed usage 1 | 캡처 emitted/error |
| direct nonstream 12개 | 안전한 typed 502, 원문 오류 정보 비노출, failed usage 1/persistence 0 | 캡처 status/response |

새 78개 사례의 terminal memory sink 총 80회, retry sleep 0회, success usage 8회, failed usage 72회다. 성공 사례와 의도된 실패 사례를 섞어 전체 제품 실패율로 해석하지 않는다. `counts.json`과 `final-v3/socket-attempts.json`의 물리 socket 시도는 0회다. API TestClient/real manager/provider/실제 egress helper를 사용하고 **urllib terminal만 모의화**했다. metadata discovery는 별도 fixture이며 실제 모델 metadata 호출 증거가 아니다.

## 패치와 무결성

`source-binding.json`은 실제 dirty 시작 preimage 및 최종 4개 소스 SHA를 연결한다. `task-only.patch`를 `patch-reconstruction/`의 preimage에 적용한 결과 네 파일 모두 현재 최종 소스와 바이트가 일치했다(`patch-reconstruction.json`, exit 0). 원래 source의 무관한 변경을 되돌리지 않았다. 작업 전 전체 repo 보호 스냅샷을 새로 주장하지 않는다. `artifact-manifest.json`은 worker 산출물만 수록하고 parent의 controlled-wire/publication 파일은 제외한다.

## 공식 계약 근거

[OpenRouter streaming](https://openrouter.ai/docs/api_reference/streaming)은 comment/multiline framing, 마지막 DONE 및 중복 usage finish_reason을 설명한다. [오류 문서](https://openrouter.ai/docs/api_reference/errors-and-debugging)는 HTTP 200 이후에도 top-level 오류와 finish_reason:error가 실패임을 설명한다. 이번 구현은 서버가 오류를 보내면 성공으로 승격하지 않고, 응답에서 실제로 소비하는 필드 타입을 검사한다.

독립 검수 및 clean publication 검증은 parent에게 인계한다. Worker의 commit/stage/push는 없다.
