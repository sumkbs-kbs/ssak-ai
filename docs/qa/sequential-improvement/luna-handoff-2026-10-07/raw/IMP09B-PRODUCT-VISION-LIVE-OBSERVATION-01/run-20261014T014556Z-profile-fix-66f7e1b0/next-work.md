---
title: Product Vision 출력 계약 후속 작업
date: 2026-10-14
tags: [implementation-plan, product-vision, structured-output]
---

작업 ID: IMP-09-C-PRODUCT-VISION-OUTPUT-CONTRACT-01.

목표는 현재 관측의 fence 출력 실패를 바탕으로, 명시적으로 JSON을 요구하는 새 요청 계약에서 provider까지 구조화 출력 제약을 전달하고 검증하는 것입니다. 기존 관측의 acceptance나 원본을 수정하는 작업이 아닙니다.

현재 근거는 final-result.json, runtime-cli-result.json, 원본 product/provider 응답입니다. 비전 수량은 2/1로 일치하지만 원문은 markdown fence입니다. format은 의도적으로 생략된 기존 계약이므로, 새 작업은 format 허용·전달 기준을 별도 계약으로 확정해야 합니다. 기존 format 금지와의 대체 관계를 문서화하기 전 라이브 계약을 재사용하지 않습니다.

1. 현재 graph로 ChatCompletionRequest와 non-stream route, ModelManager._provider_kwargs, OllamaProvider._generate_native의 response_format 전달 여부를 확인합니다. 소스를 읽고 현재 baseline을 저장합니다. 일반 텍스트 요청 호환성도 확인합니다.
2. 새 UUID 소유 작업 폴더에서 실제 route→translator→manager→provider 경로를 사용한 오프라인 fixture를 만듭니다. 모델/네트워크 호출은 금지하고 terminal만 mock합니다. 구조화 출력 요청이 단 한 번 전달되는지, 빠진 요청은 기존 payload를 유지하는지 먼저 실패를 재현합니다.
3. 지원 형태를 정확히 정합니다. Ollama native가 받는 JSON schema와 제품 요청의 response_format을 어떻게 연결할지 현재 구현과 공식 계약을 대조합니다. 임의 문자열을 통과시키거나 provider별 형식을 혼합하지 않습니다. 실제 지원이 없으면 최소 전달 구현과 입력 검증을 추가합니다. 수정 파일 소유권을 선언하고 기존 미커밋 변경을 preimage로 보존합니다.
4. 새 수락 기준은 원문 strict JSON object, 정확한 키 두 개, bool을 제외한 정수 2/1, provider/product assistant 동일성입니다. 옛 FAIL_SEMANTIC을 fence stripping으로 PASS로 정정하지 않습니다. 저장 원문에 대해 형식 실패와 보조 수량 일치가 구분되는지도 검증합니다.
5. malformed response_format, 일반 텍스트 요청, streaming 범위, provider 오류가 성공 텍스트로 보이는 기존 문제와의 경계를 검사합니다. 일반 provider 오류 매핑은 별도 발견 사항으로 기록하고 무관한 대규모 수정으로 확장하지 않습니다.
6. task-only patch, red/green 원문·JUnit·exact command·source SHA, 보호 snapshot·counts·한국어 handoff를 고유 run에 보존합니다. 원장은 append-only 또는 새 고유 파일로 유지합니다.

완료 기준은 새 구조화 요청의 정확한 provider payload와 기존 일반 요청 호환성이 오프라인 실제 경로에서 입증되고 독립 검수가 끝나는 것입니다. 새 라이브 관측은 별도 fresh request/binding·실행 범위가 고정된 후 수행합니다. 이번 관측의 inference 1회 예산은 이미 소비됐으며 같은 사례를 재송신하지 않습니다.

현재 이 후속 구현은 NOT_STARTED입니다. 이 문서는 수행할 수 있는 범위와 수락 조건을 기록한 것이며, 구현이나 라이브 성공을 주장하지 않습니다.
