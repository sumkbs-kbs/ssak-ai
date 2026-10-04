---
title: Ssak-Ai 순차 기능 감사 기반 상세 개선 개발 계획
date: 2026-10-04
tags: [ssak-ai, improvement, implementation-plan, qa, handoff]
status: planned-not-executed
planning_only: true
repository: /Users/mr.k/program/coding/ssak_comp/Ssak-Ai
observed_head: 02b9cde7fb0e890330ddebfec5ff8ad9ddc50435
source_audit: docs/qa/2026-10-04-sequential-audit/RESULTS.md
---

# Ssak-Ai 상세 개선 개발 계획

이 문서는 2026-10-04 순차 기능 감사에서 확인한 결과를 다음 개발자가 바로 재현·수정·검증할 수 있는 작업으로 바꾼 실행 계획이다. 제품 소유 저장소는 Ssak-Ai다. 이 문서를 작성하면서 제품 코드를 추가 수정하거나 전체 테스트를 다시 실행하지 않았다. 문서의 작업은 모두 예정 상태이며, 아래 완료 기준을 충족한 새 실행 증거가 있어야 구현 완료로 바뀐다.

다음 실행자는 IMP-00부터 시작한다. 이미 고친 항목은 회귀 방지 대상으로 유지하고, 미검증 항목은 먼저 재현한다. 정상임이 확인되면 코드를 변경하지 않고 검증 증거를 보강한다. 새로운 기능인 DCF/comps 계산은 현재 기능의 결함 수정과 별도 작업으로 취급한다.

## 1. 실행 환경과 작업 경계

| 항목 | 지시 |
| --- | --- |
| 작업 루트 | `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai` |
| 기준 시점 | 위 HEAD와 감사 최종 30개 소스 SHA256의 조합. HEAD만으로 dirty working tree의 코드가 동일하다고 판정하지 않는다. |
| 구현 소유 | Ssak-Ai의 engine, API, dashboard, tests, scripts, docs. 공급 저장소 `/Users/mr.k/Downloads/webapp`의 변경으로 Ssak-Ai 완료를 대신하지 않는다. |
| 로컬 상태 | 여러 작업의 수정·staged 파일이 공존한다. 무제한 `git status`나 전체 untracked 목록 대신 소유 경로별 diff와 bounded 상태를 수집한다. |
| 코드 탐색 | codebase-memory-mcp의 search_graph → trace_path → get_code_snippet을 우선 사용한다. 프로젝트명은 `Users-mr.k-program-coding-ssak_comp-Ssak-Ai`. 그래프가 부족한 경우에만 범위를 좁힌 파일 검색·읽기로 보충한다. |
| 파일 편집 | 실제 파일을 읽은 뒤 최소 변경한다. 미래 병렬 작업자는 다른 작업자의 변경을 되돌리지 않는다. 아래 공통 소유 파일은 한 명이 순서대로 통합한다. |
| 데이터 | 새 임시 프로젝트·vault·Chroma·GraphML·대화·인증 저장소를 사용한다. 개인 wiki, HOME, 모델 데이터, 기존 DB를 검증 fixture로 쓰거나 purge하지 않는다. |
| 실행 전환 | 후속 사용자가 개발 실행을 지시하면 이 문서대로 착수한다. 이 문서 자체는 실행·commit·push·배포·외부 계정 변경 지시를 대신하지 않는다. |
| 기록 보존 | 원래 감사의 실패 기록과 historical release 증거는 수정·삭제하지 않는다. 새 run ID의 증거를 추가한다. |

기존 [전체 기능 계획](FULL_FUNCTION_LIVE_PLAN_2026-10-04.md)의 이전 HEAD, 브라우저 접근 제한, 시각 검증 판정은 해당 이전 실행의 사실이다. 이번 계획의 기준은 아래 순차 감사다. 서로 다른 실행의 통과·실패를 섞어 현재 상태로 승격하지 않는다.

## 2. 테스트가 실제로 확인한 사실

### 2.1 판정 분류

| 분류 | 의미 | 이번 사례 | 다음 행동 |
| --- | --- | --- | --- |
| FIXED-VERIFIED | 수정 뒤 명시된 시나리오에서 관측한 통과 | 검색 최종 2회, 취소, 동시 Chroma, 숫자 표시, 추출, 모바일 화면 | 유지할 계약과 회귀 테스트를 등록 |
| REMAINING-RECORDED | 후속 감사에서 남은 실패로 기록됐지만 새 전체 소스로 재측정하지 않은 항목 | 문서·release 계약 9개 | 현재 소스에서 재현 후 의미를 보존하며 수정 |
| OBSERVED-INCIDENT | 실제 실패가 있었고 후속 실행은 통과, 원인은 일부만 확인 | Ollama native parser EOF/500 | 실패 경로·관측·회복 계약을 검증; 추정 원인에 맞춘 패치 금지 |
| UNVERIFIED | 기능 또는 조합을 실제 환경에서 확인하지 못함 | 긴 대화, 실 STT, 실 학습, 활성 agency | 환경 확인 → 직접 실행 → 차이가 확인되면 수정 |
| QUALITY-DEBT | 도구가 보고한 잔여 경고 또는 품질 범위 부족 | lint 36개, 큰 청크 경고, 추출 4개 입력 | 실제 영향 측정 및 경고 원인 해결 |
| NEW-CAPABILITY | 구현되지 않은 기능 | DCF/comps 계산 | 미지원 안내를 먼저 정확히 만들고 계산기는 별도 개발 |

### 2.2 수치와 해석 제한

| 결과 | 확인된 수치 | 해석 |
| --- | --- | --- |
| 과거 전체 backend 조사 | 7,846 passed / 113 failed / 11 errors / 19 skipped / 20 xfailed | 실행 중 HEAD/소스 이동이 있었다. 현재 전체 suite 판정으로 사용 불가 |
| 후속 browser 회귀 | 186 passed, live-model 1 skip, 20 deselected | 이전 browser 실패 88개는 후속 범위에서 통과. 모든 실계정·모델·브라우저 조합 통과가 아님 |
| legacy 검색 fixture | 이전 13개 setup error 후 수정 및 후속 benchmark 통과 | 과거 오류 수를 현재 전체 결과에서 산술로 차감하지 않는다 |
| 검색 benchmark | 100개 사례 × 3 paired 실행 | 해당 benchmark의 결과이며 실제 QA09 두 번과 같은 검사가 아님 |
| 실제 검색 최종 실행 | 32.58초 / 27.52초, 각 표 2개 데이터 행·공식 링크·출처 일치 | 동일 질문 2회 관측. 일반 신뢰도나 latency SLA가 아님 |
| 취소 | 실제 토큰 출력 중 cancelled, error=null, terminal 1회; 후속 답변 42 | 실행 중인 blocking model pull을 즉시 선점하는 보장은 아님 |
| 동시 vector store | 실제 Chroma 8/8, peer store 유지, 정리 뒤 registry 0 | 일부 embedding/recall은 대체 포트. 실 embedding 품질은 별도 |
| 추출 | 동일 4개 입력의 20개 필드 100% | 임의 문서 정확도 100%가 아님 |
| dashboard | 125개 파일 / 1,243 tests, typecheck·lint·build exit 0 | lint warning 36개와 큰 bundle warning 존재 |
| 시각 QA | 123개 캡처, 14개 대표 route, 375/768/1280 너비 | 두 독립 검토가 해당 캡처 전체를 확인. 모든 환경의 시각 통과가 아님 |
| package/config | SBOM 6개 누락 보완 후 관련 검사 67개 통과 | 새 wheel의 설치 환경 및 새 GA 후보의 검증 완료가 아님 |
| hygiene | 한정된 820개 텍스트의 credential pattern 0, 로컬 문서 링크 30개 누락 0 | 저장소 전체 비밀정보 부재를 증명하지 않음 |

최종 감사 backend 서버는 종료됐다. 기존 Ollama 서비스는 사용자 소유다. 후속 실행자는 자신의 API·browser·child process만 생성·종료하고, 8000 포트를 무조건 재사용하거나 기존 Ollama를 재시작하지 않는다.

### 2.3 근거 파일

아래 상대 링크는 이 문서 위치를 기준으로 해석한다. 원시 JSON이 큰 경우 필요한 필드만 파싱하고 전체를 출력하지 않는다.

| ID | 근거 | 사용처 |
| --- | --- | --- |
| E01 | [RESULTS.md](../qa/2026-10-04-sequential-audit/RESULTS.md), [QUESTIONS.md](../qa/2026-10-04-sequential-audit/QUESTIONS.md) | 전체 27개 기능군의 최종 범위와 실제 질문 |
| E02 | [최종 소스 manifest](../qa/2026-10-04-sequential-audit/source-final-marker-after.json) | HEAD와 30개 소스, 실행 전후 일치 |
| E03 | [backend 재확인](../qa/2026-10-04-sequential-audit/backend-recheck-report.md) | browser 및 legacy 실패의 후속 판정 |
| E04 | [backend 후속 보고](../qa/2026-10-04-sequential-audit/backend-recheck-followup-report.md), [원시 결과](../qa/2026-10-04-sequential-audit/backend-recheck-followup-results.json) | 미해결 문서·release 계약, profiler 재확인 |
| E05 | [artifact 계약 수정](../qa/2026-10-04-sequential-audit/artifact-contract-fix.md) | 이미 수정된 5개 계약 및 67개 후속 검사 |
| E06 | [Ollama required-tool 진단](../qa/2026-10-04-sequential-audit/required-tool-ollama-diagnosis.md) | 실제 500, 알려진 사실과 미확인 원인 |
| E07 | [검색 소유자 보고](../../.omo/evidence/web-search-answer/web-search-answer-fix.md), [최종 2회 manifest](../../.omo/evidence/web-search-answer/final-two-run-manifest.json), [최종 검증](../../.omo/evidence/web-search-answer/final-two-run-verification.txt) | 검색 수정·최종 실제 실행 |
| E08 | [Root 검색 검증](../qa/2026-10-04-sequential-audit/search-final-live-verified.json), [benchmark 판정](../qa/2026-10-04-sequential-audit/search-benchmark-verification.json) | task DB/sequence/DOM/raw output와 benchmark |
| E09 | [취소 수정](../qa/2026-10-04-sequential-audit/streaming-cancel-fix.md), [최종 durable 상태](../qa/2026-10-04-sequential-audit/cancel-final-durable.json) | ASGI·ContextVar·terminal·후속 실행 |
| E10 | [vector lifecycle 수정](../qa/2026-10-04-sequential-audit/vector-lifecycle-fix.md), [동시 client](../qa/2026-10-04-sequential-audit/vector-lifecycle-root-final-green.txt), [purge](../qa/2026-10-04-sequential-audit/memory-purge-root.txt) | namespace·동시성·peer 보존 |
| E11 | [시각 검증](../qa/2026-10-04-sequential-audit/VISUAL.md), [UI 테스트](../qa/2026-10-04-sequential-audit/dashboard-responsive-tests.log), [lint](../qa/2026-10-04-sequential-audit/dashboard-responsive-lint.log), [build](../qa/2026-10-04-sequential-audit/dashboard-responsive-build.log) | 잔여 경고와 UI 회귀 |
| E12 | [학습 취소 판정](../qa/2026-10-04-sequential-audit/training-cancel-fix.md) | 동시 GET 4.07ms·signal-gated child, 실제 weight 미검증 |
| E13 | [금융 숫자 검증](../qa/2026-10-03-external-feature-upgrade/financial-validation.md) | Decimal·단위·currency·출처 보존의 기존 구현 |
| E14 | [현재 상태](../20_CURRENT_STATUS.md), [release 값 소유 문서](../ga/CR14_FINAL_CANDIDATE_VERDICT.md), [EX05 판정 충돌](../qa/2026-09-16-followup/nx10/EX05_PROMOTION_CONFLICT.md) | single owner, historical soak와 release 의미 |

## 3. 전체 기능군과 작업 연결

각 행은 후속 검증 범위를 지정한다. 해당 기능의 실제 실행이 없으면 이 표의 상태를 PASS로 바꾸지 않는다.

| 번호 | 기능군 | 감사 통과 범위 / 남은 범위 | 작업 |
| --- | --- | --- | --- |
| 1 | 코어 답변 | 실제 Qwen 답변·required read 통과 / provider failure·다른 모델 | IMP-03, IMP-09 |
| 2 | 대화 | fork·짧은 compact·cancel 통과 / 긴 compact·blocking pull 경계 | IMP-06, IMP-03 |
| 3 | 이미지·vision | JPEG 및 형식 거절 통과 / 다양한 이미지·모델 | IMP-17, IMP-09 |
| 4 | 도구·권한 | required/no-tools/approval 통과 / opaque shell의 쓰기 경계 | IMP-05 |
| 5 | durable task | 실제 done·cancel·HTTP/WS 통과 / provider 실패·restart 조합 | IMP-03, IMP-10 |
| 6 | 지속 agency | off/unavailable만 확인 / active 운영 | IMP-10 |
| 7 | legacy Kanban | 별도 API 14검사 통과 / durable task와 별도 계약 유지 | IMP-01, IMP-10 |
| 8 | scheduler | finite tick/retry 통과 / active 반복·외부 delivery·8h | IMP-10, IMP-13, IMP-20 |
| 9 | memory/privacy | 실제 purge/reopen 통과 / 실 embedding·namespace | IMP-07 |
| 10 | wiki/palette | 실제 YAML/Git/키보드 통과 / 경고 수정 뒤 UI 회귀 | IMP-08 |
| 11 | workspace/RAG | 실제 index·동시 store 통과 / 실 embedding·IDE 연동 | IMP-07, IMP-14 |
| 12 | editor | 실제 파일·source 통과 / inline completion | IMP-14 |
| 13 | terminal | auth/Origin/parent 종료 통과 / native child tree | IMP-14 |
| 14 | Git | 로컬 18사례 통과 / bare remote·외부 PR | IMP-13 |
| 15 | 파일 이력 | 빈 상태·기존 회귀 통과 / populated diff·restore | IMP-14 |
| 16 | models | 설치 목록·현재 Qwen 통과 / capability matrix | IMP-09 |
| 17 | training | capability·cancel 계약 통과 / 실제 weight·export | IMP-12 |
| 18 | voice | 합성 transcriber/API 통과 / 실제 STT·TTS·mic | IMP-11 |
| 19 | 검색·추출·금융 | search 최종 2회·4입력 추출 통과 / 광범위 품질·계산기 | IMP-04, IMP-15, IMP-16, IMP-17 |
| 20 | skills/market/MCP | catalog/health/empty 경계 통과 / install·OAuth | IMP-13 |
| 21 | frontend plugins | route/list 통과 / 실제 plugin lifecycle | IMP-13, IMP-08 |
| 22 | 평가·cognitive | off/JSON/SSE/97회귀 통과 / active 판단의 효과 | IMP-18 |
| 23 | browser/approval | Chromium/owner/deny/once 통과 / 실제 연동 조합 | IMP-05, IMP-13 |
| 24 | 관리자·보안 | 임시 auth/WS/config 통과 / 격리·권한 조합 | IMP-00, IMP-05, IMP-13 |
| 25 | remote/compat/provenance | 스키마·미지원 경계 통과 / 실제 remote provider | IMP-09, IMP-13 |
| 26 | CLI/TUI | 격리 CLI 9사례 통과 / interactive TUI | IMP-14, IMP-19 |
| 27 | package/release | SBOM/config 일부 통과 / 현재 전체·wheel·release 계약 | IMP-01, IMP-02, IMP-19, IMP-20 |

## 4. 우선순위·의존 순서·소유 경계

P1은 현재 결과를 믿을 수 있게 만드는 작업, 사용자에게 잘못된 지원 상태를 안내하는 문제, 실행 정책과 실패 처리다. P2는 실제 미검증 기능과 품질 확장이다. P3는 새 계산 기능·선택적 평가 확장이다. S/M/L은 상대 작업 크기이며 소요 시간 보장이 아니다.

| 작업 | 우선/규모 | 선행 작업 | 단독 변경 책임 |
| --- | --- | --- | --- |
| IMP-00 | P1/M | 없음 | 격리 harness·manifest·receipt |
| IMP-01 | P1/L | IMP-00 | 전체 baseline·CI 결과 분류 |
| IMP-02 | P1/M | IMP-01 | README/status/release 문서와 해당 계약 |
| IMP-03 | P1/L | IMP-01 | provider·task 실패/취소 계약 |
| IMP-04 | P2/L | IMP-01, IMP-03 | 검색 품질 및 citation 계약 |
| IMP-05 | P1/L | IMP-01 | tool 실행 정책·sandbox·approval |
| IMP-06 | P2/L | IMP-01, IMP-05 | 대화 압축·history·권한 보존 |
| IMP-07 | P2/L | IMP-01 | RAG·memory·vector lifecycle |
| IMP-08 | P2/M | IMP-01 | frontend warning·성능·시각 회귀 |
| IMP-09 | P2/L | IMP-03 | 모델·provider capability matrix |
| IMP-10 | P2/L | IMP-03, IMP-05 | 활성 agency·scheduler·restart |
| IMP-11 | P2/M | IMP-00, IMP-09 | 실제 STT/TTS와 voice 화면 |
| IMP-12 | P2/L | IMP-00, IMP-09 | 작은 실제 학습·export·취소 |
| IMP-13 | P2/L | IMP-05, IMP-09 | MCP·plugins·remote·Git/browser 연동 |
| IMP-14 | P2/L | IMP-01, IMP-05 | history·editor·terminal·TUI |
| IMP-15 | P1/S | IMP-01 | finance capability 안내 |
| IMP-16 | P3/L | IMP-15, IMP-17 | 새 deterministic DCF/comps |
| IMP-17 | P2/L | IMP-01, IMP-09 | vision·extraction 품질 확대 |
| IMP-18 | P3/L | IMP-01, IMP-03 | 활성 cognitive 비교 평가 |
| IMP-19 | P1/M | IMP-02, IMP-03, IMP-05, IMP-08, IMP-15 | wheel·SBOM·설치 provenance |
| IMP-20 | P1/L | IMP-04, IMP-06, IMP-07, IMP-10, IMP-11, IMP-12, IMP-13, IMP-14, IMP-17, IMP-19 | 새 후보 고정·최종 재검증·release 판정 |

실행 파동은 ① IMP-00/01 → ② IMP-02/03/05/15 → ③ IMP-04/06/07/08/09 → ④ IMP-10/11/12/13/14/17 → ⑤ IMP-19/20이다. IMP-16/18은 명시적으로 선택한 기능 범위에만 포함한다. 실제 환경이 없는 작업도 없었던 일로 처리하지 않고 BLOCKED_ENV로 남기며, 최종 제품 설명에서 그 범위를 지원 완료로 주장하지 않는다.

IMP-02의 문구·single-owner 수정과 candidate-dependent gate는 두 하위 단계로 기록한다. IMP-19가 요구하는 선행 단계는 문구·owner 정리다. 새 후보 SHA/fingerprint 귀속 판정은 IMP-20에서 수행한다. 후보가 아직 없는 상태를 IMP-02 전체 PASS로 표시하지 않으며, 이 분리 때문에 순환 의존을 만들지 않는다.

ToolLoop·ModelManager·system_api.py·ChatPage.tsx·server lifecycle·release owner 문서는 공유 변경 지점이다. 다음 실행에서 병렬 에이전트를 쓰더라도 한 파일을 동시에 수정하지 않는다. 병렬 사용은 별도의 사용자/적용 지시가 있을 때만 한다. 모든 개발자는 자신이 혼자 작업하지 않음을 전제로 소유 파일의 선행 변경을 다시 확인한다.

## 5. 공통 실행·증거 규약

### 5.1 시작 명령과 환경

아래 명령은 읽기 전용 시작 확인이다. 이 문서 작성 때 실행한 제품 검사로 해석하지 않는다.

```sh
cd /Users/mr.k/program/coding/ssak_comp/Ssak-Ai
git rev-parse HEAD
.venv/bin/python --version
node --version
pnpm --version
git diff --name-only -- src/antigravity_k dashboard/src tests scripts
git diff --cached --name-only -- src/antigravity_k dashboard/src tests scripts
```

현재 manifest 요구사항은 Python >=3.12, dashboard Node >=22.13, packageManager pnpm 11.3.0이다. 이전 감사의 실제 .venv는 Python 3.13.12였다. 실행 시 현재 pyproject.toml·uv.lock·dashboard/package.json·lock을 다시 읽는다. 설치가 필요하면 해당 lock을 사용하고, 기술 스택이나 package manager를 이 계획 때문에 바꾸지 않는다.

기존 [isolated_entry.py](../qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py)는 home patch·auth·스토리지 분리에 유용하다. pytest 모드의 config/env 격리 범위는 IMP-00에서 확인해야 한다. 기존 [live_driver.py](../qa/2026-10-04-sequential-audit/live_driver.py)는 실제 모델 재현 참고용이며 고정 8000/lifespan off 조건이 있으므로 전체 테스트/활성 scheduler harness로 그대로 쓰지 않는다.

### 5.2 후속 산출물 위치

새 증거 루트는 `docs/qa/sequential-improvement/<UTC-date>-<unique-run-id>/`로 만든다. 이 경로와 아래 파일은 **신규 제안**이다. 기존 감사 파일을 덮어쓰지 않는다.

- `manifest-before.json`, `manifest-after.json`: HEAD, scoped file SHA256, Python/Node/pnpm/OS/provider/model 버전, lock digest.
- `environment.json`: 자체 생성 프로젝트·저장소·포트·child PID·feature flag, 실제/대체 포트 구분. token/PIN/password는 기록하지 않는다.
- `baseline/`, `IMP-XX/`: 명령 argv/cwd/start/end/exit, stdout/stderr, JUnit, raw response, 관측 ledger.
- `coverage.json`: 27개 기능군 → scenario ID → task ID → 환경 → 판정 → evidence 경로.
- `task-ledger.md`: 모든 IMP 작업의 상태·소유 파일·미해결 원인·다음 동작.
- `candidate-result.md`: 마지막 동일 소스 통합 판정, 설치 결과, 미지원/미검증 범위, release owner 결정 유무.

각 scenario 기록에는 input, 기대 결과의 독립 근거, 실제 output, backend durable 상태, HTTP/SSE/WS events, tool calls, 변경 전후 파일 hash, elapsed, cleanup 결과를 넣는다. 기대값을 모델 답변에서 역으로 만들어 채점하지 않는다. 날짜·상태·run ID를 실행 후 추정하지 말고 실행 당시 기록한다.

### 5.3 판정 및 실패 처리

상태는 NOT_RUN → RUNNING → PASS / FAIL / INCONCLUSIVE / BLOCKED_ENV다. 재현 후 수정 중이면 FIXING, 수정 후 동일 실패 사례를 재실행하면 REVERIFYING으로 기록할 수 있다. PASS는 명시된 environment와 scenario에만 적용한다. BLOCKED_ENV에는 부족한 모델·runtime·device·account와 영향 범위를 구체적으로 기록한다.

실패한 요청을 지우고 마지막 성공만 남기지 않는다. harness의 잘못된 sequence 가정은 HARNESS_ERROR로 분류하고 원래 receipt를 보존한다. task sequence는 전역 ledger 조건을 읽어 연속성을 검사하며 매 요청이 seq=1로 시작한다고 가정하지 않는다.

LLM 모델의 seed를 API가 실제 지원·전송하는지 확인한다. 지원되면 3개 seed를 기록하고, 지원하지 않으면 3회 독립 실행이라고 표시한다. 다른 모델·예산·retrieval 설정의 결과를 동일 조건 비교로 부르지 않는다.

외부 서비스가 없으면 fake 성공을 실제 성공으로 표시하지 않는다. 실제 계정 write, publish, push, PR 생성, 외부 메시지 전송이 필요한 마지막 단계는 해당 실행의 명시적 범위가 있어야 한다. 그전까지 localhost fixture·local bare remote·격리 mock provider로 계약을 완성한다.

### 5.4 반복해서 지켜야 할 회귀 계약

1. required tool은 실제로 실행하고 no-tools·deny·read-only 제한을 동시에 지킨다. 모델 문장에 도구 이름이 있다는 이유로 실행으로 세지 않는다.
2. 검색 표는 해당 행/구절의 출처로 검증한다. table fragment의 인용, URL, mutable/immutable 문법 원문을 보존한다. verified same-row exact source 예외는 표현 변경에만 적용한다.
3. citation correction은 기존 최대 2회·4,096 token 예산을 보존한다. required search에 결과가 없으면 성공 완료로 승격하지 않는다.
4. durable task는 terminal 한 번·원인 상태·error 의미·version/event sequence를 보존하고 raw copy/UI/DB가 일치한다.
5. 취소는 같은 Context에서 create/next/close하고 shield/lock 정리 계약을 지킨다. blocking pull 완료 대기와 즉시 선점을 구분한다.
6. Chroma 동시 초기화·선택적 cache 정리·peer client 존속·reopen을 유지한다. 전체 client cache clear로 한 store를 정리하지 않는다.
7. 금융 숫자는 Decimal exact value·원래 단위/currency·source index를 유지한다. 누락된 날짜/currency를 추정해서 보충하지 않는다.
8. YAML vault 편집은 VaultEngine의 Git 흐름을 사용한다. 일반 계획 문서와 사용자 vault 데이터 편집을 혼동하지 않는다.

### 5.5 변경 검토와 rollback

각 작업의 code/test/docs 변경은 같은 task receipt에 묶고, 기존 동작과 실패 재현을 설명한 diff를 검토한다. 구현 코드 검토·수동 QA는 후속 실행에 적용되는 AGENTS/skill 지시를 따른다. 본 계획의 작성 검증이 그 구현 검토를 대신하지 않는다.

rollback은 해당 작업자가 만든 diff 또는 비활성 feature flag에만 적용한다. shared checkout의 reset/전체 restore/다른 staged 파일 삭제는 사용하지 않는다. DB schema·vector migration은 owned copy에서 먼저 검증하고 이전 데이터와 schema를 보존한다. provider·policy 변경은 오류 원인과 행동 테스트를 확인한 뒤 독립적으로 되돌릴 수 있게 한다. release 후보를 고정한 뒤 소유 코드를 되돌렸다면 source fingerprint와 영향 gate를 다시 측정한다.

## 6. 작업별 상세 실행 명세

### IMP-00 — 동일 소스·격리 실행·증거 수집 기반

**근거/목표:** E01/E02의 최종 범위를 재현할 기반을 만든다. 과거 전체 테스트의 source 이동과 HOME/config 누수를 방지한다. 선행 작업 없음.

**수정 소유:** 위 isolated_entry/live_driver를 읽고 필요한 공통 부분을 재사용한다. 신규 `scripts/run_sequential_audit.py`, `tests/test_sequential_audit_harness.py`는 제안 경로이며 아직 구현된 파일이 아니다. 기존 production config/auth를 harness용으로 약화하지 않는다.

**구현 순서:**

1. 소유 경로의 HEAD/diff/lock/sha와 E02를 기록한다. 공유 소스가 바뀌면 이전 run을 SOURCE_MOVED로 종료하고 새로운 receipt를 연다.
2. 테스트별 config, models/data/documents/vectors/logs/wiki, auth store, subprocess bootstrap을 하나의 owned temporary root로 연결한다. pytest 모드도 명시적 config를 쓴다.
3. process-local Path.home patch를 subprocess까지 전달하고 parent의 HOME/CODEX_HOME는 바꾸지 않는다. auth header 파일은 private permission을 사용한다.
4. 충돌 없는 loopback port와 테스트 lifespan on/off를 명시한다. provider fake 모드와 실제 Ollama 모드를 다른 scenario로 표시한다.
5. child/port/tempdir/browser ownership ledger와 finally cleanup을 구현한다. 보호해야 할 peer 저장소 sentinel hash를 함께 기록한다.

**검증 시나리오:** 서로 다른 임시 root의 두 suite를 동시에 실행하고 각 sentinel을 생성한다. A purge/cleanup 후 B 데이터가 그대로 있어야 한다. config가 일부 빠졌을 때 개인 경로를 사용하지 않고 preflight가 실패해야 한다. 시험 child가 실패해도 owned listener와 PID는 정리돼야 한다.

**완료 기준/산출물:** parent 환경 불변, 개인 저장소 접근 0, peer hash 불변, owned process/listener 0, manifest before/after 생성. self-test와 negative control receipt를 IMP-00에 저장한다. 허용 경로 바깥 접근이 감지되면 전체 실행을 시작하지 않는다. rollback은 신규 harness만 되돌리고 기존 감사 기록을 보존한다.

### IMP-01 — 현재 backend 전체 baseline와 CI 계약 재측정

**근거/목표:** E03/E04의 예전 전체 실패 수를 현재 소스 기준 결과로 교체한다. 선행 IMP-00. 테스트가 실행됐다는 사실과 구현 완료를 구분한다.

**수정 소유:** 먼저 테스트·fixture·receipt만 소유한다. [CI workflow](../../.github/workflows/ci.yml)의 실제 명령을 읽고 재현한다. 어떤 production failure를 수정할지는 failing selector와 trace를 얻은 뒤 해당 IMP 작업으로 배정한다.

**실행 순서:**

1. 같은 source manifest를 고정한 격리 환경에서 전체 backend suite를 실행한다. JUnit의 passed/failed/error/skipped/xfail를 각각 집계한다.
2. browser live-model skip, optional ML dependency, fixture error, assertion failure, timeout/hang, historical release 계약을 분리한다. 제외한 검사에는 selector와 이유를 남긴다.
3. 88개 browser 및 13개 legacy fixture가 현재도 정상인지 확인한다. 옛 실패가 이미 고쳐졌으면 다시 결함으로 만들지 않는다.
4. profiler/crashloop/finite soak의 후속 PASS도 재현 필요 시 같은 소스에서 확인한다. 근거 없는 원인 설명이나 불필요한 production patch를 넣지 않는다.
5. CI의 lint/format/type/package 명령은 현재 workflow를 기준으로 실행한다. 로컬 결과를 원격 Actions 성공으로 표시하지 않는다. 원격 결과가 필요하면 commit/run ID를 연결한다.

**검증 시나리오:** 동일 소스에서 나온 모든 failed/error selector가 원시 로그와 JUnit에서 1:1로 연결된다. 임의의 기존 assertion을 깨뜨린 한정 negative control은 실패로 잡히고 artifact에 구분돼야 한다. 테스트 목록·skip 조건을 통과율을 높이기 위해 축소하지 않는다.

**완료 기준/산출물:** 현재 전체 수치·실패 ledger·source 일치 여부·CI 명령 결과가 존재한다. 이 작업의 완료는 baseline 수집 완료다. failing suite가 있으면 제품 green으로 부르지 않고 소유 작업에 전달한다. 새 failure가 본 계획 밖이라면 IMP-01 추가 하위 작업으로 원인/구현/검증 계획을 명시한다.

### IMP-02 — 문서·release 계약의 의미 보존과 9개 selector 해결

**근거/목표:** E04/E05/E14. 5개 artifact 계약은 이미 보완됐고, 아래 9개는 후속 보고상 미해결이었다. 선행 IMP-01. 현재 재현 결과를 먼저 기록한다.

**수정 소유:** [README](../../README.md), [현재 상태](../20_CURRENT_STATUS.md), [단일 release 값 소유 문서](../ga/CR14_FINAL_CANDIDATE_VERDICT.md), 해당 historical 상태 문서. contract test/script 변경은 실제 요구사항 변경이 증명되는 경우만 별도로 설명한다.

**재현 selector:**

```text
tests/test_cr12_docs_alignment.py::test_readme_separates_rp_history_from_current_cr_state
tests/test_cr12_docs_alignment.py::test_readme_value_owner_pointer_is_enforced
tests/test_cr14_fence_movement_detection.py::test_no_code_scope_commit_after_the_declared_candidate
tests/test_cr14_fence_movement_detection.py::test_declared_fingerprint_is_the_fingerprint_of_head_within_the_fence
tests/test_cr14_fingerprint_scope_contract.py::test_readme_does_not_pin_the_tree_fingerprint
tests/test_nx07_doc_consistency.py::test_readme_does_not_claim_that_only_the_human_axis_remains
tests/test_nx07_doc_consistency.py::test_soak_phases_stay_separated
tests/test_nx07_doc_consistency.py::test_teeth_unscoped_human_axis_claim_is_detected
tests/test_nx07_doc_consistency.py::test_teeth_soak_done_promotion_is_detected
```

**구현 순서:**

1. 현재 실패를 문구 drift, single-owner 위반, candidate 이동, historical soak 판정 충돌로 분류한다.
2. README의 current 상태와 RP/CR history를 분리하고 현재 값은 owner 문서 링크로 전달한다. 영어 README 유지 요구와 상태 정확성을 함께 충족한다.
3. candidate SHA/fingerprint를 통과를 위해 현재 HEAD로 단순 치환하지 않는다. 과거 후보는 historical로 남기고 새 후보 측정은 IMP-20에서 별도 생성한다.
4. EX05의 원래 JSON metric PASS는 유지한다. wrapper exit 141과 run_sha_binding UNVERIFIED 때문에 전체 종료·귀속 판정은 INCONCLUSIVE로 명시한다. 이전 28,801.318초의 metric을 새 소스 8h 통과로 승격하지 않는다.
5. frozen historical contract와 current-candidate contract를 구분할 변경이 필요하면 기존 negative control을 보존하고 양쪽 의미를 검사한다. scope exclusions/fingerprint 계산을 완화하지 않는다.

**검증 시나리오:** README에 직접 fingerprint를 주입하면 검사 실패, owner pointer 삭제도 실패해야 한다. 코드가 후보 이후 바뀌면 candidate validity 검사 실패를 유지한다. JSON 지표 PASS만으로 종료·귀속 DONE 또는 GA GO가 되지 않아야 한다.

**완료 기준/산출물:** 각 9개 selector의 새 결과와 repair 근거를 제출한다. 새 후보가 필요한 selector는 IMP-20 의존으로 명시하고 이 단계에서 resolved라고 세지 않는다. 문서 중복 값 0, historical 결과 보존, 새 source 결과와 과거 결과 구분. 원래 release owner의 GO 결정권을 문서 수정으로 대신하지 않는다.

### IMP-03 — provider 오류·도구 실행 후 실패·취소 계약

**근거/목표:** E06/E09. QA06에서 native parser EOF/500이 실제로 있었으나 후속 실제 UI와 runtime은 통과했다. 요청 body가 확보되지 않아 정확한 parser 원인은 확정되지 않았다. 선행 IMP-01.

**시작 코드/소유:** [model_manager.py](../../src/antigravity_k/engine/model_manager.py)의 _do_ollama_generate/_build_stream_request/_do_ollama_stream, [inference_providers.py](../../src/antigravity_k/engine/provider_adapters/inference_providers.py)의 OllamaProvider._generate_native, [chat_agent_stream_generator.py](../../src/antigravity_k/api/chat_agent_stream_generator.py), [direct_task_execution.py](../../src/antigravity_k/engine/direct_task_execution.py).

**구현 순서:**

1. 실제 QA06의 provider endpoint·adapter·messages/tool schemas 경로를 trace한다. OpenAI compatible 경로와 native /api/chat 경로를 구분한다.
2. 요청 metadata·status·parser error type을 비밀정보 없이 관측한다. response_format/format 계약은 실제 wire 및 provider 버전으로 확인한 뒤 수정한다. 미확인 API 차이를 확정 버그로 취급하지 않는다.
3. 이미 있는 오류 타입을 우선 재사용해 transport/provider failure가 일반 답변 문자열이나 성공 DONE으로 해석되지 않게 한다.
4. 실패 회복은 미실행 또는 증명된 idempotent 요청에만 제한된 budget으로 허용한다. 도구가 실행된 뒤의 자동 재시도는 durable tool call ID/result를 재사용하며 side effect를 다시 실행하지 않는다.
5. ASGI 2.3 disconnect/2.4 send OSError, ContextVar close·취소 terminal 계약을 유지한다. blocking pull 지연은 측정하며 단순 task.cancel로 즉시 종료됐다고 주장하지 않는다.

**검증 시나리오:** read_file 한 번 뒤 provider500 → failed terminal 한 번·error 원인 명시·파일 hash 불변. recovery 허용 경로에서도 read_file 실제 호출은 한 번이다. 변형 tool이 실행된 뒤 장애에서는 자동 재실행 0. mid-token cancel 뒤 같은 대화의 후속 질문은 42/done이고 seq/version이 연속이다.

**완료 기준/산출물:** native/compatible·stream/non-stream 실패 fixture와 실제 installed Qwen 재실행 모두 명확한 판정. wire receipts, tool call counts, DB terminal, error/cancel elapsed, cleanup 증거 제출. upstream 원인 미확인은 별도 잔여 항목으로 남긴다. rollback은 provider별 변경을 분리하고 기존 취소 수정은 보존한다.

### IMP-04 — 검색 답변·citation·실제 모델 신뢰도 확대

**근거/목표:** E07/E08. 최종 두 번은 성공했지만 질문·모델 범위가 좁다. 선행 IMP-01/03.

**시작 코드/소유:** [tool_loop.py](../../src/antigravity_k/engine/tool_loop.py)의 ToolLoopEngine._citation_revision, [citation_table_contract.py](../../src/antigravity_k/engine/citation_table_contract.py)의 render_verified_exception_output, [search_quality_evaluator.py](../../src/antigravity_k/tools/search_quality_evaluator.py)의 evaluate_citations. web search 구현은 graph로 현 경로를 확인한다.

**구현 순서:**

1. 개발용 20개·holdout 20개, 합계 40개의 서로 다른 질문을 만든다. 공식 문서 표, 버전 조건, 한국어, negation, source 충돌, 결과 0, network error, Markdown 링크, 코드 backtick을 포함한다.
2. retrieved source snapshot과 정답 근거를 고정한 deterministic suite와 실제 search/provider suite를 분리한다. actual source의 날짜·URL·응답을 기록한다.
3. QA09를 포함해 같은 모델·token/search 예산으로 3회 paired baseline/candidate를 실행한다. seed 미지원이면 3회 반복이라고 표시한다.
4. 행/구절별 근거, 문법 원문, source relevance, 표 보존, no false completion을 각각 채점한다. 단순 citation marker 개수를 품질로 사용하지 않는다.
5. 실제 실패가 확인된 경로만 수정한다. correction budget 2회/4,096 및 verified exact-source 예외 범위를 넓히지 않는다.

**검증 시나리오:** 한 행의 URL만 다른 행에 붙인 표는 실패; malformed 문법을 source 없이 정당화한 답변도 실패; empty required search는 done이 될 수 없다. 검증된 같은 행의 문법 원문은 보기 개선 후에도 보존된다. raw response·UI 복사·task DB final output이 동일하다.

**완료 기준/산출물:** deterministic critical negative cases 100% 통과, holdout의 근거 없는 DONE 0, 기존 QA09 3회 모두 계약 통과. paired citation/correctness/latency/token/false-completion 지표를 제출하고 새 수정의 이득 또는 tradeoff를 설명한다. 모델 자유서술의 일반 100% 정확도를 주장하지 않는다.

### IMP-05 — 실행 제약·read-only·approval의 실제 경계

**근거/목표:** E01의 no-tools/required/approval은 통과했다. 임의 shell의 모든 쓰기를 의미 분석한다는 보장은 없다. 선행 IMP-01.

**시작 코드/소유:** ToolLoop 실행 지점과 현재 PermissionGate/SandboxRunner/approval 구현을 graph로 찾는다. [browser_session_owner.py](../../src/antigravity_k/tools/browser_session_owner.py)의 owner 계약을 함께 읽는다. 새로운 policy 구조가 필요하면 기존 값 객체에 최소 확장하고 별도 정책 엔진을 중복 생성하지 않는다.

**구현 순서:**

1. 사용자 제약을 tool invocation 전에 적용되는 typed constraint로 전달하는 경로를 확인한다. prompt 문구만으로 read-only가 보장되는지 검사한다.
2. 직접 write tool, shell redirection, interpreter file write, subprocess·symlink·workspace 밖 경로를 owned fixture로 검증한다.
3. 기존 OS sandbox/allowlist가 쓰기 효과를 강제하면 그것을 사용한다. 강제가 불가능한 opaque command는 read-only 모드에서 거절하거나 지원 불가를 명시한다.
4. approval once/deny/withdraw/session ownership을 permission boundary에 연결한다. 도구 실행 결과에서 성공·거절·미지원 원인을 구분한다.
5. lexical denylist만으로 모든 임의 코드의 쓰기를 차단한다고 표기하지 않는다. sandbox 미지원 플랫폼은 capability에 드러낸다.

**검증 시나리오:** no-tools 요청은 tool calls 0. required read+no-write 요청은 read 1·writes 0·sentinel hash 불변. `printf x > sentinel`, 짧은 Python write, nested subprocess, symlink escape는 승인되지 않으면 실행되지 않는다. owner A의 승인으로 owner B가 browser 작업을 수행할 수 없다. once는 실제 invocation 한 번에만 소비한다.

**완료 기준/산출물:** 정책별 허용/차단 표와 actual tool ledger, sentinel hashes, platform sandbox capability 제출. 거절 상태를 성공으로 취급하지 않는다. 명시된 write boundary negative cases 전부 통과. rollback 시 기존 deny/once/withdraw 보호를 제거하지 않는다.

### IMP-06 — 긴 대화 압축·원본 이력·제약 보존

**근거/목표:** E01의 짧은 compact r4는 통과, 장문 품질은 미검증. 선행 IMP-01/05.

**시작 코드/소유:** [context_compressor.py](../../src/antigravity_k/engine/context_compressor.py)의 compress/_summarize_old_messages/adaptive/RAG 경로, [conversation_store.py](../../src/antigravity_k/engine/conversation_store.py)의 compact/original_history/assemble_history_for_request, [conversation_api.py](../../src/antigravity_k/api/routes/conversation_api.py)의 compact_conversation. API compact와 model context compression은 다른 기능이다.

**구현 순서:**

1. installed 모델의 context limit 기준 25/75/110% 길이 fixture를 만들고 turn ID·fact·정정·출처·명시적 tool 제약을 넣는다.
2. API compact의 CAS/version/branch와 model context의 요약 손실을 별도로 검증한다. original export는 수정하지 않는다.
3. 현재 summary role=system 경로에서 사용자/자료 지시가 system authority로 승격되는지 시험한다. 문제가 재현되면 출처/권한 계층을 보존하는 최소 변경을 한다.
4. fact preservation·최근 정정·deny/no-write 유지·token budget을 각각 측정한다. 출처 없는 요약 정보를 확정 근거로 사용하지 않는다.

**검증 시나리오:** 80개 fact 중 중요 fact 10개·최근 정정 5개·권한 제한 5개를 독립 oracle로 검사한다. 초기 문서의 악성 명령은 compact 후에도 도구 정책을 바꾸지 못한다. concurrent compact/fork는 revision conflict를 올바르게 처리하며 원본 hash가 그대로다.

**완료 기준/산출물:** 권한 보존·원본/branch 불변·budget 상한 critical cases 100% 통과. 중요한 사실 10개와 정정 5개가 답변·summary에서 유지된다. 일반 회상 점수는 paired로 보고한다. fixture/summary/raw answer/token/version/original export를 제출한다. 품질 미달이면 default compressor 변경을 활성화하지 않는다.

### IMP-07 — 실제 embedding·RAG namespace·memory lifecycle

**근거/목표:** E10의 실제 Chroma 8/8 및 purge는 통과했지만 embedding 일부가 대체 포트다. 선행 IMP-01.

**시작 코드/소유:** [chroma_lifecycle.py](../../src/antigravity_k/engine/chroma_lifecycle.py), [vector_store.py](../../src/antigravity_k/engine/vector_store.py), [gbrain.py](../../src/antigravity_k/engine/gbrain.py). workspace startup/index 경로는 graph에서 trace한다.

**구현 순서:**

1. 설치된 embedding 모델로 공개·합성 문서 30개와 20개 query/정답 document ID를 만든다. model unavailable은 별도 상태다.
2. 서로 다른 namespace A/B와 같은 root의 multi-client를 생성한다. concurrent initialize/write/read/reopen을 반복한다.
3. workspace 밖 sentinel과 B 문서가 A retrieval/purge에 들어오지 않게 검사한다. registry/cache 정리는 store 소유 범위만 적용한다.
4. 문서 수정·삭제·재색인·restart 후 stale vector와 source attribution을 검사한다. embedding dim/model 변경은 명시적으로 migration 또는 incompatible로 처리한다.

**검증 시나리오:** 정답 한 개가 뚜렷한 controlled query 10개는 top-5에 해당 문서를 포함한다. A purge/reopen 후 A 0, B vector/graph/hash는 불변. 8 clients 동시 재시작에도 duplicate init 오류·peer close·cache 피해 0. deleted source는 새 답변 근거로 사용되지 않는다.

**완료 기준/산출물:** namespace leak 0·purge residual 0·peer 손상 0·controlled top-5 10/10. 실제 embedding 설정과 recall/nDCG/latency/RSS를 기록한다. 일반 문서 품질 향상을 주장할 경우 동일 corpus/예산 baseline 대비 결과가 있어야 한다. 실패한 migration은 기존 store를 덮어쓰지 않고 보존한다.

### IMP-08 — frontend 경고 제거와 실제 로딩 성능

**근거/목표:** E11의 lint 36 warnings 및 큰 청크 경고. 선행 IMP-01. warning 존재 자체를 재현되지 않은 사용자 오류로 단정하지 않는다.

**수정 소유:** [client.ts](../../dashboard/src/api/client.ts), [ActivityTimeline.tsx](../../dashboard/src/components/Chat/ActivityTimeline.tsx), [ChatPage.tsx](../../dashboard/src/components/Chat/ChatPage.tsx), [EnvironmentPanel.tsx](../../dashboard/src/components/Chat/EnvironmentPanel.tsx), [SearchIntegrationPanel.tsx](../../dashboard/src/components/Search/SearchIntegrationPanel.tsx), [TaskQueuePanel.tsx](../../dashboard/src/features/task-execution/TaskQueuePanel.tsx), [useConversationFork.ts](../../dashboard/src/hooks/useConversationFork.ts), 해당 tests 및 [vite.config.ts](../../dashboard/vite.config.ts). 실제 파일 경로는 시작 시 다시 확인한다.

**구현 순서:**

1. 현재 lint를 다시 실행하고 36개 원래 경고와 새 경고를 비교한다. unused imports, effect deps, render purity/ref writes, unsafe finally를 분류한다.
2. Date.now를 render마다 읽는 구간은 상태 수명에 맞춘 clock/input으로 바꾸고, effect는 필요한 synchronization만 수행한다. finally가 오류·취소 흐름을 덮는지는 behavioral test로 확인한다.
3. warning을 eslint disable/type suppression으로 숨기지 않는다. 기존 unrelated warning은 위치·이유와 별도 backlog를 남긴다.
4. 초기 route의 network trace/critical JS bytes/time-to-interactive를 먼저 측정한다. Monaco 약 4,505KB·ELK 약 1,452KB·mindmap 약 544KB는 전체 chunk 크기다.
5. 실제 초기 로딩에 포함되는 불필요한 editor/graph module만 route 또는 interaction 기준으로 lazy-load한다. chunkSizeWarningLimit을 올려 경고를 지우지 않는다.

**검증 시나리오:** cancel/fork/search/queue에서 warning 수정 전후 상태·exception 결과가 동일하고 race가 없다. default chat route에서 사용하지 않은 editor/graph 청크가 선행 요청되지 않는다. editor/mindmap route 진입 후 기능이 작동하고 chunk 실패 시 회복 UI가 나온다.

**검증 명령:** `pnpm --dir dashboard test`, `pnpm --dir dashboard typecheck`, `pnpm --dir dashboard lint`, `pnpm --dir dashboard build`. build는 dashboard_dist를 갱신하므로 소유 변경으로 명시한다.

**완료 기준/산출물:** 원래 36개 경고의 각 disposition, 소유 코드 경고 0, 새 warning 0, tests/typecheck/build 통과. 14 route의 375/768/1280 캡처와 keyboard/scroll 회귀, cold/warm network 자료를 제출한다. initial-load 개선이 측정되지 않으면 bundle 구조 변경을 채택하지 않는다.

### IMP-09 — 모델·provider별 실제 capability matrix

**근거/목표:** installed 6개 목록은 확인됐지만 실제 답변은 현재 Qwen 중심이다. 선행 IMP-03.

**시작 코드/소유:** ModelManager와 model registry, provider adapters, [StudioPage.tsx](../../dashboard/src/pages/StudioPage.tsx)의 capability 화면, dashboard model selector. 모델 catalog entry의 표시와 실제 runtime capability를 구분한다.

**구현 순서:**

1. 시작 시 실제 installed model/provider/version을 기록한다. 새 대형 모델을 자동 다운로드하지 않는다.
2. text, stream, structured JSON, required tool, no-tools, vision, embedding, training/export를 독립 capability로 표시한다.
3. 각 실제 설치 모델에 text/stream/JSON/unsupported request를 실행한다. tools/vision은 지원 주장한 모델만 실행한다.
4. compatible/native의 response format 및 tool 메시지가 실제 wire에 어떻게 전달되는지 capture한다. catalog의 추정 capability를 확인 결과와 혼동하지 않는다.
5. unsupported 요청은 일관된 typed error와 화면 설명으로 전달하고 성공/blank output으로 처리하지 않는다.

**검증 시나리오:** embedding-only 모델은 chat selector에 잘못 노출되지 않는다. vision 없는 모델의 image 요청은 명확히 거절된다. tools 지원 모델은 read 1회, non-support 모델은 실행 전 거절. 모델 unavailable 상태는 offline/available로 잘못 표시되지 않는다.

**완료 기준/산출물:** 설치된 모든 모델의 capability×scenario×actual result 표, 실제 provider wire, unsupported negative cases. 환경 없는 capability는 NOT_RUN/BLOCKED_ENV. 지원 여부가 바뀐 UI와 API가 일치해야 한다. rollback은 capability 표시/adapter 변경을 모델별로 분리한다.

### IMP-10 — 활성 agency·scheduler·restart·중복 실행

**근거/목표:** off 상태와 finite scheduler만 확인했다. 선행 IMP-03/05.

**시작 코드/소유:** [persistent_agency.py](../../src/antigravity_k/engine/persistent_agency.py)의 enqueue_objective/claim_next/bind_task/scheduler_decision/pause/resume, [persistent_agency_store.py](../../src/antigravity_k/engine/persistent_agency_store.py), [agency_api.py](../../src/antigravity_k/api/routes/agency_api.py), [scheduled_job_service.py](../../src/antigravity_k/engine/scheduled_job_service.py)의 tick, [workspace_service_runtime.py](../../src/antigravity_k/engine/workspace_service_runtime.py).

**구현 순서:**

1. owned workspace에서 feature on, lifespan on으로 실제 service를 시작한다. disabled default는 유지한다.
2. 제한된 objective 3개와 scheduled job 3개를 등록하고 claim/run/observation/checkpoint를 확인한다.
3. pause/resume/cancel, 두 worker 경쟁, process restart 후 lease/recovery, retry budget을 시험한다.
4. durable task와 legacy Kanban의 상태 저장소를 별도로 검증한다. scheduler event를 대화 답변 success로 오인하지 않는다.
5. side effect idempotency는 durable job/run key와 완료 receipt로 검증한다. loop가 tick마다 같은 side effect를 반복하면 해당 경로만 수정한다.

**검증 시나리오:** append-only owned counter job은 허용 run마다 정확히 한 번 증가한다. claim 후 crash/restart에서도 중복 수행 0. pause 중 새 claim 0, resume 후 정상 재개. cancel terminal 1회, tool 정책 유지, retry 상한 뒤 failed/error 원인 명시.

**완료 기준/산출물:** active finite 시나리오 통과·중복 side effect 0·무한 retry 0·restart 결과·cleanup 0. 8시간 soak는 여기서 완료 처리하지 않고 IMP-20에서 동일 후보로 실행한다. 외부 delivery가 필요한 항목은 IMP-13의 환경별 판정으로 연결한다.

### IMP-11 — 실제 STT/TTS 및 마이크 경로

**근거/목표:** 합성 transcriber API 21검사는 통과했지만 실제 STT/TTS/mic는 미검증. 선행 IMP-00/09.

**시작 코드/소유:** [voice_service.py](../../src/antigravity_k/engine/voice_service.py)의 transcribe/synthesize/_configured_transcriber/_macos_synthesizer, [voice_api.py](../../src/antigravity_k/api/routes/voice_api.py)의 audio validation/transcribe/voice-command/synthesize.

**구현 순서:**

1. 현재 AGK_STT_COMMAND_JSON의 installed transcriber와 platform TTS availability를 확인한다. 임의 shell string 대신 argv 계약을 유지한다.
2. 공개·합성 PCM fixture 10개를 한국어/영어/숫자/무음/짧은 입력으로 준비한다. 개인 음성을 자동 수집하지 않는다.
3. 실제 STT stdout parsing·timeout·exit failure·temp file unlink·network policy를 검증한다.
4. 실제 TTS의 유효 audio 출력과 재생 경로를 확인한다. microphone 권한/장치가 있으면 별도 interactive case를 실행한다.

**검증 시나리오:** unsupported type 422, oversized 413, no transcriber는 명확한 unavailable. 숫자 marker 42/47을 포함한 4개 controlled fixture는 marker를 보존한다. 무음은 성공한 명령으로 tool을 실행하지 않는다. 실패/취소 뒤 temp audio가 남지 않는다.

**완료 기준/산출물:** actual STT/TTS command/version/audio format·transcript·latency·cleanup, fixture WER와 marker 결과. mic가 없으면 STT/TTS PASS와 mic BLOCKED_ENV를 분리한다. 실제 transcriber 없는 환경에서 fake receipt로 종료하지 않는다.

### IMP-12 — 최소 실제 학습·export·reload 검증

**근거/목표:** E12의 cancellation은 실제 child에서 확인됐고 production cancel route의 blocking 원인은 재현되지 않았다. 실제 weight 학습은 미검증. 선행 IMP-00/09.

**시작 코드/소유:** [training_jobs_api.py](../../src/antigravity_k/api/routes/training_jobs_api.py)의 _run_job/start/get/cancel/_Job, [task_process_supervisor.py](../../src/antigravity_k/engine/task_process_supervisor.py), [unsloth_training_mcp.py](../../src/antigravity_k/engine/provider_adapters/unsloth_training_mcp.py), Studio capability 화면.

**구현 순서:**

1. 실제 설치된 training runtime/backend/hardware의 지원 범위를 먼저 확인한다. 지원하지 않으면 원인을 명시하고 disabled export를 유지한다.
2. synthetic 16개 train/4개 holdout과 작은 로컬 모델 또는 adapter를 사용한다. base checkpoint를 복사/참조하고 원본 hash를 보존한다.
3. 짧은 bounded job으로 실제 weight 또는 adapter 변경을 확인한다. job progress/log와 artifact path를 실제 child에서 받아 기록한다.
4. export format manifest와 reload를 확인한다. 단순 파일 생성이나 fake child output을 학습 완료로 세지 않는다.
5. signal-gated blocked child의 cancel+동시 GET 회귀를 유지하고 실제 training 중 취소도 확인한다.

**검증 시나리오:** 실제 checkpoint digest는 달라지고 원본은 불변. reload inference가 유효하고 format mismatch는 명확히 실패한다. cancel 후 owned process/group가 없어야 하고 terminal은 한 번이다. invalid recipe가 외부 경로를 덮어쓰지 않는다.

**완료 기준/산출물:** real train/export/reload receipts·runtime/version·dataset hash·changed checkpoint·base 불변·resource/cancel 자료. holdout 결과는 관측값으로 보고하며 20개 예시만으로 모델 품질 향상을 주장하지 않는다. hardware 없는 환경은 BLOCKED_ENV로 남긴다.

### IMP-13 — MCP·plugins·remote·Git/browser 연동 경계

**근거/목표:** catalog/health/empty/OAuth 대상 0/로컬 Git/browser는 통과했지만 실제 external lifecycle은 미검증. 선행 IMP-05/09.

**시작 코드/소유:** [system_api.py](../../src/antigravity_k/api/routes/system_api.py)의 list_mcp_servers/mcp_health_status/mcp_oauth_status 및 OAuth start/callback/complete/revoke, browser owner/ledger/tools. plugin·remote·Git 구현은 정확한 registry/route를 graph로 찾는다.

**구현 순서:**

1. local MCP stdio와 loopback HTTP fixture를 각각 시작한다. init/list/tool call/timeout/disconnect/restart/cancel을 실제 프로세스로 확인한다.
2. OAuth state/nonce/PKCE 등 현재 구현 계약을 읽고 loopback identity fixture로 성공·state mismatch·expired·revoke를 검증한다. 존재하지 않는 보호가 있다고 가정하지 않는다.
3. local fixture plugin을 install/load/invoke/disable/remove하고 permission/schema 실패를 검사한다. frontend 등록만을 설치 성공으로 세지 않는다.
4. 임시 bare Git remote로 push/fetch/diverged/reject를 검증한다. 실제 hosted push/PR는 해당 실행에 명시된 계정·범위에서만 한다.
5. local browser form으로 approval once/deny/withdraw/session isolation과 remote provider failure를 검사한다. 실제 계정 messaging은 이 계획의 기본 시나리오에 포함하지 않는다.

**검증 시나리오:** unauthorized tool 호출 0, invalid OAuth state 수락 0, revoke 뒤 재사용 0. crash한 MCP process는 health에 드러나고 zombie가 없다. plugin 제거 뒤 command palette/route가 stale하지 않다. bare remote의 push reject를 성공으로 표시하지 않는다.

**완료 기준/산출물:** 각 transport와 lifecycle별 실제 receipts·protocol messages·owner/approval counts·local remote commit digest. 외부 서비스별 live 여부를 별도 표로 제출한다. 실계정 환경이 없으면 외부 설치/OAuth/publish는 BLOCKED_ENV로 남긴다.

### IMP-14 — populated 파일 이력·inline editor·terminal child·TUI

**근거/목표:** E01의 파일 이력은 빈 상태, editor는 파일 표시, terminal은 parent PID 종료만 확인했다. 선행 IMP-01/05.

**시작 코드/소유:** [HistoryPage.tsx](../../dashboard/src/pages/HistoryPage.tsx), [localHistoryStore.ts](../../dashboard/src/stores/localHistoryStore.ts) 및 기존 store tests, [system_api.py](../../src/antigravity_k/api/routes/system_api.py)의 websocket_terminal, TaskProcessSupervisor. inline completion/TUI는 graph로 exact entry를 확인한다.

**구현 순서:**

1. owned 파일의 v1/v2/v3 이력을 실제로 생성하고 diff/select/reload/restore를 확인한다. conversation history와 파일 이력을 혼동하지 않는다.
2. inline completion의 실제 model request·cancel·stale result·accept/reject를 검사한다. 편집 중 파일 revision이 바뀌면 옛 결과를 적용하지 않게 한다.
3. terminal cleanup의 현재 parent signal/time.sleep 경로를 읽고 nested child·grandchild를 owned process로 생성한다. 이것은 구조상 위험 검증이지 이미 관측된 child leak이라는 판정이 아니다.
4. 실제 leak 또는 event-loop block이 재현되면 기존 process-group supervisor를 재사용해 개선한다. 사용자 process나 다른 세션을 종료하지 않는다.
5. TUI help/input/cancel/EOF/resize를 finite pseudo-terminal로 실행한다. IDE launch는 설치된 IDE/local fixture에서 별도 판정한다.

**검증 시나리오:** restore v1 뒤 내용 hash=v1, 다른 파일 이력 hash 불변, reload 뒤 snapshot 유지. stale completion은 적용 0. terminal close 뒤 parent/child/grandchild 종료·동시 health 응답 유지. unauthorized/foreign Origin WS 거절. TUI EOF 뒤 listener/PID 0.

**완료 기준/산출물:** populated history 캡처·content hashes·inline model trace·PID tree before/after·concurrent health latency·finite TUI transcript. 환경 없는 IDE/TUI는 별도 BLOCKED_ENV. 모든 owned process가 정리되지 않으면 이 작업을 PASS로 판정하지 않는다.

### IMP-15 — finance 지원 상태 안내를 실제 구현과 일치

**근거/목표:** [slash_commands_workflow.py](../../src/antigravity_k/engine/slash_commands_workflow.py)의 _cmd_finance는 DCF/Comps/3-Statement 및 financial-assistant/fa-modeling 스킬을 장착했다고 안내하지만, 읽은 경로는 문장 반환뿐이었다. 감사에서는 DCF/comps 계산이 미구현이다. 선행 IMP-01.

**수정 소유:** _cmd_finance, [slash_commands_base.py](../../src/antigravity_k/engine/slash_commands_base.py)의 finance/comps/dcf aliases, capability/help/command palette. existing financial_numbers는 이 작업에서 다시 만들지 않는다.

**구현 순서:**

1. 현재 alias별 실행·help·UI 표시를 재현하고 실제 skill load/calculator 연결이 있는지 trace한다.
2. 숫자 추출/단위/출처 보존 등 현재 제공 기능을 정확히 표시한다. 계산기가 없으면 계산 미지원/준비 필요 상태를 반환한다.
3. 실제 registry 확인 없이 skill installed/attached를 선언하지 않는다. capability 값은 alias/help/UI가 같은 출처를 쓰게 한다.
4. IMP-16이 완료된 경우에만 DCF/comps ready를 올릴 수 있게 한다. 3-Statement는 이 계획에 새 구현이 없으므로 별도 지원 여부를 정확히 표시한다.

**검증 시나리오:** calculator 없음 → /finance·/dcf·/comps가 지원 완료라고 말하지 않고 계산 결과를 꾸미지 않는다. 숫자 추출 기능은 기존 exact Decimal fixture를 통과한다. skill registry empty 상태에서 장착했다고 안내하지 않는다.

**완료 기준/산출물:** 사용자 안내/API capability/help/palette의 실제 지원 상태 일치, unsupported 계산 성공 0, 기존 금융 숫자 회귀 통과. before/after outputs와 capability tests를 제출한다. 계산기 구현을 기다리지 않고 이 항목을 먼저 완료한다.

### IMP-16 — 선택 범위: deterministic DCF/comps 계산기

**근거/목표:** NEW-CAPABILITY. 후속 실행에서 이 기능을 개발 범위로 선택했을 때만 진행한다. 선행 IMP-15/17. 시장 데이터나 투자 판단을 모델이 추정해 계산 입력으로 사용하지 않는다.

**신규 소유 제안:** `src/antigravity_k/engine/financial_valuation.py`, `tests/test_financial_valuation.py`. 현재 존재하는 구현 파일이라는 뜻이 아니다. 기존 금융 숫자 parser에 계산 로직을 섞지 않는다.

**계산 계약:**

- DCF 입력: 연도별 명시적 FCF, discount rate r, terminal growth g, cash/debt, shares, currency, unit, as_of, source IDs. Decimal 기반, 마지막 표시 단계만 반올림.
- 식: EV = Σ FCF_t/(1+r)^t + [FCF_n×(1+g)/(r-g)]/(1+r)^n. Equity=EV+cash-debt, per_share=Equity/shares. r>g, shares>0 등 domain 검증.
- Comps 입력: 동일 currency/unit/as_of 기준 peer EV/EBITDA와 target EBITDA/cash/debt/shares. 선택 통계는 median으로 명시한다. 음수/0 EBITDA·불일치 통화·누락값은 정책에 따라 제외 사유 또는 error를 반환한다.
- 모든 가정·입력·단위·제외 사유·공식·source를 계산 결과에 포함한다. 상용 제품 지원 여부는 독립 capability flag로 제어한다.

**구현 순서:** pure typed calculation → independent oracle tests → request validation → capability-gated slash/API 연결 → 입력·가정 표시 UI. 기존 source/Decimal parser가 제공한 값을 그대로 재사용한다. 암묵적 currency conversion이나 시장 API 조회를 추가하지 않는다.

**독립 oracle fixture:** FCF=[100,110,121], r=0.10, g=0.02, cash=20, debt=80, shares=10, 단일 currency/unit. PV_FCF=272.727272727…, terminal=1542.75, EV=1431.818181818…, Equity=1371.818181818…, per_share=137.181818181…. final 2자리 표시만 EV=1431.82/per_share=137.18이다. peer multiple=[6,8,10]이면 median=8; target EBITDA=50이면 EV=400, 같은 cash/debt/shares이면 per_share=34.

**검증 시나리오/완료 기준:** oracle exact Decimal 허용 오차와 rounding 정책을 명시한다. r=g/negative shares/mixed currencies/missing date/source는 accepted success가 될 수 없다. source index/원래 unit은 보존한다. 기능 off에서 계산 ready 표시 0. pure 계산/API/UI/raw copy 일치와 independent reference 결과를 제출한다. 기능 미선택 시 current 지원 상태는 IMP-15대로 유지한다.

**산출물:** 입력 schema·typed pure calculator·독립 oracle JSON·invalid-input receipt·capability off/on 결과·UI/raw 계산표·rounding/source manifest를 IMP-16에 저장한다. rollback은 계산 capability를 off로 돌리고 기존 추출 기능을 유지한다.

### IMP-17 — vision·추출 품질 범위와 숫자 정확도 확장

**근거/목표:** 실제 image 및 4개 입력 20필드 결과를 일반 정확도로 확대하지 않는다. 선행 IMP-01/09.

**시작 코드/소유:** [data_extractor.py](../../src/antigravity_k/engine/data_extractor.py)의 extract_numeric_data, [financial_numbers.py](../../src/antigravity_k/engine/financial_numbers.py)의 extract_financial_numbers, attachment/vision의 exact API/model 경로는 graph에서 찾는다.

**구현 순서:**

1. 합성·공개 fixture 50개를 HTML/text/table/image, 한국어/영어, 단위/천 단위/음수/범위/누락/null/긴 소수/잘못된 형식으로 구성한다. 30 development/20 holdout을 고정한다.
2. 필드별 exact value/type/null/currency/unit/source span을 사람이 읽을 수 있는 oracle JSON으로 작성한다. missing 값은 추정하지 않는다.
3. deterministic parser와 actual vision 결과를 분리하고 actual model/version을 기록한다. JPEG/PNG/WebP/GIF 지원은 현재 capability에 따라 확인한다.
4. valid decimal의 scalar compatibility는 exact binary float일 때만 사용하고, 그외 exact string 보존의 기존 계약을 유지한다.
5. 실제 실패 유형에 맞춰 parser/schema/vision prompt를 최소 변경하고 holdout을 개발 중 수정하지 않는다.

**검증 시나리오:** 0/null/missing은 서로 구분, long decimal은 truncation 0, 중복 숫자 중 올바른 source를 선택, unsupported media 거절, HTML instruction이 도구 권한을 바꾸지 않는다. 깨진 표를 성공 완성 표로 꾸미지 않는다.

**완료 기준/산출물:** controlled numeric/value/unit/source 계약 100% 통과, holdout missing-value hallucination 0, 필드별 accuracy/precision/recall와 vision actual subset 결과. 기존 4입력20필드 회귀 유지. 일반 vision 지표는 baseline 대비로 보고하며 미설치 모델에 PASS를 부여하지 않는다.

### IMP-18 — 선택 범위: 활성 cognitive·평가 의사결정의 실제 효과

**근거/목표:** off 상태/API/QualityGate 97은 통과했다. 과거 mutation snapshot은 현재 활성 결과가 아니다. 선행 IMP-01/03. feature flag off 기본값을 유지한다.

**시작 코드/소유:** [quality_gate.py](../../src/antigravity_k/engine/quality_gate.py)와 cognitive_surface/cognitive decision/experience 구현은 graph로 exact symbol을 찾는다. 기존 평가 엔진에 연결하고 중복 gate를 만들지 않는다.

**구현 순서:** current baseline와 cognitive candidate를 동일 모델·token/time/search budget으로 비교한다. 20 development/20 holdout task 및 3회 반복을 고정하고 정답 성공, false completion, tool 비용, latency, 반복 어휘 우회, mutation provenance를 기록한다. 설명 점수 상승만으로 실제 task 이득이라고 판정하지 않는다.

**검증 시나리오:** low-diversity 답변은 긴 길이로 gate를 우회하지 못한다. 제안된 mutation은 허용된 owned scope에서만 적용된다. source/run mismatch snapshot은 current proof로 거절된다. 중단·provider 실패를 objective done으로 바꾸지 않는다.

**완료 기준/산출물:** policy/false-completion critical cases 통과, paired efficacy 결과와 채택/기각 근거. holdout success가 악화되거나 false completion이 증가하면 default 활성화 금지. 개선이 측정되지 않으면 REJECTED_EXPERIMENT로 보존하고 기능 off를 유지한다. 선택하지 않은 작업은 이번 release에 cognitive 이득을 주장하지 않는다.

### IMP-19 — 실제 wheel 설치·SBOM·패키지 provenance

**근거/목표:** E05의 6개 dependency/notices 및 67개 계약 보완은 새 wheel 설치 증명이 아니다. 선행 IMP-02/03/05/08/15.

**수정 소유:** pyproject/uv.lock/package metadata/SBOM/notices generator, CI package job, 설치 smoke harness. dependency 버전은 current lock에서 가져오고 계획 문서의 숫자를 새 lock으로 삼지 않는다.

**구현 순서:**

1. IMP-02의 문구 drift 수정과 historical/new-candidate 경계가 정리됐는지 확인한다. 후보 고정 이후 다시 측정할 항목은 남겨 둔다.
2. 같은 scoped source에서 dashboard build와 wheel을 만든다. artifact SHA256, included files, lock/SBOM/notices 연결을 기록한다.
3. 깨끗한 venv에 non-editable wheel을 설치하고 저장소 밖 cwd에서 CLI/API/dashboard assets import·help·health·finite task를 실행한다.
4. PYTHONPATH/source checkout 의존을 제거하고 package data·lazy optional import·default config bytes를 확인한다.
5. cssselect/lxml/orjson/scrapling/tld/w3lib을 포함한 실제 설치 dependency와 SBOM/notices를 비교한다. 모듈 import 성공만으로 license completeness를 판정하지 않는다.

**검증 시나리오:** source tree 없는 cwd에서 UI 정적 파일과 CLI/API가 동작. 필수 packaged asset을 하나 뺀 한정 mutation은 smoke 검사 실패. optional GPU training dependency 없는 설치에서도 core가 시작되고 capability는 unavailable. config byte drift와 missing SBOM dependency는 검사 실패.

**완료 기준/산출물:** wheel digest·non-editable 설치 receipt·밖 cwd smoke·package manifest·SBOM 비교·default config 계약. install이 source tree를 참조하면 FAIL이다. package version·배포 여부·원격 CI 상태를 각각 구분한다. 공개 publication은 이 작업의 자동 단계가 아니다.

### IMP-20 — 새 후보 고정·전체 재검증·8시간 soak·최종 판정

**근거/목표:** 현재 소스의 통합 품질과 release 근거를 새로 만든다. 선행은 의존 표를 따른다. IMP-02의 candidate-dependent selectors는 이 단계에서 최종 해결한다. 선택 IMP-16/18을 포함했다면 두 작업도 선행 조건이다.

**시작 코드/소유:** [ga_gate.py](../../scripts/ga_gate.py)의 worktree_fingerprint/tree_digests, [ga_gate_verify.py](../../scripts/ga_gate_verify.py)의 verify_gate_report/verify_soak_artifact, [collect_soak_result.py](../../scripts/collect_soak_result.py)의 expected fingerprint/judge, [soak_control.sh](../../scripts/soak_control.sh), release owner 문서.

**실행 순서:**

1. 모든 소유 변경과 미검증 범위를 확정한다. clean release 후보가 필요하면 사용자가 허용한 commit 범위만 확정하고 다른 staged 파일을 끌어오지 않는다. 후보 commit이 없으면 committed release 검증을 완료했다고 말하지 않는다.
2. 기존 gate가 정의한 scope/fence로 새 candidate fingerprint를 계산한다. historical SHA·fingerprint·8h 결과는 보존하고 새 run과 명시적으로 연결한다.
3. 동일 후보에서 전체 backend·frontend·package 설치·27기능 시나리오를 수행한다. 정확한 source before/after를 대조한다. 코드가 바뀌면 영향 검증 및 후보 binding을 갱신한다.
4. 실제 provider와 활성 service를 사용한 새 8시간 soak를 수행한다. 기존 schema/SC1..SC6/resource/error 기준을 시작 전에 읽고 그대로 적용한다. 관측에는 task 완료/취소, scheduler, memory, provider 실패, restart/recovery가 포함돼야 한다.
5. wrapper 종료 코드·실제 child 종료·28800초 이상 duration·candidate SHA/fingerprint 귀속·cleanup을 함께 확인한다. metric JSON PASS만으로 전체 성공을 선언하지 않는다.
6. 9개 문서/release selector를 새 후보 맥락에서 최종 재실행하고 README/current/owner 문서의 상태를 다시 대조한다.
7. candidate-result에 executed scope, unsupported/blocked scope, independent review evidence, commit/push/CI/배포 여부를 각각 작성한다. 기존 release owner가 요구하는 마지막 판정은 완성된 결과물에 대해 받는다.

**검증 시나리오:** wrong candidate digest, wrapper nonzero, duration 부족, missing child exit, hidden error, source movement 각각을 validator가 거절해야 한다. optional 기능이 환경 미충족이면 최종 표에 그대로 노출한다. 정상 새 soak는 모든 gate가 같은 run/candidate를 가리켜야 한다.

**완료 기준/산출물:** 현재 전체 failed/error 0을 확인하거나 합의된 제외 scope를 구체적으로 명시한 제한 판정, 9개 contract의 최종 결과, UI 경고 disposition, installed wheel PASS, 새 8h receipt/validator PASS, 정리 결과. 전 기능 검증 완료 주장은 27행의 실제 환경 증거가 모두 있을 때만 가능하다. release owner GO가 없으면 기술 검증 상태만 보고하고 GA GO로 표시하지 않는다.

## 7. 후속 실행자가 사용할 검증 명령

아래는 기존 파일을 사용하는 명령 예시다. IMP-00의 격리 preflight를 먼저 통과시키고 새 evidence 경로로 저장한다. 새로운 harness CLI는 구현 전에는 존재하지 않으므로 실행 가능한 기존 명령으로 가장하지 않는다.

```sh
cd /Users/mr.k/program/coding/ssak_comp/Ssak-Ai
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_cr12_docs_alignment.py tests/test_cr14_fence_movement_detection.py tests/test_cr14_fingerprint_scope_contract.py tests/test_nx07_doc_consistency.py -q --tb=short
pnpm --dir dashboard test
pnpm --dir dashboard typecheck
pnpm --dir dashboard lint
pnpm --dir dashboard build
```

전체 backend 명령은 IMP-00의 current isolated wrapper로 `pytest tests`의 현재 CI 대상 전체를 수행한다. 특정 GPU/live-provider/hosted-service 항목의 skip은 자동 PASS가 아니며 coverage.json에 환경 조건을 기록한다. Ruff/type/format/build/SBOM/GA/soak의 상세 argv는 시작 시 현재 CI 및 scripts의 실제 argparse/help를 읽어 receipt에 복사한다. 과거 CLI 옵션을 추정해 넣거나 오래된 script 결과를 재사용하지 않는다.

개발 과정에서는 실패한 selector와 해당 behavioral regression을 먼저 실행하고, 수정이 확인된 뒤 소유 module 검사·영향 통합 검사로 넓힌다. 매 사소한 문구 수정마다 전체 8시간 soak를 반복하지 않는다. 최종 후보 code/scope가 바뀌었거나 validator binding이 깨지면 최종 gate의 재측정이 필요하다.

### 7.1 이미 존재하는 회귀 테스트 출발점

아래 파일은 계획 작성 중 graph에서 찾은 기존 파일이다. 이 목록을 각 작업의 전체 테스트 범위로 제한하지 않는다. 시작 시 파일의 최신 fixture/selector를 읽고 새 시나리오를 같은 behavioral 계약에 추가한다.

| 작업 | 기존 테스트 |
| --- | --- |
| IMP-03 | [cancel cleanup](../../tests/test_chat_stream_cancel_cleanup.py), [disconnect cleanup](../../tests/test_chat_stream_disconnect_cleanup.py) |
| IMP-04 | [citation table](../../tests/test_citation_table_contract.py), [web search](../../tests/test_web_search.py), E08 benchmark receipts |
| IMP-05 | [turn constraints](../../tests/test_turn_tool_constraints.py), [tool loop](../../tests/test_tool_loop.py), [approval review](../../tests/test_approval_review.py), [shell API boundary](../../tests/test_cr04_shell_api_boundary.py) |
| IMP-06 | [compact validation](../../tests/test_conversation_compact_validation.py), [conversation API](../../tests/test_conversation_api_ctx01.py), [conversation store](../../tests/test_conversation_store_ctx01.py), [context end-to-end](../../tests/test_fr_context_end_to_end.py) |
| IMP-07 | [durable memory purge](../../tests/test_durable_memory_purge.py), [memory scope](../../tests/test_memory_scope.py), [RAG](../../tests/test_rag.py), E10 actual lifecycle receipts |
| IMP-10 | [persistent agency](../../tests/test_persistent_agency.py), E01 scheduler·legacy Kanban receipts |
| IMP-11 | [voice API](../../tests/test_voice_api.py), [voice audio](../../tests/test_voice_audio.py) |
| IMP-12 | [training jobs API](../../tests/test_training_jobs_api.py), E12 signal-gated child receipts |
| IMP-13 | [MCP tool loader](../../tests/test_mcp_tool_loader.py), [browser recovery](../../tests/test_ssak_browser_recovery.py) |
| IMP-14 | [local history store](../../dashboard/src/stores/__tests__/localHistoryStore.test.ts), [terminal sandbox](../../tests/test_terminal_sandbox_routing.py) |
| IMP-15/16/17 | [financial numbers](../../tests/test_financial_numbers.py), [data extractor](../../tests/test_data_extractor.py) |
| IMP-18 | [quality gate](../../tests/test_quality_gate.py) |

예를 들어 IMP-03의 기존 회귀는 격리 preflight 후 아래처럼 실행한다. 다른 task도 위 기존 파일 경로를 동일 wrapper의 pytest 인자로 전달한다.

```sh
.venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_chat_stream_cancel_cleanup.py tests/test_chat_stream_disconnect_cleanup.py -q --tb=short
```

## 8. 최종 인계 체크리스트와 보고 양식

### 8.1 착수 체크리스트

- [ ] Ssak-Ai cwd와 현재 HEAD/diff/source hashes를 기록했다.
- [ ] E01/E02/E04/E14를 읽었고 과거 전체 수치를 현재 green으로 취급하지 않았다.
- [ ] graph-first 탐색과 실제 파일 읽기를 완료했다.
- [ ] 자신의 수정 파일과 공통 파일 lock 소유자를 정했다.
- [ ] owned fixture/config/auth/port/process 격리 self-test가 통과했다.
- [ ] IMP-01의 새 baseline과 각 failure의 owner를 만들었다.
- [ ] IMP-15의 실제 capability 안내를 계산기 개발과 분리했다.

### 8.2 작업별 제출 양식

```text
Task: IMP-XX
Status: PASS | FAIL | INCONCLUSIVE | BLOCKED_ENV
Source: HEAD + scoped SHA256 + lock digest
Evidence root:
Owned files:
Reproduced issue or verified gap:
Before behavior:
Final behavior:
Implementation and reason:
Scenario IDs + independent expected values:
Commands: argv / cwd / start / end / exit
Actual versus fake ports:
Negative controls:
Regression results:
Source before/after:
Owned process/store cleanup:
Remaining limitations and next owner:
Commit / push / remote CI / publication: separately stated
```

### 8.3 최종 수락 체크리스트

- [ ] 27개 기능군마다 scenario와 actual environment 또는 명시적 BLOCKED_ENV가 연결된다.
- [ ] 남은 9개 selector와 새 전체 failed/error가 각각 새 receipt에 연결된다.
- [ ] 이미 수정된 search/cancel/Chroma/Decimal/permissions/UI 계약을 유지했다.
- [ ] 도구 제약·provider error·empty search에서 false DONE이 없다.
- [ ] 지원한다고 안내하는 model/finance/plugin/training/voice capability와 실제 결과가 일치한다.
- [ ] warning을 suppression이나 threshold 변경으로 숨기지 않았다.
- [ ] 새 wheel의 non-editable 설치와 source 밖 cwd 동작을 관측했다.
- [ ] historical soak PASS metric과 종료·귀속 미확인 상태를 보존했다.
- [ ] 새 후보와 8h soak의 source/run/exit 귀속이 validator에서 확인된다.
- [ ] 사용자/다른 작업자의 데이터·staged 변경·process를 보존했다.
- [ ] 구현·테스트·commit·push·CI·release 판정의 단계를 구분해 보고했다.

## 9. 다른 에이전트에게 그대로 전달할 시작 지시

> Ssak-Ai 저장소 /Users/mr.k/program/coding/ssak_comp/Ssak-Ai에서 이 문서의 IMP-00부터 의존 순서대로 개선을 실행하라. 먼저 현재 shared working tree와 최종 순차 감사 manifest의 차이를 기록하고, owned temporary fixture와 실제/대체 환경을 구분한 새 evidence root를 만들라. codebase-memory-mcp로 코드를 우선 탐색하고 편집 전 파일을 읽어라. 다른 작업자의 변경을 되돌리지 말고 공통 소유 파일은 단독 통합하라. 이미 수정·검증한 항목은 회귀 계약으로 유지하고, 미검증 항목은 먼저 실제 재현한 뒤 문제가 관측되면 최소 수정하라. 현재 지원 상태를 정확히 안내하는 IMP-15를 신규 DCF/comps 구현과 분리하라. historical release 값·soak 결과를 새 현재 통과처럼 고치거나 실패 테스트를 완화하지 말라. 각 IMP의 재현·수정·negative control·같은 사례 재실행·source 귀속·cleanup을 증거로 제출하라. 환경이 없으면 BLOCKED_ENV를 기록하고 가능한 독립 작업을 계속하라. 마지막에 27기능군 결과, 새 전체 suite, wheel 설치, 새 후보/soak를 종합하고 기술 완료와 사용자 release 결정을 구분하라.

이 문서를 검증할 때의 성공 판정은 **PASS_DOCUMENT_STRUCTURE**다. 구현 PASS, 전체 기능 PASS, GA GO는 후속 실행의 실제 증거로만 부여한다.
