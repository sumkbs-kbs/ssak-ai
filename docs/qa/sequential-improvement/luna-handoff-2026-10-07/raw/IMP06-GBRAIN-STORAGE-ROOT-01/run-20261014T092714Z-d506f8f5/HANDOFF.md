# IMP06-GBRAIN-STORAGE-ROOT-01 — READY_FOR_INDEPENDENT_REVIEW

clean WT base `7802aa1b3043d66a80f6f891c6cf3db039b393a0`. 소유 파일은 `src/antigravity_k/engine/gbrain.py`와 새 `tests/test_gbrain_storage_root_contract.py`만. Root 제품 소스 수정, stage/commit/push 없음.

문제: module import의 global_gbrain 생성이 기존 Path.home()/.antigravity/gbrain을 사용하여 명시적 격리 실행의 소유 경계를 벗어나려 했다. 최소 수정은 `configured_dir = storage_dir or os.environ.get("AGK_GBRAIN_DIR")`; 유효한 생성자 경로 우선, 다음 환경변수, 둘 다 없거나 빈 문자열이면 기존 HOME 기본값이다. Path 기존 처리 그대로: 상대경로는 cwd 기준, 공백/Unicode 경로 지원; HOME 변경이나 자동 tilde 확장 없음. 생성자 문서 한 줄 외 메모리/Chroma/lifecycle 로직 변경 없음.

## 증거
- `red/`: 원본 제품 source SHA + 정확한 argv/cwd/출력/JUnit. fresh child에서 env를 지정했으나 global import가 `/Users/mr.k/.antigravity/gbrain` mkdir 시도 ⇒ 소유경로 audit가 차단, test exit1. 실제 외부 쓰기는 실행 전에 거절됨. `red/captures/env/receipt.json`은 denied mutation1, socket0, embedding0을 기록한다.
- 최종 `candidate-v2/`: **7 passed, 0 failed/skipped**, pytest argv/source SHA/JUnit/stdout/stderr/exit 보존. `scenario-evidence.json`은 각 정확한 nodeid/하위 프로세스 argv/probe SHA/receipt 경로를 연결한다. 모든 child exit0, 실제 import는 clean WT의 gbrain.py이며 최종 SHA 일치.
- 7 fresh-process 사례: env 경로, explicit 경로가 env보다 우선, empty explicit→env, env 없는 기본값, empty env→기본값, relative env, 실제 Chroma fresh import. 기본값 두 사례만 Path.home 메서드를 owned mock-home으로 대체하고 HOME 환경변수는 전혀 바꾸지 않는다. 나머지는 실제 HOME 반환값을 그대로 유지한다.
- `candidate-v2/captures/native_import/receipt.json`: Chroma1.5.9 PersistentClient 실제 지정 경로, 실제 chroma.sqlite3 존재, 실제 empty collection count0, global close/정상 프로세스 종료. Python filesystem audit는 owned tmpdir 이외 mutation을 차단하며 native factory wrapper도 Chroma 경로를 owned root로 제한한다. Rust 내부의 모든 syscall을 추적했다고 주장하지 않음.
- 7개 receipt 모두 `denied_mutations=[]`, `socket_attempts=[]`, `embedding_attempts=[]`, `home_unchanged=true`. DefaultEmbeddingFunction/download guard 활성. 실제 NN 검색/문서 임베딩/모델 다운로드/HTTP 없음. native 이외 여섯 사례는 Chroma constructor double로 경로 선택만 격리 검증.
- candidate-v1: 6pass/1fail. 테스트 default embedding guard의 잘못된 (*args, **kwargs) 서명이 Chroma의 (self,input) 인터페이스 검사에 걸린 harness 오류. guard 서명만 수정하고 candidate-v2 전체7 재검증. 이 실패를 제품 결함 또는 성공으로 세지 않으며 원본 로그 보존.
- `static-v2/{ruff,format,basedpyright,compile}.json` + stdout/stderr: owned2 모두 네 검사 exit0, BasedPyright0errors, in-memory compile2. 최종 테스트와 static source SHA 일치.
- `ownership-after.json`: 비소유 src577 unchanged. `task-only.patch` SHA `334de8b4f93bce261457b6d055d441a82a9d9eab59f836c9e4d5bb0a2d3ae67b`; `preimage/`+patch reconstruct2/2 SHA일치. `candidate-source/` 최종 소유2개. `graph-fallback.txt`: graph transport failure와 exact source fallback 기록.

## 범위
이 결과는 저장 루트/최초 import 경계 검증이며 실제 Uvicorn/API startup/리스너/HTTP 성공을 대신하지 않는다. 다음 root startup에서 `AGK_GBRAIN_DIR=<owned absolute directory>`를 명시해야 한다. 다른 저장소의 독립적인 기본 HOME 경로, global cache clear 등 기존 lifecycle은 수정하지 않았다. 독립 검토 및 root transplant/commit/push는 root 소유.
