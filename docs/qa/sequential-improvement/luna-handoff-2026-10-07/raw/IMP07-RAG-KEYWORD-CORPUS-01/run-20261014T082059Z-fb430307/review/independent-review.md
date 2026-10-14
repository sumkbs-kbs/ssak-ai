# RAG keyword corpus 독립 검수

판정: **CLEAR / APPROVE**, 차단 사항 없음. 저장 증거와 현재 후보를 읽기 전용으로 대조했고 실행·쓰기는 하지 않았다.

Actual VectorStore의 public export_all을 keyword corpus로 사용한다. 빈 export는 빈 결과이고 malformed/noncallable/failed/closed export는 semantic fallback 없이 오류를 전파한다. 기존 private _chunks 및 실제 export 기능이 없는 legacy fallback은 유지한다. 점수·rank·RRF·provenance 코드는 불변이다.

현재 소스 SHA가 패킷과 일치한다. 저장36 passed(새25 + 기존11), 정적4 exit0, 봉인93개, 빈 socket attempts와 native fixture15개의 forbidden calls=[]를 확인했다. Lexical parity, 수정·삭제·reopen의 새 corpus, 추가 keyword embedding 호출 제거를 검증한다.

Programming 및 remove-ai-slops 관점에서 추가 소견은 없다. 이 승인은 lexical routing과 호출 예산 계약이다. 실제 semantic 품질·큰 corpus 성능은 별도이며 keyword stale 표시의 기존 동작은 유지한다.
