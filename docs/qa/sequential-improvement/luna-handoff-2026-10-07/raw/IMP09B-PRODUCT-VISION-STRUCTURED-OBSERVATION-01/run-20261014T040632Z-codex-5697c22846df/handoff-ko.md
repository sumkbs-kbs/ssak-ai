---
title: 구조화 Product-Vision 실제 관측 및 검수 결과
date: 2026-10-14
tags: [product-vision, structured-output, live-observation, review, handoff]
---

**PASS_SCOPED_STRUCTURED_VISION_UVICORN_AUTH_LIFESPAN_OFF**입니다. 새 schema 요청의 실관측과 독립 저장 증거 검수를 완료했습니다. 생성 acceptance의 표기 결함은 별도 정정 영수증으로 보존했습니다. 전체 IMP-09는 PARTIAL, 과거 format 생략 사례는 FAIL_SEMANTIC, 역사 원장은 NOT_RECOVERED입니다.

## 실제 관측

인증된 외부 loopback Uvicorn의 실제 제품 POST **1회**가 Ollama native /api/chat inference **1회**로 이어졌습니다. 제품/provider 모두 HTTP200, provider done=true이며 양쪽 assistant 원문은 정확히 동일합니다.

```json
{"blue_squares": 1, "red_circles": 2}
```

fence를 제거하거나 내용을 수정하지 않고 직접 strict JSON으로 디코딩했고, 고정 schema 및 이미지의 실제 수량 2/1에 맞았습니다. Schema에는 키·integer·required·additionalProperties:false만 지정했으며 정답 const/enum은 넣지 않았습니다. 실제 native 요청의 format은 envelope가 아닌 정확한 schema 객체입니다.

모델은 qwen3.8:latest, digest `22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643`, Ollama0.40.3입니다. Profile은 think=false, keep_alive30m, num_ctx32768, num_predict128, temperature0, repeat_penalty1.3, min_p0.05로 관측됐습니다.

무인증 readiness401 / 임시 Bearer200을 확인했습니다. worker 종료 코드0, reap 및 handle release가 관측됐고 cleanup은 약0.686초로 5초 한도 안입니다. 외부 launcher가 관측한 supervisor 종료 코드는0입니다. 내부 영수증의 supervisor 종료는 NOT_OBSERVED로 남깁니다.

이번 run만의 HTTP 계수는 parent8 + 별도 provider wire1 = **총9회**입니다. 인증 readiness2, 사전 metadata4, 제품1, 사후 metadata1, provider inference1입니다. http-read22개를 요청 수로 세지 않았습니다. 재시도·redirect·별도 native/direct/tool inference는0입니다. 사후 모델은 keep_alive 계약대로 메모리에 남았으며 강제 unload는 하지 않았습니다.

## 검증 및 보존

새 준비 fixture14개가 실패·오류·skip 없이 통과했습니다. 실제 route→translator→manager→provider를 연결하고 terminal만 모의 응답으로 대체한 경로1회, socket 시도0회였으며 정적 검사4개는 exit0입니다. 이전36/50/45/18 등 성공 selector와 과거 actual 사례는 반복하지 않았습니다.

보호 소스28개와 실행 구현6개는 바인딩 및 전후 SHA가 같습니다. 기존 staged97개도 binary diff SHA가 동일합니다. 부모의 실제 관측 패키지125개, 구조화 구현 패키지1123개 파일의 크기/SHA와 manifest를 그대로 유지했습니다. task-only patch의 변경 대상5개는 preimage 재구성 후 바이트 일치가 확인됐습니다.

Binding: `ec3f6b4293b400500c0b21329c0cc4d6358ff315dcbfed9ba810b4253754746d`.

핵심 자료:

- [기계 판정](final-result.json), [새 요청의 사전 수락 기준](planned-acceptance.json)
- [준비 결과](preparation-result.json), [준비 독립 검수](schema-preflight-review.md)
- [실제 실행 영수증](launches/live-62dcc6a8320945ae95260e8b823436fd/launch-receipt.json)
- [원본 runtime 판정](runtime-cli-result.json), [원장](task-wire-journal.jsonl), [HTTP 실행 기록](runtime-observations.jsonl)
- [제품 원본](attempts/codex-final-gate-candidate-6/product-response.bin), [provider 요청 원본](runtime-state/captures/provider-7529a2780c094597a3b0776a096efabd-request.bin), [provider 응답 원본](runtime-state/captures/provider-7529a2780c094597a3b0776a096efabd-response.bin)
- [원문 재대조](stored-observation-verification.json), [독립 실관측 검수](final-evidence-review.json)
- [최종 소스/부모 보존 대조](final-protection-verification.json), [봉인 manifest](artifact-manifest.json)

독립 실관측 검수는 closeout_evidence_audit의 저장 원문 검토 보고를 root가 JSON으로 기록했습니다. 검수자는 테스트·HTTP·모델을 재실행하지 않았습니다. 패키지 봉인은 이 보고와 별도로 root가 최종 파일 목록/크기/SHA를 대조합니다.

## acceptance 표기 결함

원래 [acceptance.json](acceptance.json)의 format 필드에는 **omitted**가 남았습니다. 실행된 run_harness.py:1267의 이전 snapshot writer 문자열이 원인입니다. 준비 단계의 새 계획·schema·profile·request와 실제 native guard에는 schema 계약이 반영됐습니다. 해당 계획은 실행 binding에 사전 고정돼 있었고 실제 raw payload가 동일한 schema를 전달했음을 확인했습니다.

원본 acceptance나 실행 소스를 덮어쓰지 않고 [정정 영수증](acceptance-metadata-correction.json)에 원본 SHA, 사전 계약 SHA, 실제 요청/응답 SHA와 정정을 연결했습니다. 독립 검수도 이를 runtime blocker가 아닌 **기록 표기 결함**으로 분류했습니다. 이 성공은 옛 format 생략 FAIL을 PASS로 바꾼 결과가 아닙니다.

하네스 내부 task_id는 재사용한 FINAL-GATE-CLOSEOUT 계보를 유지하며, binding의 future_observation_task_id와 이번 문서/최종 결과가 새 STRUCTURED-OBSERVATION 작업을 구분합니다. 과거 결과의 launch cross-link 오기 하나도 root-start-baseline.json에 별도 기록했으며 기존 파일은 수정하지 않았습니다.

## 범위와 다음 작업

이번 결과는 고정 이미지·질문·모델 하나와 non-stream schema 요청에 한정됩니다. 일반 시각 품질, lifespan-on, 전체 suite/GA를 입증하지 않습니다. 이번 차례에는 제품 소스를 추가 수정하거나 commit/push하지 않았으며 구조화 기능의 이전 후속 변경도 미커밋입니다.

다음 항목은 **IMP-09-C-PRODUCT-VISION-ACCEPTANCE-METADATA-CONTRACT-01**입니다. 실행된 이 폴더를 읽기 전용으로 두고 새 고유 폴더 사본에서 acceptance writer의 format 표기를 고정 schema로 바꾸십시오. 새 집중 offline snapshot-writer 사례만으로 generated acceptance와 planned/request/profile/schema의 일치를 확인하면 됩니다. 실행 소스를 사후 재바인딩하거나 이번 성공 inference를 반복할 필요는 없습니다.
