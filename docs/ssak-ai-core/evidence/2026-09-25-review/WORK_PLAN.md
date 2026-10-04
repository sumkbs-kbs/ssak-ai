---
title: Cognitive Core integrated follow-through
date: 2026-09-25
status: full-snapshot-dry-run-complete-followups-blocked
---

# 작업 계획

> 공개 범위 안내(2026-10-04): 아래 로컬 보관·미게시 원자료는 원래 QA 작업 공간에 보존되어 있으며 공개 저장소에는 포함되지 않습니다. 역사적 결과와 해시는 기록된 당시 revision에만 적용됩니다. 이 공개 요약만으로 원자료를 재검토하거나 현재 소스의 인수를 확정할 수 없습니다.


최신 분업/인수 기준: [리더·실행 에이전트 계획](../../EXECUTION_PLAN_2026-09-25.md).
사용자 지시에 따라 root는 방향·분배·검토를 맡고 주요 검증/후속 구현은 실행 에이전트에 위임한다.

1. 완료: 현재 tree(6be0263d121c1e2a7ade92d3127af226c5e0581f + dirty)와 기존 evidence 대조. Cognitive tests 777 passed, 1 skipped (수정 전).
2. 완료: 재현된 protection/digest/ancestor/override 및 action replay/freshness/persist-before-effect 결함 수정. 원문 헌법은 불변.
3. 완료: ACTIVE adapter의 journal/canonical sink/live authority/authenticated activation 필수 연결 완료. 서버 준비 요청만 받는 인증 HTTP 표면과 실제 ToolExecutor/Git/HTTP 재시작 검증 완료.
4. 완료(검증 산출물 인수): 전체 회귀 종료 후 변경 digest·시험 개수 증거 갱신, 최종 독립 검토와 잔여 범위 보고. 문서 5개 최신 요약 정합화는 완료.

# Debug journal

임시 데이터는 pytest tmp_path 및 임시 root에만 생성한다. production vault와 data는 수정하지 않는다.
검토 report와 명령 출력은 지속 evidence이며 삭제하지 않는다. 원본 source에 임시 debug print/breakpoint는 추가하지 않는다.

가설 H1: approval request digest가 비어 원래 허용 내용과 다른 write가 통과. PermissionGate→ProtectedWriteGuard에서 재현.
가설 H2: dispatch마다 메모리 receipt가 초기화돼 같은 action key가 재실행. surface 생성자 경계로 재현.
가설 H3: cached ALLOWED가 실행 시 expiry/revocation을 재확인하지 않는다. expired grant 시각을 주입해 재현.
각 수정은 실패 회귀시험→최소 수정→성공 실행 순서로 검증한다.

현재 소유: code_review(독립 코드), security_review(독립 보안), qa_review(최종 회귀 및 release 계약 시험), migration_audit(실데이터 read-only), live_pilot_plan(provider pilot 설계), root(계획·최종 인수).

## 위임 결과 갱신

- code-final: 정확한 source pin에 결박된 PASS, root가 19개 hash 재확인 후 review-ledger 기록.
- security-final: bounded HTTP 경계 PASS 보고서 작성됨. 에이전트 종료는 사용량 제한이므로 레인 전체는 INCONCLUSIVE로 분리 기록.
- QA: 기존13 실패 재현에서12 PASS, release 관측 증가 equality1 실패. 지시한 계약 정정을 root가 작은 통합 수정으로 적용; source/test freeze 후 전체 시험809 passed / 1 skipped, exit0.
- migration: 최초 audit driver에서 앞/중간/뒤30건 sample PASS와 60초 제한 full probe 미완을 확인했다. 이후 root가 bounded batch import/store snapshot/index 최적화를 구현하고 등록 snapshot 전체 56,961건 dry-run 네 차례를 각각 별도 JSON으로 보존했다. 최신 집계 증거 (로컬 보관·미게시: `migration-real-optimized-results-final-rerun.json`)는 CLI exit0/full report PASS/errors0, imported/mapping/canonical/index/digest/replay/rollback 각 56,961건, mapping digest `sha256:e4c99d0bc660e87442ede3cf536ce8854d745b1afb2cc0a8ba14dc781d7f4a75`, wall 170.95초/report total 170.60초, source bytes/count 불변, destructive=false, 강화된 success criteria 13/13 true 및 `overall_acceptance=true`를 기록한다. 대상 snapshot digest는 `7d69ed65667db079957a9277b59ebcfb232293582beb6d53f267a4f61e726836`; audit driver SHA-256은 `2e5e44ccf63e51a487ce74467a065c18b267733a4ead7c27d0da1736eaf48f12`다. 최적화 전 전체 baseline은 없으므로 성능 개선율은 주장하지 않는다. 운영 migration/cutover, objectives/tasks 경로(원본0건), 독립 재검토와 G2-B 이후 전체 cognitive 회귀 인수(817 collected, 804 passed/12 failed/1 skipped, exit1)는 미완료. 상세 회귀 결과는 [full cognitive 증거](pytest-cognitive-g2b-2026-09-26.json).
- KG validator gate: 현재 checkout에서 `KGBinaryValidator` 구현을 찾지 못해 `validate() -> OK=True`를 입증하지 못했다(NOT_RUN). 이어받는 담당자는 validator의 정식 위치·실행 명령을 찾아 별도 증거로 기록해야 한다. 이번 migration에서 reward/score 업데이트는 없었다.
- pilot: live-pilot-plan 작성됨. 로컬 provider 확인, 실제 generation/pilot은 NOT_RUN. 후속 major 카드 LP-A/B/C/D 보존.

G1 source/test freeze 당시 전체 기준선은 809 passed / 1 skipped / 1 warning, 774.52초였으며 G2-B 최적화보다 앞선 실행이다. 2026-09-26 G2-B 이후 `.venv/bin/python -m pytest tests/cognitive -q` 전체 실행은 817 collected, 804 passed, 12 failed, 1 skipped, 1 warning, 754.92초, exit1로 끝났다. 실패는 architecture의 810/817 test-count 마커 및 stale digest artifact·재확인 4건(4 tests), digest drift 최신성(3 tests), 이에 의존하는 evidence gate(5 tests)에 집중됐다. source/test Python 573개 aggregate SHA-256은 실행 전후 `205d6323bc62d5ab5e3f0b56ebd8c7d94763378df3dc8240e0fac7bc4f8e15a0`로 동일했다. 상세 [full cognitive 회귀 증거](pytest-cognitive-g2b-2026-09-26.json)를 참조한다. 2026-09-26 targeted migration/store/adapter 재실행은 48 passed / exit0 (2.51초); migration 감사 driver Ruff PASS, basedpyright `--level error` 0 errors/warnings/notes / exit0. 실제 full snapshot dry-run도 최신 증거에서 PASS다. 전체 cognitive suite는 현재 red이며, artifact·marker 갱신은 dirty-tree 파일 ownership과 승인된 인수 절차를 확인한 뒤 별도 수행하고 전체 suite를 재실행해야 한다. 독립 hash review, 운영 migration 인수와 KG validator `OK=True` gate도 남아 있다. 프로젝트 전체 완료로 처리하지 않는다.
