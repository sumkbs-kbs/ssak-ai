# Current root keyword corpus integration

READY_FOR_INDEPENDENT_REVIEW. 승인된 불변 스냅샷 두 파일만 이식했습니다. RAGIndexer의 공개 export corpus 획득17줄 외 모든 메서드와 keyword scoring suffix 동일성을 scope-verification.json에서 확인했습니다. 신규 테스트는 승인 SHA와 동일합니다.

현재 root 기준 candidate-v1/invocation.json의 exact argv/cwd/env/source SHA에서36개(새 keyword25+인접11) 통과. junit.xml/stdout.log/stderr.log/exit.json과 실제 Chroma captures가 근거이며 실제 import는 root/src입니다. 물리 socket 시도0, fixture forbidden0. Identity58은 반복하지 않았습니다. static-v1 네 검사(Ruff/format/Basedpyright/메모리 compile) 모두 exit0입니다.

keyword rank/empty/no-match/reopen/changed/deleted/closed/export failure 및 malformed public export를 확인했습니다. Keyword-only model0, legacy private corpus 및 no-export fallback 호환, hybrid 기존 semantic channel budget을 검증했습니다. 실제 모델/HTTP/Ollama/다운로드/품질 평가 아님. 공개 export는 매 검색 전체 corpus를 읽으며 대규모 성능은 미검증입니다.

root VectorStore/dependencies 기존 identity+lifecycle 변경은 그대로 유지했습니다. preservation.json에 비소유 Python 전체 및 staged binary/HEAD 불변 근거가 있습니다. task-only.patch는 이번 root preimage 기준이며 reconstruction.json의 두 파일 바이트가 일치합니다. stage/commit/push/clean WT 수정은 하지 않았습니다. 이번 실행에서 실패한 검사나 helper는 없습니다.
