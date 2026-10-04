---
title: Self-capability runtime debugging audit
date: 2026-10-03
tags: [qa, debugging, runtime-audit, chat-routing]
---

# Runtime audit verdict

**PASS for the observed chat-routing scenario.** Full Git HEAD:
`8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. Final selected-source manifest:
`1fa855b80aaa27b7fbf7464f513cb02a6f8994a4146eea0e6563bc5bb76b8d13`.
This audit covers the selected changes and observed scenarios, not every existing
runtime path in the shared tree.

## Hypotheses and discriminating evidence

1. **Confirmed: predicate overmatch.** Original regex searched the entire request
   for bare `기능`. Both chat.py's direct response and stream.run_stream evaluated
   it before normal provider dispatch. The exact same prompt evaluates True on
   the preserved old predicate and False on the final predicate
   ([chat-routing-toggle.log](chat-routing-toggle.log)). Actual browser output
   changed from the self report to the requested phrase after replacing only the
   predicate and restarting the server. A real stream-dispatch regression changes
   from the self-report fast path to one provider-double call with original input.
2. **Refuted for this turn: lost latest request/history budget.** The latest user
   message was visibly the expected input. Independent trace confirmed both
   latest-user resolvers reverse-scan the messages and the self-report branches
   run before memory/context budgeting. The related latest-request budget tests
   also pass in the 361-case final suite.
3. **Refuted for this turn: stale process/UI or cached provider output.** The owned
   old server PID 24639/session 10358 stopped with exit 143. New PID 32914/session
   27894 started without reload. Browser reload, fresh submission, HTTP 200 and
   completed visible reply all refer to the final source. The final live health
   shows qwen3.8 loaded with a nonempty last-used timestamp, where the earlier
   pre-inference health had no loaded backends.

## Original scenario and corrected output

- Page: existing authenticated `http://127.0.0.1:8000/chat`.
- Input: `도구 없이 다음 문장만 그대로 답해: 외부 기능 연결 검증 완료`.
- Before: `Ssak-Ai Self Capability Report` and capability sections.
- After, verbatim: `외부 기능 연결 검증 완료`.
- Selected model: `qwen3.8:latest (27.3B)`; Search/Code OFF; existing full access.
- Receipt: POST `/v1/chat/completions` 200; reply completed and Send button restored.
- Evidence: [before](chat-routing-before.txt), [after](chat-routing-after.txt),
  [screenshot](chat-routing-after.png), [server receipts](root-final-runtime-receipts.log),
  [final health](root-final-live-health.txt).
- Actual token usage is not exposed in this UI/default server log and was not
  measured. No fake usage count or real-STT claim is made.

## Failing-first and retake

- Generic feature task: [RED](chat-routing-red.log),
  [GREEN](chat-routing-green-first.log); provider called once and self renderer not called.
- Independent review found missing direct Korean tool usage question in the first
  repair. [Retake RED](chat-routing-retake-red.log) preceded the minimal correction;
  [retake GREEN](chat-routing-retake-green-first.log) and final 4-case suite pass.
- Root final combined suite: **361 passed, 1 warning in 7.90s**. The earlier stdin
  launcher failure is preserved and identified as multiprocessing harness misuse;
  final `python -c` invocation succeeds without weakening a test.
- Final independent chat review: **CLEAR / APPROVE**, source hashes
  `7e6428f660078089eb5411461b1d5e0bf3a1eae4a27f192fc5fb7f55a8258f7d` and
  `9dce35c96bc1db38f342d28d7c753fcf8acfae5e103e6d4c0c7c4e77783d2c8c`.
- Exact delta against the pre-debug snapshot is [chat-routing-delta.diff](chat-routing-delta.diff).

## Cleanup contract

No temporary production instrumentation, debugger, auth bypass, model/config
change, or .git mutation was installed. Durable QA evidence is promoted here;
temporary baseline copies and synthetic input fixtures are removed after promotion.
The owned root journal is removed last. The normal main server and original
browser tab remain as the running deliverable. Its local runtime log is retained
while that server runs; only sanitized relevant receipts are exported.
Cleanup verification is recorded in `root-final-cleanup.txt`.
