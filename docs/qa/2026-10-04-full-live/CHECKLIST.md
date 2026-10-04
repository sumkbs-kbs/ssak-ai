---
title: SSAK-AI 전체 기능군 현재 실사용 검증 체크리스트
date: 2026-10-04
tags: [qa, live-manual, coverage, isolated-production, limitations]
status: final-evidence-with-live-gaps
inventory_families: 27
head_supplied_by_root: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
head_independently_read: false
http_root_receipt: 118/118
cli_root_receipt: 9/9
source_binding: frozen-owned-source-manifest
final_source_manifest_sha256: c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5
owner: full_feature_inventory
---

# 현재 판정의 범위

[INVENTORY.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/INVENTORY.md)의 실제 27개 기능군을 각각 기록했다. 앞선 “약 26개” 설명은 이 목록의 행 수와 달라 27개로 바로잡았다. 27개는 목록의 범위이며, 전체 기능군이 정상 작동한다는 통과 수가 아니다.

Root가 직접 실행한 최신 [HTTP 영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-118.json)은 **118/118**, 최신 [CLI 영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-cli-final.jsonl)은 **9/9**이다. 이전 [114/114 HTTP](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-final.json)·[8/8 CLI](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-cli-results.jsonl) 기록은 역사 증거로 보존되며 최신 결과에 더하지 않는다. HTTP 영수증의 마지막 엔진 검사 2개는 별도 검사이며 HTTP 건수에 더하지 않는다. UI·질문·CLI·HTTP·controlled test는 범위가 겹치므로 합산한 “전체 기능 통과 수”를 만들지 않는다. 소스·worker 테스트 보고나 과거 QA 통과도 현재 수동 UI 통과로 승격하지 않는다.

상태는 아래 의미로 사용한다.

- **verified:** 명시한 사례와 실행 경계에 현재 Root 실행 증거가 있다.
- **partial:** 현재 확인한 하위 사례가 있지만 해당 기능군의 다른 실제 동작은 미검증이다.
- **unavailable:** 현재 실행 영수증이 없거나 필요한 하드웨어·외부 연동 경계를 실행하지 않았다. 제품의 기능 부재나 고장 판정과는 구분한다.

아래 표의 기능군 상태는 넓은 기능군을 기준으로 한다. `partial` 행 안의 `verified` 사례는 해당 사례만 통과했다는 뜻이다. UI “방문”은 화면이 열린 사실까지만 포함하며 버튼 실행, 저장, 외부 호출이나 전체 플로우 통과를 뜻하지 않는다. 이 문서 작성자는 브라우저·모델·사용자 저장소를 실행하지 않았고, Root의 현재 관찰과 허용된 QA 문서만 취합했다.

# 27개 기능군별 체크리스트

| ID / 기능군 / 상태 | 현재 실제 실행 표면과 확인 사례 | 저장소·fixture·외부 경계 및 아직 확인되지 않은 범위 | 실제 소스 |
| --- | --- | --- | --- |
| F01 코어 채팅·adaptive — **partial** | Root 실제 `/chat` Qwen 응답. R2-01..11 최종 응답 `verified`(05·06 수정 후 재검증), R2-13 계획만 출력, R2-14 Stop UI, R2-15 취소한 숫자 나열을 재개하지 않고 새 `5+6` 질문에 `11`, R2-16 purpose JSON `verified`. | 실제 모델 실행은 이 질문 범위. 05 성공 요청의 정확한 live 토큰 ledger 없음. Stop UI는 provider/native 취소 완료 증거가 아님. R2-17 제출 후 결과 미관찰. adaptive queue 전체 조작·reconnect 미검증. 최신 UI 재검증은 저장된 browser permission으로 차단. | [ChatPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/Chat/ChatPage.tsx), [chat.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py) |
| F02 대화 생명주기 — **partial** | 실제 UI에서 다른 화면 방문 후 R2-04 이력·정정 보존. `/v1/conversations` 실제 HTTP: disk hydration, stale append 409, append, fork와 독립 append, local compact, refresh, 원본 history/export `verified`. 최신 추가4건의 append revision/role·fork revision 422와 invalid 입력 후 원본 보존도 `verified`. | 실제 ConversationStore·SessionManager를 임시 디스크에 결합. compaction은 deterministic local summary, 모델 요약 아님. 실제 UI fork·compact·삭제·여러 탭의 revision 경합은 미검증. | [conversation_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/conversation_api.py), [useConversationFork.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/hooks/useConversationFork.ts) |
| F03 첨부·vision — **partial** | Root가 합성 txt의 file chooser를 시도했고 메뉴 닫힘을 관찰. | attachment가 실제 수락·표시된 증거 없음. 업로드·제거·unsupported 모델·vision 해석은 미검증. chooser 시도를 첨부 PASS로 세지 않음. 개인 파일은 QA 대상 아님. | [ChatComposer.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/Chat/ChatComposer.tsx), [ChatComposerTools.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/Chat/ChatComposerTools.tsx) |
| F04 도구·policy·access — **partial** | `/api/toolsets`, `/api/toolsets/safe/tools`, `/api/system/access-mode` 실제 격리 HTTP의 catalog·8개 readonly 도구·policy `verified`. Root R2-05·R2-09 `read_file` 각1회, R2-12 retry 실제 `web_search` 1회와 non-error 결과 receipt `verified`. | catalog가 모든 도구 실행을 입증하지 않음. R2-12 전체 URL receipt 없음·최종 clickable citation/표 형식 FAIL. production access 변경·모든 allowlist 실행·MCP 호출 없음. | [system_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/system_api.py), [ChatComposerTools.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/Chat/ChatComposerTools.tsx) |
| F05 agent 모니터링 — **partial** | Root 격리 `/agent`의 idle·disabled agency 및 pending approval 4개 표시, 한 개 deny 후3개 `verified`. 합성 채팅 tool receipt 확인. | approval 거절 표시만 확인하며 browser action 없음. production audit·raw log·사용자 이력은 열지 않음. SSE·WebSocket plan/error/quality 이벤트·재연결 전체 미검증. | [AgentPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/AgentPage.tsx), [agent_activity.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/agent_activity.py) |
| F06 durable task — **partial** | 실제 `/api/tasks`: 임시 paused task status, missing 404, invalid limit 422, cancel `verified`. 실제 `agk task list` 임시 빈 표 `verified`. | 실제 TaskStateStore·BackgroundTaskRunner·AgentRuntime, 임시 DB. submit/fork/resume/steer/output/replay·response loss·LLM dispatch의 현재 Root 실행 없음. 이전 task fixture 시나리오는 현재 통과로 세지 않음. | [task_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/task_api.py), [task-execution](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/features/task-execution) |
| F07 persistent agency — **partial** | `/api/agency/status` disabled·scheduler 미기상·빈 objective task 목록 및 Root 격리 `/agent` disabled 표시 `verified`. | 임시 설정의 disabled 경계. 사용자 live agency 상태를 뜻하지 않음. objective 우선순위·pause/resume·자동 실행은 미검증. | [agency_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/agency_api.py) |
| F08 legacy Kanban — **partial** | Root authenticated 격리 GET의 HTTP200·`data:[]`·`workspace:null` [영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-kanban-list.txt) `verified`. | empty list 경계만 확인. dispatch·status·cancel·delete·WebSocket 미검증. 별도 직접 GET을 HTTP118에 더하지 않으며 durable task와 구분. | [kanban_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/kanban_api.py) |
| F09 scheduled job — **partial** | 실제 `/api/jobs` 12건 lifecycle `verified`. Root 최신 격리 job-operations UI: Success rate `—`, `No completed runs`, Healthy, 미래 job1개·run0 표시 `verified`. | 실제 ScheduledJobService/Store·임시 DB, 2100년 예약·delivery none. 빈 실행 집합을 성공률100%로 표시하지 않음. trigger·retry·스케줄 기상·전송·실제 completed run은 미검증. | [job_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/job_api.py), [JobOperationsPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/features/job-operations/JobOperationsPage.tsx) |
| F10 memory·privacy — **partial** | 실제 project MemoryManager/provider의 stats, recall, ranked provenance, redact(valid no-op), retention 1건 삭제, current 보존·expired 제외 `verified`. 직접 엔진 zero-budget·other-project 분리 2건 `verified`. 실제 `agk memory list` 빈 상태. | 임시 합성 사실만 사용. 다중 provider dedup·correction·모든 scope·production 데이터 삭제/내보내기는 미검증. 엔진 2건은 HTTP 118에 포함하지 않음. | [system_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/system_api.py), [vault_privacy.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/vault_privacy.py) |
| F11 knowledge·vault — **partial** | `/api/vault` tree/read/write/read-back, `/v1/notes/search`, traversal 차단 `verified`. 실제 Git vault의 synthetic redact·read·snapshot restore·restored read 5건 `verified`. Root 최신 빌드의 격리 UI: `/wiki` seed.md 읽기 → Cmd+K `QA_SEED_TEXT` keyword hit → Enter 본문 연결; `root-ui-qa.md` YAML title/tags 생성 → `ROOT_UI_NOTE_CHECK` 본문 편집·저장 **verified**. | 실제 VaultEngine·YAML frontmatter·autocommit, 임시 repo. 이전 production palette No results만으로 HTTP 성공/401을 확정하지 않음. 최신 긍정 hit/문서 쓰기는 격리 fixture UI 범위. production 개인 note 열람·sync·모든 렌더러는 미검증. | [vault_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/vault_api.py), [commandRegistry.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/features/command-palette/commandRegistry.ts) |
| F12 workspace·project — **partial** | 현재 UI에서 Ssak-Ai 선택 유지. 격리 `/api/fs/workspace`, `/api/workspace/context`, `/api/execution-context/resolve` 유효 context·invalid 404 `verified`. | 임시 project·conversation revision으로 결합. production project switch/remove 없음. 전환 후 stale 응답의 다른 scope 오염과 다중 탭·동시 workspace는 미검증. | [filesystem.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/filesystem.py), [projectStore.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/stores/projectStore.ts) |
| F13 editor·code intelligence — **partial** | 실제 `/api/fs/read` 임시 파일 읽기·bounds 403 `verified`. Root 실제 `read_file` 성공·missing 관찰. | 실제 파일 read 경계와 합성/nonprivate 문서만 확인. editor save/replace/rename/delete, code-intel index/search/impact, inline 생성·실제 파일 생성 미검증. R2-13은 계획 응답이며 파일 없음·도구 0회. | [filesystem.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/filesystem.py), [code_intel_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/code_intel_api.py) |
| F14 terminal·output — **unavailable** | 현재 `/ws/terminal` 접속·shell 실행 영수증 없음. | 인증·disabled 표시·명령 결과·프로세스 종료·native cancel 미검증. 채팅 Stop toast는 terminal 중지 검증이 아님. | [TerminalSession.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/UI/TerminalSession.tsx), [system_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/system_api.py) |
| F15 Git — **partial** | 임시 Git vault API status·wiki autocommit log·diff `verified`. Root 격리 `/git`의 non-Git project HTTP400 오류 표시 `verified` boundary. | non-Git 오류 표시를 실제 Git UI 작업 성공으로 세지 않음. stage/unstage/commit/branch/checkout/stash·복구 미검증. QA 작성자는 Git을 실행하지 않음. | [git_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/git_api.py), [GitPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/GitPage.tsx) |
| F16 local file history — **partial** | Root 격리 `/history` Files0 empty 표시와 Now Save 클릭 후 파일 선택 요구 `verified` empty boundary. | 실제 snapshot 생성·비교 없음. browser localStorage의 A/B diff·autosave/limit·clear 미검증. 기존 사용자 이력 변경 없음. job API와 별도 기능군. | [HistoryPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/HistoryPage.tsx), [localHistoryStore.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/stores/localHistoryStore.ts) |
| F17 model 관리 — **partial** | Root 실제 readonly local discovery [영수증](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-model-status.json): running1·installed5·unknown0 `verified`. 실제 채팅 Qwen 사용, 격리 integration capability metadata 읽기. | status backend 수정 후 Model UI 재검증은 saved browser permission으로 차단. installed는 loading/generation proof 아님. 새 load/default 변경·embedding·vision·모든 모델 generation 미검증. 호환 API529는 합성 unavailable port. | [ModelHubPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/ModelHubPage.tsx), [local_model_discovery.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/local_model_discovery.py) |
| F18 training·recipes — **partial** | Root 격리 `/studio` Monitor의 loss/speed `—` 및 disabled export 표시 `verified`. 실제 recipe catalog/capability와 CLI recipes 출력 `verified`. | telemetry 없음의 표시와 export 불가 상태 확인. 실제 training·job/cancel·adapter export/register·MLX/Unsloth 자원은 hardware 미검증. disabled export는 export 성공이 아님. | [StudioPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/StudioPage.tsx), [recipes_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/recipes_api.py) |
| F19 voice — **partial** | 실제 `/api/voice/transcribe` malformed WAV 422·unsupported 422·overlarge 413, speak blank 422, valid PCM 200 `verified`. | 실제 WAV parser와 VoiceService, valid transcriber만 합성 fixture. 실제 microphone/STT/TTS·voice command의 job 생성은 미검증. dashboard 음성 UI는 inventory에서 발견되지 않음. | [voice_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/voice_api.py), [voice_service.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/voice_service.py) |
| F20 search·extraction — **partial** | 실제 extract invalid400·numeric/null/unavailable/empty4건 및 Root 격리 `qa-extraction` UI의 정확한 큰 정수·단위 표시 `verified`. R2-12 retry 실제 `web_search` 1회·non-error 결과·docs.python.org domain/citationID 존재 확인. | extraction의 외부 search producer는 fixture이며 실제 시세 정확성 아님. R2-12 full URL receipt 없음·2개 bullet pipe 출력/no href로 표·링크 요구 FAIL. latest citation/table fix 후 live 재검증은 browser permission 차단. probe/retry/A-B metric 전체 미검증. | [DataExtractionPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/DataExtractionPage.tsx), [search_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/search_api.py) |
| F21 finance — **partial** | 실제 extractor가 `9007199254740993` 문자열 정밀도, 한국 수 단위, `%p`, `bp`, stock partial null을 보존 `verified`. Root R2-08 가상 종목 확정 가격 거절 `verified`. | 입력 출처는 deterministic search fixture. 실제 시세·환율 검증 아님. `/finance`, `/dcf`, `/comps` readiness 응답을 valuation 실행으로 세지 않으며 DCF/comps 계산 영수증 없음. | [financial_numbers.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/financial_numbers.py), [slash_commands_workflow.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/slash_commands_workflow.py) |
| F22 skills·marketplace·MCP — **partial** | Root 격리 Skills catalog·Marketplace·MCP의 authenticated empty0 표시와 실제 `/api/mcp/health` empty boundary `verified`. | catalog/empty 상태 확인이며 사용자 live MCP 연결 통과 아님. 실제 server/tool 호출·OAuth·npm install/remove·publish·revoke 없음. | [SkillsPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/SkillsPage.tsx), [McpOAuthPanel.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/components/shared/McpOAuthPanel.tsx) |
| F23 frontend plugin — **partial** | Root `/plugins` 및 Cmd+K `Show test toast` 실행 후 실제 toast 표시 `verified`. 내장 job-operations empty-run UI는 F09에 기록. | plugin enable/disable·새 route 등록·storage persistence 전체 미검증. test toast를 별도 backend 작업 완료로 세지 않음. | [PluginPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/PluginPage.tsx), [pluginRegistry.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/plugin/pluginRegistry.ts) |
| F24 evaluation·cognitive — **partial** | Root `/mutation` stale label과 failed filter empty 표시 `verified`. 실제 decision known/invalid422, cognitive off/finite SSE/limit422, 실제 CLI decision valid/invalid·cognitive status `verified`. | supplied probabilities 평가이며 calibration unverified. cognitive off는 fixture 설정. active episode·self-test runtime 없음. mutation은 historical snapshot, 현재 CI 실행 아님. | [MutationDashboardPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/MutationDashboardPage.tsx), [decision_evaluation_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/decision_evaluation_api.py), [cognitive_surface_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/cognitive_surface_api.py) |
| F25 approval·browser·agent tools — **partial** | 실제 approval HTTP19건 state/grant 경계 `verified`. Root 격리 `/agent` pending4→deny→3 UI `verified`. | 실제 ApprovalManager/BrowserApprovalGate·임시 상태. browser action·ticket consumption·실행 후 replay 없음(gate consumed0). shell/fs-write/TDD/external-brain 미검증. 이 제품의 approval denial과 현재 browser automation의 saved permission 차단은 별도 경계. | [approval_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/approval_api.py), [agent_tools.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/agent_tools.py) |
| F26 admin·security — **partial** | 실제 auth middleware protected401/200·verify·policy·isolated settings·health/ready `verified`. Root 격리 `/settings` all unconfigured·search disabled 읽기 `verified`, mutation 없음. | 실제 TokenService·임시0600 header/config, lifespan OFF·ready degraded/traffic accept. PIN/restart/env/shields/security mutation·full startup 미검증. 현재 saved browser permission은 사용자의 채팅 허용으로 해제되지 않았으며 우회 없음. | [server.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/server.py), [SettingsPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/SettingsPage.tsx), [system_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/system_api.py) |
| F27 agent 호환·remote·services·provenance·배포 — **partial** | Root 격리 `/start`: 실제 origin port50816·수정 후 `--api-base` URL·copy toast `verified`. CLI `start codex` 합성 URL/guarded token reference/fake token 없음과 호환 API invalid400·model-unavailable529 4건 `verified`. | clipboard 읽기는 empty라 실제 복사 내용 **inconclusive**. copy toast는 clipboard proof 아님. Codex/Claude 실행·gateway·pair/relay·workspace services·provenance dispatch·package/native signing/update/install·다른 OS 미검증. compatibility model은 unavailable fixture. | [AgentStartPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/AgentStartPage.tsx), [messages_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/messages_api.py), [responses_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/responses_api.py), [cli.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/cli.py), [pyproject.toml](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/pyproject.toml) |

# 현재 Root 코어 질문 증거의 해석

[QUESTIONS.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/QUESTIONS.md)에 R2-09 receipt·R2-11 PASS·R2-12 retry·R2-16..17·마지막 permission 차단이 동기화되었다. 각 질문의 실제 실행 범위와 최종 UI 재검증 한계를 아래에 구분했다.

| 질문 | 현재 판정과 한계 |
| --- | --- |
| R2-01..04, 07..08, 10 | 최종 응답 **verified**. 합성 산술/JSON/정정/자료-지시 구분/미확인 정보 거절의 제한된 사례. |
| R2-05 | 최초 실제 read_file 1회 후 8000-budget 초과 halt는 유지. 수정 후 실제 read_file 1회·필수5필드·halt 없음으로 재검증 **verified**. 성공 요청의 정확한 전체 live 토큰 ledger는 없음. |
| R2-06 | 최초 one-number 지시 위반 표 출력은 유지. 수정 후 `9` 단독 응답 재검증 **verified**. |
| R2-09 | 실제 read_file1회·`missing_file` receipt·`파일 없음` 응답 **verified**, QUESTIONS 동기화 완료. 허용 합성 경로에 생성/수정 없음. |
| R2-11 | `813` 단독 응답 **verified**, QUESTIONS PASS 동기화 완료. |
| R2-12 최초 | Python list/tuple 변경 가능 여부의 내용은 일치. 실제 도구0회, URL이 code fence여서 검색·clickable citation 요구 **FAIL**. version 표 질문이 아님. |
| R2-12 retry | `direct_8ee2ba63edc2` done, 실제 `web_search`1회·non-error 결과·docs.python.org domain·citationID `23316a30b478` 존재 **verified**. full URL receipt 없음. 최종 응답은 두 bullet의 pipe 형식이고 href 없어 요청한 두 행 표·clickable citation **FAIL**. 최신 citation/table fix의 controlled 검사는 통과했으나 실제 UI 최종 retry는 saved browser permission으로 **blocked**. |
| R2-13 | 두 항목의 앞으로 할 계획만 응답, 도구0회·`qa-plan.txt` 없음. 계획 응답 관찰이며 코드/파일 생성 통과가 아님. |
| R2-14 | Stop toast 관찰. 실제 backend/native 취소·task 종료는 **미검증**. |
| R2-15 | 취소한 숫자 나열을 이어 쓰지 않고 새 `5+6` 요청에 `11` 단독 응답 **verified**. R2-11의813/context 반복이 아님. provider 취소 receipt·응답 SLA는 판정하지 않음. |
| R2-16 | Root 실제 purpose JSON 응답 **verified**. 이 합성 질문 범위의 출력 계약만 확인. |
| R2-17 | 제출했으나 결과 미관찰. 통과로 세지 않음. |

# 실제 격리 API·CLI의 실행 경계

[API_SCENARIOS.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/API_SCENARIOS.md)의 protocol은 real loopback uvicorn socket + curl로 production FastAPI app과 auth middleware를 호출한다. fake route는 mount하지 않는다. Path.home/cwd/config/task/job/usage/vault/conversation/GBrain/cache를 import 전에 임시 경로에 결합하고 dotenv를 비활성화한다. HOME·CODEX_HOME은 유지하며, outbound socket은 local model port까지 차단한다. lifespan OFF로 startup 자동 작업을 실행하지 않는다.

| HTTP 영수증의 scope | 사례 수 | 의미 |
| --- | --- | --- |
| real production route + real isolated stores | 53 | 실제 구현·임시 저장소·합성 데이터 |
| real production conversation route + real isolated stores; no model execution | 20 | 실제 디스크 lifecycle·local compaction·invalid input 보존, 모델 없음 |
| real scheduled-job service/store; no trigger/delivery | 12 | 실제 임시 job 정의 lifecycle, run0 |
| real approval manager/gate; no browser action | 19 | 승인 상태·ticket 발급까지만, action/consume 없음 |
| real privacy route + isolated Git vault | 5 | 합성 vault 내용·실제 Git rollback |
| real route/extractor + deterministic external search provider | 4 | 검색 결과 producer만 fixture |
| real compatibility route + unavailable external model port | 4 | typed-unavailable 경계 |
| real WAV/VoiceService + synthetic external transcriber | 1 | 실제 parser/service, transcriber fixture |
| **HTTP 합계** | **118** | 기능 수·함수 수·전체 운영 통과 수가 아님 |

Root JSONL 종료 기록은 서버 종료와 임시 auth header 제거를 확인한다. CLI 기록은 각 child의 임시 저장소 제거를 확인한다. 사용자 실제 vault/memory/auth/log를 읽거나 쓰는 실행은 포함하지 않는다. Vault의 YAML frontmatter·Files-first/Git-first 작업과 실제 autocommit은 임시 repo 안에서만 수행했다.

현재 CLI 실제 9개 사례는 `--help`, `--version`, `recipes`, `cognitive status`, `decision-eval {sample}`, `decision-eval {invalid}`, `task list`, `memory list`, `start codex`의 합성 URL dry plan이다. 각각 현재 Root 영수증 **verified**. help 출력에 없는 command를 source inventory만으로 현재 CLI 실행 통과로 세지 않는다.

# 증거·HEAD·해시 결합

HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`는 Root와 [final-source-manifest.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/final-source-manifest.json)이 기록했다. 이 작성자는 Git을 호출하지 않았다. 최신 manifest의 SHA256은 `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`이며 **이번 작업 소유 소스56개: production28·test28**를 고정한다. 공유 dirty tree는 보존되었고, 이 56개를 전체 checkout이나 기능 수로 해석하지 않는다. 현재 bytes의 재검사에서 소스56개와 manifest의 harness12개 모두 hash mismatch0이었다. HEAD commit만으로 uncommitted 최종 수정이 식별되지 않으므로 이 manifest가 앞선 일부 snapshot보다 우선한다.

| 현재 증거 파일 | SHA256 |
| --- | --- |
| [root-api-118.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-118.json) | `37585c5db0d2c0fd8112de67ed96054ecdaa9d9c81986bc9a690b608b01c8d69` |
| [root-api-118.jsonl](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-api-118.jsonl) | `1a38cf942fab24af5ca0391e2db6875333c8a87844f88a84635def141ed709bc` |
| [root-cli-final.jsonl](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-cli-final.jsonl) | `7c623a739ea255b93269751bf869582a48df1f47c74faf1af9834f675e8e946d` |
| [API_SCENARIOS.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/API_SCENARIOS.md) | `8125f3ae8d531a0d5876957178497ee5dd4ad7ca0d2557ae84ea1883a7bd9225` |
| [INVENTORY.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/INVENTORY.md) | `11758516f357442d16a97381cc7484ebb1df406bdc8743bbab95bdd0b95d1c68` |
| [harness-source-manifest.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/harness-source-manifest.json) | `e1bea1ab971778e403fa7c6315c80aaa1e423c572a5d7fb865aa17b87f9912a8` |
| [final-source-manifest.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/final-source-manifest.json) | `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5` |
| [QUESTIONS.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/QUESTIONS.md) | `0c8fd27fb56b57a618f22e50cd95c8f34b64f1378b65a63e0d3b25caa5ec35a3` |
| [root-model-status.json](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-model-status.json) | `3b0f706720ced0ba03c4423b90f8d5288657467b32412b64590dbe8c8644f420` |
| [root-kanban-list.txt](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-kanban-list.txt) | `e02828c03d54a9ee6f7613b610d917a824ca6154c12f0d910e82a78dc6199dc7` |
| [root-final-regression.log](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-final-regression.log) | `d58938e92ca74f4e96a5e512b94ff66d13682fe230772c075f8a3217f78376e0` |
| [root-final-ui-tests.log](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/root-final-ui-tests.log) | `e7309e04aa0c3d6943d251da600c8aecb65a0bf30d665e58bc5b83708864a51d` |
| [citation-source-links-regression.txt](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/2026-10-04-full-live/citation-source-links-regression.txt) | `c40c6b3764fb81421cbf7482c96fb1150dd4c7b818fa0d0056b40438fd42915b` |

harness-source-manifest는 HTTP118/CLI9 catalog와 driver10개를 기록하고, final-source-manifest는 추가 regression/model-status driver를 포함한 harness12개를 고정한다. harness-author 결과와 Root 개인 실행 영수증은 구분한다. Root 최신118/118·9/9가 현행 catalog와 일치하며 이전114/114·8/8만으로 확대된 사례를 통과 처리하지 않았다.

| 최신 final manifest의 주요 production 소스 | SHA256 |
| --- | --- |
| [system_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/system_api.py) | `610334086c50b0b0e0ff09b57d3ae45e7b46739be8316baa7627ade67d35c7a6` |
| [conversation_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/conversation_api.py) | `2f78dae05b39f192e37cec047e5fb88a7f08bf77b451314b04f5a5af60889a69` |
| [vault_api.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/vault_api.py) | `54bc1e8527adb8dc5e98e6041ca412fab857edc2f37b1ba7a63915f49c92fa7a` |
| [DataExtractionPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/DataExtractionPage.tsx) | `bb692638a7796301f4af27681bfc598302c137342ab1498f07d5e91364060a58` |
| [StudioPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/StudioPage.tsx) | `63fc39c0ab8aca62c8a80cfb8c1d8d4c59c07e18920cdf5c520b25f135b70c92` |
| [AgentStartPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/AgentStartPage.tsx) | `b25399815bac5f949f64c40a3c90a0c936ee2e79021c281bc418b627ac9221cb` |
| [commandRegistry.ts](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/features/command-palette/commandRegistry.ts) | `b2d2c947c615c568d9e4abc3d9e53ccb040e87d302cae19ea8454f277ba20bfd` |
| [ModelHubPage.tsx](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/src/pages/ModelHubPage.tsx) | `787705754d1d979d1d708aa9e73d4150b9251bc12a669b45a6031766f87d8417` |
| [tool_loop.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/tool_loop.py) | `eb018c1d080534d5e9e6b4deb60f8d9c953eace064f2ec9a303e55ee1b6eea17` |
| [quality_gate.py](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/quality_gate.py) | `1d905c500a60a7f2f722b8d9118e73c8910ee73e766082e8336669e4de2bfd55` |

최신 citation/table 수정의 controlled backend regression은 **243 passed**, Root 최종 backend regression은 **283 passed**, Root dashboard test는 **133 passed / 16 files**다. 세 집합은 중복 가능하므로 합산하지 않는다. 이는 고정 소스의 controlled test 영수증이며 실제 브라우저의 최종 citation/table·Model UI 동작 통과를 대신하지 않는다.

# 미해결 범위

Wiki read/search/create/edit/save, fixture extraction·Studio empty telemetry/disabled export·Skills empty catalog·start URL/copy toast·plugin toast·agent idle/denial·settings readonly·non-Git 오류·history empty/save prompt·job empty-run·mutation stale/filter는 명시한 실제 Root UI 경계까지만 확인했다. empty/disabled/error 화면이나 toast를 전체 기능 실행 통과로 세지 않는다. attachment 수락·실제 snapshot·clipboard 내용·Git UI 작업·scheduler delivery·코드 파일 생성·terminal/native 취소·task dispatch/reconnect는 미검증이다.

R2-12 retry의 실제 검색 호출과 non-error 결과는 확인했지만 full URL provenance와 최종 표·clickable citation은 미충족이다. 최종 citation/table 수정 후 실제 UI retry와 수정 후 Model UI 및 남은 UI 재검증은 **저장된 browser permission으로 blocked**다. 사용자의 채팅 허용이 이 저장 설정을 해제하지 않았으며 우회하지 않았다. 사용자가 해당 browser permission을 해제하기 전까지 이 후속 live 검증은 미완료다. R2-17은 제출만 되었고 답변 결과는 미관찰이다.

실제 STT/TTS·training·embedding·새 model load·OAuth/account·remote relay·external-brain·publish·native signing/update/install·다른 플랫폼은 hardware/external 미검증이다. 제품 support matrix의 지원 범위는 QA 수치로 확대하지 않는다. source-only 의심, 수정 보고, disabled UI, historical snapshot은 해당 현재 실행 증거 없이 live defect나 operational PASS로 분류하지 않는다.
