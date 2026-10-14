# 실제 브라우저 실패 상태 검수

판정: DONE_SCOPED_PIN_CHAT_FAILURE_TASK_TERMINAL. 현재 ROOT 작업 트리를 실제 빌드해 사용했습니다. ROOT의 기존 별도 UI 수정 38개는 검증 사본에 포함됐으며 이 작업의 게시 변경에 포함하지 않았습니다. 별도 독립 시각 검수는 NOT_RUN입니다.

revision-v1: PIN 실패·성공 UI를 확인했으나 모델 검색이 통제된 경계를 벗어나 실패했습니다. backend 종료 0, browser driver 종료 1입니다. 전체 PASS로 승격하지 않습니다.

revision-v2: 모델 검색 fixture를 격리했으나 기본 에이전트의 미로드 선행 거부와 추가 경계 위반이 발생했습니다. backend 종료 0, driver 종료 1입니다. 원문을 보존합니다.

revision-v3: 모델 준비 수리 후 실제 chat POST 1회가 실제 통제 제공자 HTTP 503 1회로 이어졌습니다. 제품 SSE는 typed 오류를 전달했고 오류 UI 뒤 입력을 다시 사용할 수 있었습니다. 작업 POST 1회는 별도 기본 combo fixture 누락으로 실패했습니다. 서버의 failed와 이벤트 24..35를 받았지만 UI는 replay incomplete/sequence 0/running 상태로 남았습니다. backend/driver 종료는 각각 0이지만 guard 위반 1건이므로 전체 PASS는 아닙니다. 모바일 후 desktop으로 바꾼 일부 v3 캡처는 모바일 UA를 유지했고 viewport 증거로만 취급합니다.

revision-v4: 글로벌 커서/종료 목록 갱신 수리 뒤 새 번들을 생성했습니다. 역할의 기본 combo를 통제 모델 하나에 연결한 전용 설정으로 실제 PIN 잘못된 입력/정상 인증, Task Queue 제출 1회(202), 제공자 HTTP 503 1회, failed와 스트림 완료·재제출 없음·유효하지 않은 취소 동작 없음, 1280x900 및 460x900의 가로 넘침 없음을 관찰했습니다. backend 74600 종료 0/reap/group empty, driver 74700 종료 0/profile 제거, guard 위반 0/실제 신경망 0/fixture provider 종료를 확인했습니다. v4 desktop 전환은 emulation을 초기화해 desktop UA를 확인합니다. v4 sparse 글로벌 커서는 회귀 테스트가 보완합니다.

실제 Uvicorn/lifespan ON, 제품 API, PIN 인증, registry/manager/runtime 및 실제 loopback HTTP를 사용했습니다. 응답 interception으로 성공/실패를 만들지 않았고 provider만 명시적으로 통제한 HTTP fixture입니다. Persistent Agency의 Unavailable 상태는 캡처에 보이는 범위 밖 결과이며 완료로 판정하지 않습니다. 인증 재시작/전체 페이지/모델 의미 품질·실제 모델 취소를 보장하지 않습니다.

raw backend log와 PIN/JWT 및 native DB는 로컬에 보존합니다. 게시할 원문/캡처는 별도 publication manifest로 한정하고 로그의 exact-byte 원문 SHA와 게시용 사본 경로를 연결합니다. 과거 one-shot TOOL/native/live 검증은 반복하지 않았습니다.
