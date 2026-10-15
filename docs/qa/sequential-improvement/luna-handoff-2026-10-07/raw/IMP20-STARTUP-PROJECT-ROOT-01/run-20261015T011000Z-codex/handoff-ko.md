# 시작 시 설정된 프로젝트 루트 적용

상태: `COMPLETE_SCOPED_OFFLINE / 독립 검수 PENDING`. 후보 작업 트리 기준 HEAD는 `7360c78544abeea41e38c65faa6eba2610a8a33b`이며 커밋·푸시는 실행하지 않았다.

## 변경과 이유

`src/antigravity_k/api/server.py`의 lifespan은 `__file__`에서 계산한 설치 소스 루트를 RAG, IDE, 기본 hook/audit 저장소에 전달하고 있었다. 반면 EventBus는 이미 `config.paths.project_root`를 사용했다. 공유 `project_root` 값을 `str(config.paths.project_root)`로 바꾸는 한 줄 수정으로 설정을 일관되게 적용했다. `PathConfig`의 미지정 기본값은 기존 소스 루트와 동일하다. `AGK_HOOK_VAULT_DIR`의 명시적 우선순위도 유지된다.

기존 `tests/test_lifespan_agency_root_contract.py`는 agency만 수정하던 범위에서 RAG/IDE의 과거 동작을 고정했다. 이번 작업은 해당 두 소비자도 설정 루트를 사용하도록 계약을 확장하므로, 관련 단일 assertion을 `str(configured)` 기준으로 교정했다. 실제 agency SQLite 경로·영속 이벤트·종료 검사는 그대로 유지했다. 이 변경은 과거 테스트가 동일한 계약으로 계속 통과한다는 주장이 아니다.

## 검증

| 기준 | 실행과 관측 | 원본 증거 |
|---|---|---|
| 수정 전 원인 재현 | 실제 lifespan 6회: 절대·상대 설정 4건 FAIL, 미지정 2건 PASS. RAG/IDE가 설치 checkout을 선택한 값이 영수증에 보존됨 | `red-01/receipt.json`, `red-01/junit.xml`, `red-01/captures/*/receipt.json` |
| 설정 루트·기본값·hook 우선순위 | 절대/상대/미지정 × 기본/명시 hook 설정 6건 PASS. 실제 lifespan 시작·종료, RAG/IDE/EventBus/hook/audit 인자 및 종료 관측 | `green-02/captures/`, `green-02/junit.xml` |
| 실제 RAG의 작은 프로젝트 처리 | 설정 루트 4건 각각 소유 프로젝트의 Python 파일 하나를 실제 RAGIndexer로 인덱싱해 청크 1개 생성 | `green-02/captures/absolute-*/receipt.json`, `green-02/captures/relative-*/receipt.json` |
| 인접 회귀 | 신규 6건 + agency 3건 + storage roots 12건 + RAG incremental/provenance 및 startup security. 합계 35 PASS, 실패·오류·skip 0 | `green-02/receipt.json`, `green-02/stdout.txt`, `green-02/junit.xml` |
| 정적 검사 | Ruff, format, basedpyright 오류 수준 검사, 메모리 compile, diff-check 모두 exit 0. basedpyright 출력 0 errors / 0 warnings | `static-02/checks.json`, 대응 stdout/stderr |
| 변경 재구성 | task-only patch로 세 파일 재구성 후 현재 파일과 바이트 일치 | `task-only.patch`, `source-binding.json`, `patch-replay/` |
| 보호 경계 | config/RAG/EventBus/IDE/hook/audit 원본 6파일이 작업 시작의 clean HEAD와 동일 | `protected-files.json` |

실제 명령은 각 receipt의 `command` 배열이다. 소유 SourcePlan 저장소와 기존 OS provider 차단 정책에서 실행했다. 새 cold probe 내부에서는 socket connect/bind, 하위 프로세스, 모델 라이브러리 import를 차단하며 각 실행의 `forbidden`은 빈 배열이다. pytest를 실행하는 바깥 검증 프로세스와 cold probe subprocess는 실제로 실행되므로 전체 프로세스 생성이 0회였다는 뜻은 아니다.

초기 green-01도 35건 PASS였으나 신규 테스트의 문자열 구분자 형식 검사만 실패했다. 삼중 작은따옴표를 Ruff 요구 형식으로 바꾼 최종 파일에서 green-02 전체 선택자를 다시 실행했다. 초기 실패는 `static-01/`에 보존했다. 이후 검사는 반복하지 않았다.

## 한계와 인계

IDE listener, 실제 hook/audit 파일 서비스 및 EventBus는 신규 사례에서 통제된 대역이다. 기존 agency 사례는 실제 EventBus/agency SQLite 경로를 검증한다. HTTP, Ollama, 모델 추론, 전체 23개 게이트, 8시간 soak 및 독립 검수 완료를 뜻하지 않는다. RAG thread 취소·wait/reap 소유권은 이번 수정 범위에 포함하지 않았다. 위협·권한·제품 실행 루프 설계는 변경하지 않았다.

`artifact-manifest.json`은 생성 당시 158개 산출물의 크기와 SHA를 고정했다. 이 인계 문서는 그 뒤 추가되었으므로 해당 manifest에 들어 있지 않다. 부모 검수자는 manifest와 현재 3파일 SHA를 대조한 후 최소 패치를 검토하고 새 후보 전체 게이트로 진행할 수 있다. ROOT의 공유 작업 트리와 동시 실행 중인 WT3에는 수정하지 않았다.
