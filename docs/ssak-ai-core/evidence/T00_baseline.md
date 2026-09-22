---
title: "T00 기준선 — P00 경계 재검증 증거"
date: 2026-09-22
status: partial-evidence
owner: 통합 담당
---

# T00 최신 기준선 (P00)

```yaml
check_id: T00
status: PARTIAL
owner: integration
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest: docs/ssak-ai-core/CURRENT_TREE_MANIFEST.json (observed_at 2026-09-22T02:44:20Z)
command: shasum 재계산 / .venv/bin/python -m pytest <핵심 회귀 5개 파일> -q
exit_code: 0
observed_behavior: manifest 14개 파일 digest drift 0, 기존 회귀 127 passed, 상세 아래
artifact: docs/ssak-ai-core/evidence/T00_baseline.md
limitations: 전체 저장소 회귀와 모든 entrypoint 실호출은 미실행. 아래 표는 코드 경계 근거이며 실행 인수 기록이 아니다.
verified_at: 2026-09-22T03:16:57Z
```

## 1. manifest 대조

`docs/ssak-ai-core/CURRENT_TREE_MANIFEST.json`의 14개 파일 SHA256을 현재 작업 트리와 재계산 대조했다.
결과: **drift 0, missing 0**. 문서작성 시점(02:44:20Z)과 대조 시점의 파일 내용이 동일하므로 P01/P02는 최신 gap 분석을 근거로 진행했다.

## 2. 실행 entrypoint와 경계 (코드 근거)

| entrypoint | 파일·symbol | runtime 경계 | tool gate 도달 |
|---|---|---|---|
| CLI stream | `cli.py:252 runtime.start_stream(...)` | `AgentRuntime.start_stream` → `DirectTaskExecution.start_stream` | orchestrator 내부 tool 실행 경로 |
| API stream | `api/routes/agent_stream_api.py:82` | 동일 | 동일 |
| API task 제출 | `api/routes/task_api.py:128,162,240`, `models_api.py:144` | `AgentRuntime.submit_task` → `TaskRunnerPort.submit_task` | background 태스크 내부 |
| API runtime 조립 | `api/dependencies.py:278,306` | `AgentRuntime(task_runner=...)` | 동일 |
| MAX 실행 | `agent_runtime.py:166 run_max` | `orchestrator.max_engine` → `DirectTaskExecution.run_max` | MAX engine 내부 |
| subagent/cowork | `tools/cowork_delegate.py:146 runner.submit_task` | TaskRunner 직접 | 동일 |
| tool 실행 | `engine/tool_executor.py:188 ToolExecutor.execute` | PlanGuard/GatePipeline/preflight/registry permission | 자기 자신이 gate |
| context | `engine/context_shaper.py:101 ContextShaper.shape` | 메시지 절삭·압축·handle collapse | 해당 없음 |
| 영속 agency | `engine/persistent_agency_store.py:85`, `engine/persistent_agency.py:97` | append-only trajectory + SQLite | 해당 없음 |
| vault | `engine/vault.py:627 VaultEngine.write_note` | lock·atomic replace·Git·RAG/wiki 동기화 | 해당 없음 |

## 3. 기존 회귀 기준선 (신규 red 0)

```
.venv/bin/python -m pytest tests/test_agent_runtime.py tests/test_context_shaper.py \
    tests/test_tool_executor.py tests/test_cognitive_loop_events.py tests/test_task_state_store.py -q
127 passed in 1.92s   (exit 0, 2026-09-22)
```

P01/P02 완료 후 재실행에서도 **219 passed** (신규 cognitive 83 + 위 5개 파일 136, `test_persistent_agency.py` 포함)로 기존 실패는 0이다.

## 4. 남은 P00 조사 (미완료로 명시)

- CLI/API/stream/background/secondary/self-evolution별 **실제 실행 관찰**(P11 범위)과 별도 data root 기준선은 아직 수집하지 않았다.
- Makefile/CI 명령 확인: `make lint`(ruff), `make test-quick`, `make typecheck`(mypy, pyproject `[tool.mypy]`), CI는 ruff+mypy+fast tests. 신규 cognitive 코드는 ruff check/format과 `mypy src/antigravity_k/engine/cognitive`에서 clean이다.
