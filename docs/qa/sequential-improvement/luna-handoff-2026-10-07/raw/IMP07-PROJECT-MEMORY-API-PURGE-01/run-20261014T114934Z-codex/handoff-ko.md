# 관리 API 프로젝트 메모리 삭제 검수

실제 active-registry A를 실제 auth/login과 DELETE /api/memory scope=all로 확인했다. 수정 전 HTTP500, A graph 삭제 후 bound project-vector 2개 잔여를 보존했다. 수정 후 HTTP200, A graph·graph-vector·project-vector 잔여0, B graph/vector 내용·저장 파일 SHA 및 outside/global GBrain sentinel 보존. 별도 새 프로세스 재개방에서도 A0, B graph2/graph-vector1/project-vector2를 확인했다.

변경은 vector_store.py의 기존 ID만 삭제하는 관리 함수, dependencies.py의 purge 연결, 9개 회귀다. 정상 VectorStore 생성/검색/쓰기 identity 검사는 유지했다. ephemeral fallback·default embedding·공유 Chroma cache reset을 사용하지 않는다. 누락 컬렉션은 생성하지 않고 오류는 전파한다. ROOT에는 기존 CHROMA_LIFECYCLE_LOCK을 재사용한 최소 함수와 연결만 반영했고 전체 preimage 역변환·독립 src/tests1250개·staged97 SHA로 보존을 확인했다.

Clean 초기56(신규9+인접47) 및 최종 fixture9, ROOT56은 별도 소스 검증이며 합산하지 않는다. 최종 정적4 종료0. 최초 타입검사는 editable ROOT import 때문에9 오류였고 원문을 보존했다. 명시 clean source/Python3.13 config로0 errors를 확인했다. 중간 Python3.9 추론 오류25개의 전체 출력은 tool transcript에만 있으며 이를 파일 보존했다고 주장하지 않는다. 실제 ASGI 요청은 전후 각각3회, auth purge 각1회이며 모든 model/socket/listener 호출0. 두 제품 probe와 새 재개방 process 종료0. 계수의 coroutine resume4는 제품 purge4회가 아니다.

기능 커밋 6f0bd05d84506ab9435bbc4866f2acf2cb49585b는 푸시했다. result.json, artifact-manifest.json, task-only.patch, 전후 request/response/guard/supervisor receipt, JUnit와 root-preservation.json을 참고한다. 주세션 검수 완료, 독립 검수 미실행. lifespan OFF/ASGI·3D 삭제 fixture 범위이며 concurrent session project 선택, 의미 품질, 전체 IMP07/GA, cross-provider atomic purge를 검증한 것이 아니다. 전체 IMP09 PARTIAL·유실 원장 NOT_RECOVERED 유지. 다음은 실제 브라우저 login/SSE 오류/queued task failed 표시 검증이다.
