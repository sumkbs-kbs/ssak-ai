# 경로 및 Git API 테스트 전제 교정

상태: COMPLETE_SCOPED / 독립 검수 PENDING. 후보 시작 HEAD f3a42e6f08ecdc112d8e651862fe99b2b02e2afe. 커밋하지 않았습니다. 요청에 5건이라고 쓰여 있었으나 명시된 selector는 4건이며 그 4건을 모두 재현했습니다.

## 확인한 원인

SourcePlan child_environment는 실행 소유 runtime을 AGK_ALLOWED_ROOTS에 등록합니다. pytest tmp_path가 그 아래에 있어, 테스트의 workspace 형제 outside도 명시적 허용 경로였습니다. 세 거부 테스트는 테스트별 허용 목록을 소유 workspace로 고정하고 실제 allowed_roots() 전체에 대해 outside가 포함되지 않음을 선행 검증하도록 교정했습니다. resolver나 정책을 mock하지 않았고 제품 권한을 확대하지 않았습니다. 명시적 allowlist의 형제 경로를 받아들이는 별도 양성 계약도 추가했습니다.

Git 실패 매핑 테스트는 '커밋 없는 저장소'라고 적었지만 실제로 저장소를 초기화하지 않아, 부모 ROOT 저장소를 Git이 발견하고 show HEAD에 성공했습니다. fixture에 실제 git init을 수행해 고유 빈 저장소를 만든 뒤 기존 400 판정을 검증합니다.

## 증거

- red/checks.json 및 red/junit.xml: 명시된 4개 모두 실패. Git/path 예외가 발생하지 않은 원문 보존.
- green/checks.json 및 green/junit.xml: 같은 4개 모두 통과.
- tests/test_git_api_boundary.py 거부 사례: 실제 경로 검증 후 HTTP 403, 감싼 subprocess.run 호출 수 정확히 0. stub 응답을 만들지 않았습니다.
- tests/test_git_api_endpoints.py 빈 저장소 사례: fixture git init 1회 이후 실제 show HEAD subprocess.run 정확히 1회, HTTP 400. 이 수치는 fixture 초기화와 구분합니다.
- regression/checks.json 및 regression/junit.xml: 경로 전체 5개, Git 상대/파일 경계 2개, helper 6개 = 13 통과. 기존 정상 descendant/상대 경로, 명시적 whitelist, 절대/symlink 거부, Git 실패/timeout/실행파일 부재 계약 포함. 앞의 green 4건과 중복 항목이 있으므로 17개 고유 테스트라고 집계하지 않습니다.
- Ruff lint, format, git diff --check 모두 exit 0. 초기 import 순서 Ruff 자동 정리 1건 후 최종 검사 통과.
- Starlette/httpx 및 AnyIO portal deprecation 경고 2건 보존. 기존 ToolInvocation generic type 인자 누락 LSP 진단은 이전 파일에도 있는 코드이며 수정하거나 숨기지 않았습니다. 전체 타입검사 통과를 주장하지 않습니다.
- task-only.patch: 테스트 3개만 변경. red/source에서 패치 적용 후 현재 파일과 바이트 일치. protected-source-check.json: 제품 path_security.py 및 git_api.py 시작 사본과 동일.

SourcePlan의 전용 auth/storage 및 닫힌 provider endpoint를 사용했습니다. 세 driver 실행에서 loopback bind-only socket 각 1개, listen/connect 없음. 실제 제품 HTTP/Ollama/추론은 이 선택자에 포함되지 않았습니다. 전체 syscall 계수는 계측하지 않았습니다. runtime 하위 임시 auth/캐시는 공개 manifest에서 제외합니다. 기존 a613/1c 실행·읽기 경계 변경과 다른 작업자의 파일은 수정하지 않았습니다.
