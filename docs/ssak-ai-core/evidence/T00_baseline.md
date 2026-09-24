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
| CLI stream | `cli.py:322 runtime.start_stream(...)` | `AgentRuntime.start_stream` → `DirectTaskExecution.start_stream` | orchestrator 내부 tool 실행 경로 |
| API stream | `api/routes/agent_stream_api.py:82` | 동일 | 동일 |
| API task 제출 | `api/routes/task_api.py:128,162,240`, `models_api.py:144` | `AgentRuntime.submit_task` → `TaskRunnerPort.submit_task` | background 태스크 내부 |
| API runtime 조립 | `api/dependencies.py:306` | `AgentRuntime(task_runner=...)` | 동일 |
| MAX 실행 | `agent_runtime.py:166 run_max` | `orchestrator.max_engine` → `DirectTaskExecution.run_max` | MAX engine 내부 |
| subagent/cowork | `tools/cowork_delegate.py:146 runner.submit_task` | TaskRunner 직접 | 동일 |
| tool 실행 | `engine/tool_executor.py:188 ToolExecutor.execute` | PlanGuard/GatePipeline/preflight/registry permission | 자기 자신이 gate |
| context | `engine/context_shaper.py:101 ContextShaper.shape` | 메시지 절삭·압축·handle collapse | 해당 없음 |
| 영속 agency | `engine/persistent_agency_store.py:85`, `engine/persistent_agency.py:97` | append-only trajectory + SQLite | 해당 없음 |
| vault | `engine/vault.py:627 VaultEngine.write_note` | lock·atomic replace·Git·RAG/wiki 동기화 | 해당 없음 |

(행번호는 2026-09-24 재검증 값이다 — §5b. 2026-09-22 표의 `cli.py:252`·`dependencies.py:278,306`·`tool_executor.py:188`는 그 시점 관찰이다.)

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

## 5. 2026-09-24 재확인 회차 — T00a 경계·매니페스트 + T00b 초기 계측 (P00)

v1.1 남은 조건(T00a 현재 경계·기존 실패 재확인, T00b-A/B)을 현재 트리에서 닫은 회차다.

```yaml
check_id: T00a / T00b-A / T00b-B
status: PASS (boundary·registration·CLI 관찰)
owner: integration
source_head: 4603ff89 (dirty — 본 회차: benchmark_spec.md 신규 · benchmark_cognitive_growth.py · architecture_review.py 등록부 · 본 문서)
command: 매니페스트 재계산 / scripts/measure_cognitive_surface.py / scripts/benchmark_cognitive_growth.py 배터리 / 핵심 회귀 5파일
exit_code: 0
observed_behavior: 아래 각 절
limitations: 사용자 표면 실호출·별도 data root 기준선 수집은 P11 이월(NOT_RUN).
verified_at: 2026-09-24T13:31:00Z
```

### 5a. 매니페스트 재대조 (T00a)

`CURRENT_TREE_MANIFEST.json`(observed 2026-09-22T02:44:20Z, 14파일)을 현재 트리와 재계산했다:
**drift 1 · missing 0**. 드리프트는 `src/antigravity_k/engine/tool_executor.py`(645aa56e→8de05c5f) 한 파일이고
커밋 `b1d85c19`(P05 "land the opt-in cognitive core")로 귀속된다 — 재탐색 결과: `ToolExecutor.execute`는
188→**230행**으로 이동했고, 같은 커밋이 추가한 `set_governance_gate`(221행, 옵트인 governance adapter,
**기본 None = 기존 동작**)은 실행 경계의 새 위임점이지 우회 경로가 아니다(P05 증거가 31 시험으로 검증).
나머지 13파일은 그대로다.

### 5b. 경계 표 symbol 재검증 (T00a)

§2 표의 모든 symbol을 현재 트리에서 다시 확인했다. 행번호 이동 둘(cli.py `runtime.start_stream`
252→**322**, `api/dependencies.py` `AgentRuntime(` 278→**306**)과 tool_executor 행(위)만 갱신하고
나머지 여덟 행(agent_stream_api 82 · task_api 128/162/240 · models_api 144 · run_max 166 ·
cowork_delegate 146 · context_shaper 101 · persistent_agency_store 85 · vault 627)은 그대로 유효하다.
표면 실측 재관찰: `scripts/measure_cognitive_surface.py` — **legacy 도달 7/9 · core 도달 2/9**
(T11 실측과 동일, 경계 변화 없음).

### 5c. 회귀 명령·기존 실패 분리 (T00a)

핵심 5파일 기준선 재실측: `pytest tests/test_agent_runtime.py tests/test_context_shaper.py
tests/test_tool_executor.py tests/test_cognitive_loop_events.py tests/test_task_state_store.py -q`
→ **127 passed (exit 0, 2026-09-24)** — 2026-09-22 관찰과 동일. 전체 저장소 회귀 수치와 실패 소유
분리는 이제 [T14_regression_ledger.md](T14_regression_ledger.md)가 소유한다(502파일 · 9 scope ·
결정적 11 · 무소유 0 — seed·순서 변화에 안정). 핵심 회귀 command는 Makefile/CI 확인과 함께 §4 기록을 유지한다.

### 5d. T00b-A/B — 초기 계측 (사전 등록 + skeleton 직접 관찰)

사전 등록 명세의 소유·계약·칸별 소재를 [benchmark_spec.md](benchmark_spec.md)에 정리했다(값은 박지
않는다 — `growth.py` spec 구조와 `--print-spec` 산출물이 소유). T00b-B 직접 관찰(help·print-spec·
demo/fresh/mature/ablation·live-pilot NOT_RUN exit 2·잘못된 mode 거부 exit 2)는 그 문서 §3에 있고,
**그 관찰이 상대 경로 `--store-root`의 이중 경로 결함을 잡아 CLI에서 절대 경로 정규화로 고쳤다**
(자세한 근거는 benchmark_spec.md §3). `RunManifest` 18필드(source/brain/policy/task/cache/seed 기록,
prompt·hardware 칸의 소재는 문서 §2 표)를 실행에서 관찰했다.
