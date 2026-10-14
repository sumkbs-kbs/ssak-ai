# IMP06-LIFESPAN-AGENCY-ROOT-01 — READY_FOR_INDEPENDENT_REVIEW

Base clean WT `7482ebb8b76c7c686e729e68c48f7258e2cc7e66`. 제품 변경은 api/server.py의 한 줄: `bridge_to_hook_event_bus(project_root=str(config.paths.project_root))`. 기존 source-derived project_root 변수/RAG indexer/IDE workspace 인자는 바꾸지 않았다. 새 테스트 tests/test_lifespan_agency_root_contract.py. ROOT server는 수정하지 않았으며 Gitstage/commit/push 없음.

## 실제 경계와 검증
- `red/`: 원본server에서 fresh child가 **실제 imported server.lifespan → 실제 bridge_to_hook_event_bus → 실제 PersistentAgencyController → 실제 PersistentAgencyStore.__init__**를 호출했다. 환경 설정 owned project와 달리 cleanWT/.antigravity_k 쓰기를 시도하고 소유경로 audit가 차단함. 정확한 호출 path/출력/argv/child receipt/JUnit/원본SHA 보존. 오류를 bridge가 잡고 lifespan이 계속되어도 명시 경로 assertion이 실패하므로 silent success를 통과시키지 않는다.
- `candidate-v1/`: 새 lifecycle3(absolute configured, relative configured, legacydefault) + 기존 TestHookEventBusBridge2 = **5 passed / 0 failed/skipped**. argv/cwd/env/실행 sourceSHA, stdout/stderr/exit/JUnit 보존. static-v1 네 검사(Ruff/format/BasedPyright/in-memory compile) owned2 모두 exit0, 소스SHA 동일.
- absolute/relative 두 사례는 실제 SQLite agency.db가 configured root 아래 존재하고 실제 hook callback이 agency_events에 observation1을 기록함을 SQL로 확인한다. project_id=configured.resolve(), trajectory_id=hooks도 확인. bridge/controller/store 동작 결과를 mock하지 않는다. Store init wrapper는 전달 경로를 기록한 뒤 실제 생성자를 호출한다.
- default 사례는 실제 PathConfig 기본값이 PROJECT_ROOT 및 기존 source workspace와 같음을 확인하고, 명시env 없는 lifespan bridge 인자를 spy로 검증한다. 사용자의 기본위치에 DB를 만들지 않는다. 이 사례를 actual default SQLite 검증이라 주장하지 않는다.
- 모든 사례에서 RAG/IDE 인자가 기존 source workspace 그대로임을 확인하고 RAG thread join, hook/audit/IDE shutdown flags를 검증했다. 실물 RAG/IDE/routes/bootstrap와 부가 shutdown 서비스는 격리 stub이다. server 모듈/async lifespan/PathConfig/bridge/controller/store는 actual source. 네 모듈의 실제 path/SHA는 각 receipt.modules에 기록.
- 모든 child audit denied_mutations/socket_attempts/forbidden_imports=[]; socket connect/bind/subprocess spawn 및 NN backend imports 차단. HOME 변경 없음. Listener/HTTP/실제NN/model download 없음. config validation은 모델이 없는 owned absent-config fixture 경고를 낼 수 있으며 실제 제품 startup전체 성공 판정이 아니다.
- `scenario-evidence.json` exact testname→child invocation/receipt 연결. `ownership-after.json`: 비소유 src577 SHA unchanged. 단일 제품 줄 역치환으로 originalserver 전체 bytes 일치 확인. source2는 candidate-source/, originalserver는 preimage/.
- `task-only.patch` SHA `d45ef29ddbfaf65decdba4deffd7141582b425f8e6fa3113bf9d5c52206b60be`; preimage+patch reconstruction2/2 SHA일치. 최종 serverSHA `6b5945cefe9d39294a1a3372bf812e9e5d28bd6e190f59846a6b4ce81a7655a7`, testSHA `fe62bdd200d1b493104e6ab196b906e448fe4bbb066aef55340b51f546e4e0ca`.

## 다음 단계
독립 검토 후 root가 dirty ROOT server에 같은 한 줄만 적용한다. 기존 API runtime/health 및 보존구성은 다음 실제 isolated startup에서 확인한다. agency/event_bus 재설계·새 실행자·기존 저장소 migration·RAG/IDE 경로 이동은 포함하지 않는다. 이전 봉인 GBrain/root packet은 수정하지 않았다.
