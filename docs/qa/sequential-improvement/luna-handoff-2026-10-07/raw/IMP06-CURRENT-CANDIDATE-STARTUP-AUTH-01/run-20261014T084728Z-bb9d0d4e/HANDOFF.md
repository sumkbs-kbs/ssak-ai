# Priority 6: current-candidate startup/auth — PREPARED_OFFLINE_VERIFIED

준비만 완료했고 독립 검수 PENDING, live 승인 NOT_ISSUED, 실제 실행 NOT_RUN입니다. 현재 plan.json은 clean WT HEAD `7802aa1b3043d66a80f6f891c6cf3db039b393a0`, 앱 `0.1.0`, src 및 빌드 입력580개 SHA에 연결됩니다. 우선순위5의 소스/HEAD가 바뀌면 이 계획을 재사용하지 말고 새 바인딩과 검토가 필요합니다.

## 실행 경로
`startup_probe.supervisor` → 새 세션/PGID의 기존 venv Python(심볼릭 링크를 resolve하지 않음) → `startup_probe.entry` → 실제 server.app / Uvicorn lifespan=on. 제품 코드·인증·lifespan·dependency override는 바꾸지 않습니다. 런타임 파일과 cwd는 새 `live-once/` 아래입니다. `live-once`가 존재하면 mkdir 실패로 재실행을 거부합니다.

SourcePlan과 다섯 runtime package 파일의 SHA가 일치하는 별도 승인 JSON(scope STARTUP_AUTH_ONCE) 없이는 시작하지 않습니다. approval-required.json은 요구사항일 뿐 승인 파일이 아닙니다. 실제 실행은 root가 우선순위5와 독립 검토를 마친 뒤 별도로 결정합니다. 승인 후 명령 형태는 `PYTHONPATH=<이 run> <root>/.venv/bin/python -m startup_probe.supervisor <별도 승인 JSON>`이며, supervisor stdout/stderr/외부 exit도 별도 원문으로 캡처해야 합니다. 현재 이 명령은 실행하지 않았습니다.

실제 요청 예산은 startup marker 후 무인증 GET /api/system/access-mode 1회(401), 실제 임시 PIN POST /api/auth/login 1회(200 bearer), Bearer GET access-mode 1회(200 full_access), Bearer GET /v1/health 1회(200 ok/version)입니다. 각 요청의 시도 영수증을 전송 전에 쓰고 완료 응답의 bytes/SHA/status를 별도 기록합니다. 재시도·redirect·proxy 사용 없음. health는 실제 runtime을 구성하므로 별도 provider 호출0 조건을 확인합니다.

startup60초, 요청 전체 wall-clock5초씩, graceful10초, kill/reap5초, 전체90초입니다. 부모는 성공 후 owned stop file로 server.should_exit를 요청하여 실제 Uvicorn lifespan shutdown을 실행합니다. TERM을 그냥 보내면 설치 Uvicorn capture_signals가 재전파하여 -15로 끝날 수 있으므로 종료코드0을 가정/변조하지 않습니다. graceful 초과 시 새 소유 process group만 SIGKILL, OS wait와 group-empty를 기록합니다. 강제 종료·미수거·남은 group은 PASS가 아닙니다.

## 격리와 위험
화이트리스트 환경을 사용하며 HOME 원값만 필요시 보존하고 덮어쓰지 않습니다. API keys/proxies와 CODEX_HOME을 자식에 전달하지 않습니다. AGK_CONFIG_FILE의 owned `{}`, AGK_ENV_FILE의 빈 파일, PYTHON_DOTENV_DISABLED=1로 실제 dotenv 로딩을 차단합니다(설치 구현 SHA 고정). auth hash/secret, project/models/data/docs/vectors/logs/wiki/hooks/usage/vault/tmp/cache 모두 소유 경로입니다. PATH=/usr/bin:/bin으로 optional code-server 설치를 찾지 못하도록 제한합니다.

Python audit guard는 자식 outbound socket과 추가 bind/비소유 write/예상 밖 subprocess를 관측하고 실패시킵니다. 모델/embedding/download 호출도 profile guard에서 금지하며 scheduled-job tick만 계수합니다. 실제 lifespan의15초 job loop 및 source-derived RAG scan은 유지합니다. 후자는 WT source를 읽으며 no-VectorStore이므로 영구 manifest를 만들지 않는 현재 코드입니다. 네이티브 확장의 OS 네트워크까지 packet capture로 증명했다고 주장하지 않습니다.

PIN/JWT/login 원문/원래 stdout·stderr는 권한0700 auth-private/ 아래이며 publication 제외입니다. 공개 로그는 PIN/JWT를 지운 사본, 응답은 상태/bytes/SHA 영수증입니다. 임시 auth-file 존재/bytes/SHA도 기록합니다. 실제 startup 실패 원문과 optional failure 로그를 숨기지 않습니다.

## 오프라인 근거
final-verification/의 exact argv/cwd/env/source SHA, JUnit/stdout/stderr/exit: 24 PASS, Ruff/format/Basedpyright/메모리compile 네 검사 exit0. offline-boundary.json은 socket/process 시도0 및 antigravity_k/Uvicorn/Chroma 제품 모듈 import0입니다. 환경 격리, 소스·dotenv drift 거부, 승인 source/harness 연결, deadline cap/expiry, cleanup 미완료 거부, 잘못된 port/bind/outbound/write 거부를 순수 입력으로 확인했습니다. 이24개는 실제서버 검증을 대체하지 않습니다.

초기 준비 오류/중간 후보는 result.json과 precheck-*에 보존했습니다. root제품·설정·Git index를 수정하지 않았으며 staged SHA는 preparation-baseline과 동일합니다.
