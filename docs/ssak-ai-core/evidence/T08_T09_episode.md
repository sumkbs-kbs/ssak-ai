---
title: "T08/T09 — 최소 운영 루프와 Experience 형성 증거"
date: 2026-09-22
status: verified-module-and-tool-executor-surface
owner: 통합 담당 카드(P08) / 주 에이전트 구현
---

# T08/T09 최소 운영 루프·Experience (P08)

```yaml
check_id: T08, T09
status: PASS (module + 실제 ToolExecutor·CanonicalStore 표면) — T08-A~D, T09-A~E
owner: p08-loop
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
working_tree_manifest:
  - src/antigravity_k/engine/cognitive/runtime.py (sha256 f77646f20a310a89…, 신규)
  - src/antigravity_k/engine/cognitive/experience.py (sha256 a9279ef1bcd51fc5…, 신규)
  - tests/cognitive/test_episode.py (sha256 20e686601a1603e1…, 신규 21 시험)
  - docs/ssak-ai-core/ARCHITECTURE_DECISIONS/ADR-0004-cognitive-loop-ownership.md (P08 요구 ADR)
command: |
  .venv/bin/python -m pytest tests/cognitive -q
  .venv/bin/python -m pytest tests/cognitive/test_episode.py -q
  .venv/bin/python -m pytest tests/cognitive tests/test_tool_executor.py tests/test_ws02_tool_root.py tests/test_tool_contracts.py tests/test_claw_integration.py tests/test_plan_guard.py tests/test_command_execution_boundary.py tests/test_fr02_shell_execution_boundary.py tests/test_autonomous_capabilities.py tests/test_persistent_agency.py tests/test_cognitive_loop_events.py -q
  .venv/bin/python -m ruff check src/antigravity_k/engine/cognitive tests/cognitive src/antigravity_k/engine/tool_executor.py
  .venv/bin/python -m ruff format --check src/antigravity_k/engine/cognitive tests/cognitive
  .venv/bin/python -m mypy src/antigravity_k/engine/cognitive
exit_code: 0 (모든 명령)
observed_behavior: simple task가 PREPARE→THINK→COMMIT→ACTION→OBSERVE→EXPERIENCE로 끝나고 Secondary·재사고·
  verifier 호출이 0이다. 거부된 요청은 바뀐 ground 범위만 재검토하며, material delta가 없으면 stop한다.
  readiness 부족은 ACTION 없이 BLOCKED_READINESS로 끝난다. Experience 선별은 정상 읽기를 OPERATIONAL_ONLY,
  실패·회복을 EXPERIENCE, 불명 결과를 DEFERRED로 남기고 Operational Record는 항상 보존된다. 실제 ToolExecutor로
  파일을 쓰고 episode 전이가 canonical Event record로 store에 commit·검증됐다.
artifact:
  - docs/ssak-ai-core/evidence/T08_T09_episode.md (이 문서)
  - tests/cognitive/test_episode.py (21 시험: T08-A 2 / B 2 / C 2 / D 4, T09-A~E 9, 실제 표면 2)
limitations: engine/agent_runtime.py·orchestrator·config 연결과 사용자 표면 opt-in은 P11 이월이다(ADR-0004).
  즉 이 카드의 PASS는 module + ToolExecutor·CanonicalStore 표면이며 production 대화 경로에서 실행됐다는
  뜻이 아니다. episode의 decision/context record 생성은 실제 제공자(Context/Brain adapter)와 함께 P11에서
  닫아야 한다. Experience→Knowledge/Policy 승격은 P09 범위이며 여기서 생성하지 않는다. guard를 실제로
  집행하는 주체는 executor이며, 이 카드는 receipt 경계만 사용한다.
verified_at: 2026-09-22T05:21:21Z
```

## ownership (ADR-0004)

legacy `CognitiveLoop`(`engine/cognitive_loop.py`, Plan→Execute→Verify→Reflect→Adapt, production 대화 경로
사용)과 신규 `engine/cognitive/runtime.py`의 경계를 ADR-0004로 확정했다. 신규 runtime은 port 주입 시에만
동작하는 opt-in이며, canonical state/experience 소유는 Body store에 남고, 한 요청을 두 loop가 동시에
dispatch하지 않는다. 합치거나 legacy history를 옮기는 작업은 human decision(P12)이다.

## T08 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A | simple task | `PREPARE→THINK→COMMIT→ACTION→OBSERVE→EXPERIENCE`, brain 1회, rethink 0, secondary 0, verification 0, tool request 0 |
| A | simple인데 요청이 있는 경우 | GOVERN 단계 자체가 생략되고 secondary 요청은 실행되지 않는다 |
| B | governance가 요청을 허용하지 않음 | `TARGETED_RETHINK`가 1회 돌고 `affected_grounds`·`feedback_refs`·이전 judgment ref가 그대로 전달된다. 새 judgment로 교체되고 기존 피드백은 기록으로 남는다 |
| B | 승인된 요청 | `EXECUTE`에서 dispatcher가 실제 receipt를 만들고 피드백에 receipt ref·disposition이 남는다 |
| C | 같은 signature 재요청 | 두 번째는 `STOPPED_NO_DELTA`이고 "새 ID는 새 의미가 아니다"가 note에 남는다. brain 호출은 1회 유지 |
| C | material delta 없는 rethink | `No Material Cognitive Delta → stop`, ACTION 단계 진입 없음 |
| D | readiness NOT_READY | `BLOCKED_READINESS` + "stop은 READY가 아니다", ACTION 진입 0, dispatch 호출 0 |
| D | readiness 없음 / context 없음 | `BLOCKED_READINESS` / `BLOCKED_CONTEXT`가 서로 다른 사유로 기록 |
| D | dispatch 중 결과 불명 | `ACTION_OUTCOME_UNKNOWN`, outcome 없음(성공 아님), reconciliation 요구 |
| D | 관측 없음 | `OBSERVATION_PENDING` + 선별 DEFERRED |

## T09 시나리오별 관찰 결과

| 항목 | 시나리오 | 관찰 |
|---|---|---|
| A | 정상 읽기 | `OPERATIONAL_ONLY`(사유 ROUTINE)로 남고 Operational Record는 그대로 보존. EXPERIENCE 선별이 아니면 core 형성 거부 |
| A | 실패·회복 | `EXPERIENCE` + 사유 FAILURE·RECOVERY·MATERIAL_DELTA, evidence reference 유지 |
| A | 결과 불명 | `DEFERRED`(UNRESOLVED), reusable 아님 |
| B | expected==observed | 환경 차이·독립 재검증 신호가 있으면 EXPERIENCE가 될 수 있다 — 수치 차이 유무만으로 선별하지 않는다 |
| C | 결과 실패 + 당시 판단 합리 | `OutcomeEvaluation=DEVIATION` / `DecisionEvaluation=MATCH` / `ExecutionEvaluation=FAILED`로 분리. 나중 지식 사용 시에만 판단이 달라진다 |
| D | 지연 관측 | `supplement`가 새 Observation record를 연결하고 core digest history는 불변 |
| E | 해석 주체 | Body가 해석을 시도하면 거부, Primary Brain/Human만 revision 1→2로 append하며 `supersedes` 체인이 남고 core digest는 그대로 |
| E | 중복·선별 없는 형성 | 중복 Operational Record와 선택 없는 core 형성이 각각 거부된다 |
| — | 승격 | 지식/정책 승격 API를 호출하지 않아 Experience→Knowledge 승격은 발생하지 않는다(P09) |

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                        → 229 passed (episode 21 포함)
.venv/bin/python -m pytest tests/cognitive/test_episode.py -q        → 21 passed
.venv/bin/python -m pytest (영향 영역 11 suite, cognitive_loop_events 포함) -q → 406 passed
.venv/bin/python -m ruff check / ruff format --check                 → clean
.venv/bin/python -m mypy src/antigravity_k/engine/cognitive          → Success: no issues found in 15 source files
```

## 기존 red (분리 기록, 이번 변경과 무관)

이번 카드는 신규 2 모듈 + 신규 시험 + 문서만 추가했고 기존 runtime 파일을 수정하지 않았다(ADR-0004 결정).
기존 증거가 보고한 `tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for`
실패는 그대로이며 신규 red는 없다.

## 남은 것 (다음 카드)

- P09: `Evaluation → PatternCandidate → ValidationReport → PolicyActivation → BehaviorChangeTrace` 경로와
  human-assisted 후보, CAS 승격·rollback·retire를 구현한다.
- P10: P00/P01의 benchmark skeleton을 인계받아 frozen split으로 fresh/mature를 비교하고 ablation 6개를 기록한다.
- P11: ADR-0004의 opt-in을 실제 CLI/API/stream/background에 연결하고 feature off 회귀를 확인한다.
