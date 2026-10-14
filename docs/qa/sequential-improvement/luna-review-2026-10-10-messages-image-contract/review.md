---
title: Messages 이미지 누락 계약 독립 검수
tags: [ssak-ai, imp-09, independent-review, luna]
date: 2026-10-10
task_id: CODEX_REVIEW_IMP-09-C-MESSAGES-IMAGE-CONTRACT-01
verdict: APPROVED_SCOPED_OFFLINE
---

# 검수 결과

**APPROVED_SCOPED_OFFLINE**. COMPLETE_OFFLINE 상태를 승인하며, 이번 수정에 필요한 추가 코드 변경은 없다. [기계 판정](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-review-2026-10-10-messages-image-contract/review.json), [독립 대조 결과](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-review-2026-10-10-messages-image-contract/verification.json).

| 확인 항목 | 결과 |
| --- | --- |
| 수정 전 재현 | 보존된 JUnit의 동일 8개 사례가 HTTP 200 == 기대 400 assertion으로 실패. 과거 실행 재현은 반복하지 않음 |
| 수정 후 집중·영향 | 보존된 집중 8개 및 영향 회귀 61개 통과. 8개는 61개에 포함되며 합산하지 않음 |
| 독립 route 확인 | 실제 현재 route를 오프라인 TestClient로 한 번 확인해 8/8 통과. 정확한 JSON 400 및 manager capability/generate/stream 호출 0을 검증 |
| 실제 네트워크 | 독립 검사에서 IPv4/IPv6 connect를 차단하고 연결 시도 0을 확인. HTTP wire·Ollama·추론·listener 실행 없음 |
| 수정 위치 | body 검증에서 direct image 및 tool_result.content image를 찾아 flatten 전에 거절. stream 값과 무관하며 과거 턴도 검사 |
| 변경 범위 | task-only patch는 Messages production route와 신규 테스트 두 파일만 포함. 현재 소스·final 사본·기록된 최종 SHA 일치 |
| 독립 patch 재구성 | 시작 production preimage 및 신규 테스트 부재에서 재구성해 두 최종 파일과 byte-identical |
| 증거 보존 | 72개 산출물 크기·SHA 일치, 보호 144개 시작/현재/검사 후 해시 일치. 독립 대조 16항목 통과 |

오류는 `400 invalid_request_error`, 메시지는 `Image content is not supported by /v1/messages`이다. manager/provider·공유 bridge·model registry·config·auth·기존 테스트를 수정하지 않았다. 기존 text 및 tool-use 계약은 보존된 영향 selector 결과로 확인했다. Ruff lint/format, production basedpyright 오류 수준, compile의 최종 검사 기록은 해당 최종 소스 SHA와 연결되며 exit 0이다.

# 판정 범위

승인 대상은 메시지 입력에서 지원하지 않는 이미지를 조용히 버리는 오류의 오프라인 수리다. 인증된 외부 HTTP, full lifespan, 실제 모델 vision capability 및 인식 품질은 이번에 검사하지 않았다. 독립 route 테스트는 기존 conftest의 격리된 개발용 인증 설정을 사용하며 제품 인증 수정을 포함하지 않는다.

최초 수정 전 실행과 Ruff repair 명령의 실행 당시 시작/종료·소스 해시 영수증 일부가 없다는 한계는 원 기록 그대로 인정한다. 실패 로그/JUnit/preimage를 보존했으며 과거 시각을 역산해 보충하지 않았다. 현재 수정은 독립 route 재검사와 patch/소스 대조로 승인한다.

독립 검사에는 plugin 자동 로드를 제한하여 발생한 asyncio_mode 설정 경고와 upstream TestClient deprecation 경고가 각 1건 있었다. 동기 route 검사 8개는 모두 통과했다. 원 보고의 manager double 호출 0은 **수정 후 이미지 거절 사례**의 수치다. 수정 전을 포함한 전체 66개 mock 요청의 manager 호출이 모두 0이라는 뜻으로 사용하지 않는다.

공용 원장의 PENDING 기록 및 과거 증거를 덮어쓰지 않고 이 검수 문서를 후속 승인 기록으로 추가한다. 전체 IMP-09=PARTIAL, ledger=NOT_RECOVERED, 과거 FAIL을 유지한다. 검수자는 제품 코드를 수정하거나 commit/push하지 않았다.

# 다음 작업

**IMP-09-B-VI-01-NATIVE**: 실제 설치된 qwen3.8:latest의 native vision 입력을 작은 합성 PNG 한 장으로 한 번 관찰한다. 이미지 전달·기계 판독 가능한 출력·동결된 도형 수 oracle을 검사하며, 제품 API나 이미 완료한 TOOL 요청을 보내지 않는다. 성공해도 native scoped 결과이며 제품 vision 경로와 일반 인식 품질은 별도 미검증이다.

[GPT-6 Luna 실행 프롬프트](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/ssak-ai-core/GPT6_LUNA_NATIVE_VISION_2026-10-10.md).
