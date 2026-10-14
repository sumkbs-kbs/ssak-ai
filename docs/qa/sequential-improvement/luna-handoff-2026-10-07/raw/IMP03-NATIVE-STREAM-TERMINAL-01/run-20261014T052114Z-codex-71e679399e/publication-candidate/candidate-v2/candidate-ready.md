# 검수 수정 반영 게시 후보2

기준 HEAD50437f0ccbb0dd512204ce38b640bd5c238eb97a + 소유6파일입니다. 기존 candidate-v1/92pass 원본은 보존합니다.

malformed native 필드 검증과 새19개 회귀를 반영했습니다. 111 passed, 실패/오류/skip0, Ruff·format·basedpyright·메모리 compile exit0. 원문 checks.json/junit.xml 및 source/를 참조하세요. socket-attempts.json은0이고 import-bindings.json의7모듈은 모두 worktree/src입니다.

candidate.patch는 clean HEAD 대비6파일이고 patch-reconstruction.json에서 바이트 일치합니다. root120과의9개 차이는 기존 root 미커밋 Messages 테스트이며 이번 기능에 포함하지 않았습니다. provider SHA5c79de1d7ee00f92a379bf6b0b33b742f900483e70d874a86b25f12c09ecdcca, 새test SHA50f40ca9d52a9082d2d1fe372d39bebd337ee0f31f9b8750799d5a45ce7a338f.

실제 live/controlled 요청 반복 및 stage/commit/push는 하지 않았습니다. 독립 재검수/게시 판단은 root 담당입니다.
