# IMP06-STARTUP-STORAGE-ROOT-CURRENT-TREE-01 — READY

승인 clean 패킷 `892947e96c830b8c4fe11821d8c039416e871d1b6eaf613f5388e31f1685c31e`의 경로 선택만 ROOT `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`에 이식. 소유 제품3+승인 테스트2. ROOT GBrain 전체 파일을 clean 버전으로 덮어쓰지 않았다. root preimage SHA96a8499c55ad0c2c5ef8f70b3cf8afa1f2ca063a7f7508b6cf1a9cd29b7d1a47에 생성자 env 경로2줄 및 해당 docstring만 적용했다. 다른 두 생성자 원본은 승인 preimage와 byte동일 검증 후 승인된 최소 변경만 적용했다. 테스트2개는 승인된 byte그대로 복사.

## ROOT 구성 검증
- `root-gbrain/`: 새 ROOT composition **7 passed**. `root-other-stores/`: 새 ROOT composition **12 passed**. 각각 argv/cwd/env/source SHA/JUnit/stdout/stderr/exit 보존. 이전 clean 결과의 단순 재사용이 아니라 ROOT의 다른 GBrain lifecycle/import 구성에 대한 새 실행이다. 19개 새 기능이라고 주장하지 않는다.
- `scenario-evidence.json`: 모든 exact nodeid와 child argv/probe SHA/receipt 연결. child source_path는 ROOT, SHA는 실제 최종 ROOT 파일. GBrain native_import는 실제 Chroma1.5.9의 owned persistent path, empty collection0 및 정상 close/프로세스 exit0. 다른 경로 사례/메모리·context roundtrip도 모두 정상.
- 모든 child denied_mutations/socket_attempts/embedding 또는 forbidden backend import 목록0, HOME 환경변수 불변. NN/다운로드/HTTP/listener 실행 없음. 기본경로 시험은 owned mock-home 반환만 사용한다. Python audit와 native factory path guard 범위를 넘는 OS 전체 syscall 추적을 주장하지 않는다.
- `static-v1/{ruff,format,basedpyright,compile}.json`와 로그: 소유5 전체 네 검사 exit0, BasedPyright0errors, 메모리 compile5. 테스트/정적 검사 source SHA와 최종 ROOT SHA 일치.
- `lifecycle-preservation.json`: 승인된 constructor/doc hunk를 역적용하면 ROOT GBrain preimage 전체 bytes와 일치. CHROMA_LIFECYCLE_LOCK import/init/close 사용 보존, SharedSystemClient/global cache clear는 여전히 없음. clean legacy lifecycle을 다시 도입하지 않았다.

## 보존·재구성
- `baseline.json`: 적용 직전 ROOT HEAD, Python5135 SHA, 기존 owned3 preimage SHA. `index-before.bin`/`staged-before.bin`: 기존 index-entry 및 staged97 snapshot. `ownership-after.json`은 종료 HEAD를 별도 기록하여 concurrent clean commit/ROOT CAS와 소스 검증을 구분한다.
- 기존 staged97 각 path의 mode/blob/stage entry 완전 동일. Git stage/commit/push 명령은 실행하지 않았다.
- 독립 비소유 Python5129 SHA 동일. 추가 3경로는 과거 IMP03 baseline-overlay의 **기존 symlink**로 이번 소유 ROOT 3파일을 직접 가리킨다. 해당 dereference SHA 변화는 `owned_source_symlink_aliases`에 before/after/target/samefile로 명시한다. 과거 패킷 파일을 직접 편집하거나 독립 source를 바꾼 것이 아니며, 이 live overlay를 불변 사본이라고 주장하지 않는다.
- `root-preimage-only.patch` SHA `bb30b19e4270740c633f5aadfb99f914160d94e090a326a2c54c0ccd959e89b7`; exact ROOT preimages+patch reconstruction5/5 SHA일치(`reconstruction.json`). `candidate-source/` 최종ROOT5 파일. `approved-source-reference.json`은 승인 clean 패킷/manifest/patch를 연결한다.

ROOT 최종 GBrain SHA `235e226d79c92d08c4b24e27ee418fb24f7d5f5c75e438299ef70a5e5c3bc4ec`. GlobalMemoryProvider/ContextShaper와 두 테스트 SHA는 승인 clean packet과 동일. 다음 startup은 AGK_GBRAIN_DIR/AGK_GLOBAL_MEMORY_DIR/AGK_CONTEXT_STORE_DIR을 owned 절대경로로 설정해야 한다. 실제 API startup/health 통과 판정은 root의 다음 단계다.
