---
title: Product Vision 오프라인 게이트 완료 이후 작업 경계
tags: [qa, imp09, next-work]
date: 2026-10-14
---

이번 요청의 직접 후속 수정은 완료했습니다. 완료된 FG selector와 native/기존 18·45 selector를 반복하는 추가 준비 작업은 필요하지 않습니다.

다음 미완료 항목은 기존 계약에 있는 **IMP-09-B-PRODUCT-VISION-LIVE-OBSERVATION-01**입니다. auth/readiness, 실제 provider 응답, OS timeout·wait/reap/cleanup, 이미지 의미 정답은 아직 관측하지 않았습니다. 본 오프라인 검수는 live 권한을 발급하지 않았습니다.

해당 항목의 시작 조건은 현재 소스·요청·fixture·런타임 계약에 연결된 독립 검수와 별도 live 실행 범위/승인입니다. 기존 run_harness/runtime_adapter 및 supervise_once 경로를 재사용하고, 새 실행 체계를 만들지 않습니다. 이 문서는 승인 파일을 만들거나 CLI 실행을 지시하지 않습니다.

시작 조건이 충족되면 새 소유 run에서 현재 소스와 요청의 해시를 다시 고정합니다. 원본 fixture·질문·model alias/digest와 기존 endpoint/budget/deadline 계약을 대조한 뒤 계약에 정한 인증·readiness 사전 관측, 제품 POST/Provider wire의 단일 lineage, 제한된 cleanup을 수행합니다. 성공한 과거 요청을 재전송하지 않으며 결과 불명은 조회·증거 대조 후 별도로 판정합니다.

외부 supervisor 종료 관측과 내부 receipt 종료 관측은 구분하고, 원본 stdout/stderr/HTTP body/journal/receipt는 고유 경로에 보존합니다. cleanup 이후 gate를 판정하고 모든 작성자가 종료된 뒤 최종 manifest를 봉인합니다. 인증 차단·timeout·모델 미지원·의미 오답을 transport 성공과 분리합니다. 공용 원장 복구는 정확한 백업 없이 추정해서 완료 처리하지 않습니다.

현재 source-bound 인계는 [handoff-ko.md](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/handoff-ko.md), 실제 final receipt는 [checks](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261014T003707Z-codex-d6851e1f-71d862ec/checks-956ad18301aa472b81ff2e9c74263531.json)입니다.
