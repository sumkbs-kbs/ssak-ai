---
title: "SSAK-AI 실제 대화 503 복구 및 27B 검증"
date: 2026-10-03
status: completed-scoped-recovery
tags: [qa, chat, recovery, model-preference]
---

# 실제 대화 복구

실행 중인 사용자 저장소의 이전 누락과 125B 추론 메모리 부족을 각각 확인하고 복구했다. 사용자가 승인한 `qwen3.8:latest` 27.3B 모델에서 실제 답변을 받았다. 마지막 호스트 재시작 뒤에도 모델 선택이 유지됐고, 최신 대시보드 번들에서 대화가 완료됐다. 기본 방침·인증·전역 ACTIVE·사용자 기존 작업은 변경하지 않았다.

## 원인과 조치

1. 실제 브라우저에서 `exceeded retry limit — Server returned 503`을 재현했다. 실제 `ConversationStore` 상태는 `legacy_requires_migration`이었다. 대화 기록을 읽는 단계에서 이전 요구 오류가 발생했다.
2. 공식 CR01 절차로 dry-run 충돌 0을 확인한 뒤 소유한 프로그램/API를 정지하고 원본 보존 이전을 수행했다. 기존 대화 4개의 v2 사본과 journal backfill을 만들었으며 verify-only는 `verified`였다. 원본 삭제나 파괴적 cutover를 수행하지 않았다.
3. 저장소 이전 뒤 125B 요청은 실제 Ollama 추론까지 진행했으나 Metal `Insufficient Memory`로 종료됐다. 초기 provider 경로 추측은 이 실제 실행 근거로 기각했다.
4. 사용자가 설치된 qwen3.8 27B로 전환하도록 승인했다. UI에서 27B를 선택한 뒤 응답을 확인했다. 취소된 이전 요청 뒤 첫 전송은 stale revision 409로 동기화됐으며, 재전송한 27B 대화는 성공했다.
5. 새로고침이 125B 선택으로 돌아가는 별도 결함을 수정했다. `chatStore`가 선택 모델을 `agk_chat_selected_model`에 저장하고 세션 캐시 유무와 관계없이 복원한다. 기본값 추천 API도 설정된 reasoning 프로필과 발견된 로컬 모델의 별칭을 우선 대응한다. 125B는 계속 명시적으로 선택할 수 있으며, 설정된 모델이 없으면 기존 fallback을 유지한다.

## 사용자 데이터 보존

백업: `/Users/mr.k/.antigravity/conversations.migration-backup-20261002T234359Z`.

최종 대화 뒤에도 원본 4개와 백업 4개가 이전 전 SHA-256과 모두 일치했다. [보존 확인](migration-preservation-receipt.json)에 집계만 기록했다. 개별 대화 ID·본문·인증 정보는 이 QA 기록에서 제외했다. 원본 상세와 이전 도구의 원시 보고서는 `/private/tmp/ssak-chat-503-20261003/`에 유지한다. 이미 압축된 QA 대화 1개는 이전 검증에서 `history_incomplete=true`였으므로 모든 과거 이력이 완전하다고 주장하지 않는다. 이전 전 journal 1개가 별도로 존재했고, 이번 backfill은 4개다.

## 현재 소스와 검증

기준 HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`와 현재 사용자 작업이다. 커밋·staging은 수행하지 않았다.

| 수정·검증 범위 | 결과 | 증거 |
|---|---|---|
| 모델 선택 저장·복원 | red 4건 실패 후 관련 5개 파일 23 passed; `pnpm typecheck` exit 0 | [작업 보고서](model-preference-report.md), [패치](model-preference.diff), red/green/typecheck 로그 |
| 설정된 기본 모델 추천 HTTP 계약 | red 8건 실패·fallback 5건 통과 후 13 passed | [작업 보고서](backend-model-default-report.md), [패치](backend-model-default.patch), [focused 결과](backend-model-default-focused.txt) |
| 모델 레지스트리·발견·정책 관련 suite | 66 passed, 기존 설정 사본 불일치 1 failed | [결과](backend-model-default-green.txt), [단독 재현](backend-model-default-config-drift.txt) |
| Python 대화 저장소·권위 API 관련 3개 모듈 | 32 passed, 기존 Starlette 경고 1개 | [결과](related-tests-final.txt), [XML](related-tests-final.xml) |
| 전체 대시보드 | 94개 파일, 938 passed | [결과](dashboard-tests.txt) |
| 최신 대시보드 production build | exit 0; 기존 대용량 chunk 경고 | [빌드 로그](dashboard-build.txt) |
| 변경된 Python route | Basedpyright 0 errors/warnings/notes; Ruff·format·컴파일·diff check 통과 | [타입 결과](backend-model-default-types.txt), 작업 보고서 |

기존 실패는 `tests/test_model_registry.py::test_bundled_default_config_matches_repository_default`다. 패키지의 `src/antigravity_k/config.yaml`에 추가 search 항목이 있고 두 설정 파일은 이번 작업에서 수정되지 않았다. 단독 실행에서도 같은 실패를 확인했다. 이 실패를 PASS로 합산하지 않는다.

Python 첫 실행은 sandbox의 사용자 홈 GBrain lock 접근 제한으로 수집에 실패했다. 두 번째 실행은 부모 프로세스만 격리되어 spawn 시험 1건이 실패했다. 최종 실행은 임시 `SSAK_QA_HOME`과 `sitecustomize.py`로 부모·spawn 모두 격리했다. 시스템 `HOME`은 변경하지 않았고 운영 프로세스에 helper를 주입하지 않았다. 실패 시도 로그도 별도로 보존했다. TypeScript skill checker의 실제 로그는 caller project에서 `typescript`를 resolve하지 못했다는 오류다. 최초 작업 보고서의 TS7 API 불일치 표현은 독립 검토 지적 후 로그에 맞게 정정했다. 프로젝트 자체 typecheck는 통과했다. 재현에 사용한 helper 내용은 [텍스트 증거](test-isolation-helper.txt)에 보존했다.

[현재 소스 해시](current-source-hashes.json), [현재 번들 해시](current-bundle-hashes.json), [기존 코어 manifest 대조](prior-core-source-delta.json)를 기록했다. 기존 1,505개 manifest 항목 중 변경은 route 1개와 재생성 번들 항목 23개뿐이며 예기치 않은 다른 변경은 0이다. 새 회귀 파일과 프런트엔드 저장소 수정은 별도 해시에 포함했다. 과거 1,193건의 전체 코어 PASS를 이번 새 route·번들의 전체 재검증으로 자동 승계하지 않는다. 각 suite는 중복되므로 건수를 합산하지 않는다.

## 실제 화면과 추론 검증

마지막 재시작한 API PID는 `31860`이었다. 공개 `/health`는 `status=ok`, 실제 대화 뒤 reasoning backend `qwen3.8`가 등록됐다. 인증 없는 `/api/health` 요청은 401이며 인증을 우회하지 않았다.

Codex 브라우저의 `http://127.0.0.1:8000/`에서 다음을 직접 확인했다.

- 사용자 PIN 해제 후 실제 503을 재현했다.
- 최신 번들 `assets/index-Bh-w7yNi.js`를 확인했다. [실제 페이지 script URL](live-bundle.json)과 현재 번들 해시를 대응했다.
- 새로고침 및 호스트 재시작 뒤 모델 표시가 `qwen3.8:latest (27.3B)`로 유지됐다.
- 모델 목록에서 27B가 현재 선택이고 125B도 목록에 남았다.
- 입력 `재시작 후 연결 확인입니다. 정상 연결이면 한 문장으로 알려 주세요.`를 실제 전송했다.
- 생성 진행 상태에서 최종 응답 `정상 연결입니다.`로 전환됐으며 오류 alert나 생성 중단 상태가 남지 않았다. [최종 DOM](chat-success-dom.txt)에는 표시 토큰 In 35 / Out 9가 있다. 이는 UI 표시값이며 upstream 정밀 계측과 같다고 주장하지 않는다.
- Ollama `2026/10/03 09:10:33 POST /api/chat`는 HTTP 200, 18.213초였다. [런타임 발췌](ollama-runtime-excerpts.txt)는 오류와 성공의 진단 행만 포함한다.
- 마지막 새로고침 이후 경고·오류 콘솔 행은 0이다. 이전 호스트 정지 중 발생한 fetch 오류는 별도 과거 행으로 구분했다. [콘솔 확인](final-console.json)

![27B 실제 대화 성공](chat-success.jpg)

## 화면 QA 범위와 한계

대상은 chat 페이지 1개, 실제 브라우저 기본 크기 757×954, 패널을 닫은 4개 상태다: [준비](ready-27b.jpg), [모델 목록](model-list.jpg), [생성 중](chat-in-progress.jpg), [완료](chat-success.jpg). layout·CSS는 수정하지 않았다. 이전 모델 초기화 캡처와 패널이 열린 재시작 진단 캡처는 배경 증거이며 픽셀 일치 목표가 아니다.

[캡처 metadata](capture-metadata.json)로 JPEG signature·크기·해시를 확인했다. PNG 전용 diff CLI에 JPEG를 넣은 최초 시도는 실패했다. 원본 JPEG를 보존하고 두 상태의 인코딩만 PNG로 변환하여 [상태 차이 JSON](chat-state-diff.json)을 생성했다. 91/100 similarity와 23 hotspots는 생성 중→응답 완료의 내용·상태 변화를 설명하기 위한 참고이며 디자인 충실도 PASS 점수가 아니다. 투명 배경 요구가 없는 RGB 캡처다.

macOS native Electron 화면 제어는 접근성·화면 기록 권한 대기 때문에 확인하지 못했다. 실행 중인 동일 API·번들의 브라우저 화면에서 검증했다. 브라우저 viewport capability도 제공되지 않아 다른 크기 검증은 하지 않았다. 좁은 화면에서 기존 환경 패널을 열면 대화 일부가 가려지며, 최종 대화는 패널을 닫은 상태에서 검증했다. 선택 복원과 신규 추천의 결정적 계약은 회귀 테스트로 검증했으며 실제 native profile의 최초 추천을 직접 캡처했다고 주장하지 않는다. 활성 대화의 새로고침 자동 복원은 이번 완료 범위가 아니다.

독립 Pass A(기능·구현)와 Pass B(화면·한글)는 모두 HIGH confidence PASS, BLOCKING 0이다. 두 검토자가 현재 4개 캡처를 모두 직접 열고 소스·번들·캡처 해시 및 실제 대화 증거를 대조했다. [독립 검토 기록](INDEPENDENT_REVIEW.md)에 현재 dirty 소스 대응과 범위·한계를 기록했다. 선택 복원, 125B 명시 선택 보존, 설정된 기본값 별칭 및 기존 fallback, 실제 응답과 한글 표시를 인수했다.

## 완료 확인

- [x] 실제 503 재현과 사용자 저장소 상태를 대응했다.
- [x] 충돌 없는 이전과 원본·백업 4개 보존을 검증했다.
- [x] 승인한 27B의 실제 대화를 마지막 재시작 뒤 확인했다.
- [x] 모델 선택 복원과 신규 기본 추천을 failing-before/passing-after 계약으로 검증했다.
- [x] 최신 번들·변경 소스·전체 대시보드 검사 및 독립 화면 인수를 대응했다.
- [x] 기존 실패와 미검증 표면을 제외하고 계획서를 완료 상태로 정리했다.

[최종 산출물 확인](final-artifact-check.json)에서 현재 소스·번들 해시 및 문서 링크를 다시 대조했다. root의 임시 debug journal은 [보존본](DEBUG_JOURNAL.md)으로 옮겼고, test helper도 텍스트 증거를 남긴 뒤 임시 실행 파일만 정리했다. [정리 기록](cleanup-receipt.json)에 사용자 원본·백업·프로그램과 브라우저 산출물 보존을 명시했다. 소스는 독립 인수 뒤 변경되지 않아 같은 검사를 반복 실행하지 않았다.

## 후속 에이전트

동일 503 복구와 모델 선택 수정을 다시 구현하지 않는다. 원본·백업·legacy 파일을 지우지 않는다. 신규 변경은 현재 소스 해시를 먼저 대조하고 영향 범위의 테스트와 실제 대화를 새로 검증한다. 기존 config 사본 불일치, native 화면 권한, 다른 viewport 및 활성 대화 복원은 이번 복구의 PASS로 포함하지 않는다.
