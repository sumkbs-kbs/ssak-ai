# Current working tree embedding identity integration

상태: READY_FOR_INDEPENDENT_REVIEW. 승인된 불변 candidate-source의 계약을 현재 root 작업 트리에 이식했습니다.

5개 소유 파일만 변경했습니다. root의 CHROMA_LIFECYCLE_LOCK, PersistentClient 실패 전파(인메모리 fallback 없음), 전역 cache clear 제거를 유지했습니다. 생성자 collection lookup/identity 검증도 기존 잠금 안에서 실행합니다. close는 기존 잠금/실패 전파를 유지하고 collection 참조도 해제합니다. clean 후보의 cache-clear 제어 필드는 root에서 불필요하므로 추가하지 않았습니다. dependencies의 기존 str(generate()) 제거는 그대로 유지했습니다.

최종 candidate-v2/invocation.json의 정확한 명령과 소스 SHA로 58개(신규 계약47+인접11) 통과를 확인했습니다. junit.xml/stdout.log/stderr.log/exit.json, captures 및 module-socket-binding.json이 근거입니다. 실제 root/src 모듈 경로, 물리 socket 시도0입니다. static-final/에 Ruff/format/Basedpyright/메모리 compile 네 검사의 명령·소스 SHA·원문·종료0이 있습니다. 실제 Chroma 임시 저장소와 FakeEngine만 사용했습니다.

첫 candidate-v1은58 통과했으나 format1이어서 해당 원문/소스를 보존하고 서식만 수정 후 최종 후보를 검증했습니다. 첫 준비 스크립트의 generate 표현식 assertion은 소스 쓰기 전 실패했고 baseline-only 별도 run은 그대로 보존했습니다. 저장된 테스트 성공을 과거 실행에 소급하지 않습니다.

preservation.json은 비소유 Python 파일 전체, 기존 staged binary SHA, HEAD 불변을 확인합니다. task-only.patch는 이번 root preimage 기준이며 reconstruction.json의5개 재구성 바이트가 모두 일치합니다. source-binding.json/candidate-source가 최종 바이트입니다.

실제 HTTP/Ollama/모델/다운로드/Uvicorn과 품질 평가는 하지 않았습니다. 기본 활성화 없음. weights revision UNVERIFIED, 전체 write/delete 원자성·동시 writer 보장은 범위 밖입니다. commit/stage/push는 root 소유이며 수행하지 않았습니다.
