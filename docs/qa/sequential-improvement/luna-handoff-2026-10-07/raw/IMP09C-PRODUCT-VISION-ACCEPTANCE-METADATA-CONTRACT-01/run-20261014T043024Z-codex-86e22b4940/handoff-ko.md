# Acceptance snapshot 메타데이터 수정 인계

상태: COMPLETE_OFFLINE / 독립 검수 PENDING.

`run_harness.py`의 실제 `supervise_once` writer에서 `format: "omitted"` 한 줄만 `json.loads(SCHEMA_JSON)`으로 수정했습니다. 부모 실관측·제품 소스는 수정하지 않았습니다.

전용 회귀는 수정 전 1 실패, 수정 후 1 통과입니다. 실제 supervisor/immutable writer/journal과 기존 메모리 adapter를 사용했습니다. 독립적으로 선언한 전체 schema를 저장값·request·planned acceptance·profile·schema 파일과 대조했습니다. 두 예약과 두 모의 wire에서 이미 동일한 acceptance bytes가 존재했고, frozen→reserved→dispatched 순서를 확인했습니다. 덮어쓰기 거부와 부모 acceptance 불변도 확인했습니다.

실행 명령·소스 SHA·원문·JUnit은 `offline-checks/red/receipt.json` 및 `offline-checks/green/receipt.json`에 있습니다. 최종 Ruff·format·basedpyright 오류 수준·메모리 compile 모두 exit 0입니다. pytest asyncio_mode 경고 1건을 보존했습니다.

각 실행의 모의 product/provider는 1/1, 두 실행 합계는 2/2입니다. 실제 HTTP/socket/worker/Uvicorn/Ollama/추론은 0입니다. 메모리 adapter가 OS cleanup 사실을 제공하지 않아 원본 supervisor verdict는 INCONCLUSIVE_CLEANUP_NOT_CONFIRMED입니다. 실제 cleanup 검증 결과로 해석하지 않습니다.

부모 봉인 144파일, 보호 28파일, staged 97개와 staged diff SHA가 모두 유지되었습니다. `task-only.patch`는 2파일이며 시작 preimage에서 재구성한 최종 바이트가 일치합니다. 상세 수치와 SHA는 `result.json`에 있습니다. 부모 요청·실행 바인딩·권한·runtime-state·실행 영수증은 새 실행으로 복사하지 않았습니다. 테스트 임시 폴더의 request/binding은 전용 모의 사례에서 새로 생성한 것입니다.

후속: 저장 증거와 한 줄 patch 독립 검수. 재실행 및 live 승인은 발급하지 않았습니다. 전체 IMP-09 PARTIAL / ledger NOT_RECOVERED를 유지합니다.
