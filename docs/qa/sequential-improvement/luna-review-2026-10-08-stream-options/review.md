---
title: Luna 스트리밍 옵션 수정 검수 및 원장 유실 판정
tags: [ssak-ai, imp-09, review, evidence, incident]
date: 2026-10-08
---

# 판정

현재 작업 폴더와 보존된 실행 자료를 직접 대조했다. `IMP-09-C-STREAM-OPTIONS-01`의 최소 코드 수정과 오프라인 회귀는 검수 범위에서 수용한다. 이 판정은 실제 provider 재호출, Uvicorn/lifespan, 전체 suite 또는 전체 IMP-09의 승인을 뜻하지 않는다. 추가 모델 추론이나 테스트를 실행하지 않았다.

별도로, 기존 실행·변경 원장의 유실은 미해결이다. 두 원장 모두 현재 새 행 1개만 남아 있다. 과거 22/21행이라는 개수는 기존 STATUS/tasks와 사고 보고에 따른 값이며, 잃어버린 원문을 직접 세어 재검증하지는 못했다. 원장 복구와 다른 독립 기능 사례의 진행을 별도 작업으로 관리한다.

## 수용한 코드와 근거

| 항목 | 직접 확인한 결과 |
| --- | --- |
| 제품 변경 | create_message → _stream_events → stream_generate_async에 max_tokens/temperature 전달 |
| 0 보존 | temperature=0, 양수 0.35, 생략 시 API 기본값 1.0을 각각 회귀에서 확인 |
| 수정 전 | 같은 selector 37건 중 실패 3 / 통과 34, exit 1 |
| 수정 후 | 같은 selector 37/37 통과, exit 0 |
| 영향 회귀 | 별도 streaming/provider fixture 16/16 통과, exit 0 |
| provider payload | mock transport가 만든 Ollama options의 num_predict=64 / temperature=0 검사 |
| 정적 검사 | 보존된 Ruff exit 0, basedpyright 오류 단계 exit 0 로그 확인 |
| KG | 보존된 validator 출력 OK=true, DB 전후 SHA 동일; 재실행하지 않음 |

실제 route와 SSE generator, async wrapper를 거쳐 fake manager에 도달하는 회귀를 확인했다. provider payload 검사는 별도 mock transport 사례이며 실제 수정 후 Ollama wire를 관측한 결과가 아니다. 기본 경고 단계 basedpyright의 47 warnings/exit 1은 Luna 보고에 남아 있으며 전체 타입 검사가 깨끗하다는 주장으로 바꾸지 않는다.

현행 네 파일의 SHA-256이 수정 후 기록과 일치한다.

| 파일 | SHA-256 |
| --- | --- |
| src/antigravity_k/api/routes/messages_api.py | d27a89eb248d6036a21d10b4de50cfbd212578878e6c3d76c1133aa0708e79b2 |
| tests/test_messages_api.py | 23cc04dca43bbe02529e81996486e4c86d7dc0899cfd99bad608e0a7a560a289 |
| tests/test_messages_streaming.py | 05b80703a820b3d10787c0258b1d3fdd480186897da509ab0414b05937b3b98c |
| tests/test_inference_providers.py | de605dade997ac9d25700f809e7ab015915160cbe8d82480c12517c96774078e |

근거: [제품 코드](../../../../src/antigravity_k/api/routes/messages_api.py:242), [전달 회귀](../../../../tests/test_messages_api.py:91), [수정 전 receipt](../luna-handoff-2026-10-07/raw/IMP09C-STREAM-OPTIONS-01/before-20261008T/receipt.json), [수정 후 receipt](../luna-handoff-2026-10-07/raw/IMP09C-STREAM-OPTIONS-01/after-20261008T/receipt.json), [영향 회귀 receipt](../luna-handoff-2026-10-07/raw/IMP09C-STREAM-OPTIONS-01/impact-20261008T/receipt.json), [결과 요약](../luna-handoff-2026-10-07/raw/IMP09C-STREAM-OPTIONS-01/summary.json), [patch](../luna-handoff-2026-10-07/diffs/IMP-09-C-STREAM-OPTIONS-01.patch).

## 원장 사고와 복구 조사

| 원장 | 현재 보존 상태 | 현재 SHA-256 |
| --- | --- | --- |
| runs.jsonl | 새 실행 1행, 3,820 bytes, 마지막 LF 없음 | 850cdaa3a1223084ee628caad465b9672663233437d63eeb68da48c235c4cb98 |
| changes.jsonl | 새 변경 1행, 3,488 bytes, 마지막 LF 없음 | 4981745fd5ff85378124cee030175b7dc8d9c13a511d27137fcafd5118087eed |

덮어쓰기 전 파일의 SHA-256은 테스트 격리 실행의 [checkout manifest](../luna-handoff-2026-10-07/raw/IMP09C-STREAM-OPTIONS-01/before-20261008T/checkout-manifest.json)에 남아 있다.

- runs.jsonl: `e971718b5d014ccbe48472b48fe5cbd8c465be3e6324acff503be6b71aa00cbe`
- changes.jsonl: `edfab9713d1e62c97093259c5b5c3f79a8897df7c68ea2966e2d152181b4d7f0`

세 격리 실행의 manifest는 이 해시를 보존하지만, cleanup으로 삭제된 checkout의 파일 본문을 대신하지 못한다.

읽기 전용 조사 범위:
1. 기존 handoff/격리 실행 자료와 Git 추적 여부, 이전 검수 자료.
2. coding-agent-sessions 검색기: Codex 및 지원 플랫폼의 task/path 검색.
3. Codex state/history SQLite: 해당 저장소 세션 및 task/원장 경로와 일치하는 tool 기록.
4. OpenCode SQLite의 해당 프로젝트 세션, 로컬 snapshot의 worktree와 현재 index.

확인한 위치에서 위 두 시작 해시에 일치하는 원문을 확보하지 못했다. 모든 저장 장치·클라우드·과거 snapshot 객체를 전수 조사했다는 뜻은 아니다. 원문 복구는 `NOT_RECOVERED`로 유지한다. 보고서, stdout 일부, 기억으로 과거 JSONL 행을 재작성하지 않는다.

현재 남은 두 새 행은 [보존 파일](surviving-ledger-snapshot.json)의 raw_text에 UTF-8 문자열 그대로 보관했다. 마지막 줄바꿈까지 원본 형태를 보존하며 원장 복구본으로 명명하지 않았다. 향후 정확한 백업을 찾으면 먼저 별도 파일에서 해시를 확인하고, 현재 새 행과 충돌하는 run/change ID를 확인한 뒤 통합한다.

## 남은 기능과 다음 작업

- 전체 IMP-09: PARTIAL. 기존 parent 집계 2 DONE / 9 PARTIAL / 8 NOT_RUN / 2 OPTIONAL은 기존 자료의 집계이며 이번 검수로 21개 전체를 다시 승인하지 않았다.
- US-01: embedding-only 모델을 chat 경로에 지정했을 때 명확한 unsupported 오류를 내는지 아직 검증되지 않았다.
- TOOL-01: 기록된 SSE content-block lifecycle 결함이 열린 상태다. 이번 옵션 전달 수정으로 해결됐다고 볼 수 없다.
- 수정 후 실제 provider wire와 외부 Uvicorn/lifespan, 남은 capability matrix는 미검증이다.
- 기존 STATUS/tasks에는 원장 복구를 기다린다는 문구와 과거 원장이 보존됐다는 낡은 문구가 함께 있다. 그 파일들을 이번 검수에서 덮어쓰지 않았다.

다음 실행은 [US-01 전용 프롬프트](../../../ssak-ai-core/GPT6_LUNA_US01_AFTER_LEDGER_INCIDENT_2026-10-08.md)를 사용한다. 기존 공용 원장은 동결하고 새 실행 전용 디렉터리에 기록한다. 원장 복구의 미해결 상태는 계속 공개하며 기능 검증을 무기한 백업 대기로 묶지 않는다.

이 검수에서 제품 소스, 공용 STATUS/tasks/runs/changes, 기존 raw evidence를 수정하지 않았고 commit/push하지 않았다.
