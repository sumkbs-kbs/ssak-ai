# IMP-07-RAG-KEYWORD-CORPUS-01 — READY_FOR_INDEPENDENT_REVIEW

Base clean WT HEAD `f11c8563e88540c8c8322ba98c23eff53e0604e6`; WT `/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai`. Root 제품 소스 READ-ONLY. 소유 2파일: `src/antigravity_k/engine/rag_indexer.py`, 새 `tests/test_project_rag_keyword_corpus_contract.py`. stage/commit/push 없음.

## 변경
`_keyword_search` corpus 획득만 수정. 기존 fake store `_chunks` 호환을 유지하고, 없으면 공개 `export_all()`에서 list/record/string id/string document/dict metadata를 검증하여 document→text로 변환한다. export 기능 자체가 없는 legacy store만 기존 semantic fallback을 유지한다. 존재하지만 noncallable/잘못된 응답/export 실패/closed store는 오류를 전파한다. cache/schema/backend 추가 없음.

`scope-verification.json`: 모든 다른 RAGIndexer 메서드 소스 동일, `_keyword_search` query_tokens 이후 점수/정렬 suffix 동일. RRF, query expansion, provenance, stale filtering, bound path 정책은 변경하지 않았다. keyword-only stale 결과는 기존대로 provenance=stale이며 hybrid/long_context에서 기존 stale 제외 동작을 유지한다.

## 검증
- `red-v3/invocation.json`, stdout/stderr/exit/JUnit 및 captures: 제품 수정 전 actual bound Chroma 두 keyword 사례가 model call 1 vs expected0으로 실패(exit1). query는 reconcile ledger/invoice archive. 초기 red는 fixture import 수리 전 collection error(유효 RED 아님), red-v2는 rank 차이로 실패; 전부 보존하고 red-v3를 주 RED로 사용. `red-tests.executed.py`와 original preimage 보존.
- 최종 `candidate-v2/invocation.json` source SHA/cwd/절대 Python/argv/env, `junit.xml`, `exit.json`: **36 passed / 0 failed / 0 skipped**. 새 계약25 + 기존 offline RAG11(증분3/subdir1/provenance3/chunk identity4). 최신 identity58은 맹목 재실행하지 않았다.
- `scenario-evidence.json`은 모든36 exact testname과 native15 사례의 capture 경로를 연결한다. 각 `candidate-v2/captures/*.json`에 fake engine exact texts/model_name/allow_fallback, actual Collection.get/upsert/query/delete 호출 및 results 관찰을 저장했다. fixture 의존 소스는 기존 identity test의 FakeEngine/socket/default callback/download guard이며 변경 없이 `fixture-dependencies/`에 고정했다.
- 실제 Chroma keyword 모드: 식별자/파일명 top rank; empty/no-match/empty query 모델0; 변경/삭제/재개방 최신 corpus; 다른 collection 불포함; closed/export 오류 모델0. public export 결과와 private corpus lexical ranking exact equality. malformed6/noncallable3는 semantic fallback0. 기존 no-export fallback/private chunks 호환 유지.
- hybrid 실제 fake-provider budget: query ledger=1(raw), context=2(raw+기존확장), keyword fallback 추가 호출0. namespace 별도 collection 보존, stale/provenance 기존 동작 검증.
- `candidate-v2/module-socket-binding.json`: 실제 모듈은 clean WT, socket_attempts=[]; native15 captures forbidden=[] (물리 네트워크/real model load/fallback/default embedding/download 0). fake embed는 corpus setup 및 명시된 semantic channels에만 사용. 실제 Ollama/모델 추론/품질 향상을 주장하지 않음.
- `static-v1/{ruff,format,basedpyright,compile}.json` + stdout/stderr: owned2 전체 네 검사 exit0, BasedPyright0errors, in-memory compile2. 초기 import order 경고는 정리 후 최종후보 재검증했다.
- `ownership-after.json`: 비소유 src577 SHA 불변. `task-only.patch` SHA256 `fc0503c03d40bbc813448de5f86f21dd2f115f97cce3a5f24ca6b55a6593aaf5`; `reconstruction.json` preimage+patch 2/2 일치. 소스 최종 SHA는 candidate-v2/invocation과 정적검사에서 동일 확인. 소유코드2개는 `candidate-source/`.

## 경계
공개 export는 매 검색 현재 모든 record를 읽는다. 캐시/대규모 corpus 성능 개선은 하지 않았으며, 이 변경은 불필요한 모델 호출 제거와 lexical routing 계약 검증이다. 의미 검색 및 실제 품질 평가30/20은 별도 목표. 독립 검토/승인/commit/push는 root 소유.
