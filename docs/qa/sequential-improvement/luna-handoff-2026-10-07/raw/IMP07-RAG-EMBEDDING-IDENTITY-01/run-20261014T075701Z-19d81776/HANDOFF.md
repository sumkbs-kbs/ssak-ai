# IMP-07-RAG-EMBEDDING-IDENTITY-01 — READY_FOR_INDEPENDENT_REVIEW

후보: clean managed worktree `/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai`, base `2a8791ed8259543b54a12225bcc46cea69451efa`. 제품 코드 4개와 새 테스트 1개만 변경. stage/commit/push 하지 않음. `ownership-after.json`: 기존 비소유 Python 소스 574개 SHA 동일.

## 구현
- `ProjectEmbeddingBinding` 명시적 opt-in. 등록된 Ollama embedding profile만 허용하며 기존 strict `EmbeddingEngine.embed(..., allow_fallback=False)` 사용. 생성자는 추론하지 않음. 매 호출 전후 registry/profile/endpoint 동일성 확인.
- identity v1에 provider/profile/wire repo/nonsecret resolved endpoint/configured dimensions/document/query prefix 저장. dimensions=0은 UNKNOWN. 실제 weights revision은 null/UNVERIFIED; `:latest` 불변성을 주장하지 않음.
- 실제 Chroma에 사전 계산 embeddings/query_embeddings 전달. prefix는 임베딩 입력에만 붙이고 저장 document는 유지. 벡터 개수/양의 일관된 차원/finite numeric/nonbool/float32 positive norm 검증 후 write.
- 기존 collection을 먼저 lookup. legacy metadata 없음(빈 collection 포함), 다른 identity, implicit bound open 거절. autostamp/migration 없음. 첫 실제 차원은 성공 upsert 뒤 기록. metadata commit 실패는 전파하고 handle을 차단하며 재개방도 uncertain 상태 거절.
- 새 bound 모드 persistent 오류는 전파. close는 소유 Chroma client.close()를 호출하고 참조를 해제하며 전역 cache clear 하지 않음. implicit/different identity 거절 시에도 peer 보호. closed guard는 모델/collection 사용 이전 동작.
- bound RAG replacement는 모든 변경 source를 한 배치로 embed/검증한 뒤 upsert하고 해당 source의 stale ID만 삭제. 성공 이후 hash/manifest 진행. sync의 삭제 source도 같은 단계로 연기. 모델 실패 시 기존 rows/manifest 유지, 복구 재시도 가능. 기존 None 경로 유지.
- bound index_file/index_project/sync의 외부 경로와 외부 symlink는 읽기/해시/임베딩 전에 거절. API factory optional binding 실패는 fallback 없이 전파, None fallback 유지.

## 검증과 정확한 증거
- 최종 `candidate-v2/invocation.json`에 Python 절대 경로/cwd/argv/env/소스 SHA. `stdout.log`, `stderr.log`, `exit.json`, `junit.xml`: **58 passed, 0 failed, 0 skipped**. 새 contract47 + 기존 offline RAG11. fixture의 실제 Chroma owned tmpdir와 결정적 FakeEngine만 사용.
- `scenario-evidence.json`: 각 contract의 정확한 nodeid와 `candidate-v2/captures/*.json` 경로, 모델/native 호출 및 binary assertion. 해당 JSON은 model_name/allow_fallback/prefix 입력, actual native precomputed vectors/query/delete, 실패 보존 rows/manifest observations를 포함. `candidate-source/tests/...`가 모든 assertion의 고정 소스.
- `candidate-v2/module-socket-binding.json`: 실제 import는 clean WT 소스, socket attempts=[]; 47개 fixture forbidden=[] (물리 network/model load/fallback/default callback/download 시도 0). Legacy None callback 회귀 한 개는 명시적으로 deterministic callback을 사용하여 기존 default 동작을 검증함.
- real-Chroma 사례: 문서/query/redaction 같은 provider, 차원0→3 저장/재개방, 동일차원 다른 identity 거절, empty/nonempty legacy 거절, implicit bound 거절, peer close/거절 후 peer read/write, metadata 실패 uncertain reopen, provider/벡터 오류 write0, delete/purge model0, RAG 3진입점 failure 보존/복구, 동시 changed+removed 보존, 다른 프로젝트/정본 파일 유지, outside sentinel read/store/embed0.
- `red-optin/`: 동일 현재 동작 테스트 + original VectorStore preimage ⇒ opt-in keyword TypeError, exit1. `red-ordering/`: 동일 테스트 + original RAGIndexer ⇒ index_file/index_project/sync 3개 모두 provider 실패 뒤 기존 rows 삭제로 실패, exit1. argv/JUnit/captures와 preimage source SHA 보존. RED는 실패 동작을 약화하지 않음.
- `static-v2/{ruff,format,basedpyright,compile}.json` 및 stdout/stderr: 모두 exit0, owned5 파일 전체. BasedPyright 0 errors/warnings, in-memory compile5. static-v1 format1은 마지막 API factory 줄 포맷 후 수정, 이에 따른 새 후보 candidate-v2로 전체58 재검증; 과거 결과 덮어쓰지 않음.
- `task-only.patch` SHA256 `feb95510b5ab2807caaad657f9c15080f96464d03169534dd18a26cd5152b43c`. `preimage/` + patch로 reconstruction5/5 SHA 일치 (`reconstruction.json`). `candidate-source/`에 최종5 파일만 보존. 거대한 tmp DB/fixture 복사 없음.
- `chroma-close-source.json`: 설치1.5.9 close 실제 코드/경로/SHA. peer 보호는 실제 collection tests로 별도 확인.

## 경계와 다음 항목
- 이 판정은 offline routing/namespace/failure 계약. 실제 Ollama/HTTP/download/추론/semantic quality/8-client load 검증 아님. 기본 활성화 없음.
- Native upsert/delete 단계 전체의 transaction atomicity를 주장하지 않음. native failure는 전파되고 manifest를 진행하지 않으나 이미 성공한 native write는 남을 수 있음. metadata-write failure는 uncertain 상태로 차단함. 동시 index writer 잠금은 추가하지 않음.
- Bound 변경 배치는 index_file/index_project/sync 각각 변경 청크 전체에 **모델 호출 1회**, 변경 없음/삭제만은0. 대규모 배치 메모리 성능은 검증하지 않음.
- 기존 manifest 파일 I/O 오류 처리(로그 후 반환)는 이번 수정 밖의 기존 계약. 일반 authority/TOCTOU 경쟁 문제 전체를 해결했다고 주장하지 않음.
- 별도 다음 목표: `_keyword_search`가 private `_chunks`를 기대하여 실제 VectorStore에서 semantic fallback, 기본 hybrid가 raw+expanded+fallback으로 3회 embed 가능. 다음 작업은 export_all corpus 재사용 + actual-Chroma keyword model0; 이번 패치에는 포함하지 않음.
- 독립 검토/승인/commit/push는 root 소유. 현 상태 READY_FOR_INDEPENDENT_REVIEW.
