---
title: SSAK-AI Core 리더·실행 에이전트 분업 계획
date: 2026-09-25
status: post-fix-cognitive-and-snapshot-dry-run-pass-delegated-followups-blocked
source_head: 0a9498e3846a48bbf158bf870957064cdc9bbb11
---

# 목적과 역할

사용자의 최신 지시에 따라 주 에이전트(root)는 방향 결정, 우선순위, 작업 분배, 계획 갱신, 결과 인수를 담당한다.
주요 구현·시험·데이터 검증은 실행 에이전트가 맡는다. 파일별 소유 범위를 분리하고, 미완료 작업을 완료로 보고하지 않는다.
기준은 위 commit만이 아니라 **현재 working tree와 새 파일을 포함한 manifest**다. 원문 헌법과 기본 방침은 변경하지 않는다.

# 현재 판단

- 핵심 결함 수정은 구현됐다: 승인 인자 결박, 보호 대상 상위 경로/복수 class, override 순서, action 선기록, durable replay 차단, 실행 직전 권한/인증 세션 재검증.
- ACTIVE용 인증 HTTP 경로를 추가했다. 클라이언트는 서버가 준비한 자신의 request ID, 확인한 action digest, 사유만 보낸다. 도구 인자·권한·readiness·승인자 이름은 서버가 소유한다.
- 임시 환경의 실제 HTTP → ToolExecutor → 파일 쓰기 → Git canonical 기록 → 서버 재시작 후 중복 차단을 직접 관찰했다. 운영 활성화나 live Brain 성능 증거로 해석하지 않는다.
- 수정 중 실행된 전체 시험은 792 passed / 13 failed / 1 skipped다. 이를 최종판 PASS로 재사용하지 않는다. 증거 해시·수집 개수 갱신 후 architecture 검사 PASS. 관련 경계 150개와 추가 세션취소 API 시험 3개 PASS.
- 독립 레인을 재개해 code review를 완료했고, security 보고서와 QA 재현 결과도 받았다. 이후 사용량 제한으로 일부 에이전트가 다시 중단됐다. 보고서 판정과 에이전트 종료 상태를 분리하여 원장에 남긴다.

# 단계와 담당

**G1의 구현/실행 검증과 결과 인수는 완료했다.** 정상 종료하지 못한 독립 레인과 G2/G3/G4 후속 주요 구현은 아래 차단 사유를 보존한다. 운영 변경은 하지 않는다.

| 카드 | 상태 | 실행 담당 | 소유 파일/산출물 | 완료 기준 |
|---|---|---|---|---|
| G0 최신 tree 조사·보안 결함 수정 | 완료 | action_fix / protection_fix / root 통합 | action helper, protected_targets, permission_gate, surface adapter, API | 관련 회귀와 실제 HTTP 재시작 증거 확보 |
| G1-A 코드 검토 | 완료 · PASS | code_review | evidence/2026-09-25-review/code-final.md만 | 현재 HEAD+dirty hashes, 구체적 결함 또는 범위 한정 PASS |
| G1-B 보안 경계 검토 | 보고서 PASS / 에이전트 종료 제한 | security_review | security-final.md만 | 인증/owner/digest/revoke/replay/선기록 검증, lexical shell 보호 한계 명시 |
| G1-C 회귀와 release 검사 정합성 | G1 당시 완료 · G2-B 최신 전체 cognitive 회귀 821 PASS/0 FAIL/1 SKIP | qa_review 분석 / root evidence 갱신 | 이전 G2-B 결과물 및 [최신 post-fix 결과](evidence/2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.json) + [JUnit](evidence/2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.xml) | 최신 tree에서 822 collected, exit0, 821 passed, 0 failed, 1 skipped, 1 warning, 733.65초. 이전 817 collected/816 PASS 결과는 과거 hash 기록으로 보존 |
| G1-D 문서 정합화 | 완료 | docs_sync | 보고서/체크리스트/architecture/T11/T13 및 docs-sync.md | 역사 기록과 현재 상태 구분, 실모델·resume/cancel 기존 완료 반영 |
| G1-E 최종 인수·증거 원장 | 결과 패키지 완료 / full 인수 보류 | root | FINAL_REVIEW.md, WORK_PLAN.md, evidence manifest/ledger | 판정과 실행 기록이 같은 tree에 결박, 미검증 항목 명시 |
| G2 실데이터 migration 검증 | 등록 snapshot 56,961 events의 수정 후 전체 read-only dry-run PASS; 운영 인수 아님 | root 독립 검토·수정·재실행 | [수정 후 dry-run JSON](evidence/2026-09-25-review/migration-real-post-independent-review-2026-09-26.json) + [독립 focused JUnit](evidence/2026-09-25-review/pytest-migration-independent-review-2026-09-26.xml) | exit0/170.47초/errors0, import·mapping·canonical·index·digest·replay·rollback 각각 56,961, source 불변·destructive=false. objective/task 원본 0건 미관측; destructive/운영 인수 별도 open |
| G2-B migration 성능 구현 | 수정 후 전체 cognitive 및 등록 snapshot dry-run PASS; 비교 baseline 없음 | root 통합·검증 | [최신 cognitive JSON/JUnit](evidence/2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.json) / [최신 migration JSON](evidence/2026-09-25-review/migration-real-post-independent-review-2026-09-26.json) | cognitive 822 collected, 821 PASS/0 FAIL/1 SKIP/1 warning, exit0/733.65초. snapshot 56,961 전량, exit0/170.47초. objectives/tasks 실데이터 0건; KG·destructive/운영 인수 미종료 |
| KG validator release gate | NOT_RUN — 현재 checkout에서 `KGBinaryValidator` 구현 확인 불가 | 다음 인수 담당자가 위치·호출법 조사 | 최종 인수 문서 및 별도 validator 실행 증거 | 정식 `KGBinaryValidator.validate()`가 `OK=True`를 반환함을 기록하기 전 전체 KG release gate 닫지 않음 |
| G3 실제 provider pilot 설계 | 계획서 작성 완료 | live_pilot_plan | live-pilot-plan.md만 | 현재 provider 확인, 실측 가능한 지표·paired split·예산·누수 방지·구현 카드 확정 |
| G3-B pilot 구현·실행 | 차단: 에이전트 사용량 제한 | 별도 실행 에이전트 지정 | 별도 port/driver/evidence 소유 예정 | 실제 provider 관측만 기록, fixture와 분리, 통계적 주장 범위 명시 |
| G4 운영 구성·활성화 | 차단: 선행 구현/독립 인수 미완 | root 범위 결정 후 전담 | 서버 composition 및 rollout 계획 | 실제 project/store/profile/principal 바인딩과 rollback 확인. 기본 OFF 유지 |

# G1-C 결정 기록

release 기록은 관측 증가를 보고만 하고, 허용 감소 초과·하한/근거/승인 변조를 실패로 판정한다.
기존 실물 시험의 `record_moves == ()`는 파일이 늘어도 실패시키므로 구현 계약과 모순된다.
QA 담당은 `record_problems == []`를 유지하고 증가 보고의 정확성을 검사하도록 해당 시험만 바로잡는다.
하한·허용폭·저장된 승인/기준값은 변경하지 않는다. 기존 감소/변조 민감도 시험도 유지한다.

# 에이전트 공통 인수 계약

1. 처음에 현재 파일과 해당 task card를 읽고, graph 도구로 코드 탐색한다. transport 오류면 그 사실을 기록하고 파일 기반 탐색으로 전환한다.
2. 담당 파일 밖 편집은 root에게 알려 소유 범위를 정한 뒤 수행한다. 다른 작업자의 dirty 변경을 되돌리지 않는다.
3. 보고에는 실행한 명령·종료 코드·관찰·한계·HEAD 전체 SHA·대상 파일 hash를 남긴다. 미실행 검사는 NOT_RUN이다.
4. 단위시험, 임시 통합시험, 실제 provider pilot, 운영 인수를 구분한다. 하나를 다른 것의 증거로 승격하지 않는다.
5. root는 결과를 읽고 PASS/재작업/차단으로 판정한다. 중단·사용량 제한·응답 부재는 INCONCLUSIVE다.
6. 운영 vault·원본 DB·헌법 변경, 배포, 파괴적 migration, 자동 권한 상향은 이 검증 작업에 섞지 않는다.
7. source/test freeze 이후 최종 시험을 시작한다. 변경이 추가되면 영향을 받은 검증과 manifest를 갱신한다.

# 재개 순서

다른 에이전트가 인계받으면 이 파일 → WORK_PLAN → FINAL_REVIEW → 각 담당 report 순서로 읽는다.
기존 구현을 다시 만들지 않고, 위 표의 담당/상태와 실제 파일을 대조한다. reviewer findings가 생기면 root가
심각도와 소유 파일을 정해 별도 수정 카드로 배정하고, 같은 reviewer가 수정된 hash를 재검토한다.

# 후속 주요 구현 카드: 실행 에이전트 재개 시 우선순위

**G2-B 현재 판정 — 수정 후 전체 검증 완료.** 구현은 bounded event batches, migration 격리 batch commit, manifest snapshot 재사용, index 1회 rebuild를 포함한다. 독립 검토에서 재현·수정한 두 문제는 (1) 고정 rollback scratch의 선행 파일 삭제 가능성 → 회차별 `mkdtemp` scratch, (2) objective/task mapping 뒤 publish interruption 복구 누락 → canonical ID 기반 동일 transaction 재시도다. focused migration/adapter/store/protection/sandbox는 100 PASS/exit0, Ruff PASS, basedpyright `--level error` 0이다. 이어서 [새 full snapshot dry-run](evidence/2026-09-25-review/migration-real-post-independent-review-2026-09-26.json)이 같은 등록 snapshot digest `7d69ed65667db079957a9277b59ebcfb232293582beb6d53f267a4f61e726836`에서 exit0/170.47초, 56,961 events import·mapping·canonical·index·digest·replay·rollback 전량 일치, source 불변 및 destructive=false를 확인했다. [새 전체 cognitive 회귀](evidence/2026-09-25-review/pytest-cognitive-post-migration-review-2026-09-26.json)는 822 collected, 821 PASS/0 FAIL/1 SKIP/1 warning, exit0/733.65초다. 파일별 code/test hash 및 audit-driver hash는 새 migration JSON에 before/after로 기록했다. 이전 run은 각자 과거 hash 역사 기록으로 둔다. 기존 temp target/evidence를 덮어쓰지 않았다. objectives/tasks 원본 0건은 미관측이고 destructive/운영 인수 및 KG gate는 별도 open. 최적화 전 full baseline이 없어 개선율은 주장하지 않는다.

**KG release gate:** 프로젝트 지침에 `KGBinaryValidator.validate() -> OK=True`가 요구되지만 현재 checkout에서 해당 구현을 찾지 못해 NOT_RUN이다. 다음 담당자는 정식 모듈/호출 방법을 추적하고 그 결과를 새 evidence에 남겨라. migration 변경은 reward/score update를 수행하지 않았으므로 0.95/tick decay 및 10/pair cap 대상은 없다. validator OK 증거 전 전체 KG 인수를 닫지 않는다.

**우선순위 2 — G3 LP-A/B/C/D.** 상세 인계서는 [실제 provider pilot 계획](evidence/2026-09-25-review/live-pilot-plan.md)이다. LP-A(harness 기록/예산/분모)와 LP-B(실모델·정책 학습 사슬)는 별도 구현 worker가 맡고 public protocol 변경을 먼저 합의한다. 이어 LP-C가 CLI 및 bounded smoke/pilot을 수행하고 LP-D가 오염·raw ledger 재계산을 검증한다. source와 fixture 결과는 분리한다. root는 제안된 local 0.5B 모델, 108 FINAL paired trials, 20분/360 calls 상한을 **구현할 예산 계약**으로 채택한다. 실제 run 등록·실행은 구현·단위검증·별도 smoke가 완료된 뒤 한다. 이번 조사에서는 generation을 실행하지 않았다.

**우선순위 3 — G4 운영 composition.** 준비 요청의 생성 주체, project별 canonical root, 최신 authority profile 조회, executor workspace를 기존 서버 composition에 결선할 worker를 별도 지정한다. 기존 모든 chat/tool 호출을 한 번에 ACTIVE로 전환하지 않는다. opt-in 서버 service가 없는 현재 상태의 503은 의도된 fail-closed다. 실제 운영 rollout은 검증 산출물과 독립 리뷰가 갖춰진 뒤 별도 인수한다.

LP 구현 및 G4 운영 composition은 여전히 실행 대기/차단 상태다. 독립 migration 수정 뒤 최신 전체 cognitive 회귀와 registered snapshot full dry-run을 각각 실행해 PASS했고, 세부 결과와 hash는 위 G2-B 행 및 두 JSON/JUnit에 결박돼 있다. collect-only marker 822, digest gate 및 architecture review의 최신 상태는 아래 문서 검증에서 별도로 재확인한다. 이것은 프로젝트 전체 release gate를 닫지 않는다. KG validator `OK=True`, objectives/tasks 실데이터, destructive/운영 migration 인수도 남아 있다. 이 문서는 완료 범위와 대기 조건을 구분하며 자동 재개를 주장하지 않는다.

G1 source/test freeze 당시 전체 회귀 기준선: 810개 수집 중809 passed / 1 skipped(774.52초). G2-B 과거 source/test hash에서 최종 전체 cognitive run은 817개 수집 중816 passed / 0 failed / 1 skipped, exit0이었다. 이후 독립 검토가 Python source/test를 바꿨으므로 이전 aggregate hash와 초록 결과는 역사 증거다. 현재 collect-only 822는 수집 개수 측정일 뿐 전체 실행 결과가 아니다. 원문 헌법/하한 승인은 변경하지 않았다.
