# IMP03-AGENT-FAILURE-TERMINAL-01

판정: IMPLEMENTED_SCOPED / 독립 검토 대기. root 작업 트리 기준이며 clean worktree 매핑·게시·커밋은 수행하지 않았다.

## 변경

- 기존 DirectTaskExecution 경계가 내부 ToolLoop의 failed 상태를 감지하면 AgentExecutionError를 발생시킨다. paused/cancelled 상태 처리와 실행 소유자는 유지한다.
- ToolLoop의 NativeTransportError/NativeProtocolError는 일반 재시도 분류 전에 실패를 기록하고 중단한다. 도구 dispatch/retry를 진행하지 않으며 이미 출력한 부분은 task output에 보존한다.
- agent SSE는 안전한 agent_execution_error/task_failed 또는 기존 provider 오류 envelope를 한 번 내보낸다. assistant session/conversation 저장, done=True, 정상 [DONE] 경로에 도달하지 않는다. 일반 escaping 예외도 공개 고정 문구를 사용한다.
- UI 기존 error 판별 union에 agent_execution_error/task_failed만 추가한다. 기존 provider 6코드와 conflict 계약은 유지한다.
- 이전 quality-failed 테스트의 정상 반환 기대 한 곳만 typed exception으로 바꾸고 부분 내용/task 실패/checkpoint/event 검사를 보존했다.

## 재현 및 검증

정확한 argv/cwd/env/source SHA는 각 invocation.json, 원시 stdout/stderr/프로세스 반환값은 해당 폴더에 있다.

- baseline-final-red: 변경 전 3개 Python 모듈 overlay + 최종 신규 테스트로 5 실패 재현. root source 해시는 invocation.json, 실제 overlay 교체 해시는 effective-source-overrides.json. overlay는 비변경 소스를 root symlink로 읽었으며 원본 파일을 덮어쓰지 않았다.
- final-bound-green: 170 passed. 신규 제품 5시나리오, DirectTaskExecution stream, native transport/terminal, ToolLoop 전체와 quality-failed 노드. 성공·중단·승인/도구 경계 관련 기존 검사를 포함하되 전체 런타임 suite 통과를 주장하지 않는다.
- 제품 5시나리오의 바이너리 관측과 raw 캡처 매핑: criteria.json 및 final-bound-green/captures/*.json. task failed, error event 1, 정상 final/DONE 0, 두 assistant 저장 0, provider retry 0, tool dispatch 0, active done false.
- UI: ui-junit.xml 46 passed / ui.log / ui-invocation.json. 실제 parser와 ChatPage에서 대기열을 보내지 않고 부분 답변을 보존한다. browser/E2E 실행은 아니다.
- static/{ruff,format,basedpyright,memory-compile}/receipt.json: 실제 returncode 전부 0. dashboard typecheck 출력은 ui-typecheck.log.
- task-only.patch는 이번 9개 파일의 작업 시작 preimage에 대한 차이만 담는다. reconstruction.json 9/9 byte-identical, reconstruction.log에 실제 patch argv 결과. final-source와 source-binding.json은 검토 기준 파일 및 SHA.

## 공유 시작 경로 차단

전체 runtime 검사는 완료되지 않았다. tests/test_agent_runtime.py::test_chat_stream_route_uses_canonical_runtime 단독 실행도 변경 전 overlay와 candidate 모두 SIGSEGV(returncode -11)다.
baseline-segfault/{invocation.json,effective-source-overrides.json,exit.json,stderr.log} 및 candidate-segfault/{invocation.json,exit.json,stderr.log}가 대응 근거다.
스택: chat.chat_completions의 session manager 획득 -> acquire_project_runtime -> _build_project_runtime -> _attach_project_rag_indexer -> RAGIndexer._load_manifest/_store_has_chunks -> VectorStore.get_stats -> chromadb/api/rust.py:397 _count.
이번 실패 처리 hunk에 도달하기 전의 공유/current startup Chroma BLOCK으로 분리한다. 수정·패키지 교체·재설치·삭제를 수행하지 않았다. 전체 runtime PASS나 실제 서비스 시작 성공을 주장하지 않는다. root가 후속 조사한다.

## 게시 의존성/경계

HEAD49cd03b93a1486c04ead02156c0243d2a642d669와 root 사이 기존 차이: DirectTaskExecution은 cancellation record_event=True 8줄, ToolLoop은 기존 445줄 diff, chat 58줄 diff, client 1줄 diff가 있었다. 본 수정은 기존 경계의 작은 hunk와 새 예외 모듈이다. pending ToolLoop 전체 모듈 채택을 요구하지 않는다. clean HEAD 적용/실행 검증은 root의 별도 승인 매핑 이후 수행해야 한다.
TaskRunner/TaskStateStore/AgentRuntime/실행 프레임워크 수정 없음. stage/commit/push 없음. 실제 모델/HTTP/Ollama/Uvicorn/browser/download 검증 없음. 신규 제품 fixture는 socket 연결을 차단하고 provider terminal 응답만 모킹했다.

참고: final-bound-red 폴더 이름은 실행자 오기이며 invocation은 candidate, 5 passed다. RED 증거는 baseline-final-red만 사용한다. 초기 red/green 로그는 수리 이력이며 최종 판정으로 합산하지 않는다.
