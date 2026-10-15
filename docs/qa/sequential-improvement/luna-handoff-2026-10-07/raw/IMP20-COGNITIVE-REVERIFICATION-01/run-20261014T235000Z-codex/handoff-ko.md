# Migration digest 재확인 인계

범위는 `digest_reverification.json`의 T12 migration 소스 행 1개와 기존 생성기가 작성한 `digest_drift.json`이다. 제품·테스트 코드는 수정하지 않았으며 T12 원문 pin, 문서, 테스트 재확인 행, Architecture Review 문서는 보존한다.

367863ce 변경은 SQL 식별자 보간을 고정 SQL로 대체한 수정이다. 이전의 whitespace-only 재확인 사유를 승계할 수 없어 현재 소스 SHA와 실제 수정 범위, 근거 및 한계를 기록했다. 과거 56,961행 migration rehearsal이나 실모델 결과를 갱신한 것이 아니다.

`prior-evidence-validation.json`은 기존 Bandit 증거 manifest 27개 파일의 bytes/SHA, 현재 소스 binding 6개, JUnit 141개(그중 migration 30개), 실행 receipt 연결을 대조한 결과다. migration 소스와 두 migration 테스트 파일은 367863ce 커밋과 현재 바이트가 같다. 옛 receipt에 테스트 실행 당시 바이트 SHA가 따로 없다는 한계는 남긴다.

수정 전 `before-drift`는 stale migration 재확인과 저장 artifact 불일치로 실패했다. 수정 후 기존 `scripts/digest_drift.py` 생성 및 `--gate`가 통과했고 match 8 / reverified 42 / drift·stale·missing 0이다. 테스트의 최종 판정은 `result.json`, 실제 명령은 `cognitive-tests-attempt-2.receipt.json`, 원문은 같은 이름의 stdout/stderr 및 `junit-attempt-2.xml`을 사용한다.

초기 테스트 실행은 evidence helper가 basetemp 상위 폴더를 만들지 않아 145개 setup error로 종료됐다. 원본 `verify-attempt-1.py`, 최초 JUnit·원문·receipt를 보존하고 helper에서 부모 폴더를 생성한 뒤 동일 3파일 selector 전체를 재실행했다. 제품 실패로 분류하거나 숨기지 않았다. 초기 helper Ruff format 실패는 세션에서 관측했고 원문 파일로 별도 보존하지 못했음을 결과에 명시한다. 최종 정적 검사 및 메모리 compile은 `final-checks.json`을 따른다.

`task-only.patch`는 2개 문서 파일만 포함한다. preimage 기준 patch 적용으로 최종 바이트를 재구성했고 `scope-verification.json` 및 `final-binding.json`에 보호 파일과 재구성 결과를 기록한다. 독립 검수 PENDING이며 전체 23개 gate, live/GA 승인을 뜻하지 않는다. worker는 commit/push하지 않았다.

공개 파일은 `artifact-manifest.json`에 한정한다. `private-runtime/`은 pytest 임시 상태와 재구성 체크아웃이며 인계 manifest에서 제외한다.
