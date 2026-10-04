---
title: Chat routing code review
date: 2026-10-03
tags: [qa, code-review, chat-routing, self-capability]
---

# Chat routing review

## Verdict

- **codeQualityStatus:** BLOCK
- **recommendation:** REQUEST_CHANGES
- **blockers:** Restore Korean explicit tool-capability questions to the self-capability route. `어떤 도구를 사용할 수 있어?` currently returns `False`.

## Reviewed candidate

- Full HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`
- `src/antigravity_k/engine/self_capability.py`: `84e9fadd6d24c17125d1cedd64d5069ba65f0bb82c1ee9523d6982d1a5b03d3cf`
- `tests/test_self_capability.py`: `b0c479ffdaddef7e63f662cc91d9138ff16bc09eb17b55c628a51af0bd9e0e7f`

The source hashes match `chat-routing-source.sha256`. The supplied evidence is present at `chat-routing-{red,green-first,regression,ruff,lsp,validation}*`; it was treated as supporting material and independently checked below.

## Findings

### HIGH

- [self_capability.py:27](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/self_capability.py:27) narrows `어떤 도구` to a fixed set of question/response words but omits the normal explicit capability form `어떤 도구를 사용할 수 있어?`. Independent isolated evaluation returned `False`, and the assertion `assert is_self_capability_request("어떤 도구를 사용할 수 있어?")` failed. This is a user-visible routing regression: it is a direct question about the agent's available tools, was matched by the prior `어떤\s*도구` alternative, and should render the runtime-grounded capability report. The test suite covers `등록된 도구 목록을 알려줘` but not this lost form, so it would not prevent recurrence.

### CRITICAL

None.

### MEDIUM

None.

### LOW

None.

## Independent checks

- The exact browser-QA request, `도구 없이 다음 문장만 그대로 답해: 외부 기능 연결 검증 완료`, evaluated to `False`; it no longer takes the capability route.
- A generic feature request also evaluated to `False`. The scoped suite passed: `HOME=$(mktemp -d /private/tmp/ssak-chat-routing-review.XXXXXX) PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_self_capability.py` → `4 passed in 0.76s`.
- The behavioral stream test is relevant rather than tautological: it checks a real `run_stream` dispatch reaches the provider double and does not call `_render_self_capability_response`. The supplied RED log shows the pre-change direct fast-path failure; its GREEN log shows the repaired behavior.
- `ruff check src/antigravity_k/engine/self_capability.py tests/test_self_capability.py` independently passed. No server, browser, external model, or user database was used.
- Caller-path check: `chat_completions` obtains the latest user message at [chat.py:65](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:65) and directly renders a capability response at [chat.py:934](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/api/routes/chat.py:934). `run_stream` uses the same latest-user selection and predicate at [stream.py:345](/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/src/antigravity_k/engine/orchestrator/stream.py:345), before memory/context processing. This rules out history-budget loss or stale request selection for the observed request.

## Skill-perspective check

Ran `omo:programming` and `omo:remove-ai-slops` before this maintainability/test-relevance judgment. The candidate does not violate either perspective through needless abstraction, untyped escape hatches, brittle prompt-output assertions, deletion-only testing, or implementation-mirroring tests. The provider-dispatch test is behavior-bearing. Its coverage is incomplete for the HIGH finding above.
