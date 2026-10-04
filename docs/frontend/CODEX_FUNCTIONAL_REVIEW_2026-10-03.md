---
title: 공개 Codex 기능 대조와 SSAK-AI 반영 결정
tags: [codex, source-review, functional-upgrade, architecture]
date: 2026-10-03
---

# 비교 기준

공개 [openai/codex](https://github.com/openai/codex/tree/55b6f282a810c3146a1f79c7c2e6e919cc0aa974)의 2026-10-03 06:32 UTC 커밋 `55b6f282a810c3146a1f79c7c2e6e919cc0aa974`를 읽었다. 공개 범위는 Rust CLI/TUI/app-server이며 Desktop React 앱 전체가 아니다. 기능·실패 경계·상태 모델을 SSAK-AI의 기존 계약에 맞춰 흡수한다. Rust 코드를 복사하거나 Desktop 기능 동등성을 주장하지 않는다.

현재 작업 폴더의 HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`와 dirty source를 조사했다. 이전 코어 통합 PASS는 과거 검증이며 이번 변경 검증을 대신하지 않는다. 원본 프롬프트의 Constitution, Brain/Body 구분, 기록 보존, minimum sufficient context, 근거 기반 권한 경계를 유지한다.

# 기능별 결정

| 영역 | Codex의 근거 | 현재 SSAK-AI 근거 / 판단 | 이번 결정 |
|---|---|---|---|
| 응답·실행 정체성 | [event_mapping.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/event_mapping.rs#L362-L370), [turn.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/turn.rs#L293-L335) | ChatPage 실행은 프로젝트 epoch만 검사한다. 같은 프로젝트에서 세션을 바꾸거나 Stop 후 새 실행을 시작하면 이전 콜백이 현재 대화를 수정할 수 있다. | **MODIFY / P0**: 세션·프로젝트·실행 token을 결속하고 전환/중지 시 동기 무효화. 모든 늦은 콜백·복구·finalizer·대기 전송 차단. 서버 turn steer는 별도 보류. |
| 점진 응답·읽기 위치 | 같은 delta 근거, [plan_panel.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/tui/src/analytics/plan_panel.rs#L49-L64), [plan_tests.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/tui/src/analytics/plan_tests.rs#L78-L99) | SSE가 이미 있으나 currentAssistantContent를 화면에서 읽지 않아 완료 때만 답변 표시. messages 변경 시 무조건 끝으로 이동한다. TUI scroll 패턴을 브라우저에 그대로 복제할 수는 없다. | **MODIFY / P1**: 기존 sanitized renderer로 chunk 표시, 새 실행 buffer 초기화, 수동 스크롤 보존·최신 응답 이동. 브라우저 위치 추적은 로컬 구현. |
| 대기 입력의 소유권 | 안정적인 실행/item 정체성의 로컬 확장 | queueRef는 string[]이며 첨부는 공유 ref에서 실행 시 가져온다. 대기 입력 순서 변경·삭제 시 파일이 다른 입력으로 이동할 수 있다. | **MODIFY / P1**: text·첨부·owner를 가진 완전한 draft를 대기시킨다. bytes는 기록/localStorage에 저장하지 않는다. |
| 원본 보존 대화 분기 | [thread.rs fork](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L536-L568) | ConversationStore.fork는 잠금·CAS·원본 보존을 구현하고 테스트된다. client.forkConversation은 미사용이며 금지된 project_revision 본문이 주입될 수 있다. applyServerSnapshot은 현재 세션을 rename하므로 분기 채택에 부적합. | **NEW consumer / P1**: 기존 endpoint + canonical history 조회 + 새 세션 삽입으로 원본 보존. 실행 중 비활성·충돌/늦은 응답 보호·명령 팔레트 발견. 임의 턴 시점 분기는 endpoint 확장 없이는 제공하지 않는다. |
| 작업 재시도·중복 방지 | [common.rs request correlation](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/common.rs#L226-L247) | TaskSubmitRequest/TaskForkRequest와 runtime은 idempotency_key를 지원한다. dashboard submitTask/forkTask는 사용하지 않고 실패 후 pending을 버리며 입력도 미리 비운다. | **MODIFY / P1, 로컬 hardening**: 사용자 작업별 key·요청을 보존하여 응답 유실 재시도에서 서버 작업 하나를 선택. JSON-RPC ID 자체가 실행 중복 방지라는 upstream 주장은 하지 않는다. |
| 이력 복원 | [thread.rs resume](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L340-L374) | 서버 권위 이력·revision, 프로젝트 scoped cache, initial hydration이 구현되어 있다. 비동기 history 응답의 세션 소유권 검사는 부족하다. | **KEEP + MODIFY**: 기존 이력 재사용; late-history 및 cancelled conversation 재방문 정합성은 실행 보호 작업에 포함. |
| 계획·도구 출력·승인·작업 분기 | typed item/turn 및 기존 실행 primitive | task-execution projection, agent tree, checklist, terminal output, approval queue, 서버 task lifecycle/fork가 이미 있다. | **KEEP**: 새 모방 저장소/승인 레이어를 만들지 않고 회귀 검증. |
| 구조화된 사용자 질문 | [item.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/item.rs#L1745-L1803), [ordered resolution](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server/src/thread_state.rs#L228-L257) | 현재 SmartBreakpointGate는 옵션을 텍스트로 출력하고 approval은 approve/deny/always_allow다. 질문·응답 영속 DTO/상관관계는 새 계약이 필요하다. | **DEFER**: request/answer ID, owner/권한, 취소/만료/재시작 replay, 이벤트 순서와 Brain의 의미 판단 경계부터 ADR 작성 후 별도 구현. 승인 수를 늘리는 방식으로 대체하지 않는다. |
| MCP 구조화/미디어 결과 | typed item 접근의 확장; 동일기능을 upstream에서 직접복제한다고 주장하지 않음 | mcp_tool_result는 structured_content/partial/blocks를 보존하나 tool_loop completion과 UI는 일부 텍스트만 전달한다. | **DEFER**: bounded validated result DTO·미디어 descriptor·partial/error·provenance를 backend delivery부터 연결해야 한다. 대화 스타일 변경으로 해결되지 않는다. |
| context 압축·출력 예산 | [compact.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/core/src/compact.rs#L314-L329), [response_history.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/tools/src/response_history.rs#L36-L70) | 기존 canonical conversation compaction·context assembler·budget·provenance가 있으므로 일괄 재작성의 근거가 없다. | **KEEP / CONDITIONAL**: 실제 overflow/대규모 tool 결과 측정 후 ephemeral context만 조정. canonical 경험 기록을 지워 예산을 맞추지 않는다. |
| archive / lifecycle / rollback | [archive guard](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/tui/src/resume_picker/archive.rs#L46-L89), [notifications](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/common.rs#L1934-L1944), [revert](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L1273-L1296) | 현재 UI의 delete는 로컬 목록 동작이며 durable archive/restore는 별도 서버 계약이 필요하다. 역사 수정은 원본 코어 방침과 충돌한다. | **DEFER archive / REJECT destructive rollback**: 먼저 tombstone·복구·owner·audit 계약. 새로운 이해/분기를 덧붙이는 방향 유지. |
| 전용 코드 review | [review.rs](https://github.com/openai/codex/blob/55b6f282a810c3146a1f79c7c2e6e919cc0aa974/codex-rs/app-server-protocol/src/protocol/v2/review.rs#L14-L66) | 현재 change panel/approval과 개발 에이전트 리뷰는 있지만 제품의 first-class review target/session 계약은 별도다. | **DEFER**: 실제 사용자 수요와 target DTO·read-only 도구 프로필·보고서 provenance 정의 후 추가. 모델 평가자를 상위 권위로 승격하지 않는다. |

# 구현 경계와 다음 실행자가 지킬 조건

이번 작업의 상세 인수 조건·담당은 [실행계획](CODEX_FUNCTIONAL_UPGRADE_PLAN_2026-10-03.md)에 있다. backend의 기존 계약을 소비하는 작은 기능과 실제 발견된 race를 먼저 고친다. 보류 항목은 구현 누락이나 기존 코어 미완료라는 뜻이 아니며, 새 계약/측정이 필요한 다음 후보이다.

다음 작업은 현 소스와 최종 QA manifest를 다시 읽고 시작한다. 수정된 파일의 과거 PASS를 재사용하지 않는다. 새 기능은 command palette와 기존 typed execution projection을 우선 연결하며, 정보가 없을 때 synthetic success나 권한을 표시하지 않는다.
