# 임베딩 테스트 추가 경고 교정 v2

상태: `COMPLETE_OFFLINE_REVISION_V2`. 부모가 허용한 WT3의 `tests/test_api_server.py`만 수정했다. 기존 증거 45개와 manifest는 보존했으며 commit은 하지 않았다.

변경은 세 부분이다. 항상 예외를 던지는 factory의 반환형을 `Never`로 바꿔 private `_EmbeddingModel` import를 없앴다. fallback은 고정 두 좌표를 반환하는 spy로 설치해 private 속성을 직접 읽지 않으며 여전히 `assert_not_called()`로 0회를 검증한다. 기존 불완전 TestClient 타입에 추가 경고를 만들던 `response.text` 검사는 이미 파싱한 전체 JSON의 직렬화 문자열을 검사하도록 바꿨다. 정확한 typed 503/detail, factory 1회, fallback 0회와 내부 loader 오류 비노출 계약은 그대로다.

| 검증 | 명령·원문 | 관측 |
|---|---|---|
| 수정 계약 + 기존 strict/정상 encoder 4개 | `green/receipt.json`, `green/junit.xml`, `green/observations.json` | exit 0, 5 passed, fail/error/skip 0; ASGI POST 5회; 네트워크·listen·자식 프로세스 시도 0회 |
| Ruff·format·compile | `static/checks.json`, `static/compile.json` | Ruff/format exit 0, memory compile PASS |
| 타입 비교 | `static/type-after.stdout.txt`, 원본 `../static/type-before.stdout.txt` | 기존 4 errors/156 warnings; severity/rule/message multiset 동일, 새 오류·경고 0 |
| 패치 재구성 | `static/patch-replay.json` | exit 0, byte-identical |
| 원본 증거 보존·현재 source binding | `result.json`, `final-artifact-check.json` | 원본 45개와 manifest SHA 유지, 현재 후보 파일과 검사 사본 SHA 동일 |

정확한 실행은 WT3 `.venv/bin/python -B run_checks.py green` 및 `finalize.py`이며 receipt에 절대 경로가 기록돼 있다. 실행된 테스트는 SHA가 같은 소유 사본이고 제품 import는 WT3를 사용한다. `task-only.patch`는 v1 적용 상태 SHA `3a5b9611b68a7e42c21495ad5d57697288539d0d2b59d7345880a27611ed2805`에 대한 v2 증분이다.

최종 SHA: `ca0d78899a0191dbe47e14f9bff88a478f01e6d770abf90c0286011019bef7a2`.

제품 모델/NN/Ollama 호출 및 외부 HTTP는 실행하지 않았다. app lifespan은 비활성화한 오프라인 범위이며 실제 lifespan/전체 gate/GA 검증으로 해석하지 않는다. 기존 `_RuntimeDouble.cancel_verdict` 오류 4개는 변경하지 않아 basedpyright의 전체 종료 코드는 여전히 1이다. pytest의 기존 설정 및 deprecation 경고 3개도 보존한다.
