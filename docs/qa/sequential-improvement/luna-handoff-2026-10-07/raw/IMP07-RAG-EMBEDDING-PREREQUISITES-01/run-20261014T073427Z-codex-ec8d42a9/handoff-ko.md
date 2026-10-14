# 임베딩 선행 변경 게시 후보

최종 상태: **READY_FOR_INDEPENDENT_REVIEW**. `candidate-v2`의 **66개 회귀와 정적 검사 4개 모두 통과**했다. 이전 타입 오류 후보의 결과·인계·manifest·patch는 `candidate-v1/closeout-*`에 보존했고 아래 최종 결과로 대체한다.

## 소스 범위

깨끗한 managed worktree HEAD `23708fe45cfb9140f9934bec88ec487913e3f7f6`에서 시작했다. Root 작업 트리·기존 증거·staging은 수정하지 않았다. 소유 파일은 `owned-paths.json`의 10개다.

기존 strict patch SHA `41784c194f6ff9d2f134bd453f11a92d03eb9c7cacda29278b83992239714ff2`와 routing patch SHA `28c9d43e0946512c120ef6436898e0c660d0ce0ad77a50e3995ca18dba43e078`를 읽어 확인하고 필요한 hunks만 순서대로 적용했다. 기존 HEAD에 없던 `test_embeddings_model_contract.py`는 과거 보존 baseline과 해당 patch로 재구성했으며 SHA `8cc10be711d036cda641f02f2b82fdd2d4b4f32880cd1e8a2b18500115cfab41`와 일치했다. 과거 보고를 현재 검증 대신 사용하지 않았다.

- EmbeddingEngine strict 실패 및 등록 Ollama provider routing, 공개 API의 strict 503/invalid-response 502를 포함한다.
- API dependency에는 `ModelRegistry()` 생성 및 `EmbeddingEngine(registry=registry)` 주입과 새로 승인된 타입 전용 Protocol 보완을 포함했다. 기존 `str(model_manager.generate(...))` 변환은 유지했다. 과거 routing patch가 제거했던 str 변환은 이식하지 않았다.
- ModelRegistry에는 경로 인자가 생략됐을 때 `AGK_CONFIG_FILE`을 읽는 기존 root의 한 줄만 포함했다. 명시 경로가 우선하며 환경변수가 없거나 비면 기존 기본 경로를 유지한다.
- 기존 routing 테스트의 kwargs를 `_ClientOptions` TypedDict/Unpack으로 정확히 표기하고 이미 tuple이던 기본값의 annotation을 맞췄다. 테스트 단언이나 실행 의미를 낮추지 않았다.
- vector_store/chroma_lifecycle/config.yaml, 사용자 기본 모델 활성화, RAG identity/precompute는 포함하지 않았다.

## 실행 결과와 관측 자료

`config-red-v1/`은 `CONFIG_RED=1` 환경에서 새 경로 계약만 실행했다. **1 failed / 3 passed**: 생략된 경로에서 환경 설정을 무시하던 문제를 재현했다. 원문·JUnit·소스 snapshot·exact argv를 보존했다. 초기 타입 검사에는 역사적 테스트 주석 오류와 기존 dependencies 오류 합계 22개가 있었다.

최종 명령: worktree cwd에서 root `.venv/bin/python <이 run>/verify.py candidate-v2`. 이미 성공한 실행을 다시 하지 않는다. `candidate-v2/checks.json`은 정확한 argv/cwd/exit, stdout/stderr와 source 전후 SHA를 연결한다.

**66 passed / failures 0 / errors 0 / skipped 0** (`candidate-v2/junit.xml`). 기존 임베딩/strict/routing/모델 API selector 61개, 새 config precedence 4개, 기존 `test_r15_boot_attach_never_installs_active` 1개다. 마지막 사례는 타입 전용 변경 주변의 SHADOW/ACTIVE 배선 동작을 확인한다. 경고 43개(기존 Starlette·record_property/xunit2)는 원문에 보존했다.

| 계약 | 실제 관측 | 근거 |
|---|---|---|
| API strict loader 실패 | 503, fallback 0, 성공 벡터 없음 | JUnit model-contract testcase properties의 원본 요청·응답/계수 |
| 등록 Ollama 임베딩 | 실제 dependency/engine/provider → MockTransport, 요청 model/input 및 반환 벡터·인덱스 일치 | JUnit routing testcase properties 및 `junit-observations-v2.json` |
| 잘못된 provider 성공 응답 | 구조화된 502, fallback 없음 | 같은 routing raw 응답과 검증 단언 |
| registry 없는 내부 기본 embed | 결정적 1536차원 hash fallback 유지 | `test_embeddings` JUnit 및 fallback 관측 properties |
| 환경 경로 우선순위 | 명시 경로 우선 / 환경 적용 / 없거나 빈 환경은 legacy 경로 | 새 4개 testcase JUnit |

Cold wrapper는 import 전 socket connect/bind/listen과 기본 SentenceTransformer 모델 로딩을 차단했다. **socket attempts 0 / model attempts 0** (`candidate-v2/socket-attempts.json`). 테스트가 직접 설치한 stub encoder/MockTransport만 사용한다. 제품 모듈 5개의 `__file__`이 worktree/src 아래임을 단언했다(`candidate-v2/import-bindings.json`). Models/system TestClient의 lifespan은 명시적으로 offline noop fixture이며 실제 lifecycle/auth/서버/모델 품질 검증이 아니다.

## 정적 검사 수정 이력

이전 candidate-v1은 Ruff lint/format 및 메모리 compile exit 0이었으나 전체 10파일 basedpyright는 **exit 1, 오류 2개**였다. `dependencies.py`의 기존 `_attach_cognitive_surface`에서 object의 `get_target_for_role`/`generate` 접근을 지적했다.

보존 preimage만 검사해 **동일 2개, exit 1**을 확인했다(`type-comparison-checks.json`). 이후 parent가 최소 Protocol 주석 보완을 명시적으로 승인했다. 두 메서드의 기존 str 계약을 표현하고 불필요해진 ignore를 제거했으며 런타임 변환/분기는 유지했다. **최종 candidate-v2는 전체 10파일 basedpyright 0 errors / exit 0**, Ruff lint/format 및 메모리 compile도 모두 exit 0이다. 이전 실패 근거는 그대로 보존한다.

## 보존 및 게시 준비

`candidate.patch`는 시작 HEAD preimage 기준 10파일 변경만 담는다. 별도 reconstruction에 적용 후 전 파일 바이트 일치를 확인했다(`patch-reconstruction.json`). `source-binding.json`과 manifest는 후보 파일·검증 근거를 연결한다. 임시 reconstruction 및 격리 캐시는 manifest에 중복 수록하지 않는다.

candidate-v1 뒤 worktree `vault_data/.chroma/chroma.sqlite3`가 미추적으로 나타났다. 작업 시작 Git 상태가 깨끗했던 관측과 실행 시각을 근거로 이번 테스트 생성 캐시로 분리했다. 과거 전체 파일 부재를 timestamp만으로 증명한다고 주장하지 않는다. 크기·SHA를 보존해 `isolated/chroma-from-candidate-v1`로 이동했고 삭제하지 않았다(`ephemeral-cache-relocation.json`). candidate-v2의 Models API fixture는 `ANTIGRAVITY_VAULT_PATH`를 매 테스트의 임시 owned-vault로 설정하고 실제 VectorStore 경로가 그 아래임을 단언·기록한 뒤 close한다. 제품 기본 경로는 바꾸지 않았다. 최종 Git 상태에는 10개 소유 경로만 남으며 vault_data는 깨끗하다. Root vault는 접근하거나 수정하지 않았다.

Worker commit/stage/push 없음. 독립 검수와 게시를 마친 뒤 별도 RAG embedding identity 작업을 시작한다. 이번 결과는 그 선행 코드의 깨끗한 게시 후보이며 RAG 연결·검색 품질 완료가 아니다.
