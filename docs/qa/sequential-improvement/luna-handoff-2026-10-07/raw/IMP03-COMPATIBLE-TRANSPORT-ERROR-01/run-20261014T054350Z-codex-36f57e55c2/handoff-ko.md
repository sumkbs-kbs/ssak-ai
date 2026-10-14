# IMP-03-COMPATIBLE-TRANSPORT-ERROR-01 인계

상태 COMPLETE_OFFLINE / 독립 검수 PENDING. 실제 HTTP/socket/Ollama/모델 추론/서버 실행 및 commit/stage/push는 worker가 수행하지 않았습니다.

## 변경 및 지원 범위

inference_providers.py의 OpenRouter shared stream과 Ollama non-qwen3 direct generate 두 분기만 변경했습니다. safe_urlopen(max_retries=0)을 사용하고 HTTPError/URLError/TimeoutError/OSError를 기존 NativeTransportError로 전파합니다. 공개 HTTP503→502/upstream_status503, refusal→503, timeout→504 계약과 고정 안전 메시지를 재사용합니다. 에러 body를 정상 답변으로 읽어 넣지 않습니다. API·ModelManager·예외 타입은 수정하지 않았습니다.

검증한 등록 provider는 LMStudio, OpenRouter, Ollama Gemma4 호환 nonstream입니다. LMStudio/OpenRouter는 shared stream→generate join 및 직접 SSE, 중간 전송 timeout을 검증했습니다. Ollama의 모든 stream은 native 경로이므로 기존 native 회귀로 따로 보호했습니다. 정상 `[API Error]` prefix가 포함된 답변은 직접 target에서 정상 텍스트로 유지합니다.

공유 클래스 상속을 받는 OpenAIDirect/Unsloth도 같은 transport catch 동작의 영향을 받습니다. 기존 provider 정상 endpoint/auth/no-auth/tool payload 회귀는 유지되지만 해당 모든 provider의 장애 계약까지 포괄 검증했다고 주장하지 않습니다. Anthropic SDK/MLX/Nim/legacy manager 인라인 경로는 이번 수정 밖입니다. explicit combo의 기존 prefix 휴리스틱도 변경하지 않았습니다.

## 증거

- red-junit.xml:34 failed/6 passed. source-preimage/provider와 red-test-source.py, red-captures/ 및 red-route-captures/에 수정 전 소스·실제 ASGI 응답·usage·sink 횟수를 보존했습니다. red 실행은 PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_compatible_transport_error_contract.py -q --junitxml=<run>/red-junit.xml 입니다.
- 최종 명령 `.venv/bin/python <run>/verify.py final-v2`: 실제 argv/cwd/source hash는 final-v2/checks.json에 있습니다. 최종 source2개는 final-v2/source/입니다.
- final-v2/junit.xml 및 focused.stdout/stderr:109 passed, 실패/오류/skip0. 신규40 + native stream38 + native direct21 + provider10. Starlette deprecation 경고1건.
- final-v2/lint/format/types/compile stdout/stderr: 정적4개 exit0. basedpyright --level error 출력은 errors/warnings/notes0.
- final-v2/socket-attempts.json: import 전 연결/listen 차단한 cold 프로세스의 물리 시도0.
- final-v2/compat-captures/40개와 route-captures/: 등록 profile→ASGI→실제 translator/manager/provider→실제 safe_urlopen→mock urllib.request.urlopen. 신규40건 총 sink40/sleep0/실패usage34·성공6. 모든 실패는 성공usage0 및 assistant저장0; streaming은 성공 DONE/message_stop 없음. counts.json 참조.
- task-only.patch와 patch-reconstruction.json: 시작 dirty provider preimage 대비2파일을 재구성해 바이트 일치. 다른 source/evidence/publication worktree는 수정하지 않았습니다.

## 실패 이력 및 잔여

final-v1은 기능109개 통과했지만 신규test import 정렬 린트1건이 실패했습니다. 원문/소스 snapshot을 보존하고 정렬한 새 후보 final-v2로 검증했습니다.

OpenAI-compatible SSE의 JSON error payload, malformed JSON/content, terminal marker 없는 EOF를 프로토콜 오류로 정규화하는 것은 별도 잔여입니다. native NDJSON done:true 규칙을 호환 SSE에 적용하지 않았습니다. 이번 보장은 실제 발생한 전송 예외의 안전한 실패 전파와 HTTP 자동 재시도0에 한정합니다. 전체 suite/실제 인증·lifecycle/실제 provider 품질은 미검증입니다. root의 실제 fake-server 관측은 별도 소유 자료입니다.
