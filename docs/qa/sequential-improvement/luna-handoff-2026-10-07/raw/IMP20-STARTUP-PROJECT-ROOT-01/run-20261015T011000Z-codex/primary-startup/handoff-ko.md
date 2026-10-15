# 실제 시작 표면 검수

판정은 **FAIL**이다. 주세션이 Uvicorn lifespan-on 시작 1회와 curl GET `/health` 1회를 실행했다. 이 하위 검수자는 저장된 원문과 바인딩을 대조했으며 시작·요청을 재실행하지 않았다.

설정된 작은 프로젝트에서 RAG 한 청크가 처리됐고, 기본 hook/audit 경로는 그 프로젝트의 `vault_data`를 사용했다. 실제 파일도 프로세스 실행 중 관측됐다. 세 변경 소스의 전후 SHA는 동일하다. 이 범위는 기존 경로 수정의 실제 시작 효과를 뒷받침한다.

그러나 `/health`는 ModelManager를 지연 초기화한 뒤 5초 안에 응답하지 않았다. curl은 5002 ms와 수신 0 bytes를 기록하고 exit 28로 끝났다. SIGTERM 후 10초 내 종료하지 못해 SIGKILL이 필요했고 실제 서버 exit는 -9였다. hook/application 정상 shutdown은 관측되지 않았다.

추가로 ModelManager 초기화 로그가 ChromaDB 경로를 후보 checkout의 `.antigravity/vault_data/.chroma`로, PermissionGate의 project_root를 후보 checkout으로 기록했다. 이는 수정된 시작 hook/audit 경로와 다른 하위 경로이며 소유 프로젝트 격리 범위를 벗어난 관측이다. 저장소 삭제나 제품 수정은 하지 않았다. 이 실행의 cwd는 후보 checkout이었고, 주세션은 프로젝트 registry의 기본 상대 저장소와 active project가 cwd를 사용하는 계약을 확인했다. 따라서 이 관측만으로 시작 루트 한 줄 수정의 제품 결함으로 판정하지 않는다.

5초 health 및 10초 graceful 한계는 이번 QA 하네스의 수락값이며 제품 SLO로 인용하지 않는다. 주세션이 배포에 맞춘 cwd·HOME 격리와 별도 cold-start 예산을 갖춘 attempt-02를 실행하더라도 이번 실패는 그대로 유지하고 결과와 matrix를 분리해야 한다.

원본 result의 `audit_close_method`에 정상 shutdown 관측을 뜻하는 상수 문장이 잘못 남아 있다. 실제 불리언은 false이고 원문에도 완료 로그가 없다. 원본은 보존하고 `qa-correction.json`으로 그 문장만 정정했다. 강제 종료 뒤 SQLite read-only integrity가 ok라는 사실은 정상 close 메서드 관측으로 바꾸지 않았다.

정확한 명령·기준·판정은 `IMP20-STARTUP-PROJECT-ROOT-01-manual-qa.md`, 실행 전후 값은 `execution-binding.json`과 `result.json`, 실제 원문은 `server.stderr.txt`와 `health.stderr.txt`에 있다. 기존 158개 manifest와 증거를 덮어쓰지 않았으며 새 산출물은 `supplemental-manifest.json`에만 추가 고정한다. `private-runtime/`은 인증·개인 실행 자료를 포함하므로 공개 manifest에서 제외한다.

이 결과는 전체 게이트·8시간 soak·독립 검수 승인·모델 품질 통과가 아니다. 실제 호출 계수의 경우 QA 클라이언트 POST/추론은 0회이며 전역 provider 호출은 계측하지 않았다. 성공한 기존 회귀나 native 관측을 반복하지 않았다.
