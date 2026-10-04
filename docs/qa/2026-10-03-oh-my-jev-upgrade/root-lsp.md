---
title: 최종 변경 파일 LSP 진단 기록
date: 2026-10-03
tags: [qa, lsp, diagnostics]
---

Full HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, 최종 source manifest
SHA256 `0d19f8f285706674ef9326e6a0e649d5c4a93804ed0f22b5312893cee1a414aa`.
Root가 `mcp__lsp__diagnostics`를 아래8파일에 severity=error로 직접 호출했다.
모든 호출은 isError=false와 `No diagnostics found`를 반환했다.

- src/antigravity_k/engine/decision_evaluation_models.py
- src/antigravity_k/engine/decision_evaluation.py
- src/antigravity_k/decision_evaluation_cli.py
- src/antigravity_k/api/routes/decision_evaluation_api.py
- src/antigravity_k/cli.py
- src/antigravity_k/api/routes/__init__.py
- tests/test_decision_evaluation.py
- tests/test_decision_evaluation_surfaces.py

새4모듈·새2시험·QA2helper의 경고까지 포함한 별도 무필터 basedpyright는
root-frozen-types.log에0오류0경고로 기록했다. JSON Biome LSP는 설치되지 않았고
사용자가 이전에 설치를 거절하여 설치하지 않았다. JSON은 실제 Pydantic 파싱과
jq 비교 및 python json.tool로 검증했다.
