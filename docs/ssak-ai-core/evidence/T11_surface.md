---
title: "T11 — 사용자 표면 opt-in 통합 (부분): 실측 + adapter + read-only CLI"
date: 2026-09-22
status: partial — code-level opt-in PASS, 실제 표면 QA·API/stream/background 배선은 이월
owner: 통합 담당 카드(P11) / 주 에이전트 구현
---

# T11 사용자 표면 통합 (P11, 부분 완료)

```yaml
check_id: T11
status: >-
  PARTIAL PASS (module + read-only CLI 표면) — 실제 CLI/API/stream/background 대화 경로의 core 전환과
  실제 환경 QA(happy/bad input/resume/cancel, feature off 회귀)는 아직 수행하지 않았다. 체크박스는 열어 둔다.
owner: p11-surface
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive_surface.py (sha256 2d77ecce28d8748e…, 신규 647 lines)
  - scripts/measure_cognitive_surface.py (sha256 76d3a88b1b517171…, 신규 69 lines)
  - tests/cognitive/test_surface.py (신규 / 20 시험)
  - src/antigravity_k/cli.py (sha256 80b5da5ebd9a5a57…, +70 lines — cognitive status/surface 명령)
  - src/antigravity_k/api/routes/cognitive_surface_api.py (sha256 1302f8118555fbc5…, 신규 100 lines — status/reach/stream)
  - src/antigravity_k/api/routes/__init__.py (sha256 0c2c63bf72948d6a…, +2 lines — 라우터 등록)
  - tests/test_cognitive_surface_api.py (sha256 2cccfed8d5f499c1…, 신규 188 lines / 11 시험)
  - scripts/measure_feature_off_regression.py (sha256 47c4369bbe122426…, 신규 321 lines)
  - tests/cognitive/test_feature_off_regression.py (sha256 9871541e5e6c50b3…, 신규 103 lines / 5 시험)
  - (측정 method 보정: 상대 import 해석 추가 — 2026-09-22 재측정)
command: |
  .venv/bin/python scripts/measure_cognitive_surface.py --output /tmp/surface-p11/surface.json
  .venv/bin/python -m antigravity_k.cli cognitive status
  .venv/bin/python -m antigravity_k.cli cognitive status --json
  .venv/bin/python -m antigravity_k.cli cognitive surface
  .venv/bin/python -m pytest tests/cognitive/test_surface.py -q
  .venv/bin/python -m pytest tests/test_cognitive_surface_api.py -q
  .venv/bin/python -m pytest tests/test_nx05_sse_live_revocation.py tests/test_messages_api.py tests/test_api_server.py -q
  .venv/bin/python scripts/measure_feature_off_regression.py --output /tmp/feature-off.json
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/test_cli_smoke.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive_surface.py \
      scripts/measure_cognitive_surface.py tests/cognitive/test_surface.py src/antigravity_k/cli.py
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive_surface.py src/antigravity_k/cli.py
exit_code: 0 (모든 명령)
observed_behavior: >-
  실측 결과 9개 entrypoint 중 7개가 legacy `engine.cognitive_loop`에 도달하고, 신규 core(runtime) 도달은 2개다.
  그 2개는 이번에 추가한 read-only 조회 표면(CLI 하위 명령, API 라우터)이며 대화·스트림·legacy hook 실행
  경로는 core에 도달하지 않는다. 설정이 없으면 표면 adapter는 OFF로 fail-closed 하며
  source=legacy를 보고하고, shadow/active 실행을 조용히 대신하지 않고 거부한다. SHADOW는 실제 dispatcher(port=None)로
  episode를 돌리지만 dispatch 0·refusal=NO_DISPATCH_PORT로 끝난다. ACTIVE는 사람 승인 + dispatch port + governance
  gate + canonical project id가 모두 있어야 활성화되고, 승인 없이는 실행되지 않는다.
artifact:
  - docs/ssak-ai-core/evidence/T11_surface.md (이 문서)
  - /tmp/surface-p11/surface.json (P11 진입 실측 artifact; 재생성 가능)
  - tests/cognitive/test_surface.py (20 시험)
  - tests/test_cognitive_surface_api.py (11 시험)
  - tests/cognitive/test_feature_off_regression.py (5 시험) + /tmp/feature-off.json
limitations: >-
  실측은 **정적 import 그래프** 도달성이며 실행 trace가 아니다. `background/durable task`·`agent runtime`은
  orchestrator를 import하지 않고 주입받으므로 도달 False가 "core를 쓰지 않는다"는 뜻은 아니다(런타임 확인 필요).
  실제 대화 경로를 core로 전환하지 않았고(legacy 유지), API/stream 표면 배선·shadow 상태 노출·feature off
  실사용 회귀·resume/cancel QA는 P11 잔여 항목이다. ACTIVE 경로는 테스트의 stub dispatch port로 경계만 확인했고
  실제 도구 실행으로 검증하지 않았다. config.yaml에는 섹션을 추가하지 않았다(설정이 없으면 OFF).
verified_at: 2026-09-22T06:46:18Z
```

## 1. 진입 실측 — 어떤 표면이 legacy를 쓰는가

정적 import 그래프 기준(`scripts/measure_cognitive_surface.py`, source_head `79582ccd`, 4.2s):

| 표면 | legacy 도달 | core 도달 | legacy 도달 경로 |
|---|---|---|---|
| CLI | ✅ | ✅ (신규 read-only 명령) | api.dependencies → orchestrator → orchestrator.agent → engine_context → cognitive_loop |
| API server | ✅ | ✅ (신규 read-only 라우터) | (위와 동일) |
| API chat | ✅ | ❌ | (위와 동일) |
| API agent SSE | ✅ | ❌ | (위와 동일) |
| 대화 경로(orchestrator.agent) | ✅ | ❌ | api.dependencies → orchestrator → orchestrator.agent → engine_context → cognitive_loop |
| legacy loop 소유(engine_context) | ✅ | ❌ | engine_context → cognitive_loop |
| legacy hook(tool_loop) | ✅ | ❌ | cognitive_loop (reflect / verify_tool_result / adapt_strategy) |
| background/durable task | ❌ (import 없음) | ❌ | orchestrator를 주입받는다 |
| agent runtime | ❌ (import 없음) | ❌ | orchestrator를 주입받는다 |

**legacy 7/9 · core 2/9 → 수치 해석:** core 도달 2건은 이번에 추가한 **조회 표면**(CLI `cognitive` 하위 명령,
`/api/cognitive/surface` 라우터)이 adapter를 import하기 때문이며, **실행 경로(대화·스트림·legacy hook)는 전부
core에 도달하지 않는다.** 이번 작업은 실제 통합이 아니라 **경계·계측·조회 표면**을 먼저 세운 것이다.

측정 method 보정: 초기 측정은 상대 import(`from . import x`)를 보지 못해 legacy 6/8로 나왔다. 이후 해석을
추가하고 entrypoint 1건(engine_context)을 보강해 7/9·2/9로 재측정했다(정적 reachability, 실행 trace 아님).

> **2026-09-23 재확인(정정 아님).** `scripts/measure_cognitive_surface.py` 가 그 뒤 자기시험·탐지력 하한을
> 갖게 되면서 이 문서가 못 박은 digest 가 움직었다(감사 API 로 잡혔다). 그 파일을 다시 돌려 **이 절의 수치가
> 그대로임을 확인했다** — 표면 표는 legacy **7/9** · core **2/9** 이고, 이제 빈 entrypoint 표를 내면 exit 1 이다
> (측정 artifact 에 `probe` 6건 · `coverage` 가 함께 남는다). 위 `working_tree_manifest` 의 sha256·line 수는
> **그 시점의 snapshot** 이므로 갱신하지 않는다.

`legacy` hook 지점(코드로 확인): `engine_context`가 `ctx.cognitive_loop`를 만들고(`amplification.cognitive.enabled`,
기본 true), `tool_loop`이 `reflect` / `verify_tool_result` / `adapt_strategy`를 호출한다.

## 1b. feature-off 회귀 실측 — legacy가 그대로인가

`scripts/measure_feature_off_regression.py`는 **실제 legacy `CognitiveLoop`**(verify → reflect → adapt)를
세 설정에서 돌리고 transcript digest와 workspace 상태를 비교한다.

| 설정 | enabled | mode | surface source | shadow 결과 | legacy transcript |
|---|---|---|---|---|---|
| `absent` (`cognitive_core` 없음) | false | off | legacy | (실행 안 함) | `sha256:6a9a4142fc12b964…` |
| `disabled_explicit` (`enabled=false`, `mode=active`) | false | off | legacy | (실행 안 함) | `sha256:6a9a4142fc12b964…` (동일) |
| `shadow_enabled` (`enabled=true`, `mode=shadow`) | true | shadow | core_shadow | `REFUSED_ACTION` / `NO_DISPATCH_PORT` / `dispatched=0` | `sha256:6a9a4142fc12b964…` (동일) |

- **legacy 동일성:** 세 설정의 transcript digest가 같다. transcript에는 `verify_tool_result`(실패 → grade F +
  issue / 성공 → grade A), `reflect`(what_failed·lessons), `anti_patterns`, `adapt_for_retry`, `max_retries`가 담긴다.
- **shadow 옆에서도 legacy 불변:** shadow가 episode를 돌린 설정에서도 legacy transcript digest가 같다.
- **외부 효과 0:** dispatch되었다면 파일을 만들 의도(would-be write)를 shadow에 넘겼는데, workspace 파일 digest가
  세 설정 모두 동일하고(workspace unchanged) 대상 파일도 생기지 않았다(`would_be_target_created=False`).
- **명시적 거부:** `enabled=false` + `mode=active` 조합은 실행을 켜지 못하고 OFF로 남는다.

한계: 설정 OFF일 때 adapter를 아예 만들지 않는 기존 경로는 그대로이므로, 이 실측이 고정하는 것은 "adapter를
만들고 shadow를 돌려도 legacy hook 결과와 파일 상태가 변하지 않는다"까지다. 실제 대화 1건의 응답·도구 호출 수
비교(모델 필요)와 stream/background 배선 QA는 이월 항목이다.

## 2. 표면 adapter 계약 (구현)

| 인터페이스 | 구현 | 계약 |
|---|---|---|
| 설정 | `CognitiveCoreSettings.from_config` | 섹션 없음·`enabled=false`·알 수 없는 mode → **OFF fail-closed**, 사유를 note로 남긴다 |
| 상태 조회 | `CognitiveSurfaceAdapter.status` / `SurfaceStatus` | mode·source·legacy/core 경로·hook 지점·마지막 episode/판정·dispatch/refused 수 (read-only) |
| SHADOW | `run_shadow` | 실제 `ActionDispatcher(port=None)`로 episode 실행, **dispatch 0**, receipt·planned record 없음 |
| ACTIVE | `activate` + `run_active` | 사람 승인(approver·reason) + dispatch port + governance gate + canonical project id 필요 |
| 결박 검사 | `_bound_readiness` | readiness가 다른 action digest에 귀속되면 `SurfaceNotReadyError`(판정 재사용 금지) |
| 실측 | `measure_surface_reach` | entrypoint별 legacy/core 도달과 최단 경로(정적 import 그래프) |
| API 조회 | `GET /api/cognitive/surface/status` / `/reach` | read-only, 기존 라우트·경로 변경 없음, 실측은 프로세스당 1회 계산·캐시(`?refresh=true`) |
| API 스트림 | `GET /api/cognitive/surface/stream` | read-only SSE, `limit`(1~10)회 snapshot 후 `done`으로 종료. 무한 폴링·자동 갱신 없음, 상태를 바꾸지 않는다 |

## 3. 관찰 결과

| 시나리오 | 관찰 |
|---|---|
| 설정 없음 | `source=legacy`, note `cognitive_core 설정이 없다 — legacy 경로 유지(기본 OFF)`, CLI 표에 그대로 출력 |
| `enabled=false` + `mode=active` | `effective_mode=off` (mode 값이 enabled를 이기지 못한다) |
| `mode=sometimes` | `enabled=false`, note `알 수 없는 mode 'sometimes' — OFF로 fail-closed 한다` |
| OFF에서 `run_shadow` | `SurfaceDisabledError: cognitive_core가 OFF다 — legacy 경로를 그대로 쓴다` |
| SHADOW (brain port 있음) | `termination=REFUSED_ACTION`, `refusal=NO_DISPATCH_PORT`, `dispatched_actions=0`, `planned_records=[]` |
| SHADOW (clearance 없음) | `refusal=NOT_AUTHORIZED`, dispatch 0 |
| SHADOW (readiness 없음) | `termination=BLOCKED_READINESS`, dispatch 0 |
| SHADOW (다른 action에 결박된 readiness) | `SurfaceNotReadyError: readiness가 이 action에 결박되지 않았다` |
| SHADOW (brain port 없음) | `SurfaceNotReadyError: Primary Brain port(think)가 연결되지 않았다` |
| ACTIVE 승인 없음 | `SurfaceNotReadyError: 사람 승인 기록이 없다 — activate() 없이 실행하지 않는다` |
| ACTIVE 승인 빈 문자열 | `SurfaceNotReadyError: 사람 승인(approver)과 사유(reason)가 필요하다` |
| ACTIVE project id 비정규 | `SurfaceNotReadyError: ACTIVE는 canonical project id('project:<uuid>')가 필요하다` |
| ACTIVE 승인 후 | `dispatched_actions=1`, `action_status=DISPATCHED`, `source=core_active`, status에 approver 기록 |
| SHADOW에서 activate 시도 | `SurfaceNotReadyError: mode가 ACTIVE가 아니다 — 설정을 바꾸지 않고 승인만으로 켤 수 없다` |

API 관찰(라우터 단독 마운트 + TestClient, `tests/test_cognitive_surface_api.py`):

| 시나리오 | 관찰 |
|---|---|
| `GET /api/cognitive/surface/status` (설정 없음) | 200 · `enabled=false`, `mode=off`, `source=legacy`, `notes`에 legacy 사유 |
| 위 응답 shape | `legacy_module`은 `engine.cognitive_loop`, `core_module`은 `engine.cognitive.runtime` |
| 위 응답의 실행 흔적 | `dispatched_actions=0`, `refused_actions=0`, `last_episode_id=null` (episode를 돌리지 않는다) |
| SHADOW 설정 주입 | `mode=shadow`, `source=core_shadow`, `activation=null` |
| ACTIVE 설정 + 승인 없음 | `mode=active`이지만 `source=core_shadow`·`activation=null` (승인 없이 active가 되지 않는다) |
| `GET /api/cognitive/surface/reach` | 200 · `legacy_count=7`, `core_count=2`, entrypoint 9건 |
| `/reach` 반복 호출 | 첫 호출 3.18s → 캐시 0.001s, payload 동일 · `refresh=true`만 재계산(호출 1→2회 관찰) |
| `GET /api/cognitive/surface/stream` | 200 · `content-type: text/event-stream`, `event: surface_status` 1건 + `event: done` 1건 후 종료 |
| `/stream?limit=3` | `surface_status` 3건(index 1·2·3) + `done` 1건 |
| `/stream?limit=0` / `limit=11` | 422 (범위 밖 거부 — 유한 스트림 강제) |
| `/stream` 반복 | 두 번의 snapshot payload가 동일, 스트림 후에도 `last_episode_id=null`·`dispatched_actions=0` (상태 변화 없음) |
| `/stream` SHADOW 설정 | `source=core_shadow`, `mode=shadow`, `activation=null` |
| 라우터 등록 | `api_router`에 세 경로 등록, `methods={'GET'}` (read-only) |
| 전체 app import | `/api/cognitive/*` 2경로 추가, 기존 총 라우트 275건 유지 |

CLI 관찰:

```
$ python -m antigravity_k.cli cognitive status
│ enabled              │ False                                  │
│ effective mode       │ off                                    │
│ surface source       │ legacy                                 │
│ legacy path          │ antigravity_k.engine.cognitive_loop    │
│ core path            │ antigravity_k.engine.cognitive.runtime │
· cognitive_core 설정이 없다 — legacy 경로 유지(기본 OFF)

$ python -m antigravity_k.cli cognitive surface
legacy 도달 7/9 · core 도달 2/9
```

## 4. 이월·잔여 (P11 미완료 항목)

1. **대화 스트림·background 배선:** `agent_stream_api`·`durable task`의 **실행 스트림에 core 상태를 얹는** 작업은 남아 있다.
   현재 연결된 것은 CLI 명령과 read-only HTTP 조회(`/status|/reach`)·read-only SSE(`/stream`)이며, 대화 스트림 자체는
   legacy를 그대로 쓴다(신규 SSE는 별도 prefix라 기존 chat/agent 스트림 계약을 건드리지 않는다).
2. **feature off 실사용 회귀(모델 필요):** 실제 대화 1건을 OFF/ON(shadow)로 돌려 legacy 응답·도구 호출 수가 동일한지
   확인한다. 현재는 실제 legacy hook transcript·파일 상태까지 고정했고 모델 호출 비교는 수행하지 않았다.
   기존 SSE 계약(`test_nx05_sse_live_revocation`, `test_messages_api`, `test_api_server`, stream 계열 48 시험)은 회귀 없음.
3. **resume/cancel·임시 파일 action·Brain/process 교체 복원 QA:** 실제 실행 환경과 사람 확인이 필요하다.
4. **ACTIVE 실사용 검증:** 실제 도구 실행·governance gate·guard receipt 경로에서 확인해야 한다(현재는 stub port로 경계만).
5. **설정 노출:** `config.yaml`에 `cognitive_core` 섹션을 심지 않았다(없으면 OFF). 실제 전환은 사람 결정으로 남긴다.

## 5. 2026-09-24 회차 — 대화 스트림·background에 shadow 관찰 배선 (이월 1항을 닫음)

§4의 이월 1("agent_stream_api·durable task의 실행 스트림에 core 상태를 얹는 작업")을 닫은 회차다.
**shadow(관찰) 배선** — legacy 실행을 core로 바꾸지 않고, 끝난 뒤 core episode로 관찰한다.

```yaml
check_id: T11-shadow-wiring
status: IMPLEMENTED (shadow 배선) / UNVERIFIED (실모델 표면 QA — 이월)
owner: integration
source_head: 79354d8d (dirty — agent_runtime.py · cognitive_surface.py(SurfaceBrainPort) · agent_stream_api.py · dependencies.py · test_surface.py)
command: pytest tests/cognitive/test_surface.py(24) + SSE/API/runtime 회귀 148 passed + scripts/measure_feature_off_regression.py
exit_code: 0
observed_behavior: 아래 배선 관찰
verified_at: 2026-09-24T21:04:20Z
```

### 배선 관찰

- **runtime 훅** — `AgentRuntime.observe_interaction(...)`: surface가 없거나 OFF면 no-op, SHADOW에서만
  `run_shadow`(dispatch 0)를 돈다. **shadow 실패는 legacy를 절대 깨지 않는다**(예외는 조용히 녹인다 —
  시험 `test_runtime_observation_never_breaks_legacy_on_failure`). ACTIVE는 사람 승인 경로
  (run_active) 전용이라 여기서 조용히 돌지 않는다.
- **대화 스트림** — `agent_stream_api`가 스트림 완료 후 `observe_interaction`(episode=stream:<task_id>,
  expected=사용자 질의 앞부분)를 부른다. legacy 응답은 이미 완료된 뒤다.
- **background** — 기존 `task_outcome_recorder` 결과 기록 **뒤에** shadow 관찰을 붙였다(기록 자체는
  먼저, 관찰은 뒤 — 시험 `test_background_outcome_recorder_fires_shadow_after_recording`).
- **think port** — `SurfaceBrainPort`(실제 모델 호출 → ThinkOutcome; 모델 실패는 failed think로
  episode가 BRAIN_FAILED 종료). `dependencies`가 `cognitive_core` 설정이 SHADOW일 때만 surface를
  붙인다(없거나 OFF면 부착 자체를 안 한다).
- **표면 실측 변화** — `measure_cognitive_surface`가 **core 도달 2/9 → 5/9**를 잡는다(CLI·server·
  chat·SSE·agent runtime; dependencies 부착 + 스트림 라우트 호출이 import 그래프에 실재로 나타난다).
  legacy loop 소유 경로(engine_context·loop·tool_loop)와 background 집행은 여전히 미도달 — 관찰은
  observe_interaction 호출 지점에서만 일어난다(기준선 시험이 새 현실로 고정).
- **회귀** — SSE/API/runtime 계열 148 passed · feature-off 회귀 스크립트 **PASS**(세 설정에서 legacy
  transcript digest 동일 `6a9a4142…` · shadow dispatched=0 · workspace 불변 — T11 원 관찰과 같은 값).

### 여전히 이월

- 실모델 대화 1건의 응답·도구 호출 수 비교(shadow가 실제 모델 think port로 돌았을 때의 관찰) — 이
  환경에는 모델이 없다(NOT_RUN).
- resume/cancel QA · ACTIVE 실검증(사람 승인·dispatch port·실도구) — 사람 결정 필요.

## 6. 2026-09-24 실모델 회차 — 대화 1건의 응답·도구 호출 수 비교 (이월 2항을 닫음)

**환경 관찰 정정**: 2026-09-20 웹 통합 트랙이 남긴 "모델 없는 환경"은 낡았다 — 재확인(2026-09-24)한
ollama(127.0.0.1:11434)에 5종(`ssak-finetuned:qwen2.5-0.5b` · `qwen3.8:latest` 등)이 떠 있고
`get_model_manager().generate`가 실응답을 냈다. §5가 NOT_RUN으로 남긴 실모델 비교를 돌렸다.

```yaml
check_id: T11-real-model
status: PASS (실모델 1건 관찰)
owner: integration
source_head: ae9ec6a9 (dirty — cognitive_surface.py의 SurfaceBrainPort delta 수정 · test_surface.py)
command: 실측 스크립트(임시): 실 AgentRuntime+OrchestratorAgent+VaultEngine(tmp) + get_model_manager() → complete() 1건 → observe_interaction(SurfaceBrainPort=같은 모델)
exit_code: 0
observed_behavior: 아래 비교
limitations: 1회 관찰이다(표본 1 — 성능 주장 아님). resume/cancel QA·ACTIVE 실검증은 여전히 이월.
verified_at: 2026-09-24T21:54:58Z
```

### 비교 관찰 (실모델 `orchestrator-swarm` 해상, 2026-09-24)

| 항목 | legacy 실행 | shadow 관찰 |
|---|---|---|
| 응답 | 실 응답 118자("🛡️ [정밀 엔지니어링 모드]…" · "5입니다") — 완주 | legacy 응답은 이미 완료된 뒤 관찰(무영향 확인) |
| 도구 호출 | **0회**(CountingRegistry 실측) | **dispatch 0**·refused 0(관찰은 실행하지 않는다) |
| 모델 호출 | orchestrator 경유 | `SurfaceBrainPort`가 **같은 모델** 호출(brain_calls 1) — BRAIN_FAILED 아님 |
| episode | — | `stream:real-model-1` · termination `BLOCKED_READINESS`(action 없는 대화의 관찰 사실 — episode 계약상 COMPLETED는 readiness 필요, 시험 483/503이 고정) |

**이 관찰이 잡은 설계 결함(수정함)**: `SurfaceBrainPort` 첫 구현이 관찰 요약마다
`delta=EpisodeDelta(judgment=True)`를 실어 **모든 관찰을 확장 경로·readiness 요구로 몰았다**(실측:
종료가 무조건 BLOCKED_READINESS). 관찰 요약이 물질 판단을 주장하면 안 되므로 `delta=None`으로 고치고
계약을 시험으로 고정했다(`test_surface_brain_port_does_not_claim_material_judgment` — 성공 시
delta 없음·모델 실패 시 failed think).
