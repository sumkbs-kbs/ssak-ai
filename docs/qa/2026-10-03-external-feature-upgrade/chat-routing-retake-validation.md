---
title: Self-capability chat routing retake evidence
date: 2026-10-03
tags: [qa, chat, routing, self-capability, retake]
---

# Self-capability routing retake

## Direct Korean tool and model questions

- Scenario: `어떤 도구를 사용할 수 있어?` and `어떤 모델을 사용하고 있어?` are direct questions about this agent's available tools and current model.
- Invocation: `.venv/bin/pytest -q tests/test_self_capability.py::test_self_capability_request_detection`
- Red observable: before the retake predicate update, the tool question assertion returned `False`; the command reported `1 failed`.
- Red artifact: [chat-routing-retake-red.log](chat-routing-retake-red.log)
- Green observable: both detector assertions return `True`.
- Green artifact: [chat-routing-retake-green-first.log](chat-routing-retake-green-first.log)

## Ordinary tasks retain normal dispatch

- Scenario: generic feature/model implementation requests and slash commands do not classify as self-capability requests; the isolated `run_stream` scenario calls the provider double and its final chunk is `provider dispatched response`.
- Invocation: `.venv/bin/pytest -q tests/test_self_capability.py`
- Binary observable: all four tests passed.
- Artifact: [chat-routing-retake-regression.log](chat-routing-retake-regression.log)

## Static checks and candidate identity

- Invocation: `.venv/bin/ruff check src/antigravity_k/engine/self_capability.py tests/test_self_capability.py`
- Binary observable: `All checks passed!`.
- Artifact: [chat-routing-retake-ruff.log](chat-routing-retake-ruff.log)
- Invocation: `mcp__lsp__diagnostics` with `severity=error` for each changed file.
- Binary observable: `No diagnostics found` for both files.
- Artifact: [chat-routing-retake-lsp.txt](chat-routing-retake-lsp.txt)
- `src/antigravity_k/engine/self_capability.py`: `7e6428f660078089eb5411461b1d5e0bf3a1eae4a27f192fc5fb7f55a8258f7d`
- `tests/test_self_capability.py`: `9dce35c96bc1db38f342d28d7c753fcf8acfae5e103e6d4c0c7c4e77783d2c8c`
- Hash manifest: [chat-routing-retake-source.sha256](chat-routing-retake-source.sha256)

The tests use a temporary `Path.home()` before the stream runtime import and a provider double; no user database or external model inference is used. The final live-browser retest remains root-owned.
