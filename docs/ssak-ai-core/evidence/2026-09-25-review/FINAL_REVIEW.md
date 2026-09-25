---
title: Cognitive Core current-tree integration review
date: 2026-09-25
status: full-snapshot-dry-run-complete-full-acceptance-open
source_head: 6be0263d121c1e2a7ade92d3127af226c5e0581f
---

# 판정 범위

기본 방침과 헌법 원문은 유지했다. 최신 working tree의 중요한 실행 결함을 수정하고 인증된 HTTP 경계의
격리 통합을 검증했다. **프로젝트 전체 개발·운영 인수 완료를 선언하지 않는다.** 등록된 실제 snapshot의 전체
migration dry-run은 PASS지만, 실제 provider 성장 pilot, 운영 migration/cutover, 운영 server composition,
일부 독립 검토의 정상 종료가 남아 있다.

사용자 지시에 따라 root는 방향 결정·작업 배분·결과 인수·계획 갱신을 맡는다. 주요 후속 구현은
[분업 실행계획](../../EXECUTION_PLAN_2026-09-25.md)의 전담 카드로 넘긴다. 사용량 제한으로 실행 에이전트가
중단된 상태를 실행 중 또는 PASS로 표시하지 않는다.

# 구현·검증된 보완

| 경계 | 변경 | 관찰 |
|---|---|---|
| 보호 승인 | tool 이름+전체 인자 digest 결박, 빈 digest 거부, 승인 workspace 결박 | 승인 후 content 변경·workspace 변경 차단 |
| 보호 경로 | 상위 디렉터리 및 모든 대상/겹치는 보호 class 검사 | ancestor 삭제·첫 대상 승인으로 나머지 우회 차단 |
| gate 순서 | 안전 검사 뒤 override, 주입 guard 유지 | ALLOW override 우회 차단 |
| 실행 기록 | canonical authorized intent를 effect 전에 저장 | sink 실패 시 effect0, receipt의 action ID와 저장 ID 일치 |
| 영구 replay | SQLite FULL synchronous, project/action-key unique claim | 실제 두 프로세스 경합1 effect, crash/restart 후 재실행 차단 |
| 실행 권한 | live resolver 재질의 및 subject/scope/dimension/operation/time/revocation 확인 | 저장 중 grant/session 회수 후 dispatch0 |
| ACTIVE adapter | journal/sink/live authority/authenticated activation을 필수 연결 | 의존성 누락 시 fail-closed, shadow 표기를 active 결과에서 제거 |
| HTTP | 서버 준비 요청만 JWT owner/project/digest로 확인 | 무인증401, 타 소유자404, digest/context 불일치409, 임의 approver422 |
| 문서 | 설계 snapshot과 현재 상태 분리 | T03 provider window, T11 real-model shadow/resume/cancel 기존 완료 반영 |

claim은 자동으로 해제하지 않는다. 실패/불명 뒤 자동 재시도 가용성까지 입증한 것이 아니며 운영 reconciliation 절차가 필요하다.
PermissionGate의 shell 문자열 검사는 OS sandbox가 아니다. arbitrary interpreter/plugin의 모든 쓰기를 봉쇄했다는 주장을 하지 않는다.

# 실제 실행 표면

[manual-active-http.json](manual-active-http.json)은 별도 uvicorn 프로세스에 curl로 요청한 결과다.
임시 JWT/작업 root에서 실제 ToolExecutor/WriteFileTool를 사용했다.

- 무인증 요청401; 최초 승인 실행1회.
- canonical 기록2건, digest2건 확인, Git commit2건. 이 commit은 임시 canonical 저장소의 기록이며 작업 저장소를 commit한 것이 아니다.
- 서버 프로세스 재시작 후 같은 요청은 DUPLICATE_ACTION, 추가 dispatch0. 외부 관찰 파일값 보존.
- 임시 데이터/secret 정리. Brain은 시험용이며 live Brain 또는 성장 성능 증거가 아니다.

현재 API는 명시적인 server service 구성이 필요하다. 기본 service가 없으면503이다. 기존 모든 chat/background action이
canonical ACTIVE로 이행한 것은 아니다. 기존 read-only 상태 endpoint는 별도 설정 조회 표면으로 유지한다.

# 회귀와 증거 정합성

- 수정 전 baseline: 777 passed / 1 skipped.
- 수정 중 전체 실행: 792 passed / 13 failed / 1 skipped. 실행 중 파일이 변경됐으므로 최종판 결과로 사용하지 않는다.
- 그13개를 재현한 결과: 12 passed / release 관측 증가 equality1 failed. [재현 로그](qa-final-13-rerun.txt).
- release 판정은 증가를 보고만 하도록 설계됐는데 실물 시험이 증가도 실패로 처리했다. `record_problems == []`는 유지하고
  actual movement 출력과 기대값을 대조하도록 작은 시험 정정만 적용했다. 하한·허용폭·승인된 기준값은 바꾸지 않았다.
- 관련 경계 묶음150 PASS, 세션 취소 추가 API3 PASS. 독립 code reviewer30 PASS; security report는41+39 PASS를 별도로 기록했다(합산하지 않는다).
- 계획서에 적힌 신규 예정 파일을 실재 코드 인용과 구분하지 않아 새 full run에서 문서 검사가 실패했다. 예정 위치/파일명을 명확히 분리한 뒤 그 실행은111.50초에 중단하고 기록을 보존했다.
- G1 당시 최종 source/test freeze (G2-B 최적화 이전) 후 전체 시험: **809 passed / 1 skipped / 1 warning**, 774.52초, exit0. [당시 로그](pytest-frozen.txt). 이는 아래 2026-09-26 G2-B 이후 전체 회귀 결과를 대체하지 않는다.
- changed production scope basedpyright:0 errors / 69 warnings. Ruff 및 diff whitespace 검사 PASS.
- architecture mapping/증거 검사 PASS. 이는 원칙24 중 covered15/partial9라는 **문서·구조 검사**이며 통합 인수 승인과 다르다.

실제 변경 파일은 [final-source-manifest.json](final-source-manifest.json)에 결박한다. HEAD만으로 dirty tree를 대표하지 않는다.

# 독립 검토 상태

[code-final.md](code-final.md)는 에이전트가 정상 완료한 bounded PASS다. root가19개 파일 hash를 다시 확인했다.
[security-final.md](security-final.md)는 bounded PASS 보고서와 검증 기록을 남겼으나 에이전트 turn은 사용량 제한으로 종료됐다.
따라서 report의 관찰은 보존하면서 레인 종료 상태는 INCONCLUSIVE로 [원장](review-ledger.jsonl)에 구분했다.
QA와 migration/pilot 조사 에이전트도 제한으로 중단됐다. root는 확보된 결과와 작은 통합 수정/실행 확인을 마무리했으며
독립 에이전트의 정상 완료를 대신 주장하지 않는다. formal full review 인수는 보류다.

# 실제 데이터 migration 관찰

에이전트가 작성한 read-only audit driver를 root가 검토·실행했다. event-type 지원 목록은 실제 adapter 상수를 사용하게 했다.
[집계 증거](migration-real-results.json)에는 payload 원문을 보관하지 않는다.

- 원본 agency_events56,961건, objectives/tasks0건. 모두 observation이며 미지원 type0.
- mode=ro로 원본을 열어 일관된 SQLite backup snapshot 생성. 원본 DB/WAL bytes와 count는 전후 동일.
- 최초 full probe는60초 한도로 종료·회수됐으며909개 record 파일까지 관찰. 전체 변환/replay/rollback 완료가 아니었다.
- 실제 앞/중간/뒤 각10건 sample30건은30개 canonical record/index/digest, idempotent replay, rollback rehearsal을 통과했다. sample은 full의 대체 근거가 아니다.
- sample error0, destructive_executed=false, 임시 private 데이터 정리. source code hash도 전후 동일.

최적화 후 전체 dry-run 네 번을 새 증거로 보존했다: [첫 run](migration-real-optimized-results.json), [원장형 rerun](migration-real-optimized-results-rerun.json), 중간 감사판 [third run](migration-real-optimized-results-final.json), 최신 고정 스크립트의 [최종 run](migration-real-optimized-results-final-rerun.json). 기존 결과는 덮어쓰지 않았다. 네 실행 모두 같은 snapshot digest `7d69ed65667db079957a9277b59ebcfb232293582beb6d53f267a4f61e726836` 및 56,961 event를 대상으로 CLI exit0/full report PASS/errors0로 종료했다. 최종판은 강화된 전체 success criteria까지 검증한다.

최종 고정 스크립트 run은 CLI exit0, wall 170.95초(보고된 total 170.60초), imported/mapping entries/canonical records/index entries/digests verified/replay 및 rollback 건수 모두 56,961, mapping digest `sha256:e4c99d0bc660e87442ede3cf536ce8854d745b1afb2cc0a8ba14dc781d7f4a75`, rollback rehearsal PASS, 원본 bytes/count 불변, destructive=false였다. 계측상 import48.37초, index0.35초, digest검증31.64초, replay34.57초, rollback55.16초다. 원본 DB는 26,206,208 bytes / SHA-256 `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5`로 전후 같았다. `migration.py` SHA-256 `da604e23b6417cb506d2ee97d7a3a4bc721013928c3c0f859b7c89aa9edbb3e9`, `legacy_adapter.py` `4900a1b538241f7cb4bb17fe516263cc75309acb34e0f8a8af07c780b44cba04`, `store.py` `8c794de8ebba9ec0816a326a3bbda9623b35897e83af397f54aed3006babebce`; migration 시험 `a4e363fb683f629eeeb808260d0c59ac50da665ae6c37e53cd9b4e8876cac195`, 감사 driver SHA-256 `2e5e44ccf63e51a487ce74467a065c18b267733a4ead7c27d0da1736eaf48f12`. 전체 코드/시험/driver 전후 해시는 evidence에 기록돼 동일하다. 매 실행은 새 임시 target을 사용하므로 새 canonical ID가 발급되고 mapping digest가 달라지는 것은 source 변동이 아니다.

따라서 등록된 observation-only snapshot의 전체 migration dry-run은 현재 source hash 범위에서 PASS다. 최신 evidence의 `success_criteria_results` 전 항목 true, `overall_acceptance=true`다. 다만 이는 임시 target 검증이지 운영 cutover/destructive apply 인수가 아니다. objectives/tasks는 원본에 0건이라 미관측이다. 2026-09-26에 G2-B 이후 전체 cognitive 회귀 `.venv/bin/python -m pytest tests/cognitive -q`를 실행했다: 817 collected, 804 passed, 12 failed, 1 skipped, 1 warning, 754.92초, exit1. 상세 [회귀 evidence](pytest-cognitive-g2b-2026-09-26.json). 실패 12건은 architecture marker/digest artifact(4), digest drift 재확인·artifact(3), 이에 의존하는 evidence gate(5)에 집중됐다. Architecture review는 cognitive_tests 810≠817 및 digest artifact의 오래된 측정/4개 stale reverification을 보고했다. 실행 전후 source/test Python 573개 파일 aggregate SHA-256은 `205d6323bc62d5ab5e3f0b56ebd8c7d94763378df3dc8240e0fac7bc4f8e15a0`로 동일하며, 실패에 대응한 코드·시험 수정은 하지 않았다. migration/adapter/store targeted 재실행은 48 passed / exit0 (2.51초), migration audit driver Ruff PASS, basedpyright `--level error` 0 errors/warnings/notes / exit0이었다. 이전 809 passed/1 skipped는 G2-B 최적화 전이므로 현재 전체 회귀 실패 상태를 대체하지 않는다. 전체 cognitive suite는 아직 green이 아니다.

프로젝트 지침상 `KGBinaryValidator.validate()`가 `OK=True`여야 하지만 현재 checkout에서 validator 구현을 찾지 못해 이 gate는 NOT_RUN이다. 이번 migration은 reward/score를 갱신하지 않아 reward decay/cap 적용 대상은 없었다. 다음 인수자는 validator 위치/실행 가능성을 확인해 OK 결과를 별도 기록해야 하며, 그 전까지 프로젝트 전체 KG 인수는 열어 둔다.

# 후속 주요 작업

1. G2-B: 구현 및 현재 snapshot 전체 dry-run PASS. 최적화 이후 전체 cognitive 회귀는 804/817 PASS·12 FAIL·1 SKIP으로 종료했다. 다음 인수자는 ownership이 확인된 뒤 architecture/digest artifact 및 측정 마커를 승인된 절차로 갱신하고 전체 suite를 다시 실행해야 한다. 이후 독립 코드/hash 재검토가 남으며, objectives/tasks 표본이 실제로 생기면 해당 경로를 별도 검증.
2. LP-A/B: actual trial ledger/예산/표본 검증과 실제 모델→제한 도구→관찰→검증된 정책 사슬 구현. provider는 존재하며 구현 부재가 병목이다.
3. LP-C/D: 별도 smoke 뒤 사전 등록한 paired pilot과 독립 raw ledger/오염 검증. 기존 fixture 수치를 live로 재사용하지 않는다.
4. G4: 신뢰하는 project/store/profile/executor composition 및 운영 rollout 검토. default OFF 유지.
5. 사용량 제한 해소 후 미완 독립 레인 재개 및 최종 기술 인수. 사람의 Architecture Review 승인 자체는 에이전트가 대신 작성하지 않는다.

상세 파일 소유·예산·완료 기준은 [실행계획](../../EXECUTION_PLAN_2026-09-25.md)과 [pilot 인계서](live-pilot-plan.md)에 있다.
