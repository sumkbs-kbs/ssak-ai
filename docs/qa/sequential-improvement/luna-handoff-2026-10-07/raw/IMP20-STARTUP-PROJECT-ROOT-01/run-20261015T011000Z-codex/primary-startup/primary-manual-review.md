# 주세션 실제 기동 검수

주세션이 실제 `run_once.py` 두 실행을 직접 호출했다. 하위 QA 에이전트는 첫 스크립트와 실패 정리만 준비했으며 실제 HTTP를 실행하지 않았다.

| 범위 | 기대 | 실제 관측 | 판정·근거 |
|---|---|---|---|
| 첫 기동 | 설정된 작은 프로젝트를 RAG·기본 hook/audit에 적용 | RAG 1 chunk, 지정 경로의 hook 파일·audit DB 생성 | 해당 경로 동작 PASS; `result.json`, `server.stderr.txt` |
| 첫 health·회수 | QA 자체 5초 GET·10초 종료 제한 | curl 28, 강제 종료 -9 | FAIL 보존; `qa-correction.json`, `supplemental-manifest.json` |
| 별도 소유 CWD/HOME 기동 | 실제 lifespan·작은 프로젝트·기본 hook/audit | 지정 경로 초기화, RAG 1 chunk, 살아 있는 실제 파일 확인 | PASS; `attempt-02/server.stderr.txt`, `attempt-02/result.json` |
| cold health | 최초 초기화 포함 60초 내 단일 GET | 요청 1회 HTTP 200, JSON status=ok | PASS; `attempt-02/health.http.txt` |
| SIGTERM 정리 | hook/application shutdown, 회수·그룹 잔여 없음 | 모두 관측, 강제 kill 없음, 실제 종료 -15 | 설치 Uvicorn의 재전달 동작에 부합; `attempt-02/review-result.json` |
| 원본 판정 교정 | CLI SIGTERM 종료를 0으로 오인하지 않음 | 원본 harness FAIL 유지, source-bound Uvicorn `capture_signals`가 graceful cleanup 후 signal.raise_signal 호출 | 별도 저장 증거 검수 PASS; `attempt-02/uvicorn-capture-signals.txt`, 추가 실행 0 |
| 소스·저장 상태 | 최종 제품 3파일 SHA 유지·audit DB 정상 | 전후 동일, 사후 read-only integrity=ok | PASS; 실행 binding 및 review-result |

두 시나리오의 HTTP는 합계 2회다. 두 번째 시나리오는 소유 프로젝트 CWD/HOME에서 실행했으며 첫 소스 checkout CWD의 5초 health 및 강제 종료 실패를 승격하지 않는다. ProjectRegistry의 기존 CWD 기반 기본 프로젝트 선택과 최초 health의 초기화 지연은 이번 lifespan 한 줄 수정으로 해결됐다고 주장하지 않는다. 해당 사실은 범위 한계로 남긴다. 실제 IDE listener, 모델 추론의 전역 호출 계수, 전체 23개 게이트·8시간 soak·출시 승인은 이 검수 대상이 아니다.

이번 코드 검수 수락 범위는 lifespan이 config.paths.project_root를 RAG·IDE·기본 hook/audit에 전달하고, 미지정 기본값과 명시 hook override를 유지하는 변경이다. 해당 경계의 6개 cold 사례와 인접 회귀 35개, 정적 검사, source-bound 실제 기동 관측을 함께 검토한다. Doctor fixture는 제품 변경이 아니라 외부 catalog 순서 의존 제거이며 원본 테스트가 sort_keys=False 환경에서 통과한 별도 증거도 포함한다.
