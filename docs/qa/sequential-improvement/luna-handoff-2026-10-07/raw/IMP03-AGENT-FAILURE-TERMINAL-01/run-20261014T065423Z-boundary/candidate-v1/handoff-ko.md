# Clean candidate-v1 — IMP03-AGENT-FAILURE-TERMINAL-01

판정: IMPLEMENTED_SCOPED / fresh independent review pending.
기준 worktree `/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai`, HEAD `58ca7e3339759b26f7ed4d38f850c13e219a19a1`.

9개 파일만 변경했다. 원본 task-only-v2.patch의 git apply --check는 chat finally 주변 및 ToolLoop import 이웃 문맥 2곳에서 실패했다. root 승인 후 동일한 오류 처리 hunk를 clean 문맥에 맞췄다. 기존 clean finally의 reset_chat_stream_events/reset_tool_policy/iterator cleanup/active_session 정리와 스트림 실행 소유자는 그대로 보존했다. RequiredToolRecovery/445줄 pending ToolLoop 변경은 채택하지 않았다. client.ts는 오류 schema 5줄 추가뿐이며 기존 unused import 제거를 가져오지 않았다.

## 검증 / 바이너리 관측

- `scoped/invocation.json`: 정확한 argv/env/cwd와 Python 소스 SHA. 실제 clean Python 202 passed, zero skip (`scoped/junit.xml`, `stdout.log`, `exit.json`). 기존 제품/Direct/native/ToolLoop 169 + 전체 runtime 33. root 이전 숫자를 재사용하지 않았다.
- `scoped/module-socket-binding.json`: 실제 import된 AgentRuntime/DirectTaskExecution/ToolLoop/chat/newtest가 모두 clean WT 경로다. socket connection attempts `[]`. owned temporary SessionManager로 두 기존 단위 검사를 격리했으며 task error semantics는 실제 제품 경로로 검증한다.
- `criteria.json` + `scoped/captures/{terminal,late,transport,escaping,generic}.json`: task failed, typed event:error 1, 정상 DONE/final 0, 두 assistant 저장 0, provider retry 0, tool dispatch 0, active done false. late partial 응답 보존.
- `ui/invocation.json`: 정확한 npm argv/cwd/source SHA. 실제 clean UI 45 passed (`ui/junit.xml`, `stdout.log`, `exit.json`). parser known provider 6코드 + agent error, ChatPage queued-turn/partial 유지 및 정상 queue drain/conflict 회귀. root의 RunOwnership 16건 중 pending 한 건을 가져오지 않아 clean RunOwnership은 15건이다. 46으로 주장하지 않는다.
- `static/{ruff,format,basedpyright,memory-compile}/receipt.json`: mandatory 4개 실제 returncode 전부 0. stdout/stderr 파일과 source SHA 포함.
- `preimage/`, `source/`, `source-binding.json`: HEAD clean 입력과 최종 9개 파일. `task-only.patch`와 `reconstruction.json`은 HEAD preimage로 9/9 byte-identical 재구성했다. `protected-check.json`: 변경 파일 정확히 own9, 테스트 전후 Python 소스 안정.

실제 provider/Ollama/HTTP/Uvicorn/browser/download 미실행. UI는 Vitest 표면이며 browser E2E가 아니다. 공유 startup Chroma -11은 root 이전 baseline/candidate 기록과 별도 후속 조사로 남는다. 이 후보의 session fixture 단위 검사 통과를 실제 startup 안정성으로 승계하지 않는다. Git stage/commit/push 없음.
