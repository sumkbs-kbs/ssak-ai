# 독립 검수 지적 수정: native wire 필드 타입

기존 root101/clean92는 타입 검증 결함으로 게시 미승인입니다. 기존 산출물을 덮어쓰지 않고 이 후보를 새 승인 대상으로 제출합니다.

수정 전 새19개 사례에서17 failed/2 passed를 저장했습니다. red-test-source.py, source-preimage/, red-junit.xml, red.stdout/stderr 및 red-route-captures/에 실제 Messages가 malformed content를 오류 문자열 또는 빈 정상 메시지와 message_stop으로 반환한 증거가 있습니다. malformed Chat의 generator TypeError도 숨기지 않고 보존했습니다.

provider의 소비 필드에 실제 타입 검증을 추가했습니다. supplied message는 객체, content는 str(빈 문자열 포함), done은 bool, tool_calls는 배열이어야 합니다. 각 call/function은 객체이며 name은 비어있지 않은 str, arguments는 객체여야 합니다. 틀린 필드를 cast로 통과시키지 않고 NativeProtocolError invalid_stream을 냅니다. terminal done:true에서 message가 없는 기존 정상 형식과 content=""는 유지합니다. role 등 사용하지 않는 필드는 확장 범위 밖입니다.

root candidate-v4/final:120 passed, 정적4개 exit0/socket0. clean publication-candidate/candidate-v2:111 passed, 정적4개 exit0/socket0. 차이9개는 기존 root 미커밋 Messages streaming 테스트로 기능 커밋에 혼입하지 않았습니다. 두 실행 모두 동일 provider/new test SHA를 사용하며 각 작업트리의 소스 snapshot/영수증/JUnit/원문을 따로 보존합니다. clean7모듈은 worktree/src 로드 검증을 통과했습니다.

새 추가19개는 malformed content5종×2 API=10, malformed message/native tool 구조7, 정상빈문자열2입니다. 실패 경우 typed SSE error/정상terminal없음/성공usage0·실패1/assistant저장0을 단언합니다. 도구 구조 실패는 chunk0으로 tool dispatch 기회를 만들지 않습니다.

review-fix.patch는 직전후보 대비2파일(provider/new test)입니다. task-only.patch는 최초 시작 dirty preimage 대비6파일 전체입니다. root와 clean의 patch-reconstruction.json은 각6파일 바이트 일치를 확인합니다. 기존 실제 controlled NDJSON 관측은 반복하지 않았습니다. commit/stage/push하지 않았으며 독립 검수 대기입니다.
