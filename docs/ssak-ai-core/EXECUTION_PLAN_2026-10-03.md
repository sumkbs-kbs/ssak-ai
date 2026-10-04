---
title: "SSAK-AI 최신 작업 인수와 잔여 수정 계획"
date: 2026-10-03
status: completed-supported-integration
tags: [ssak-ai, handoff, verification]
---

# 최신 작업 인수와 잔여 수정 계획

기준 HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` + 현재 staged/unstaged/untracked 작업. 사용자 변경은 보존한다. 헌법·기본 방침은 변경하지 않는다.

## 이번 작업의 범위

9월 27일 실제 모델 v8·ablation 및 56,961건 migration 검증은 당시 동결 소스의 증거로 유지한다. 이를 반복 개발하거나 현재 모든 파일의 PASS로 자동 승계하지 않는다. 10월 1일 후속 통합 XML은 1,126건 중 12 failures, 1 skip을 기록했다. 11건은 digest/marker 게이트 연쇄 실패이고, 나머지 1건은 Docker daemon 연결 실패다. 10월 3일 대화 view 최신성 red 기록도 별도 존재한다.

## 담당과 실행 순서

| 단계 | 담당 | 인수 조건 | 상태 |
|---|---|---|---|
| 최신 문서·실패 기록 대조 | 리더 + current_docs_audit | 과거 완료와 현재 잔여 작업 분리 | 완료 |
| 지연 view 저장 수정 | residual_view_fix | public read 수렴, peer 삭제·최신 turn 보존, 실패 재시도, bounded coalescing; 관련 회귀 + 실제 library driver | 완료: 관련 suite 68 passed, 기존 F2 계약 10 passed |
| 증거 digest 재검증 | evidence_reconcile | 변경된 범위 실제 재검증 후 digest 기록; 기존 baseline/판정 기준 보존 | 완료: 470 passed, source 전후 변경 0; 사용자 digest 작업 보존 |
| 통합 인수 | 리더 + 독립 검토자 | 수정 소스 해시, 실제 표면 결과, 재검증 및 한계 기록 | 완료: view 수정 범위 독립 PASS, 리더 직접 driver exit 0; 전체 통합 재실행 아님 |
| 문서 최종 정합화 | 리더 | 최신 진입점·체크리스트·후속 작업을 실제 결과와 일치 | 완료: 최신 진입점·범위·증거 연결 |

## 완료 체크리스트

- [x] 최신 사용자 작업을 기준으로 범위를 정하고 중복 구현을 배제했다.
- [x] 대화 view의 데이터 유실·삭제 부활·최신성 결함을 닫았다.
- [x] 수정된 범위의 테스트·실제 사용 검증 및 독립 검토 결과를 남겼다.
- [x] digest 갱신은 실제 재검증한 범위에만 적용했다.
- [x] 이전 전체 PASS와 이번 scoped 결과를 구분하고 미실행·환경 제한을 기록했다.
- [x] 다음 에이전트가 사용할 최신 진입점을 갱신했다.

운영 effect enablement, destructive cutover, CR-14 승인과 확증 실험의 새 표본 등록은 이번 수정의 완료 조건으로 추가하지 않는다. 글로벌 ACTIVE나 권한을 자동 활성화하지 않는다.

## 현재 검증 근거

- [리더 최종 증거 게이트](../qa/2026-10-03-residual-close/leader-evidence-gate.md): `scripts/evidence_gate.py --tier fast` exit 0, 9/9 stages PASS. full tier의 release_artifacts·regression_ledger 2개는 이번 실행 범위 밖이며 통과로 세지 않는다.
- [수정·회귀 보고서](../qa/2026-10-03-residual-close/VIEW_WORKER_REPORT.md): 68 passed(최신성 계약 13건 포함), 별도 기존 F2 계약 10 passed, Ruff·Basedpyright 통과. 최초 import 옵션으로 인한 실패 실행과 정상 재실행 결과를 구분했다.
- [독립 검토·실제 별도 프로세스 검증](../qa/2026-10-03-residual-close/independent-review.md): 72회 교대 append의 최대 view 지연 7(<8), peer 삭제·최신 쓰기 보존, 재시도·읽기 시험 9 passed. 이 9건은 다른 suite와 겹치므로 합산하지 않는다.
- [리더 직접 실행](../qa/2026-10-03-residual-close/leader-manual.txt): `uv run --no-sync python docs/qa/2026-10-03-residual-close/view_worker_driver.py` exit 0. 임시 저장소에서 append→peer append→stale flush 및 peer delete→stale flush를 확인했다.
- [증거 정합화 보고서](../qa/2026-10-03-residual-close/evidence-reconciliation.md): 사용자 digest 변경 보존, 실제 재검증과 historical pins 구분.
- 선행 scoped 검증 당시 Docker는 연결되지 않았다. 아래 최종 계속 작업에서 연결을 복구하고 실제 Docker·전체 통합 검증을 완료했다.
- [최종 통합 인수](../qa/2026-10-03-residual-close/FINAL_INTEGRATION_REVIEW.md), [전담 QA](../qa/2026-10-03-residual-close/FINAL_WHOLE_QA.md), [독립 인수 감사](../qa/2026-10-03-residual-close/FINAL_ACCEPTANCE_AUDIT.md): 1,193 passed / 1 intentional skip / 0 failures·errors, full 게이트 11/11 PASS, 전후 소스·문서 일치.

## 다음 에이전트의 시작점

지원 범위의 잔여 구현·전체 통합 검증 큐는 닫혔다. 동일 view 수정·기존 live pilot·migration을 다시 개발하지 않는다. 다음 에이전트는 최종 통합 보고서의 현재 소스 manifest와 실제 범위를 먼저 확인한다. 새 소스 변경은 영향을 받는 시험·증거를 다시 검증하고, 새 기능이나 운영 전환은 목표가 정해졌을 때 별도 카드로 등록한다. 변경이 없으면 완료된 전체 회귀를 반복하지 않는다.

## 최종 통합 계속 작업 — 사용자 요청

사용자가 남은 전체 통합 검증 완료를 요청했다. 기존 Docker Desktop을 기동하여 실제 sandbox 시험을 복구하고, 과거 1,126건의 cognitive/runtime/CLI 통합 범위와 이번 conversation 수정 범위를 현재 소스에서 검증한다. 이후 full 증거 게이트·실제 HTTP/재시작 표면 확인 및 소스 대응 확인으로 최종 인수 문서를 갱신한다.

| 단계 | 담당 | 상태 | 인수 조건 |
|---|---|---|---|
| Docker 복구·실제 보호 경계 시험 | 리더 | 완료 | server 29.8.0 응답, 보호 쓰기 거절·허용 쓰기 성공, 전체 XML 해당 node PASS |
| 전체 통합 회귀 | 전담 QA | 완료 | 기존 1,126건 + conversation 68건, 1,193 passed / 1 intentional skip / 실패 0, exit 0 |
| full 증거 게이트와 실제 표면 | 리더 | 완료 | full 11/11 PASS, 실제 HTTP401/최초1/재시작0, source1505·docs380 실행 중 해시 일치 |
| 최종 인수 판정·문서 갱신 | 리더 + 독립 확인 | 완료 | 독립 XML·범위·Docker·해시 대조 PASS, 최신 상태·계획·체크리스트 반영 |

- [x] 현재 소스로 전체 통합 인수 결과를 확정했다. 적용되지 않는 공통 계약 self-probe 1건과 기존 경고 1건은 정확히 기록했다.
- [x] Docker 장애 이월을 해소했다. 실제 Docker 시험을 skip 없이 검증했다.
- [x] 지원 범위의 마지막 미완료 검증 큐를 닫고 다음 에이전트의 시작점을 갱신했다.

최종 상태 문서 편집 후 검사는 [최종 문서 게이트](../qa/2026-10-03-residual-close/final-doc-gate.md)에 별도로 기록한다. 전역 ACTIVE·파괴적 cutover·운영 서명은 이번 개발·통합 인수의 완료 조건에 추가하지 않는다.

## 실행 후 대화 503 복구 — 사용자 요청

코어 개발 인수와 실제 사용자 저장소의 운영 준비를 구분한다. 실제 사용자 저장소의 legacy 대화 4개를 원본 보존·백업 후 이전했다. 별도로 125B 모델의 실제 Metal OOM을 확인했고, 사용자가 설치된 qwen3.8 27B로 전환하도록 승인했다. 인증·기본 방침은 유지한다.

| 단계 | 담당 | 상태 | 인수 조건 |
|---|---|---|---|
| 실제 503 원인 구분 | 리더 + chat_503_trace | 완료 | 실제 브라우저 재현, 저장 상태 legacy_requires_migration, 이전 후 503 해소 |
| 원본 보존 이전 | 리더 + 독립 대조 | 완료 | dry-run 충돌 0, 서비스 정지, 4개 원본·백업 해시 일치, verify-only verified |
| 27B 실제 모델 응답 | 리더 | 완료 | qwen3.8:latest, 실제 응답 “정상 연결입니다.”, Ollama HTTP200·비영 토큰 |
| 모델 선택 재접속 유지 | model_choice_persist | 완료 | red 4건 재현 후 관련 회귀 23 passed, typecheck 통과, 실제 새로고침·호스트 재시작 후 27B 유지 |
| 신규 사용자 기본 추천 | configured_model_default | 완료 | 설정된 reasoning 기본값·별칭 우선, HTTP 회귀 13 passed, 125B 명시 선택과 기존 fallback 보존 |
| 최신 번들·최종 대화 결과 기록 | 리더 + 독립 화면 검토 | 완료 | 대시보드 938 passed·build exit 0, 재시작 후 실제 답변·Ollama HTTP200, 4개 최신 상태 독립 Pass A/B PASS·차단 0 |

관련 Python 저장소·API 시험은 격리 환경에서 32 passed, 1 existing warning이다. 격리 전의 sandbox 오류 두 실행은 최종 PASS로 세지 않고 별도 기록한다. 모델 설정 수정 전에는 기존 source manifest 1,505개가 모두 일치했다. 생성 번들을 다시 빌드한 뒤에는 새 파일 대응과 대시보드 검증을 별도로 기록하며 이전 전체 PASS를 새 번들의 검증으로 자동 승계하지 않는다.

- [x] 실제 사용자 저장소 503과 125B Metal OOM을 구분해 복구했다.
- [x] 대화 원본·백업 4개 보존 및 승인한 27B의 실제 응답을 확인했다.
- [x] 새로고침·호스트 재시작 후 27B 모델 선택을 유지하고 신규 기본 추천을 검증했다.
- [x] 최신 source·bundle·캡처 해시와 독립 검토 결과를 대응했다.

최종 근거는 [실제 대화 복구 보고서](../qa/2026-10-03-chat-503/REPORT.md)와 [독립 기능·화면 검토](../qa/2026-10-03-chat-503/INDEPENDENT_REVIEW.md)다. backend 관련 suite의 기존 config 사본 불일치 1건은 단독 재현·미수정으로 명시했다. native 화면 권한, 다른 viewport 및 활성 대화 자동 복원은 이번 복구의 검증 범위에 포함하지 않는다. 프로그램은 최신 번들·수정 route로 실행 중이다.
