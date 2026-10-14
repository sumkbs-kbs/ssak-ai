# IMP06-STARTUP-STORAGE-ROOT-CLOSURE-01 — READY_FOR_INDEPENDENT_REVIEW

Root 승인으로 GBrain 경로 수정에 확인된 eager 생성자 두 개를 추가했다. clean WT base `7802aa1b3043d66a80f6f891c6cf3db039b393a0`. 제품3개: gbrain.py, global_memory_provider.py, context_shaper.py. 테스트2개: test_gbrain_storage_root_contract.py, test_startup_storage_roots_contract.py. Root 제품 소스 READ-ONLY, stage/commit/push 없음.

## 경로 계약
- GBrain: nonempty storage_dir > AGK_GBRAIN_DIR > 기존 ~/.antigravity/gbrain.
- GlobalMemoryProvider: nonempty memory_dir > AGK_GLOBAL_MEMORY_DIR > 기존 ~/.antigravity-k/memory.
- ContextShaper: nonempty storage_dir > AGK_CONTEXT_STORE_DIR > 기존 ~/.antigravity/context_store.
빈 문자열은 기존 falsy fallback 의미 유지. 상대경로/공백/Unicode는 기존 Path/문자열 처리대로 보존. HOME 변경/기존 사용자 데이터 이동/기본 설정 재작성/새 cache·lifecycle·memory architecture 없음. GlobalMemoryProvider는 os import와 경로2줄, ContextShaper는 env fallback과 해당 docstring만 추가했다.

## 새 검증
`candidate-v1/invocation.json`, stdout/stderr/exit/JUnit: **새 12 passed, 0 failed/skipped**. 각 생성자에 env/explicit우선/emptyexplicit/default/emptyenv/relativeenv 6사례. `scenario-evidence.json`은 exact nodeid와 child argv/probe SHA/receipt를 연결한다. 모두 새 프로세스의 실제 클래스 생성 및 실제 파일 쓰기/재개방이다. GlobalMemoryProvider identity.json roundtrip, ContextShaper collapse JSON/restore roundtrip을 확인했고 기존 max_entries/token/reserve/threshold 기본값도 유지했다.

`candidate-v1/captures/*/receipt.json`: clean WT source path/SHA, round_trip=true, home_unchanged=true, denied_mutations/socket_attempts/model_import_attempts 모두 빈 배열. fresh child audit는 tmp 소유 경로 외 파일 mutation 및 physical socket을 차단한다. NN/native backend imports(chromadb/torch/mlx/sentence_transformers/transformers/embedding/GBrain)도 차단한다. ModelManager 모듈 선언 import 자체는 기존 engine package 진입에 필요하며 실제 모델 로드/추론은 수행하지 않았다. HOME 환경변수는 모든 사례에서 그대로, 기본값 검증에서만 Path.home/expanduser('~') 반환을 owned mock-home으로 대체한다.

`red-v2/`: 제품 수정 전 env 두 사례가 각각 ~/.antigravity-k/memory, ~/.antigravity/context_store mkdir 시도로 실패했다. audit가 OS 쓰기 전에 차단했다. 원본제품 SHA/argv/log/JUnit/receipt 보존. 최초 red는 ModelManager 선언 import까지 차단한 harness 과잉 guard로 목표 생성자 전 실패했으므로 의미있는 RED로 세지 않는다. guard 범위를 실제 NN/backend로 좁혀 red-v2를 먼저 확인한 뒤 제품 수정했다.

## 기존 GBrain 증거와 결합
`retained-gbrain-evidence.json`은 별도 봉인 GBrain 패킷의 경로, manifest SHA, 최종 소스2개의 동일 SHA, retained7 PASS를 기록한다. 원래 manifest 모든 엔트리를 다시 SHA 대조하여 변조 없음 확인. GBrain 성공7개는 재실행하지 않았다. 따라서 판정은 **기존7 retained + 새12 PASS**이며 하나의19-case pytest 실행으로 표현하지 않는다. 실제 Chroma import/noNN 증거는 해당 원래 패킷에 있다.

`static-v1/{ruff,format,basedpyright,compile}.json` 및 로그: 소유5 파일 전체 네 검사 exit0, BasedPyright0 errors, in-memory compile5. `ownership-after.json`: 비소유 src575 unchanged. `combined-task-only.patch`는 HEAD 대비 제품3+테스트2 전체이며 SHA `892947e96c830b8c4fe11821d8c039416e871d1b6eaf613f5388e31f1685c31e`; `preimage/`와 재구성5/5 SHA일치(`reconstruction.json`). `candidate-source/` 최종5 파일. 옛 봉인 패킷은 수정하지 않았다.

## 다음 실행 경계
root startup은 AGK_GBRAIN_DIR/AGK_GLOBAL_MEMORY_DIR/AGK_CONTEXT_STORE_DIR을 각각 owned 절대경로로 설정한다. 이번 결과는 확인된 세 constructor/import storage 경계만 검증하며 Uvicorn listener/health HTTP 성공이나 모든 제품 저장경로 보편적 격리를 주장하지 않는다. source-supported blocker가 추가 관찰되면 별도 범위 판정한다. 독립 검토/root transplant/commit/push는 root 소유.
