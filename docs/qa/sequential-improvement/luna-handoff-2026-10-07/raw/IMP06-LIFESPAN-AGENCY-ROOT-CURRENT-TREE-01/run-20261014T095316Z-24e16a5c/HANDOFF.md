# IMP06-LIFESPAN-AGENCY-ROOT-CURRENT-TREE-01 — READY_SCOPED_ROOT_COMPOSITION

승인 clean 한 줄 `bridge_to_hook_event_bus(project_root=str(config.paths.project_root))`만 dirty ROOT api/server.py에 이식. 승인 test_lifespan_agency_root_contract.py는 byte동일 복사. ROOT 제품 다른 변경 및 기존 RAG/IDE 코드 untouched. **ROOT preimage는 이미 project_root=str(config.paths.project_root.resolve())였다.** 따라서 이식은 clean publication과 호출 표기를 일치시키는 것이며 ROOT의 agency 저장 경로를 새로 활성화/변경한 것이라고 주장하지 않는다.

## 실행 결과와 fixture 경계
- `root-candidate/`: 승인 테스트를 ROOT에 직접 실행한 최초 결과 **3FAIL/2PASS** 보존. ROOT의 미게시 RAG startup이 VectorStore/project_rag_vector_dir를 추가로 실행하고 RAG/IDE에도 configured.resolve()를 전달하는데, clean fixture는 indexer만 stub하고 source workspace를 기대했다. native-import/path guard 및 인자 assertion이 실패. agency target은 configured path에 도달했다. 이 실패를 새 제품 회귀라고 단정하지 않는다.
- 승인된 evidence-local `root_fixture_overlay.py` v1을 사용한 `root-candidate-v2/`: **5 PASS**(새 lifespan3 + 기존 bridge2). ROOT 구성의 인접 subsystem fixture만 적응했다. **수정 없는 tracked test가 ROOT에서 직접 통과했다거나 전체 ROOT suite가 green이라고 주장하지 않는다.** clean 표준 테스트는 별도 clean publication 검증 대상이다.
- Overlay: Indexer가 ROOT의 vector_store keyword를 받게 함, RAG VectorStore context-manager 및 project_rag_vector_dir를 비쓰기 double로 격리, RAG/IDE 기대 인자를 이미 존재하던 ROOT configured.resolve()로 맞춤. 실제 server/async lifespan/PathConfig/event_bus/PersistentAgencyController/SQLite Store 및 agency path/persisted hook event assertions는 변경 없음. `overlay-version.json`/`fixture-overlay.json`/실제 child probe/argv/SHA에 바인딩.
- 원래 인접 stubs는 API routes/auth routes, bootstrap_cognitive_active, readiness helper/session exception, hook subscription transport, audit/panel tracker, RAG indexer, IDE, bundle-search/browser shutdown이다. Hook callback을 real bridge가 구독하고 real agency controller/store가 실제 SQLite에 기록하는 대상 경계는 real source다. 부가 network/NN/native RAG 실행은 수행하지 않는다.
- absolute/relative cases 실제 configured agency.db 존재, agency_events observation1 및 configured project_id/hooks trajectory 확인. default case는 기본 PROJECT_ROOT/bridge 인자 spy만 확인하여 기본 사용자 위치 DB를 만들지 않는다. actual async lifespan 종료/인접 shutdown/RAG join 검사 유지.
- 각 child denied_mutations/socket_attempts/forbidden_imports=[]; 실제 imports는 ROOT 경로/SHA. 소스와 child argv/JUnit/raw 출력은 root-candidate-v2에 있으며 scenario-evidence.json이 exact nodeid를 연결한다. Listener/HTTP/NN/download 없음.

## 정적·보존 증거
- static-v1 Ruff/format/BasedPyright/in-memory compile: owned2 네 검사 exit0, 최종ROOT sourceSHA 일치.
- server에 승인된 한 줄을 역치환하면 적용 전 ROOT server 전체 byte와 동일(`ownership-after.json`, root-one-line.diff). 다른 RAG/IDE 구현 편집 없음.
- 적용 전 Python5186 SHA snapshot, 독립 비소유 Python5184 unchanged. 기존 IMP03 baseline-overlay의 server.py symlink 하나는 ROOT source를 가리키므로 논리 dereference SHA 변화만 alias로 명시. symlink/이전 패킷 직접 편집 없음.
- staged97 mode/blob/stage entry 및 full index-entry hash 동일. HEAD before/after를 별도 기록해 concurrent clean commit/ROOT CAS와 분리. Gitstage/commit/push 없음.
- ROOT serverSHA `c94b3be073daa11d758df1a5dac4a30b26b5794679b72defe35bb409109c7500`; 승인 testSHA `fe62bdd200d1b493104e6ab196b906e448fe4bbb066aef55340b51f546e4e0ca`. root-preimage-only.patch SHA `caf776318cecb40abb061f735b21955863de75b81efeb6c7111a661d98dbcbc1`, exact ROOT preimages reconstruction2/2. candidate-source/에 최종2개, approved-reference.json에 clean 승인 packet 연결.

다음 실제 isolated listener/health 판정은 root의 별도 단계다. 이번 READY는 증거용 ROOT 구성 fixture 범위이며 unmodified ROOT full suite 결과가 아니다.
