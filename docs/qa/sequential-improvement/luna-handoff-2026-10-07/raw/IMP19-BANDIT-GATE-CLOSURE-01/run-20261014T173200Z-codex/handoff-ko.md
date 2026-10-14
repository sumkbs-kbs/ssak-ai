# Bandit 게이트 수정 인계

- 상태: 수정·범위 회귀 통과, 독립 검수 대기. 전체 정식 게이트 및 출시 승인은 미완료.
- 기존 실패: d868 후보의 Bandit Medium 32 / High 1. 변경 대상 6개 파일은 b91까지 같은 바이트였음을 확인했다.
- 수정: 마이그레이션·브라우저 기억의 테이블 식별자와 SQL을 고정했다. 위키의 목록·쌍·방향·분류 필터는 정적 SQL의 바인딩 값으로 전달한다. 브라우저 프레임 SHA1은 기존 참조값을 유지하면서 usedforsecurity=False로 식별 목적을 명시했다.
- 실제 검사: 공식 Bandit 명령 exit 0, Medium 0 / High 0 / 기존 Low 336. Ruff lint/format 및 Basedpyright 오류 검사 exit 0. SQLite 마이그레이션·위키·기억 및 실제 로컬 Chromium 관찰/행동 회귀 141개 통과, Starlette deprecation 경고 1건.
- 새 검사 억제·예외는 추가하지 않았다. 기존 nosec 21개는 기존 상태다. SQLite json_each를 사용하는 환경에서 위키 회귀를 수행했다.
- 근거: checks-attempt-1/checks.json, source-binding.json, junit.xml, 각 검사 stdout/stderr. 실행용 PIN과 runtime 저장소는 공개 manifest에서 제외한다.
- 제한: 의존성 감사와 전체 Python·성능·대시보드 게이트 및 같은 후보의 8시간 soak는 별도 미완료다. 기존 실패 기록은 그대로 보존한다.
