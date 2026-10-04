---
title: Chat routing code review
date: 2026-10-03
tags: [qa, code-review, chat-routing, self-capability]
---

# Chat routing review

## Verdict

- **codeQualityStatus:** CLEAR
- **recommendation:** APPROVE
- **blockers:** None.

The prior BLOCK finding is preserved in `chat-routing-review-before-retake.md` (SHA-256 `fea1e416b023b29564c10cd86ab1f6be18e3ad3d68cfcfa83fa33ac7e7fa028a). This retake restores the missing direct Korean tool/model capability forms without restoring the bare-word false positive.

## Reviewed candidate

- Full HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- `src/antigravity_k/engine/self_capability.py`: `7e6428f660078089eb5411461b1d5e0bf3a1eae4a27f192fc5fb7f55a8258f7d`
- `tests/test_self_capability.py`: `9dce35c96bc1db38f342d28d7c753fcf8acfae5e103e6d4c0c7c4e77783d2c8c`

The hashes independently match `chat-routing-retake-source.sha256`. The supplied `chat-routing-retake-{red,green-first,regression,ruff,lsp,validation}*` evidence exists and was inspected as supporting material, not trusted without the checks below.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

## Independent checks

- The exact browser-QA request, `도구 없이 다음 문장만 그대로 답해: 외부 기능 연결 검증 완료`, evaluates to `False`; it no longer takes the capability route.
- Direct capability questions now classify correctly: `어떤 도구를 사용할 수 있어?` and `어떤 모델을 사용하고 있어?` both evaluate to `True`.
- Ordinary requests retain normal routing: `외부 API 기능을 사용해 상태를 정리해줘` and `어떤 모델을 사용해 구현할지 비교해줘` both evaluate to `False`.
- Isolated execution, using a temporary HOME and no cache provider, passed: `HOME=$(mktemp -d /private/tmp/ssak-chat-routing-retake-review.XXXXXX) PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_self_capability.py` → `4 passed in 0.81s`.
- The provider-dispatch test is behavior-bearing: it runs `run_stream`, asserts the generic feature request reaches the provider double with its original text, and asserts `_render_self_capability_response` was not called. It is not a classifier-only or implementation-mirroring test.
- Independent `ruff check src/antigravity_k/engine/self_capability.py tests/test_self_capability.py` passed. No server, browser, external model, or user database was used.
- Caller-path review remains consistent: `chat_completions` selects the current user text at [chat.py:65](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:65) and directly invokes the capability branch at [chat.py:934](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:934). `run_stream` evaluates the same predicate at [stream.py:345](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/orchestrator/stream.py:345) before memory/context work. The evidence supports predicate overmatch as the original cause, rather than budget/history loss or stale-request selection.

## Skill-perspective check

Ran `omo:programming` and `omo:remove-ai-slops` before judging maintainability and test relevance. The retake violates neither perspective: it adds no needless abstraction or untyped escape hatch, and its tests are not brittle model-output, deletion-only, tautological, or implementation-mirroring tests. The direct detector cases cover both the repaired positive and the retained generic-task negative; the stream test covers the observable dispatch boundary.
