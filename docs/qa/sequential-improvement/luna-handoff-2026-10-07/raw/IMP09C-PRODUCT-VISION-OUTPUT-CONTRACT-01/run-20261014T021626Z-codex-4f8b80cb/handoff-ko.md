---
title: 구조화 출력 계약 구현 및 검수 인계
date: 2026-10-14
tags: [structured-output, offline, review, handoff]
---

현재 작업은 **COMPLETE_OFFLINE_REVIEWED / 독립 검수 APPROVED**입니다. 과거 Product-Vision 실측의 FAIL_SEMANTIC, 전체 IMP-09 PARTIAL 및 역사 원장 NOT_RECOVERED는 유지합니다.

앞선 QA 증거는 `7243c71f`, `3ed59124`로 커밋해 `ssak-ai/codex/m1-task-events`에 푸시했고 원격 SHA를 대조했습니다. 그 뒤 진행한 이번 구조화 출력 기능의 여섯 파일은 아직 미커밋입니다. 공유 작업 트리의 기존 staged 97개는 동일한 binary diff SHA로 보존했습니다.

## 구현 계약

실제 `POST /v1/chat/completions`의 raw JSON 검증, protocol translator, manager와 native Ollama provider까지 명시적 출력 형식을 전달합니다. 초기 지원은 **direct non-stream native Ollama qwen3 프로필**이며 프로필 이름과 저장소가 native dispatch 조건에 맞아야 합니다. 응답 형식이 생략되거나 null/text인 기존 요청은 기존 동작을 유지합니다.

`json_object`는 native `format="json"`, `json_schema`는 envelope 안의 정확한 schema object로 전달합니다. name/strict metadata를 native format 값으로 보내지 않습니다. 구조화 요청의 proprietary mode flag를 생략하면 direct mode를 선택합니다. 명시적 tools/agent/plan/TDD/search/stream/combo 및 non-native provider 경로는 session/conversation/inference 전에 typed 400으로 거부합니다.

구조화 요청은 자동 intent 분류, slash/self-capability dispatch와 image default-model routing을 건너뛰어 명시 모델을 유지합니다. 유효하지 않은 JSON, fence, 중복 키, NaN/Infinity 및 schema 불일치는 assistant 저장 전에 typed 502로 반환합니다. fence를 벗겨 성공으로 바꾸지 않습니다.

지원 schema는 Draft2020-12의 root object이며 reference keywords는 지원하지 않습니다. 실제 schema node의 중첩 dialect와 legacy schema keyword를 검사하고, validator에는 닫힌 referencing.Registry를 전달해 외부 참조 조회를 차단합니다. 일반 데이터 property 이름이나 annotation에 포함된 $ref/$schema는 keyword로 오인하지 않습니다.

예시의 `<등록된-native-qwen3-프로필>`을 실제 등록 프로필 이름으로 바꾸십시오. 예시 자체는 실행하지 않았습니다.

```json
{
  "model": "<등록된-native-qwen3-프로필>",
  "stream": false,
  "messages": [{"role": "user", "content": "결과를 JSON 객체로 반환하세요."}],
  "response_format": {"type": "json_object"}
}
```

두 integer property만 허용하는 예시는 다음과 같습니다. 이미지 입력은 기존 검증된 content block 형식으로 messages에 포함합니다.

```json
{
  "model": "<등록된-native-qwen3-프로필>",
  "stream": false,
  "messages": [{"role": "user", "content": "빨간 원과 파란 사각형 개수를 반환하세요."}],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "shape_counts",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "red_circles": {"type": "integer"},
          "blue_squares": {"type": "integer"}
        },
        "required": ["red_circles", "blue_squares"],
        "additionalProperties": false
      }
    }
  }
}
```

Ollama native format 계약의 공식 참고 자료는 [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs), 요청 envelope 참고는 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)입니다. 이 프로젝트의 위 지원 범위가 별도로 적용됩니다.

## 최종 검증 근거

- [v5 집중 검사](final-implementation-checks-v5/checks.json): 36 passed / failed·error·skip 0. Ruff lint/format, production basedpyright --level error, memory compile 모두 exit 0.
- [인접 회귀](adjacent-regressions/receipt.json): protocol translator와 기존 chat vision routing 50 passed / failed·error·skip 0. socket 시도 0, v5 소스 SHA 동일.
- [독립 v5 검수](code-review-v5.md): CLEAR / APPROVE, blockers 없음. 저장 근거와 현재 소스를 대조한 검수이며 모델/테스트를 재실행하지 않았습니다.
- [최종 소스 대조](final-source-check.json): 여섯 현재 파일 SHA가 v5 snapshot 및 인접 회귀 전후 SHA와 일치.
- [작업 patch](task-only.patch), [재구성 영수증](patch-reconstruction-verification.json): 실제 dirty preimage 기준 여섯 파일을 재구성했으며 최종 bytes와 동일.
- [최종 기계 판정](final-result.json), [산출물 manifest](artifact-manifest.json): 최종 상태·제한 및 저장 파일 크기/SHA 목록.

최종 집중 실행의 35개 ASGI capture에서 manager와 provider terminal mock 호출은 각각 14회입니다. 나머지 한 건은 직접 closed-registry 경계 검사입니다. 이 수치는 최종 집중 invocation에만 적용하며 과거 전체 합계가 아닙니다. 이번 후속 작업의 실제 HTTP/socket/Ollama/모델 추론은 0회입니다.

처음 독립 검수에서 중첩 Draft7 dialect와 legacy dependencies 참조가 원격 조회를 유발할 가능성을 발견했습니다. v5에서 schema-node 검사와 닫힌 registry를 보완했고 [수정 설명](implementation-correction-v5.md), 이전 검수와 실패 원문을 보존했습니다. 이전 implementation-handoff.md의 v4 최종 표기는 이 문서와 v5 correction에 의해 대체됩니다.

## 재현 이력 및 한계

[clean-red 영수증](clean-red/receipt.json)의 독립 격리 사본은 원본 chat/translator preimage로 두 사례가 실패했고 오류는 0건입니다. 일반 prompt에서 mock inference가 두 번 발생하고 native format이 누락되는 수정 전 근거입니다. 최초 mixed red의 21 실패/2 통과/teardown 오류 2건은 fixture 결함을 포함하므로 clean-red 근거로 사용하지 않습니다.

초기 verification script가 run-level source-postimage를 반복 사용해 과거 후보의 전체 source snapshot을 각각 보존하지 못했습니다. 과거 원문/JUnit/receipt/SHA는 유지했고 최종 v5는 고유 snapshot에 바인딩했습니다. 기존 asyncio_mode 설정 경고와 Starlette TestClient deprecation 경고도 남겼습니다. storage 직접 조회 대신 검수에서 validation-before-persistence 소스 순서를 확인했고, slash/self-capability bypass는 개별 회귀 대신 소스로 대조했습니다.

86개는 현재 변경에 대한 오프라인 범위 합계입니다. 실제 모델의 schema 준수·의미 정답·인증/lifespan 및 전체 저장소 gate를 증명하지 않습니다.

## 다음 작업의 시작 조건

이 결과로 다음 에이전트는 새로운 구조화 Product-Vision 관측을 준비할 수 있습니다. 새 소유 run, 현재 여섯 소스 SHA, schema가 포함된 고정 요청, 이미지 bytes, expected counts, 호출/시간/cleanup 예산을 먼저 바인딩하십시오. 과거 format 생략 요청과 그 FAIL을 재사용하거나 재판정하지 마십시오.

관측은 명시적 schema 요청이 실제 provider native format까지 도달하는지와 strict JSON/schema/의미 결과를 별도로 확인해야 합니다. 실패한 출력은 사후 수정·재전송하지 않고 원문과 단일 실행 영수증을 남깁니다. 실제 호출 여부는 새로운 작업의 승인된 범위에서 결정하며 이번 인계로 추가 inference가 수행됐다고 기록하지 않습니다.
