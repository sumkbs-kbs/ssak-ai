# 실제 RAG 평가 하네스 실행 전 검수 v1

**BLOCK / REQUEST_CHANGES, GO 발급 없음.** 읽기 전용으로 준비 코드 네 파일과 저장28개 offline 검사·정적 영수증을 대조했다. 실제 네트워크·추론·Native lifecycle은 실행하지 않았다.

1. HIGH: control.py의 HTTPX connect/read/write/pool별 timeout은 전체 요청의 절대 deadline이 아니다. 조금씩 진행하는 응답이 min(55, remaining)을 초과할 수 있으며 phase supervisor 종료가 최종 wire receipt를 건너뛸 수 있다. 전체 요청 deadline, 미리 보존한 headers/status/partial bytes, 느린 진행의 비네트워크 음성 회귀가 필요하다.
2. HIGH: supervisor.py의 group_members/ps 실패가 termination·escalation·reap 전에 예외를 내므로 child가 남을 수 있다. Inventory는 진단으로 분리하고 정리에 하나의10초 deadline을 적용한다. 최종 영수증은 finally에서 보존하고 inventory 실패·wait timeout 경로를 검증한다.
3. HIGH: 검수 중 타입 정리를 위해 relative import로 바뀌었지만 직접 runner.py를 실행하는 argv가 남아 있었다. 이 소견은 이전 봉인 snapshot의 결함으로 소급하지 않는다. 최종 module launcher와 pending-GO 거부 경로를 실제 CLI로 검증한 뒤 소스를 새로 고정한다.

나머지 검토 범위인 별도metadata 예산, 추론예약28 상한, loopback/model/prefix 검증, production 검색 경로, 원본 top-five 채점·controlled denominator10, float32 저장 비교와 pending authorization 구분은 적절하다. 기존28개 검사로 위 deadline/cleanup 결함까지 통과했다고 주장하지 않는다. 정적검사 type exit1도 full PASS가 아니다.

Programming 및 remove-ai-slops 관점에서 경계 검증의 필요성을 확인했다. 이전 실패 기록과 준비 버전을 보존한 뒤 수정 후보의 실행 근거·SHA를 다시 대조한다.
