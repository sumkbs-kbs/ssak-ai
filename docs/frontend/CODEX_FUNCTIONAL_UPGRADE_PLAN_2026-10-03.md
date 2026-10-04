---
title: Codex 기능 비교 및 SSAK-AI 개선 실행계획
tags: [frontend, codex, functional-upgrade, execution-plan]
date: 2026-10-03
---

# 목적과 기준

현재 작업 폴더의 최신 소스를 기준으로 공개 openai/codex의 기능·실패 처리·상태 모델을 대조한다. 기존 SSAK-AI Constitution, Brain/Body 책임 경계, Files-first/Git-first, 승인·권한·현재 상태와 기록 보존 계약은 유지한다. 이미 완료한 화면/폰트 개선을 중복 구현하지 않는다.

| 단계 | 상태 | 확인 기준 | 담당 |
|---|---|---|---|
| 1. 공개 소스와 현재 기능 정밀 비교 | completed | upstream SHA·근거 링크, 현재 함수/계약/테스트, 실제 기능 공백 목록 | 연구·프론트엔드·런타임 감사 에이전트 + 리더 |
| 2. 개선 항목과 상세 인수 조건 확정 | completed | 아래 인수 조건과 담당, 공개 소스 비교 기록 | 리더 |
| 3. 기능 구현 및 관련 회귀 검증 | completed | 109개 파일·1,088개 테스트, TypeScript, 생산 빌드 통과 | 구현 에이전트 + 리더 |
| 4. 실제 실행과 독립 통합 검토 | in_progress | 실제 화면/행동, 현재 소스에 결속된 검토와 결과 | 리더 + 검토 에이전트 |
| 5. 인수 기록과 계획 갱신 | pending | 구현 결과·남은 개선 후보·검증 한계·재개 기준 | 리더 |

현재 작업 트리에는 기존 사용자 작업과 이전 수정이 다수 존재한다. 변경 대상은 구현 직전 원문/해시를 보존하고, 해당 작업의 diff를 기준으로 검토한다. 이전 PASS는 수정된 소스의 현재 승인으로 재사용하지 않는다.

## 확정한 범위와 인수 조건

Upstream: `55b6f282a810c3146a1f79c7c2e6e919cc0aa974` (2026-10-03 06:32 UTC). 현재 HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` + 작업 트리. 구현 전 dashboard 원문은 `docs/qa/2026-10-03-functional-upgrade/baseline/dashboard-before.tar`, SHA-256 `be88253900d5cf0d543add74b712532b2955fad405da174e5712d7f9b8455689`.

| 우선순위 / 범위 | 담당·소유 파일 | 필수 인수 조건 |
|---|---|---|
| P0 대화 실행 소유권 + 점진 출력 | stream 구현: ChatPage 실행 영역, 새 실행 hook/소유권 유닛, 관련 테스트 | 동일 프로젝트 내 전환/생성/삭제, Stop→새 전송, 늦은 chunk/snapshot/error/finally가 다른 대화·새 실행을 바꾸지 않는다. 대기 입력은 원래 실행에 속하며 전환·중지 시 자동 전송되지 않는다. 부모 실행 실패·CAS 충돌 때는 대기 메시지와 첨부를 유지하고 자동 전송을 멈춘다. SSE chunk가 완료 전에 보인다. 사용자 스크롤을 빼앗지 않는다. |
| P1 서버 대화 분기 | fork 구현: 별도 hook/액션, chatStore 새 세션 삽입 API, fork client 계약, 관련 테스트. ChatPage 연결은 리더가 통합 | 원본 ID·이력·제목 보존. 서버 CAS로 분기 생성 후 새 이력을 읽고 revision 0에서 이어간다. 잘못된 project_revision 본문 제외. 실행/압축/분기 중 비활성. 대화/프로젝트 전환 후 결과를 현재 대화에 채택하지 않는다. 충돌·실패를 알린다. 명령 팔레트에서 발견 가능. |
| P1 작업 제출·분기 재시도 | task 구현: taskExecutionApi, useTaskExecutionEvents, TaskQueuePanel, 새 작동 유닛, 관련 테스트 | 사용자 작업마다 새 key. 응답 유실 후 같은 요청·key로 명시적 재시도하면 서버 작업 1개를 반환·선택한다. 다른 프로젝트나 변경된 입력에 이전 key를 사용하지 않는다. 실패 시 입력과 재시도 대상을 보존한다. |

리더는 설계 계약·기능 비교 문서·화면 연결·실제 실행·최종 검토와 증거를 담당한다. 각 구현은 다른 담당 파일을 덮어쓰거나 기존 사용자 수정을 되돌리지 않는다. 새 backend 프로토콜, Constitution/권한 변경, 기록 rollback은 이번 범위에 없다.
