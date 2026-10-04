---
title: 네 외부 저장소의 코드 비교와 SSAK-AI 적용 판단
date: 2026-10-03
tags: [research, architecture, orchestration, memory, finance, voice]
---

# 조사 범위

네 저장소를 shallow clone으로 읽고 실제 소스·관련 시험·라이선스를 확인했다. 의존성 설치, 외부 제품 실행, 금융 커넥터 연결, 음성 모델 다운로드는 하지 않았다. 최초 기본 sandbox의 DNS 실패는 읽기 전용 네트워크 실행으로 해소했다. 아래는 확인한 커밋 기준의 비교이며 모든 미래 변경이나 전체 저장소의 안전성을 보증하지 않는다.

SSAK-AI 비교 기준은 공유 작업 폴더의 최신 파일이다. Git HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`이며 기존 사용자 변경을 포함한다. 이번 수정 전 관련 파일 해시는 [baseline.sha256](baseline.sha256)에 있다. 현재 코드는 지식 그래프를 먼저 조회해 실제 경로를 확인했다.

# Paperclip: 실행 관리

확인 커밋: `569c7203aa24b95440682983ce7940ba1d4247bd`. [MIT 라이선스](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/LICENSE).

| 실제 메커니즘 | 소스 근거 | SSAK-AI 판단 |
|---|---|---|
| task/run을 정해진 순서로 잠그고 불변 실행 맥락이 바뀌면 재시도 | [run-dispatch postgres.ts](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/modules/run-dispatch/adapters/postgres.ts#L190-L239), [경합 시험](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/__tests__/heartbeat-queued-run-claim-isolation.test.ts#L180-L218) | 기존 SQLite status/version CAS를 실행 진입에 사용. 외부 I/O를 트랜잭션 안에서 수행하지 않고 경합 패자는 실행하지 않음 |
| deferred wake를 FIFO로 선택하고 조건부 queued 승격과 run 연결 | [wake-queue postgres.ts](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/modules/wake-queue/adapters/postgres.ts#L204-L246), [승격](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/modules/wake-queue/adapters/postgres.ts#L426-L482) | 현재 큐와 중복 실행 판정 이후의 후속 도입. 새 영구 wake 큐를 지금 중복 구현하지 않음 |
| 기록된 비용을 기준으로 company/agent/project 진입 차단 | [budgets.ts](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/services/budgets.ts#L718-L814) | prompt token 예산과 실제 비용 예산을 구분해야 함. 비용 누적 계약이 없는 경로에는 형식적인 금액 제한을 붙이지 않음 |
| 승인 상태를 CAS로 바꾼 경우에만 부작용 수행 | [approvals.ts](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/services/approvals.ts#L45-L87), [부작용](https://github.com/paperclipai/paperclip/blob/569c7203aa24b95440682983ce7940ba1d4247bd/server/src/services/approvals.ts#L144-L212) | 기존 승인 대기 경계와 중복 승인·재개 시험의 설계 근거. 승인 요구를 자동 승인하는 기능으로 해석하지 않음 |

기존 `TaskStateStore`에는 owner/status/version CAS, terminal freeze, 취소·재개가 있다. 기능 이름만 추가하는 대신 `BackgroundTaskRunner`가 실제 실행 전에 그 보장을 사용하는지 동시 SQLite 시험으로 확인한다. Paperclip의 Node/React/PostgreSQL control plane 전체를 가져오지 않는다.

# Hindsight: 회상과 근거

확인 커밋: `f7dd3f4fd7420f7beec60c32c965e5e5cf7be066`. [MIT 라이선스](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/LICENSE).

| 실제 메커니즘 | 소스 근거 | SSAK-AI 판단 |
|---|---|---|
| semantic/BM25/graph/time 후보별 한도 후 RRF, dedupe용 interleave | [fusion.py](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/hindsight-api-slim/hindsight_api/engine/search/fusion.py#L8-L110) | 실제 복수 검색 신호가 있는 경우 순위 결합에 유용. 현재 opaque provider 문자열에 가짜 vector 점수를 만들지 않음 |
| relevance에 제한된 recency/time/proof 가중치를 곱함 | [reranking.py](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/hindsight-api-slim/hindsight_api/engine/search/reranking.py#L174-L305) | 최신성만으로 관련성을 덮지 않는 원칙을 채택. 기존 episodic 한국어/stem/recency 순위는 보존 |
| 순위대로 예산에 들어가는 fact를 선택하며 큰 fact는 건너뛰어 후속 자료를 채움 | [fact_budget.py](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/hindsight-api-slim/hindsight_api/engine/fact_budget.py#L1-L105) | 실제 `MemoryManager.prefetch_all`의 결합 자료를 중복 제거하고 제한. SSAK의 엄격한 예산을 넘기는 non-empty floor는 채택하지 않음 |
| bank/tag 범위를 검색 전에 적용하며 합성 observation과 근거 fact를 구분 | [recall.py](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/hindsight-api-slim/hindsight_api/engine/memories/pg/recall.py), [observation 시험](https://github.com/vectorize-io/hindsight/blob/f7dd3f4fd7420f7beec60c32c965e5e5cf7be066/hindsight-system-tests/tests/test_27_observations_in_recall.py#L1-L90) | 프로젝트·사용자 범위와 원래 근거를 먼저 보존. observation/증거 노트의 영구 승격은 기존 Markdown/Git 승격 방침 안에서 별도 설계 |

기존 일반 대화는 `MemoryManager.prefetch_all → providers → project canonicalization → conflict resolution`을 사용한다. provider API는 문자열이며 전체 결합 예산과 일반 중복 억제가 없다. 이번 구현은 그 실제 경로에 적용한다. Hindsight의 PostgreSQL/pgvector, 별도 LLM retain/reflect 서버를 설치하지 않는다. 날짜의 soft ranking과 hard filtering은 후속 typed recall 계약에서 구분해야 한다.

# Financial-services: 분석 작업 계약

확인 커밋: `574ed3624aebd0418c7e96cd101262f30210ab26`. [Apache-2.0 라이선스](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/LICENSE). 관련 partner/skill 하위 라이선스도 별도로 확인했다.

이 저장소는 계산 라이브러리보다 Markdown/JSON plugin·skill·managed-agent cookbook이다. [현재 README](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/README.md#L1-L13)의 성격에 맞게 작업 계약과 검증 방식만 흡수한다.

| 실제 계약 | 소스 근거 | SSAK-AI 판단 |
|---|---|---|
| 원자료와 가정에 출처를 기록하고 계산 결과를 재현 가능한 수식으로 유지 | [DCF skill](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/financial-analysis/skills/dcf-model/SKILL.md#L44-L83) | 숫자·단위·원문 source index를 실제 추출/API에 연결. 계산 근거와 입력을 혼합하지 않음 |
| 명시적 시나리오와 선택된 가정을 검증 | [DCF scenario/source 조건](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/financial-analysis/skills/dcf-model/SKILL.md#L85-L107) | DCF/comps 엔진과 시나리오 모델은 별도 기능. 지금 문자열 추출에 valuation을 가장하지 않음 |
| 기준일·통화·규모를 작업물에 명시 | [comps header](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/financial-analysis/skills/comps-analysis/SKILL.md#L108-L117) | 없는 통화·날짜를 추정하지 않고 `만원/억원`, `%/%p/bp`를 구분. 현재 단위 손실과 소수 일부 매칭을 먼저 개선 |
| 숫자별 문서·날짜·링크와 자료의 최신성을 확인 | [earnings sources](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/equity-research/skills/earnings-analysis/SKILL.md#L50-L75), [freshness](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/equity-research/skills/earnings-analysis/SKILL.md#L117-L136) | 금융 evidence skill의 품질 기준. 외부 유료 데이터나 사용자 계정을 자동 연결하지 않음 |

현재 `ExtractedNumericData`는 value/unit 필드가 있어도 추출기가 label만 채우며, `/api/search/extract`는 numeric_data를 응답에서 누락한다. 부호·소수·복합 한국어 규모와 퍼센트포인트를 정확히 파싱하고 그 구조를 실제 응답까지 전달하는 것이 이번 구현 대상이다.

외부 최신 financial-analysis의 [`.mcp.json`](https://github.com/anthropics/financial-services/blob/574ed3624aebd0418c7e96cd101262f30210ab26/plugins/vertical-plugins/financial-analysis/.mcp.json#L43-L50)에는 Egnyte/Box 사이 쉼표가 빠져 JSON 파싱이 실패한다. 원본 설정을 그대로 수입하지 않는 근거다. 공급자 목록과 URL은 인증·구독·별도 서비스 약관을 대체하지 않는다.

# VoiceStudio: 오디오 경계

확인 커밋: `c4d63ef207f345b4405f8e8320a73d273ce7187f`. [라이선스 구분](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/LICENSE-NOTICE.md#L39-L59): 앱은 AGPL-3.0-only, bundled omnivoice 코드와 기본 가중치는 별도 조건이다. 이번 구현은 외부 코드를 복사하지 않는다.

| 실제 메커니즘 | 소스 근거 | SSAK-AI 판단 |
|---|---|---|
| base64/path 입력의 배타적 선택·크기 제한·파일 경로 confinement | [mcp_server.py](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/mcp_server.py#L127-L259) | SSAK의 HTTP 오디오 입력에는 필요한 업로드 크기 제한만 적용. 임의 서버 파일 경로 입력을 새로 열지 않음 |
| RIFF/chunk 길이와 실제 payload 완전성을 확인 | [audio_validation.py](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/core/audio_validation.py#L35-L108), [시험](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/tests/test_audio_validation.py#L9-L44) | 독립 표준 WAV 검증으로 손상 오디오를 STT 모델/명령 전에 거절. 현재 허용된 비-WAV 형식과 구분 |
| 문장 단위 합성과 PCM16 스트림, 완료 시 지연/재생 지표 | [tts_stream.py](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/api/routers/tts_stream.py#L145-L167), [완료 지표](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/api/routers/tts_stream.py#L452-L478) | 실제 TTS 엔진과 재생 버퍼가 준비된 뒤 streaming 도입. 지금 사용되지 않는 WebSocket이나 모델 lease API를 추가하지 않음 |
| CJK 밀도에 맞는 chunk 크기, 문장→구절→공백 순 분할 | [chunked_tts.py](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/services/chunked_tts.py#L69-L176) | 한국어 긴 답변 읽기 개선의 후속 후보. 업로드 검증과 별도로 실제 음성 품질 비교 필요 |
| 추론별 취소 token과 sidecar 종료, native call의 취소 한계 구분 | [inference_cancellation.py](https://github.com/debpalash/VoiceStudio/blob/c4d63ef207f345b4405f8e8320a73d273ce7187f/backend/services/inference_cancellation.py#L1-L32) | 기존 task 취소 계약과 연결해야 함. HTTP 취소만으로 native 추론이 중단됐다고 표시하지 않음 |

기존 `/api/voice/transcribe`, `/commands`, `/speak`와 `VoiceService`를 유지한다. 실제 녹음·voice cloning·개인 음성 전송 없이 합성한 작은 WAV와 오류 입력으로 검증한다.

# 이번 반영과 후속 도입의 구분

이번 구현·직접 검증 결과는 [RESULTS.md](RESULTS.md)와 [CHECKLIST.md](CHECKLIST.md)에 기록했다. 위의 모든 후보가 구현되었다는 뜻은 아니다. 영구 wake 큐, 금액 비용 집계, 다중 신호 RRF, evidence observation 승격, DCF/comps 계산 엔진, TTS streaming·한국어 chunking은 각각 실제 의존 경로와 객관적 인수 조건을 갖춘 후속 기능으로 남긴다.
