---
title: Self-capability chat routing regression evidence
date: 2026-10-03
tags: [qa, chat, routing, self-capability]
---

# Self-capability routing validation

## Generic feature task reaches normal stream dispatch

- Scenario: an ordinary request that contains the generic word `기능` enters `run_stream` with no benchmark or recalled-memory fast path.
- Invocation: `.venv/bin/pytest -q tests/test_self_capability.py::test_generic_feature_task_reaches_provider_in_stream_path`
- Red observable: before the regex change, the final chunk was `_render_self_capability_response()` instead of the fake provider output; the command reported `1 failed`.
- Red artifact: [chat-routing-red.log](chat-routing-red.log)
- Green observable: `provider.stream_generate` was called once with the original request and `test-model`; the final stream chunk was exactly `provider dispatched response`.
- Green artifact: [chat-routing-green-first.log](chat-routing-green-first.log)

## Explicit self-intent remains on the self-capability path

- Scenario: identity, capability, current-model, registered-tool, and settings-status questions still classify as self-capability requests; generic feature and model implementation tasks, plus slash commands, do not.
- Invocation: `.venv/bin/pytest -q tests/test_self_capability.py`
- Binary observable: all four tests passed, including `test_self_capability_request_detection` and the stream dispatch regression.
- Artifact: [chat-routing-regression.log](chat-routing-regression.log)

## Static diagnostics

- Scenario: the two modified Python files have no selected lint or language-server errors.
- Invocation: `.venv/bin/ruff check src/antigravity_k/engine/self_capability.py tests/test_self_capability.py`
- Binary observable: `All checks passed!`.
- Artifact: [chat-routing-ruff.log](chat-routing-ruff.log)
- Invocation: `mcp__lsp__diagnostics` with `severity=error` for each changed file.
- Binary observable: `No diagnostics found` for both files.
- Artifact: [chat-routing-lsp.txt](chat-routing-lsp.txt)

## Candidate identity

- `src/antigravity_k/engine/self_capability.py`: `84e9fadd6d24c17125d1cedd64d5069ba65f0bb82c1ee9523d6982d1a5b03d3cf`
- `tests/test_self_capability.py`: `b0c479ffdaddef7e63f662cc91d9138ff16bc09eb17b55c628a51af0bd9e0e7f`
- Hash manifest: [chat-routing-source.sha256](chat-routing-source.sha256)

The regression uses an isolated temporary home before importing the stream runtime and a local provider double; it does not call an external model. The final live-browser retest is root-owned.
