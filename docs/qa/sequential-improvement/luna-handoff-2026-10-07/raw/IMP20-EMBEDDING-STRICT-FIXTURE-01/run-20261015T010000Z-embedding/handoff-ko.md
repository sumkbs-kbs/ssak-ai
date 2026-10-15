# 임베딩 strict API 테스트 교정

상태: `PREPARED_OFFLINE_SCOPED / INTEGRATION_PENDING`. 후보 `302337877766a540a21dd42c61605dc590e4026b`와 ROOT 제품/테스트 파일은 수정하지 않았다. 이 폴더의 postimage 사본만 수정했으며 commit/push는 없다.

## 판정과 변경

`tests/test_api_server.py::test_embeddings_endpoint_uses_local_fallback`은 strict API가 503을 반환하는데도 200 및 해시 벡터 1536차원을 기대했다. 원본을 그대로 복사한 `red-2` 실행에서 `503 != 200`을 재현했다. 인증 오류가 아니며 본문에는 `embedding_model_unavailable`과 요청 모델명이 있었다.

교정한 `test_embeddings_endpoint_rejects_unavailable_model_without_fallback`은 실제 `EmbeddingEngine`을 의존성으로 넣고 lazy `sentence_transformers` factory만 통제된 실패로 바꾼다. 요청 모델이 factory에 정확히 한 번 전달됐는지, 실제 hash fallback spy가 호출되지 않았는지, 503/detail의 code/model/message, 공통 오류 envelope, 성공 벡터 부재, 내부 loader 메시지 비노출을 확인한다. 제품 strict 처리는 변경하지 않는다.

정상 encoder의 입력·벡터·인덱스 보존은 기존 `test_embeddings_model_contract.py`의 정확한 두 벡터 fixture로 함께 검증했다. 새로운 mock 성공 경로를 중복 추가하지 않았다.

## 실행과 증거

| 시나리오 | 재현 명령 | 이진 관측 | 산출물 |
|---|---|---|---|
| 원본 stale 기대값 | candidate `.venv/bin/python -B run_checks.py red-2` | pytest exit 1, 1 failed, 실제 503/기대 200 | `red-2/receipt.json`, `red-2/junit.xml`, `red-2/observations.json` |
| 수정 + 기존 strict/정상 encoder | candidate `.venv/bin/python -B run_checks.py green` | pytest exit 0, 5 passed, skip/error/fail 0 | `green/receipt.json`, `green/junit.xml`, `green/observations.json` |
| 정적 검사·패치 복원 | candidate `.venv/bin/python -B finalize.py` | Ruff/format exit 0, 메모리 compile PASS, patch apply exit 0 및 byte-identical | `static/checks.json`, `static/compile.json`, `static/patch-replay.json` |

각 명령은 실행 경로를 별도로 만들므로 완료된 명령을 재실행하면 mkdir에서 멈춘다. 재현이 필요할 때는 별도의 새 실행 경로를 사용한다. 정확한 절대 명령·cwd·소스 SHA는 receipt에 있다.

`red-2`는 ASGI POST 1회, `green`은 ASGI POST 5회였다. socket connect/bind 및 자식 프로세스의 시도 계수는 두 실행 모두 0이다. 모델 factory는 메모리 대체이며 실제 모델·provider·Ollama·NN 실행은 없다. 전역 app lifespan은 별도 검증 대상이므로 이 실행에서 명시적으로 비활성화했다. 실제 HTTP나 외부 listener 검증으로 해석하지 않는다.

## 보존된 실패와 한계

- 최초 `red`는 croniter import의 `platform.architecture()`가 `file` 자식 프로세스를 호출하려 해 guard가 차단했다(exit 4, collection error). 제품 실패로 세지 않는다. 당시 helper, stdout/stderr, receipt, guard 관측을 그대로 보존했다. 후속 helper는 현재 인터프리터의 `struct.calcsize('P')`로 architecture를 제공하므로 subprocess가 필요 없다.
- 최초 helper 작성 직후 닫는 괄호 누락이 편집 진단에서 잡혀 테스트 실행 전에 수정했다. 그 상태로 실행한 테스트는 없다.
- basedpyright는 preimage와 postimage 모두 exit 1이며 동일한 기존 오류 4개가 있다: 변경하지 않은 `_RuntimeDouble.cancel_verdict` 참조(568/575/582/596행). 타입 검사 전체 PASS를 주장하지 않는다. 경고는 156→159이며 private 경계 spy와 기존 TestClient 불완전 타입에서 온 추가 경고 3개를 숨기지 않는다. 이번 테스트 수정에는 새 타입 오류가 없다.
- pytest 경고 3개: plugin autoload를 끈 환경의 `asyncio_mode` 미인식, Starlette httpx 전환 안내, anyio BlockingPortal alias deprecation. skip/suppression을 추가하지 않았다.
- 전체 23 gate 결과나 release/GA 승인을 대신하지 않는다. 부모가 전체 실행 종료와 해당 실패를 확인한 뒤, candidate preimage SHA 일치를 확인하여 `task-only.patch`를 적용할 수 있다.

`artifact-manifest.json`은 공개 증거만 포함한다. `runtime/`, replay의 `.git`, 캐시/바이트코드는 제외하며 과거 기록은 덮어쓰지 않는다.
