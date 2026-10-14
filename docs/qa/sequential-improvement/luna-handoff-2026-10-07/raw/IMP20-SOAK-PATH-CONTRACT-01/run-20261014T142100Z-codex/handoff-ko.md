# Soak 후보·출력·인터프리터 경로 계약

판정: DONE_SCOPED_STUB_CONTRACT. 구현 커밋 `c472d4fcd7c52a045f9bd0a0c07bba582ff51b54`이며 주 에이전트가 검수했습니다. 독립 검수 NOT_RUN, 실제 8시간 soak NOT_RUN입니다.

runner/scheduler의 기본 repo를 실행 스크립트 위치에서 계산하고 controller의 외부 checkout fallback을 제거했습니다. runner/scheduler 경로는 evidence output이 아닌 후보 repo에서 찾습니다. NX10_REPO·NX10_PYTHON·NX10_SOAK_OUT_DIR/NX10_OUT을 실제 하위 실행에 전달하고 새 output parent를 생성합니다. 명시된 인터프리터가 없으면 실제 하네스 전에 종료 2로 중단합니다. 기존 lock·fingerprint·종료 코드 및 회수 규칙을 유지했습니다.

수정 전 새 회귀 5개가 실패했습니다. 첫 수정 후 4 통과/1 실패는 status 명령이 미예약 상태에서 ATTENTION/exit1을 반환하는 기존 계약을 새 테스트가 잘못 0으로 단정했기 때문입니다. 해당 기대만 기존 계약에 맞춰 고치고 missing-interpreter 사례 두 개를 추가했습니다. 최종 clean/root 각각 7 통과이며 Ruff/format/bash -n 통과입니다. shell fixture의 BASH_ENV 가드는 공유 checkout으로 cd하면 종료73으로 차단하며, 실제 val02·HTTP·신경망·장시간 실행은 없습니다.

ROOT runner에 이미 있던 NX10_REPO override 도입과 설명 두 줄을 preimage로 보존했습니다. 이번 변경은 override를 유지하고 기본값과 출력 전달만 확장합니다. 사용자 staged diff 97개는 동일합니다. 새 소유 테스트는 현재 테스트 Python을 사용하며 특정 사용자 인터프리터 경로에 의존하지 않습니다.

후속: clean 후보의 dashboard provenance/bundle/SBOM을 먼저 동결하고 같은 SHA·manifest·fingerprint에서 23개 공식 gate를 수행합니다. 이 짧은 fixture를 8시간 soak나 GA PASS로 승격하지 않습니다. 과거 8시간 FAIL 및 귀속 불명 결과는 유지합니다.
