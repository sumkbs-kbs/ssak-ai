# Python 의존성 최소 버전 수정 인계

- 상태: 범위 검증 완료, 독립 검수 대기. 전체 GA·soak·출시 승인은 미완료.
- 패키지 메타데이터와 resolver의 uv.lock으로 7개 패키지를 수정 버전 이상으로 고정했다. 버전은 checks-attempt-1/versions.stdout.txt에 있다. typing-extensions의 플랫폼별 추가 버전 외에 다른 패키지는 임의 갱신하지 않았다.
- 실제 출하 base+[rag] 감사: 감사 입력 합집합150개, 미해결24→0, 기존 chromadb1.5.9 예외5개 기록은 동일하다. 새 예외를 추가하지 않았다. uv lock --check 통과.
- 첫 회귀233개: 232통과/1실패, 경고35. 감사 출력 경로의 부모 환경 간섭으로 legacy 변수명 사례가 실패했다. 테스트 helper가 각 fixture 입력 전에 부모 기록 경로를 제거하도록 수정했고, 두 부모 변수명에서 기존 증거 sentinel 보존을 확인한다.
- 수정 후 해당 부트스트랩20개 통과·Ruff/format 통과. 변경되지 않은 나머지214개 통과 근거는 원본에 유지하며 처음 부트스트랩19개를 중복 합산하지 않는다. 전량 suite 한 번의 성공으로 부르지 않는다.
- 원본 감사 기록 JSON도 fixture 출력으로 바뀐 사실을 evidence-correction.md에 밝혔다. 감사 PASS와 입력150개는 보존된 실제 감사 stdout과 exit0 receipt로 판정한다. 정정 파생 자료는 audit-inputs-from-stdout.json이며 원본 JSON을 덮어쓰지 않는다.
- 기존 테스트의 수정하지 않은 dict 분산 타입 LSP 지적은 제한으로 기록한다. 타입 억제는 추가하지 않았다.
- 원본 실패·경고·검사 명령·소스 binding·수정 patch는 보존했다. OAuthlib4의 주요 변경과 근거 URL은 worklog.md에 있다. 프로젝트에서 해당 상류 provider API 사용은 발견하지 못했으며 인증·MCP OAuth 회귀를 포함했다.
- 다음: 독립 검수 후 기능 커밋 푸시, SBOM 갱신, 남은 전체 Python/성능/대시보드 게이트를 같은 새 후보에서 확인한다.
