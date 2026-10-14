---
title: 우선순위 1 acceptance snapshot writer 수정
date: 2026-10-14
tags: [offline, metadata-contract, remediation]
---

작업: IMP-09-C-PRODUCT-VISION-ACCEPTANCE-METADATA-CONTRACT-01.
직접 사용자 요청: 우선순위가 가장 높은 것부터 순차 진행.

부모는 ../IMP09B-PRODUCT-VISION-STRUCTURED-OBSERVATION-01/run-20261014T040632Z-codex-5697c22846df. 실관측은 PASS_SCOPED이고 봉인144개/SHA d6fb249e4a4f78dc85b9bdef877b1d76a7eb76e7e0639131265827744b768220을 보존한다.

목표: 새 고유 하네스 사본에서 supervise_once의 generated acceptance format=omitted 표기를 실제 고정 schema로 수정한다. 실제 writer 경로를 호출한 작은 offline 회귀로 수정 전 실패/수정 후 통과와 사전 request/planned/profile/schema 일치를 확인한다. 부모와 제품 소스·기존 기록은 수정하지 않는다. 새 real HTTP/socket/provider/inference/Uvicorn은0이다.

완료: 최소 taskpatch, red/green 원문/receipt/sourceSHA, 관련정적검사, 부모/보호28/staged97보존, 독립검수 및 handoff. 전체IMP09PARTIAL/역사ledgerNOT_RECOVERED/과거format생략FAIL을 유지한다.

그 뒤 순차작업: 최신상태표 통합 → 구조화기능 및 소유증거 커밋/푸시 → 실제실패·취소·권한·재시작검증. 독립 발견은 다음 순서를 준비하는 읽기전용 작업으로 병행할 수 있다.
