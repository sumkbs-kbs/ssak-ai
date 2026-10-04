---
title: 외부 저장소 기반 기능 강화 최종 결과
date: 2026-10-03
tags: [qa, integration, external-feature-upgrade]
---

# 구현과 직접 관측

최신 공유 작업 폴더를 기준으로 네 저장소의 실제 코드·테스트·라이선스를 비교하고,
기존 실행 경로에 아래 네 개선을 연결했다. 비교 근거는
[REPOSITORY_ANALYSIS.md](REPOSITORY_ANALYSIS.md), 인수 조건과 후속 후보는
[CHECKLIST.md](CHECKLIST.md)에 있다. 기존 Constitution, Brain/Body 책임,
Files-first·Git-first, 인증·모델 선택을 바꾸지 않았다.

| 참고 저장소 | 이번 구현 | 직접 관측과 근거 |
| --- | --- | --- |
| Paperclip | 작업 시작·재개 전에 기존 SQLite CAS로 실행자를 한 명만 점유. 패자는 worktree/snapshot/model/tool 실행 전에 종료 | 실제 SQLite와 별도 연결을 갖는 두 `BackgroundTaskRunner`의 public `resume_task` 경합: 결과 `[false,true]`, 실행 1회, 최종 `done`, checkpoint step 7과 이전 출력 보존. 시작 경합은 별도 실제 SQLite 행동 회귀로 검증. [root-library-qa.log](root-library-qa.log), [task-claim-evidence.md](task-claim-evidence.md) |
| Hindsight | 회상 조각 중복 제거, 기본 12,000 **문자** 예산, 큰 선택 조각 건너뛰기와 후속 채움. 충돌 해결 뒤 최종 길이도 제한 | 실제 `MemoryManager.prefetch_all`: 35문자, 중복 1회, 후속 작은 조각 포함. 1문자 예산에서는 빈 회상; 500문자 예산에서는 완전한 `current_user` 정정과 근거 유지. [root-library-qa.log](root-library-qa.log) |
| financial-services | 명시적 한국어 규모·통화·퍼센트·퍼센트포인트·bp를 정확히 추출하고 API에 `numeric_data` 전달. Decimal 정확도와 안전한 JSON 표현 유지 | 실제 HTTP 200: `1조 2,345억 원 → 1234500000000`, `3.5%p`, `25bp` 단위 분리. `9007199254740993원`과 큰 정수+극소 소수는 `value == normalized_value`인 정확한 문자열. [root-http-financial.txt](root-http-financial.txt) |
| VoiceStudio | 25 MiB 제한 내 streaming 읽기, RIFF/WAV 길이·chunk·지원 encoding·개별 frame 정렬 검증을 STT 앞에 연결 | 실제 HTTP: 잘린/중복 fmt/빈 입력 422, 26 MiB 입력 413, STT 호출 0. 유효 PCM16·IEEE float32는 각각 200과 합성 transcriber 호출 1회. [root-http-after-invalid.txt](root-http-after-invalid.txt), [root-http-after.txt](root-http-after.txt) |

금융 `source_index`는 해당 검색 출력 조각의 원문 연결이다. 발행일·기준일·공식 출처
URL 검증 기능의 완료를 의미하지 않는다. `$`/달러는 USD, `¥`는 JPY로 해석하는
현재 규칙이 있으며 모든 지역의 통화 모호성을 해결하는 기능은 아니다.

# 직접 실행 방법과 경계

기존 `.venv`를 사용한 재현 명령과 입력 생성 절차는 [README.md](README.md)에 있다.
`manual_driver.py --help`와 `library`는 정상 종료했다. `serve`는 loopback 8047에 실제
생산 router를 올리며 **검색 공급자와 transcriber 포트만** 합성 입력으로 대체했다.
HTTP 상태·응답 본문과 호출 횟수를 동시에 관측했다. 임시 홈을 생산 모듈 import
전에 적용하고 임시 SQLite를 사용했다. 개인 녹음이나 실제 사용자 DB로 검증하지 않았다.

음성·금융 HTTP 관측은 `root-http-*.txt`에 있다. 공백 검색어는 HTTP 200의
`ok:false`/`query is required`, 숫자형 검색어는 HTTP 400의 `Invalid request body`로
반환되고 검색 호출 횟수는 늘지 않았다. 오류 응답을 작업 성공으로 계산하지 않았다.
운영 포트 8000의 `/health`는 200, 인증 없는 음성 요청은 401이었다
([root-live-health.txt](root-live-health.txt), [root-live-auth-boundary.txt](root-live-auth-boundary.txt)).

# 실제 대화 검증 중 발견한 분류 문제

최종 실제 대화에서 `도구 없이 다음 문장만 그대로 답해: 외부 기능 연결 검증 완료`가
짧은 응답 대신 자기 능력 보고서를 출력했다. 요청 전체에 있는 `기능` 단어를 검사한
기존 predicate가 route와 stream의 자기보고 분기를 먼저 선택했다. 최신 사용자 요청은
브라우저에서 정확했고 두 경로의 resolver도 최신 사용자 메시지를 선택했다.
[chat-routing-before.txt](chat-routing-before.txt)가 수정 전 관측이다.

자기보고 의도를 명시한 질문만 해당 분기로 보내도록 수정했다. 독립 검토가 발견한
`어떤 도구를 사용할 수 있어?`·`어떤 모델을 사용하고 있어?`의 보존 회귀도 재현 후
보완했다. 일반 기능 작업은 실제 stream dispatch에서 provider를 한 번 호출하며
자기보고 분기를 사용하지 않는다. 모델 출력 문구를 생산 코드에 하드코딩하지 않았다.

최종 서버 PID 32914 / exec session 27894에서 동일 질문을 다시 보냈고 실제 응답은
**`외부 기능 연결 검증 완료`**였다. 선택 모델은 `qwen3.8:latest (27.3B)`, 검색·코드
옵션은 OFF, 기존 인증·전체 액세스를 유지했다. POST `/v1/chat/completions`는 HTTP 200이며
브라우저에서 완료된 응답과 전송 버튼 복귀를 확인했다.
[chat-routing-after.txt](chat-routing-after.txt), [화면](chat-routing-after.png),
[chat-routing-review.md](chat-routing-review.md)가 최종 근거다.
수정 전 자기보고 응답은 이력 저장 전에 반환되므로 새로고침 후 이전 사용자 질문만
남아 같은 질문이 두 번 보인다. QA 질문 두 번 전송과 사용자 데이터 보존의 결과이며
응답이 중복 생성된 것은 아니다. 최종 화면의 새 답변은 한 번이다.

운영 로그·화면에는 이 턴의 token usage 수치가 노출되지 않아 실제 모델의 정확한
token 수는 확인하지 않았다. 실제 응답·HTTP 완료와 별도 행동 회귀의 provider 호출
횟수를 확인했으며, 계측하지 않은 수치를 주장하지 않는다.

# 회귀·독립 검토와 소스 식별

네 기능을 통합한 첫 최종 후보는 관련 25개 테스트 파일에서 **357 passed**였다.
Ruff 통과, 선택한 15개 Python 파일의 basedpyright error gate와 LSP error gate가
통과했다. 새 생산 모듈 세 개와 manual driver는 warning 포함 type check에서도
0 errors/0 warnings였다. 기존 Starlette TestClient deprecation warning 1개는 남는다.
전체 공유 작업 폴더의 모든 기존 코드가 무경고라는 뜻은 아니다.

자기보고 분류를 포함한 최종 합본은 **361 passed, 1 warning in 7.90s**였다
([root-final-regression.log](root-final-regression.log)). 선택한 17개 Python 파일의
Ruff 및 basedpyright error gate도 통과했다. 기존 15개 파일은 동일 해시의 LSP error
PASS를 유지하고, 새 분류 수정 두 파일은 최종 해시에서 LSP error가 없음을 다시 확인했다.
처음 stdin으로 실행한 합본은 multiprocessing의 `<stdin>` 재진입 때문에 3개가 실패했다.
기존의 `python -c` 방식으로 다시 실행해 361개가 통과했으며 생산 코드·테스트를
약화시키지 않았다. 실패 로그는 `root-final-regression-stdin-harness-failure.log`로 보존한다.

최종 [source.sha256](source.sha256)은 17개 생산·테스트·manual driver를 식별한다.
manifest SHA-256은 `1fa855b80aaa27b7fbf7464f513cb02a6f8994a4146eea0e6563bc5bb76b8d13`이며
full Git HEAD는 `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`다. 별도 문서·증거 해시는
`documentation.sha256`에 기록한다. 금융/음성 최종 HTTP 실행 시 소스 해시는
[root-http-final-source.sha256](root-http-final-source.sha256)에 있다. 이전
`root-http-source.sha256`은 Decimal canonical text 보완 전의 역사 자료다.
독립 검토와 full HEAD/파일별 SHA-256 바인딩은
[EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md)에 기록했다. 과거 후보의 RED/GREEN/해시는
감사 이력으로 보존하며 최종 후보의 통과 근거와 구분한다.

최종 운영 서버에서도 health 200·인증 없는 음성 요청 401을 재확인했다
([root-final-live-health.txt](root-final-live-health.txt),
[root-final-auth-boundary.txt](root-final-auth-boundary.txt)). 서버와 기존 브라우저 탭을
실행 상태로 유지한다. 별도 HTTP fixture 서버는 종료했다.

임시 분류 baseline과 합성 WAV fixture, root debug journal을 정리했고 생산 코드에
임시 계측은 남기지 않았다. 정리 직전 17개 파일 해시 일치·full HEAD 유지·선택 범위
`git diff --check` 0을 확인했다. [root-final-cleanup.txt](root-final-cleanup.txt)에 실제
관측을 기록했다. 611개 shared status 항목은 기존·공유 수정과 이번 산출물을 함께
포함하므로 전체 작업 폴더가 clean이라고 주장하지 않는다. 이번 인수 체크 27개는
완료했으며 아래 후속 기능은 이번 완료 범위에 포함하지 않는다.

# 이번 완료 범위 밖

- Paperclip 전체 control plane, 영구 wake 병합·FIFO와 금액 비용 원장.
- Hindsight 서버/pgvector 설치, 다중 신호 RRF와 temporal/observation 영구 승격.
- 금융 유료 커넥터, 최신 실제 금융 데이터·기준일·출처 검증, DCF/comps 계산 엔진.
- 실제 STT 인식 품질, TTS·한국어 streaming·취소, voice cloning. 현재 UI 음성 입력은 미연결.
- 비-WAV codec 내부 검증. 기존 허용 비-WAV 입력의 전달 계약은 유지한다.

VoiceStudio의 AGPL 코드를 복사하지 않고 표준 WAV 입력 계약을 독립 구현했다.
앱과 모델 라이선스를 구분했으며 모델 가중치나 외부 금융 서비스를 설치·연결하지 않았다.
후속 여섯 후보의 선행 조건·산출물·QA는 체크리스트에 남겼다.
