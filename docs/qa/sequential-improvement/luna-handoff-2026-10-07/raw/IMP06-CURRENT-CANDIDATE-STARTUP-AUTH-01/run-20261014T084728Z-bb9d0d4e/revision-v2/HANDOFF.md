# Startup/auth ownership repair — PREPARED_OFFLINE_OWNERSHIP_REPAIRED

독립 검수 PENDING / NOGO 유지 / 실제 실행 NOT_RUN. 이 revision-v2만 새 후보입니다. 상위 run의 차단 판정·소스·계획·24개 결과 및116개 manifest 항목은 변경하지 않았습니다. 제품/설정/Git 파일 수정 없음.

## 최소 수정
`supervisor.py`의 Popen 반환 직후 `own_spawned`가 child를 인수합니다. launch.json 쓰기와 모든 관찰은 ownership try 안이며, finally에서 정리→assessment→terminal 기록을 수행합니다. 신규 lifecycle.py는 실제 subprocess와 순수 FakeProcess가 동일하게 사용하는 경계입니다. 정상 lifespan/auth/env/request 경로는 유지했습니다.

stop.requested 쓰기 실패는 바로 소유 PGID TERM으로 전환하고 wait/reap 합니다. 최초 정리 시각에 `min(total_deadline, cleanup_start+15)` 한 번만 고정하며 graceful10·kill 이후 wait·group 정리·최종 nonblocking reap이 같은 마감시각을 사용합니다. killpg ProcessLookup 경쟁은 계수하고 실제 wait의 exit를 보존합니다. 종료코드를0으로 바꾸지 않습니다.

관찰 또는 assessment 기록 실패에도 terminal 생성이 finally에 있습니다. result.json 쓰기가 실패하면 NO_SUCCESS로 낮추고 run 바깥이 아닌 이 revision의 outer-terminal.json과 stderr를 각각 시도합니다. 이들까지 실패해도 actor는 NO_SUCCESS/비성공 종료이며 메모리 상태만 남았음을 숨기지 않습니다. 외부 supervisor stdout/stderr/exit 영수증은 여전히 root가 별도로 보존해야 합니다. 파일 결과와 외부 exit가 충돌하면 PASS로 해석하지 않습니다.

## 실제 실행 없는 근거
verification-v1: 32 PASS (기존 pure24+새8), Ruff/format/Basedpyright/메모리 compile 모두 exit0. exact argv/cwd/env/sourceSHA·JUnit·stdout·stderr 및 offline-boundary.json이 근거이며 process/socket 시도0, 제품/Uvicorn/Chroma import0입니다.

신규8개는 실제 `own_spawned`와 `cleanup_owned`를 FakeProcess/FakeOperations로 호출합니다. verification-v1/captures의 signal/wait/clock/실제 fake exit/reaped/group/resultwrite/emergency 값을 확인할 수 있습니다. launch receipt 쓰기실패→정리·수거, stop 쓰기실패→TERM·-15 수거, kill 직전 소멸→-9/경쟁1 보존, unreaped timeout+result 쓰기실패→15초/None/false 및 outer channel, assessment 쓰기실패, emergency 쓰기실패, 전체90초 소진(88→90·추가15초 없음), 정상0수거를 검증했습니다. 캡처는 순수 fake이며 실제 OS 종료 관측이 아닙니다.

source-binding.json은 새9개 준비 소스와 변경된6개 runtime package 승인 해시를 고정합니다. plan.json의 제품 source 계획은 이전과 동일한7802aa1b/0.1.0이지만 새 runtime 파일 구성이므로 이전 승인은 사용할 수 없습니다. approval-required.json은 승인 파일이 아닙니다. 우선순위5 후 소스/HEAD가 바뀌면 새 계획 바인딩/검토가 필요합니다.

task-only.patch는 이전 준비 소스 기준 supervisor 변경+신규 lifecycle/test 두 파일 총3개이며 reconstruction.json의 바이트가 일치합니다. 이전 manifest 보존, root staged SHA 불변은 preservation.json을 보세요. 네이티브 확장 OS network 전체 관측은 주장하지 않으며 실제 startup/auth/health/shutdown은 후속 GO 전까지 미실행입니다.
