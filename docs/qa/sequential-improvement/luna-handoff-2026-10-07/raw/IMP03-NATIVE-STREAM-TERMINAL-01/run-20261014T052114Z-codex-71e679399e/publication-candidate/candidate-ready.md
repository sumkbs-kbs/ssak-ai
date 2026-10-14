# Stream terminal 게시 후보

기준 HEAD 50437f0ccbb0dd512204ce38b640bd5c238eb97a, worktree /Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai. stage/commit/push하지 않았습니다.

소유6파일만 적용: inference_providers.py, transport_errors.py, chat.py, messages_api.py, test_native_stream_terminal_contract.py, test_inference_providers.py. 원래 task-only.patch의 Messages import 문맥이 HEAD와 달라 해당 파일만 import 및 typed SSE catch를 정확히 이식했습니다. 나머지5파일은 patch 그대로 적용했습니다. agent streaming refactor, Messages image/capability/options, ToolLoop runtime 변경은 가져오지 않았습니다. 기존 provider test에는 이번 HTTPError400 fixture 교정만 들어갑니다.

실행은 root .venv/bin/python <이 폴더>/verify.py candidate-v1, cwd는 worktree입니다. candidate-v1/checks.json에 argv/source SHA/cwd가 있습니다.

- 92 passed, 실패/오류/skip0. 새stream19 + direct21 + provider10 + structured36 + HEAD Messages streaming6. root dirty tree의101과 차이9는 이번 기능 밖의 미커밋 Messages tests9개입니다. 관련없는 테스트를 복사하거나 목표 숫자를 맞추려고 재실행하지 않았습니다. selector-counts.json 참조.
- 실제 ToolLoop4사례도 clean HEAD ToolLoop/manager/provider로 통과했습니다. 기존 mocked orchestrator fixture와 owned read sentinel 사용은 같으며 무관한 runtime prerequisite를 추가하지 않았습니다.
- Ruff, format, basedpyright --level error, memory compile 모두 exit0. Starlette TestClient deprecation 경고1건.
- candidate-v1/import-bindings.json의7모듈이 모두 worktree/src에서 로드됨을 확인했습니다. socket-attempts.json의 물리 시도0.
- HEAD source-preimage와 candidate.patch로6파일을 재구성해 바이트 일치했습니다(patch-reconstruction.json).

독립 검수/게시 판단은 root 담당입니다. root의 실제 controlled NDJSON 관측은 별도 source-bound 증거이며 이 후보 검증에서는 실제 HTTP/모델 추론을 하지 않았습니다.
