# 실제 기동·인증 관측 인계

판정: PASS_SCOPED_EXTERNAL_UVICORN_AUTH_LIFESPAN_ON / 독립 검수 PENDING.

게시 후보 e3ef83547b70a4856ce196ef6c69fd4f4bc715f1에서 lifespan on 실제 Uvicorn 기동과 종료가 완료되었습니다. 실제 HTTP 네 요청은 미인증401 → 임시 PIN 로그인200 → Bearer 접근200 → health200입니다. 자식25538은 종료0/reaped/group empty/강제종료 없음, 관측시간 약7.287초입니다. guard 위반0, bind1, 모델호출0, scheduled tick0입니다. 정확한 file -b Python 조회의 argv와 설치 바이너리/stdlib 해시는 guard에 기록돼 있습니다. code-server 시도와 git도 기록돼 있으며 선택적 IDE는 사용할 수 없었습니다.

읽기 전용 대조: 소스580개와 준비 manifest70개 해시 일치, 응답4개의 원문 bytes/SHA 및 JSON 구조, 임시 PIN 요청 일치, Bearer 존재, 인증 모드, health 버전을 확인했습니다. 인증 원문·PIN·토큰·DB는 공개 패키지에서 제외합니다. DB 위치는 final-live-result.json의 owned 상대경로 목록에 기록했습니다. 설정 project/data/vector 루트와 hooks/agency 저장은 이 owned 실행 경로이며 source-derived RAG 읽기 스캔 루트는 별도로 candidate worktree입니다.

과거 결과는 변경하지 않습니다. v2는 import 격리 실패/HTTP0/exit1, v3는 인증4응답 및 종료 관측에도 격리 위반으로 NO_SUCCESS입니다. v4에서만 이번 전체 범위 PASS이며 완료된 두 요청 순서의 HTTP 합계는8입니다. 자동 재전송과 이번 패키징의 실행 반복은 없습니다.

등록 모델 없음 경고를 보존했습니다. 모델추론·live vision·전 범위 API 품질을 검증한 것이 아닙니다. Python audit와 모델 진입점 guard는 OS 전체 syscall 격리를 입증하지 않습니다. root dirty-tree 조합 검증과 배포 이식성은 별도 범위입니다.

final-live-manifest.json에 명시된 공개 파일만 게시 대상으로 사용하고 auth-private 및 실제 DB/설정 캐시 트리는 게시하지 않습니다. 기존 artifact-manifest.json은 그대로 보존했습니다.
