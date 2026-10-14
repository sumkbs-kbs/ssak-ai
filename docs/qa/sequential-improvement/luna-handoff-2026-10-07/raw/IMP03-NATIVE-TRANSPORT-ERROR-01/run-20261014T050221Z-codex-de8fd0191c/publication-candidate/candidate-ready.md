# 게시 후보 준비 완료

기준 HEAD: 8ed827654cb608c55b22fe75b295abf3365114f4. 소유 worktree: /Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai.

이번 변경 6파일만 있습니다: inference_providers.py, transport_errors.py, chat.py, messages_api.py, test_native_transport_error_contract.py, egress_policy.py. stage/commit/push하지 않았습니다.

root의 candidate-v3/task-only.patch를 git apply --check로 확인했을 때 Messages API의 import 문맥이 달라 적용이 거부됐습니다. 나머지5파일은 그대로 적용했고 Messages는 NativeTransportError import와 direct nonstream catch만 정확한 HEAD 위치에 옮겼습니다. root의 이미지/capability/streaming 옵션 변경과 agent streaming 리팩터링은 포함하지 않았습니다. 새로운 prerequisite는 없습니다.

실행: root .venv/bin/python <이 폴더>/verify.py candidate-v1 (cwd는 위 worktree). candidate-v1/checks.json에 정확한 argv/cwd/소스 SHA가 있습니다.

- 새 transport21 + provider10 + structured36 + egress9 = 76 passed, 0 failed/errors/skipped. candidate-v1/junit.xml 및 focused stdout/stderr 보존.
- pytest_asyncio를 명시 로딩했으며 경고는 Starlette TestClient deprecation 1건입니다.
- Ruff, format, basedpyright --level error, memory compile 모두 exit0.
- candidate-v1/import-bindings.json의7개 모듈은 모두 worktree/src에서 import됐습니다. root dirty source를 가져오지 않았습니다.
- candidate-v1/socket-attempts.json 물리 socket 시도0. 실제 HTTP/Ollama/추론/서버 실행은 없습니다.
- HEAD preimage 대비 candidate.patch는6파일뿐이며 patch-reconstruction.json에서 바이트 일치했습니다.

root의 별도 실제503/lifecycle 관측은 이 게시 후보의 오프라인 검사와 구분합니다. 독립 검수와 게시 결정은 root 담당입니다.
