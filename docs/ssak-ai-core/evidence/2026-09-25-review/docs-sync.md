---
title: Cognitive Core current-summary reconciliation
date: 2026-09-25
status: documentation-reconciled-runtime-acceptance-open
source_head: 6be0263d121c1e2a7ade92d3127af226c5e0581f
scope: documentation-only
---

# 문서 정합화 기록

[context 검토](context.md)와 [goal 검토](goal.md)가 지적한 현재 상태 문장과 날짜별 증거의 모순을 정리했다. 이 작업은 runtime 재실행이나 전체 인수 PASS가 아니다. 수정 중인 source의 판정은 `FINAL_REVIEW.md`가 소유한다.

| 수정 문서 | 정정한 현재 주장 | 근거와 제한 |
|---|---|---|
| [Implementation report](../../IMPLEMENTATION_REPORT.md) | 설계만 전달한 §1~15를 2026-09-22 역사로 명시하고 현재 구현 및 미완 경계를 앞에 추가 | [인수 체크리스트](../../ACCEPTANCE_CHECKLIST.md), T11 후속 관찰. 과거 “runtime 없음”을 현재 주장으로 읽지 않음 |
| [인수 체크리스트](../../ACCEPTANCE_CHECKLIST.md) | T03-D 체크와 같은 문단의 NOT_RUN 모순 제거; T11/T14가 모든 실모델·resume/cancel QA를 미완으로 열거하던 부분 정정 | [Context/Brain](../T03_T04_context_brain.md) §2026-09-24 T03-D: capability 32,768, COMPLETE 235, L0 초과 실패, 실모델 왕복. 요청별 num_ctx 배치 차이는 남음 |
| [Architecture review](../../ARCHITECTURE_REVIEW.md) | §5 잔여표에서 이미 관찰한 baseline/모델/Vault 동시성/provider window/shadow QA를 분리; P3/P19 및 Context 응답에 후속 근거 반영 | [T02](../T02_canonical_store.md) §2026-09-24, [T03/T04](../T03_T04_context_brain.md), [T11](../T11_surface.md) §5~7. 기존 partial 분류와 최종 통합 판정은 다름 |
| [T11](../T11_surface.md) | frontmatter와 최신 안내를 갱신하고 §1~4/YAML을 당시 기록으로 표시 | §5 shadow 배선, §6 실모델 1건, §7 실제 background 취소·SIGKILL 뒤 새 프로세스 재개. 인증된 ACTIVE canonical 복구 증거로 확대하지 않음 |
| [T13 live pilot](../T13_live_pilot.md) | provider 부재를 현재 미실행 사유로 쓰지 않음 | T11 §6의 2026-09-24 로컬 Ollama 응답은 provider 존재 증거. 실제 LiveTrialPort Fresh/Mature trial은 여전히 NOT_RUN |

헌법/원문/source manifest/state_claims는 수정하지 않았다. 과거 날짜의 YAML, 명령, 수치, source pin은 보존했다. T01b/T02/T11/T14의 체크는 열어 두었다. 기존 승인 범위 내 격리 구현·검증을 자동으로 새 사람 승인에 종속시키지 않으며, 운영 활성화·새 권한 부여·확증 성능 주장과 구분했다.

검증: 편집한 5개 문서와 이 보고서의 상대 Markdown 파일 링크를 검사했고 누락 0건이다(새 최종 보고서 포인터는 생성 전 일반 경로로 표기). 문서만 수정했으므로 runtime 시험은 이 leaf에서 실행하지 않았다.
