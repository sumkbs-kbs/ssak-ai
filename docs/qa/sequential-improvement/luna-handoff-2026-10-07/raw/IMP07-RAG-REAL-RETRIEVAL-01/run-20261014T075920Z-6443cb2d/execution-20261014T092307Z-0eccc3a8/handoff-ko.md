# 실제 RAG 검증 인계 — 제한 범위 통과

2026-10-14 실행 `execution-20261014T092307Z-0eccc3a8`은 **PASS_SCOPED**다. 기존 실행 증거를 파일 바이트로만 대조해 작성했다. 재추론, 메타데이터 재호출, 네이티브 DB API 호출, 테스트 재실행 및 Git 작업은 하지 않았다.

실행 대상은 깨끗한 publication worktree의 root 확인 후보 `7802aa1b`다. 이 문서 작성 단계에서는 Git을 다시 조회하지 않았다. 실제 import 경로와 SHA는 `actual-imports-before.json`, `approved-freeze.json`, `sources-after.json`에 기록되어 있고 현재 파일 바이트와 일치한다. 변경이 많은 root 작업 폴더 자체를 신경망으로 검증한 결과는 아니다.

## 실제 검색 결과

고정 원문30개/별도 프로젝트2개를 실제 Ollama nomic 임베딩으로 색인하고 production `RAGIndexer.search(..., n_results=5, mode='semantic')`를 사용했다. 초기20질의 결과를 `query-results.jsonl`과 사전 고정 oracle에서 다시 계산했다.

| 구분 | top5 적중 | MRR@5 | nDCG@5 |
|---|---:|---:|---:|
| 통제10개 | 10/10 (모두1위) | 1.000000 | 1.000000 |
| 탐색10개 | 9/10 | 0.783333 | 0.813093 |
| 전체20개 | 19/20 | 0.891667 | 0.906546 |
| 영어10개 | 10/10 | 1.000000 | 1.000000 |
| 한국어10개 | 9/10 | 0.783333 | 0.813093 |

탐색 한국어 Q16은 top5에서 정답 source를 찾지 못했다. Q18은3위, Q20은2위다. 탐색용 임의80% 기준을 만들지 않았다. 초기20 API 검색 지연은 p50 12.763ms, p95 15.895ms, 최대 16.763ms다. 분위수는 정렬한 관측값의 `(n-1)*p` 위치 선형 보간이며 작은 단회 표본의 기술 통계다. 그룹·언어별 수치 및 provider 호출 지연은 `live-final-result.json`에 있다.

## 호출·변경·격리 관측

신규 HTTP30회는 실제 임베딩 POST27회와 metadata GET3회다. 이전 metadata4회와 별도 집계했다. 임베딩 입력57개(색인A30/B2, 초기질의20, B질의2, 변경1, 변경후질의2), 응답57개 모두768차원이다. 최초32개 저장 행과 변경1개의 wire 입력/벡터를 직접 대조했다. upstream JSON의 Python float64 값과 저장 전 float32 양자화를 구별한다. 프로필 dimensions=0/weight revision UNVERIFIED는 유지하며 관측된 설치 digest는 `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`로 전후 동일했다.

변경 후 Q01은1위이며 현재 source MD5·provenance·재개방 저장내용과 일치하고24시간 조건이 있으며48시간 조건은 없다. 삭제한 A06은 재개방 행/변경후검색에서 사라졌다. 런타임의 A purge 잔여0, B 논리내용과 purge 전후 파일hash 동일, 외부 sentinel 불변을 확인했다. 이 포장 단계는 DB API를 열어 재검사하지 않았다. 원본 DB 파일은 로컬에 보존하고 최종 manifest에 바이트hash로 포함했다.

별도3차원 고정벡터로 네이티브8클라이언트 두 주기를 실행해 각 클라이언트가8개 ID를 읽었으며 하나를 닫아도 나머지7개가 유지됐다. 이는 생명주기 관측이며 의미검색 품질이나 네이티브 쓰기 원자성 증거가 아니다.

자식 PID 13199는 exit0, 회수완료, 잔여그룹0이고 감독 기록 실행시간은 2.396523초다. timeout/강제종료 신호/cleanup오류가 없었다. 기록된 종료후 `/api/ps`에는 nomic이 적재된 상태였다. 강제 unload하지 않았으며 현재 시점에도 적재되어 있다는 주장은 하지 않는다.

## 남은 범위와 증거

비교 baseline이 없어 일반 성능향상이나 GA를 주장하지 않는다. 기본 hybrid 품질도 측정하지 않았다. B graph를 생성하는 경로가 없어 원래 IMP07 전체는 미완료다. 고정 합성 데이터 검색범위의 통과다. 독립 실제증거 검토는 대기 중이다.

이전52개 offline 검증은 통과했고 Ruff/format은 exit0이다. basedpyright는 exit1, 오류0/경고4이며 이를 PASS로 바꾸지 않는다. 이전 포장 wrapper의 사전 SHA/개별시간 유실은 `runner-preparation/REVISION3_PACKET.md`에 그대로 기록되어 있다. 이번 실제 실행에는 별도의 승인 freeze와 실행 전후 source 관측이 존재한다.

`readonly-verification-receipt.json`은 이번 바이트 대조·보존 근거, `live-final-manifest.json`은 원본 실행자료/DB·고정fixture·source·최종문서 SHA 목록이다. manifest 자체는 자기목록에서 제외한다. 실제 호출 근거는 `wire/`30개 원본 요청·응답·header·receipt, 프로세스 근거는 `invocation.json`/`root-tool-receipt.json`이다.
