# 샌드박스 pytest 경계 수리

상태: COMPLETE_SCOPED / 독립 검수 대기. 커밋하지 않았습니다.

## 원인과 수정

저장소 안의 소유 TMPDIR에서 실행한 자식 pytest가 상위 저장소 pyproject.toml을 자동 탐색하여 seatbelt의 읽기 거부로 수집 전에 종료했습니다. 기존 7개 실패를 red/contract.stdout.txt와 red/junit.xml에 재현했습니다(7 실패, 6 통과).

공유 run_sandboxed_argv에서 pytest 호출에만 작업 디렉터리 rootdir/confcutdir 기본값을 지정합니다. 작업 디렉터리에 pytest가 인식하는 설정 파일명이 하나도 없을 때만 빈 설정을 명시합니다. 기존 로컬 설정, 명시적 -c/rootdir/confcutdir, PYTEST_ADDOPTS 및 -- 구분자는 보존합니다. 설정 내용은 권한이 높은 부모에서 읽지 않습니다. seatbelt 정책·허용 경로는 수정하지 않았습니다. 일반 비-pytest 실행도 변경하지 않았습니다.

alias 테스트는 TMPDIR가 항상 /private/var/folders라는 잘못된 가정을 제거하고, 실제 /tmp → /private/tmp의 동일 파일임을 확인한 후 비정규 경로 읽기가 PermissionError로 거부되는지 검증합니다.

## 검증

- run_checks.py red: 기존 13개 중 7 실패 / 6 통과. 실패 원문과 당시 두 파일 사본 보존.
- run_checks.py green-1: 최초 수정 후보에서 같은 13개 통과. 이후 설정 처리 구현을 좁힌 최종 후보의 근거로 대신하지 않음.
- run_checks.py green-2: 최종 16개 통과. 기존 13개와 로컬/명시적/환경변수 pytest 설정의 strict-markers 실제 적용 3개. 명령·종료 코드·source SHA는 green-2/checks.json 및 source-binding.json, JUnit에 연결.
- run_regression.py boundaries: 외부 sentinel, 형제/alias/자식 경계, 외부 쓰기 거부, 부모 비밀 환경변수, fail-closed 단위 계약을 추가 검증. 정확한 건수는 boundaries/junit.xml. 기존 ancestor_allows_are_literal_only는 특정 /private/var/folders 배치 전용이므로 이 선택에서는 deselect; 완료로 집계하지 않음.
- Ruff lint/format, sandbox.py basedpyright --level error, 소유 두 파일 diff --check 모두 exit 0 (boundaries/checks.json 및 원문).
- task-only.patch를 red/source preimage에 적용해 현재 두 파일과 byte-identical 확인: patch-reconstruction.json.

## 범위와 한계

실제 macOS seatbelt와 자식 pytest를 실행했습니다. 제품 서버·Uvicorn·Ollama·실모델 추론은 실행하지 않았습니다. 기존 agent 테스트의 모델은 fake입니다. 계측 하네스는 각 실행마다 모델 endpoint 보호용 loopback socket 한 개를 bind하고 listen/connect하지 않았습니다(4회 실행); 전체 프로세스 syscall 계수는 계측하지 않았으므로 0이라고 주장하지 않습니다. runtime 하위 auth/캐시/임시 데이터는 공개 manifest에서 제외합니다.

로컬 설정 후보 파일이 존재하면 pytest의 원래 선택 의미를 그대로 유지합니다. 해당 파일에 실제 pytest 설정이 없어 상위 설정 탐색이 계속되는 별도 프로젝트 구조, 하위 디렉터리별 설정, pytest.main() 간접 호출은 이번 수정의 검증 범위 밖입니다. 명시적 외부 설정 권한은 확대하지 않았습니다. 전체 프로젝트 테스트/전체 GA 게이트 통과로 해석하지 않습니다.

제품 변경은 sandbox.py 하나, 테스트 변경은 test_cr03_sandbox_read_boundary.py 하나입니다. 다른 작업자의 변경은 수정하지 않았습니다.
