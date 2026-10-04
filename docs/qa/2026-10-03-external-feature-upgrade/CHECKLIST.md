---
title: 외부 저장소 기반 기능 강화 인수 체크리스트
date: 2026-10-03
tags: [qa, acceptance, external-feature-upgrade, follow-up]
---

# 판정 범위

기준 문서는 [실행 계획](../../ssak-ai-core/EXTERNAL_FEATURE_UPGRADE_2026-10-03.md)과 [저장소 비교 분석](REPOSITORY_ANALYSIS.md)이다. 이번 인수 범위는 기존 실행 경로에 연결한 작업 점유, 회상 예산, 금융 숫자 추출, 음성 업로드 검증 네 가지다. 아래 체크는 최종 소스·실행 증거·독립 검토를 대조한 주 에이전트가 완료했다. 최종 판정은 [RESULTS.md](RESULTS.md)와 [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md)에 있다.

비교 시 Git HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`였으며 작업 폴더에 기존 변경이 있다. [baseline.sha256](baseline.sha256)은 수정 전 비교 자료다. 담당자 문서의 해시는 각 검증 당시 후보를 가리키며, 최종 작업 폴더 해시를 대신하지 않는다.

## 공통 경계

- [x] Constitution, Brain/Body 책임, Files-first·Git-first, 기존 모델 선택·인증·사용자 데이터 계약을 보존했다. 검증은 임시 홈·임시 저장소·합성 입력을 사용했고 운영 설정을 복원했다.
- [x] 외부 코드·모델의 라이선스 구분을 분석에 기록했다. 이번 구현에 외부 코드 복사, 프런트엔드 개편, TTS 모델 다운로드, 금융 커넥터 연결, PostgreSQL/pgvector 설치가 포함되지 않았다.
- [x] 기존 사용자 변경을 되돌리거나 함께 스테이징·커밋하지 않았으며, 이번 변경과 검증 대상 파일을 구분했다.

## 1. 작업 실행 전 SQLite CAS 점유

연결 경로: `BackgroundTaskRunner → TaskStateStore`. 담당 근거: [task-claim-evidence.md](task-claim-evidence.md).

- [x] 서로 다른 실행자·SQLite 연결이 같은 `pending` 작업을 경합해도 `pending → running` 점유 승자만 orchestrator를 호출한다.
- [x] 같은 일시중지 작업의 재개 경합에서는 `resuming → running` 승자만 실행하며, 체크포인트·결과는 한 실행에서만 기록된다.
- [x] 점유 실패 실행자는 worktree·snapshot·tool·model 실행 전에 종료하고, 승자의 상태·체크포인트·결과를 변경하거나 실행 성공으로 보고하지 않는다.
- [x] 실행 전 취소도 기대 상태를 확인한다. 오래된 중복 실행자의 취소가 이미 실행 중인 승자에게 적용되지 않으며, 기존 취소·재개·재시작·terminal freeze 회귀가 통과한다.

## 2. 제한된 회상과 정정 우선순위

연결 경로: `MemoryManager.prefetch_all → providers → canonicalization → conflict resolution`. 담당 근거: [memory-recall-budget-evidence.md](memory-recall-budget-evidence.md).

- [x] 완전한 동일 회상 조각이 여러 provider에서 반환되어도 한 번만 포함되고, 정정·출처·프로젝트 범위는 보존된다.
- [x] 예산보다 큰 선택 자료를 건너뛴 뒤 들어갈 수 있는 후속 자료를 채운다. 조각을 잘라 잘못된 사실이나 고아 헤더를 만들지 않는다.
- [x] 예산 0, 작은 양수, 기본 예산에서 **최종 conflict resolution 이후** 회상 길이가 상한을 넘지 않는다. 필수 정정 블록이 들어가지 않는 예산은 원문 절단이나 과거 사실 부활 없이 빈 회상 결과로 처리한다.
- [x] 정정 블록이 들어가는 예산에서는 현재 사용자·최신 정정·canonical project fact의 우선순위와 근거를 온전히 유지한다. 실제 임시 episodic 저장소와 일반 provider를 함께 사용한 회귀가 통과한다.

## 3. 정확한 금융 숫자와 HTTP 응답

연결 경로: `DataExtractor → POST /api/search/extract`. 담당 근거: [financial-validation.md](financial-validation.md).

- [x] 부호·소수·쉼표·복합 한국어 규모(`1조 2,345억 원`, `1조 2억 3만원`)를 중복 분할 없이 추출하고, 통화·규모·`%`·`%p`·`bp/bps`를 구분한다.
- [x] `value`, `unit`, `currency`, `normalized_value`, `source_index`, 정확한 `raw_text`가 실제 HTTP 응답에 전달된다. 없는 통화·기준일·출처를 추정해 현재 사실로 만들지 않는다.
- [x] `2**53` 경계와 그 위의 큰 정수·소수 금액이 JSON 직렬화 뒤에도 정확하다. `value`와 `normalized_value`가 서로 다른 금액을 나타내지 않는다.
- [x] 실제 FastAPI 경로에서 deterministic 검색 provider 응답을 추출하고, 기존 응답 필드·로그 계약을 유지한다. 공백 검색어는 provider 호출 전에 오류로 반환하며 기존 추출 회귀가 통과한다.

## 4. 제한된 음성 업로드와 WAV 검증

연결 경로: `/api/voice/transcribe`, `/commands → VoiceService`. 담당 근거: [voice-validation.md](voice-validation.md).

- [x] 업로드를 설정된 상한 안에서 읽고, 빈 입력·상한 초과 입력을 STT 모델·외부 명령 실행 전에 각각 오류로 거절한다.
- [x] WAV의 RIFF/container·chunk 길이·payload 완전성·지원 format·프레임 정렬을 검증한다. 잘린 입력, 잘못된 chunk, 중복 `fmt `, 각 data chunk의 불완전한 프레임은 추론 전에 거절한다.
- [x] 지원되는 PCM·IEEE float WAV 합성 입력은 transcriber에 한 번 전달되며, 잘못된 suffix는 거절한다. 기존 허용 비-WAV 형식은 기존 경로로 전달된다.
- [x] 실제 HTTP 경로에서 정상·오류 입력의 상태 코드와 transcriber 호출 여부를 함께 확인했다. 실제 개인 녹음·voice cloning·개인 음성의 외부 전송 없이 검증했다.

## 최종 실행·증거·독립 검토 게이트

- [x] 네 경로의 직접 CLI/HTTP 시나리오를 주 에이전트가 실행하고, 명령·입력·예상/실제 관측·exit code 또는 HTTP 상태·로그 경로를 최종 결과 문서에 기록했다.
- [x] 수정 후 관련 회귀와 정적 검증을 실행했다. 실제 결과와 인용 로그가 일치하며 기존 경고와 이번 변경 오류를 구분했다.
- [x] 수정 완료 후 소스·테스트·문서의 SHA-256을 동결하고, 테스트·직접 검증·독립 검토가 같은 후보를 가리키는지 확인했다. 이후 수정은 영향받는 게이트를 다시 실행했다.
- [x] [task-finance-review.md](task-finance-review.md)의 금융 정밀도·증거 불일치와 [memory-voice-review.md](memory-voice-review.md)의 최종 회상 예산·WAV 후속 해시 요구를 수정 후 후보에 대해 재검토했다. 과거 `BLOCK/WATCH` 보고서를 최종 승인으로 취급하지 않았다.
- [x] 최종 결과 문서에 완료·미검증·후속 제외 범위, 남은 제한, 증거 경로·해시·검토 판정을 명시했다. 근거가 없는 항목은 체크하지 않았다.

## 실제 대화에서 발견한 분류 회귀

- [x] 일반 기능 작업이 자기보고로 우회하지 않고 stream provider를 한 번 호출한다. 이전 실패와 최종 성공을 같은 입력 경계에서 검증했다.
- [x] 명시적 도구·현재 모델 질문은 자기보고 경로를 유지하며, 독립 검토의 첫 BLOCK을 RED → GREEN 후 재검토해 CLEAR로 해결했다.
- [x] 기존 27.3B 모델·인증·옵션을 유지한 실제 화면에서 동일 질문의 응답이 `외부 기능 연결 검증 완료`였다. 정확한 token 수는 미계측으로 표시했다.

# 후속 후보, 이번 완료 범위 제외

아래는 도입 대기 계획이다. 이번 네 기능의 통과 여부로 구현 완료를 주장하지 않는다. 기존 권한·사용자/프로젝트 범위·Markdown/Git 승격 계약을 먼저 적용하고, 각 후보를 별도 변경과 인수 증거로 진행한다.

| 후보 | 선행 조건 | 다음 산출물 | 대응 QA 시나리오 |
| --- | --- | --- | --- |
| wake 중복 병합·순서 보장 | 현 큐의 task/run 식별자, 재시작·취소 계약과 중복 기준 확정 | 같은 범위의 동일 wake를 합치는 규칙, 영구 기록·FIFO 승격·CAS 설계와 구현 | 동일 wake를 동시에 반복 제출하고 재시작해도 실행 한 번; 다른 프로젝트 wake는 합쳐지지 않음; 취소 뒤 오래된 wake가 재실행하지 않음 |
| 범위별 실제 비용 진입 검사 | 모델별 가격·사용량·정산 시점, 사용자/프로젝트/agent 비용 범위, 미확정 가격 처리 정책 확정 | 비용 원장과 provider 호출 전 admission 계약; 예약·실제 정산·환불 및 token 예산과의 구분 | 두 동시 요청이 남은 예산을 경합할 때 허용 범위만 진입; 한도 초과는 provider 호출 0회; 실패·취소 후 정산과 다른 범위의 예산 격리 확인 |
| provenance를 갖춘 다중 신호 RRF | provider의 typed 후보 ID·원문 근거·범위·신호별 rank 계약 | 범위 필터 뒤 semantic/BM25/graph 후보 결합·중복 제거와 결과별 provenance | 같은 근거가 여러 신호에 나와도 한 후보; 신호 순위가 바뀌면 재현 가능한 결합 순위; 다른 사용자 근거 유출 0건 |
| 회상 temporal 계약 | event/valid 시간·기준 시점·누락 날짜 정책, soft ranking과 hard filtering 구분 | 기준 시점 필터와 제한된 최신성 가중치; 정정 이력 보존 | 과거 시점 질의에서 미래 사실 제외; 최신 정정은 현재 질의에서 우선; 날짜가 없거나 최신성만 높은 무관 자료가 관련 근거를 덮지 않음 |
| 기준일·근거·시나리오 금융 분석 | 출처 URL/문서·발행일·기준일·통화·단위와 가정의 typed evidence 계약 | 근거를 붙이는 skill/작업물 형식, 날짜 검증, 재현 가능한 계산·명시적 시나리오; DCF/comps는 별도 구현 | 다른 기준일 자료를 섞으면 표시/거절 정책 적용; 누락 출처를 사실로 보완하지 않음; base/up/down 입력과 수식으로 결과 재계산; `%`와 `%p` 혼용 오류 검출 |
| 음성 엔진 capability·한국어 streaming·취소 | 실제 엔진의 한국어·PCM format·streaming·native 취소 능력 확인, 재생 버퍼와 task 취소 연결 | capability 계약, 한국어 문장/구절 분할, request별 스트림·취소·완료 상태와 지연 측정 | 긴 한국어 문장의 첫 오디오·순서·누락을 측정; 두 스트림 중 하나 취소 시 다른 요청 유지; 취소 뒤 오디오 전송 종료; native 추론이 계속되면 중단 완료로 보고하지 않음 |

후속 구현 시에도 새 금융 서비스 인증·구독, 모델 라이선스와 모델 선택 변경은 해당 기능의 명시된 도입 범위에서 별도로 다룬다. 지금의 업로드 검증을 TTS streaming이나 금융 계산 엔진 완료로 해석하지 않는다.
