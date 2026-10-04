---
title: Final scoped LSP error gate
date: 2026-10-03
tags: [qa, lsp, diagnostics]
---

Full HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
Final 17-file manifest: `1fa855b80aaa27b7fbf7464f513cb02a6f8994a4146eea0e6563bc5bb76b8d13`.

The first 15 files retain the exact previously checked hashes recorded in root-lsp.json and source-before-routing.sha256. The final two were checked again with mcp__lsp__diagnostics(severity=error) after the retake. All results below are actual tool output, not inferred from tests. This gate does not claim that legacy third-party warning diagnostics are absent.

| File | Actual error-gate result |
| --- | --- |
| `src/antigravity_k/engine/task_runner.py` | No diagnostics found |
| `tests/test_task_runner_claim.py` | No diagnostics found |
| `src/antigravity_k/engine/memory_provider.py` | No diagnostics found |
| `src/antigravity_k/engine/memory_recall_budget.py` | No diagnostics found |
| `tests/test_memory_recall_budget.py` | No diagnostics found |
| `src/antigravity_k/api/routes/voice_api.py` | No diagnostics found |
| `src/antigravity_k/engine/voice_audio.py` | No diagnostics found |
| `tests/test_voice_api.py` | No diagnostics found |
| `tests/test_voice_audio.py` | No diagnostics found |
| `src/antigravity_k/engine/data_extractor.py` | No diagnostics found |
| `src/antigravity_k/engine/financial_numbers.py` | No diagnostics found |
| `src/antigravity_k/api/routes/system_api.py` | No diagnostics found |
| `tests/test_financial_numbers.py` | No diagnostics found |
| `tests/test_search_numeric_contract.py` | No diagnostics found |
| `docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py` | No diagnostics found |
| `src/antigravity_k/engine/self_capability.py` | No diagnostics found |
| `tests/test_self_capability.py` | No diagnostics found |
