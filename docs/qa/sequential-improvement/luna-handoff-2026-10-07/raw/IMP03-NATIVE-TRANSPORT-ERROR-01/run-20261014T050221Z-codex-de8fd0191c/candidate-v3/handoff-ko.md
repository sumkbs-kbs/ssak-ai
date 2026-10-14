# Native transport 재시도 경계 보완 — candidate-v3

상태: COMPLETE_OFFLINE / 독립 검수 대기. 이 결과는 부모 폴더의 result.json 및 handoff-ko.md 중 direct retry0 입증 주장을 대체합니다. 이전 파일과 63개 통과 결과는 덮어쓰지 않았습니다.

## 발견과 수정

root가 별도로 수행한 controlled-wire 실관측에서 공통 safe_urlopen이 HTTP503을 자동 재시도했습니다. worker의 이전 terminal 모의가 공통 helper 전체를 대체하여 이 결함을 놓쳤습니다. 해당 실제 시도의 호출/중단 계수와 exit143은 root 소유 기록이며 이 문서에서 새로 측정했다고 주장하지 않습니다.

safe_urlopen에 keyword-only max_retries: int를 추가했습니다. 기본값2를 유지하며 native nonstream 호출만 max_retries=0을 전달합니다. URL 정책 검증은 그대로 거칩니다. 스트리밍/다른 호출자의 기본 동작은 변경하지 않았습니다.

## 증거 및 판정

- red-junit.xml: 공통 helper를 통과하는 새 3개 집중 사례에서 2 failed / 1 passed. route→real translator→real manager→real provider→real safe_urlopen→mock urllib.request.urlopen 경계의 503 시도는 3회였습니다. 기본 GET의 기존 두 재시도는 통과했습니다. red-test-source.py 및 source-preimage/에 당시 입력을 보존했습니다.
- final/junit.xml 및 focused.stdout: 75 passed / 1 failed. 실패는 기존 비동기 egress 테스트 하나에서 pytest_asyncio를 autoload 차단으로 불러오지 못한 하네스 설정 문제입니다. 그 원문은 그대로 보존했습니다.
- async-repair-junit.xml 및 async-repair-receipt.json: 동일 소스 SHA에서 해당 실패 1개만 -p pytest_asyncio.plugin으로 실행하여 1 passed, exit0. 성공한 75개와 정적 검사는 반복하지 않았습니다. 따라서 최종 수락 시나리오 76개가 모두 통과했으나 단일 실행 76 passed 기록이라고 표현하지 않습니다.
- final/checks.json: Ruff, format, basedpyright --level error, memory compile 모두 exit0. final/source/는 실제 실행 소스 6개입니다.
- final/socket-attempts.json 및 async-repair-receipt.json: 두 프로세스의 물리 socket 시도0. 실제 HTTP/Ollama/추론/서버 실행은 worker가 하지 않았습니다.
- 새 real helper 사례는 HTTP503 제품502, native 전송1회, sleep0, 실패usage1, assistant 저장0을 검증합니다. 별도 helper 사례는 원래 HTTPError 객체 identity 보존, 호출1/sleep0을 검증합니다. 기본 GET은 호출3/sleep[1,2]로 기존 재시도2 유지, private 목적지는 retry0이어도 sink 전에 차단됩니다. 이전 terminal mock도 max_retries=0 전달을 단언합니다.
- task-only.patch는 최초 dirty preimage 대비 6파일 전체 작업 패치입니다. retry-delta.patch는 이전63-pass 후보 대비 이번 추가3파일 패치입니다. patch-reconstruction.json에서 각각6/3파일 byte 일치를 확인했습니다.

## 제한

초기 통합검사 경고3건(asyncio 설정/mark, Starlette deprecation)과 비동기 하네스 실패는 보존했습니다. 기존63-pass 결과는 mocked helper 상위 오류 매핑 증거로만 유효하며 실제 재시도 없음의 증거로 사용할 수 없습니다. root controlled-wire-v2/의 실제 관측과 독립 검수는 별도입니다. 제품 상태 전체 완료나 전체 suite 통과를 주장하지 않습니다. commit/stage/push는 하지 않았습니다.
