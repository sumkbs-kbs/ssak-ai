# 글로벌 작업 이벤트 커서와 종료 상태 검수

판정: DONE_SCOPED. 구현 커밋 `c12830506c50d887606aebfd5d54351133101463`. 주 에이전트 검수이며 독립 검수는 NOT_RUN입니다.

실제 브라우저 revision-v3의 작업 이벤트는 글로벌 SQLite sequence 24..35였지만 UI는 작업별 sequence가 1부터 연속이어야 한다고 가정했습니다. 서버는 이미 failed로 저장했는데 화면은 replay incomplete와 running을 유지했습니다. 저장된 실패 원문을 재실행하지 않고 보존했습니다.

API 이벤트·재생 응답·SSE 종료 및 WebSocket 종료에 `sequence_scope=global`을 명시하고 UI가 그 선언을 따르도록 수정했습니다. task 범위 또는 선언이 없는 기존 계약은 연속 번호 검사를 유지합니다. 글로벌 커서는 다른 작업의 번호 때문에 생긴 수치상 공백을 누락으로 취급하지 않습니다. 미수신 종료 커서는 재생을 요구하며, 동일 번호의 상충 payload와 다른 task ID는 계속 거부합니다. 캐시는 번호 범위를 보존하고 기존 캐시는 task 범위로 읽습니다. terminal stream.end 뒤 목록 GET을 한 번 갱신하며 작업을 재제출하지 않습니다.

수정 전 집중 회귀 5 통과/3 실패. 최종 clean/root 화면 회귀 각각 60 통과/실패 0, Python 작업 API/실제 SQLite 계약 각각 24 통과/실패 0. tsc, Ruff, format, production basedpyright 모두 종료 코드 0입니다. 소유 TypeScript 7개 파일의 ESLint도 경고 0입니다. 기존 staged 97개 경로와 독립 소스 1,837개를 보존했습니다.

revision-v4의 실제 PIN UI 인증 후 작업 POST 1회(202), 통제된 제공자 HTTP 503 1회, failed/스트림 완료 UI 및 desktop/mobile 넘침 없음, 정상 프로세스 종료를 확인했습니다. v4의 글로벌 값은 1..3이며 24/27/35 재생은 집중 회귀에서 확인했습니다. 실제 브라우저에 수치 공백이 있었던 v3 원문은 실패 근거입니다. 제공자는 fixture이고 신경망 호출은 0입니다.

글로벌 sequence만으로 중간 이벤트가 누락됐는지 다른 task의 번호인지를 구분할 수는 없습니다. 본 변경은 선언된 서버 커서 의미를 보존하며 새로운 task별 연번이나 역사 데이터 재번호 매김을 도입하지 않습니다. 일반 모델 품질과 전체 릴리스 게이트 통과를 뜻하지 않습니다.
