# Compatible transport 게시 후보

기준 HEAD d2aed8c1f7237f08f7b497e6760b792754c61b1e. worktree /Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai. provider 및 새test2파일만 변경됐으며 stage/commit/push하지 않았습니다.

root task-only.patch를 clean HEAD에 적용했습니다. 최초 후보는93pass/16fail: clean manager가 LMStudio capability /v1/models GET을 수행하지만 재사용 structured fixture가 Ollama /api/show만 허용하여 실제 추론 전 막혔습니다. candidate-v1 원문과 소스를 보존했습니다.

새compat test에 LMStudio의 정확한 GET endpoint와 등록 model id를 반환하는 metadata terminal만 추가했습니다. 기존 Ollama metadata fixture를 유지하며 production이나 ModelManager를 우회하지 않았습니다. 수정은 clean 새test에만 적용했고 root source는 수정하지 않았습니다.

최종 candidate-v2:109passed/실패·오류·skip0, Ruff·format·basedpyright·메모리compile4개 exit0. Starlette 경고1건. checks.json의 argv/cwd/source SHA, junit.xml, 원문로그, source/를 참조하세요. import-bindings.json의6모듈은 worktree/src로 고정됐고 socket-attempts.json은0입니다.

candidate.patch는 HEAD 대비2파일, patch-reconstruction.json에서 byte-identical입니다. provider는 root와 동일SHA0e758c675045b35d8b3b6a38577b6583ee2a255e8128a07c8c495b1eb92de97f입니다. 테스트는 metadata fixture를 보강했으므로 root와 SHA가 다릅니다. 실제 HTTP/Ollama/모델 실행은 반복하지 않았습니다. root 독립 검수 및 게시 결정 대기입니다.
