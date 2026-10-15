# CR03 중첩 Seatbelt 환경 진단

판정: `CONFIRMED_SCOPED_OUTER_SEATBELT_INTERFERENCE`. 제품 소스 수정은 필요하다고 입증되지 않았다. 인위적으로 추가한 외부 provider Seatbelt 정책이 제품 자체의 필수 Seatbelt 적용을 막는 현상을 최소 사례에서 확인했다.

## 실행과 관측

WT2의 기존 `tests/test_cr03_sandbox_read_boundary.py::TestWorkspaceStillRuns::test_python_runs_inside_workspace` 하나만 같은 인터프리터와 소스로 두 번 실행했다. 테스트 자식 코드는 `print('PYTHON_OK')`뿐이다. 제품 `run_sandboxed_argv`의 enabled=True, network=none, require_sandbox=True 경로는 모두 유지했다.

- outer provider profile 있음: pytest 1 failed, exit 1. 제품 자식 sandbox-exec return_code=71, stderr=`sandbox-exec: sandbox_apply: Operation not permitted`. 증거: `with-artificial-outer-profile/stdout.txt`, `junit.xml`, `receipt.json`, `audit.json`.
- 제품 sandbox만 사용: pytest 1 passed, exit 0. 기존 테스트의 sandboxed=True, success=True, PYTHON_OK 단언을 모두 통과했다. 증거: `product-sandbox-only/stdout.txt`, `junit.xml`, `receipt.json`, `audit.json`.
- 각 실행에 제품 sandbox-exec 호출 1회, 진단 pytest 프로세스의 socket.connect/bind 감사 이벤트 0회. 감사 훅은 시도가 있으면 차단한다. 별도 HTTP/Uvicorn/Ollama/모델 실행은 하지 않았다. 자식 Python의 네트워크 권한은 제품 sandbox가 차단한다.
- 부모 pytest는 plugin autoload를 끈 명시적 집중 진단이다. 각 실행에 기존 asyncio_mode unknown 경고 1건이 있어 원문을 보존했다.
- 실제 Python은 WT2 `.venv/bin/python`이고 심볼릭 링크 대상은 `/Users/mr.k/miniforge3/bin/python3.13`이다. runtime prefix 및 제품 allow-list는 두 `runtime.json`에 있다. formal gate의 별도 uv 임시 인터프리터까지 이 결과로 검증한 것은 아니다.

## 기존 실패와 연결

기존 중단된 formal Python report에는 CR03 26개, CR04 8개 FAILED 진행 줄이 있다. 해당 report에는 개별 traceback이 없으므로 모두 같은 원인이라고 확정하지 않는다. `formal-failure-extract.json`에 당시 report SHA 및 해당 줄을 보존한다.

CR04는 소스상 `api/routes/agent_tools.py::run_shell` → `SandboxRunner.execute` → `_execute_macos_sandbox`의 같은 필수 backend를 사용한다. require_sandbox=True이며 raw fallback은 없다. 따라서 8건도 같은 외부 정책 간섭과 일관되지만, 이번에는 CR04를 재실행하지 않았다.

외부 정책에 따라 제품의 ps 기반 프로세스 budget도 64/760으로 달랐다. 실패 메시지는 Python 시작이나 ulimit 실패가 아니라 sandbox_apply이므로 이는 부수적인 환경 차이로 기록한다.

## 안전한 후속 방향

현재 formal 실패 기록을 유지하고 Python gate를 PASS로 승격하지 않는다. 제품 sandbox를 끄거나 sandbox_apply 실패를 우회하거나 CR03/04를 제외하는 수정은 부적절하다.

전체 formal run은 중첩 Seatbelt 없이 제품의 Seatbelt를 실제 적용할 수 있는 macOS 실행 환경이 필요하다. 가장 안전한 대안은 사용자 모델 저장소·실제 provider 프로세스·사용자 자격증명이 없는 별도 macOS 검증 계정 또는 VM에서 동일 후보·frozen dependencies·23개 원래 manifest를 실행하는 것이다. 거기에서도 저장소/인증 데이터는 실행별 격리하고 provider endpoint를 소유 비서비스 주소로 고정한다. 새 환경의 준비 및 네트워크/모델 부재 확인이 먼저이며, 이 진단은 현재 호스트에서 외부 guard 없이 전체 suite를 실행해도 안전하다는 증거가 아니다.

새 안전 경계 구현, provider profile 수정, 제품 변경, 테스트 skip, commit/push는 수행하지 않았다. 두 작업 트리와 기존 formal 증거는 읽기 전용으로 다뤘고 지정 증거 폴더에만 결과를 기록했다.
