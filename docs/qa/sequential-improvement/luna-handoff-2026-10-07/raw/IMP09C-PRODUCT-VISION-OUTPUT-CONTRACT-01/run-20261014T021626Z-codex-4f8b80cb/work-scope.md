---
title: Structured Product Vision output contract
date: 2026-10-14
tags: [implementation, structured-output, offline]
---

Task: IMP-09-C-PRODUCT-VISION-OUTPUT-CONTRACT-01.

Direct user request authorizes continuing implementation after commit/push. Previous evidence is published at 3ed59124 on ssak-ai/codex/m1-task-events. Existing strict FAIL_SEMANTIC and original inference budget remain historical and immutable.

Implement explicit OpenAI-style json_object/json_schema inputs for direct native Ollama qwen3 completions. Normalize envelopes to native format="json" or the exact object schema. Preserve plain text defaults. Reject malformed format, unsupported orchestration/tool/provider paths before side effects. Prevent automatic intent classification from causing extra inference for explicit structured requests.

Validate explicit structured responses without stripping fences: malformed or schema-invalid model output must not be declared successful. Ordinary text behavior and general provider error mapping remain outside this new strict response path.

Verification uses the real ASGI route, translator, manager and provider with only terminal transport mocked and socket guards. Record failure before fix, source-bound final tests/static checks and independent review. No historical successful suite or actual inference is replayed.

Ollama reference: https://docs.ollama.com/capabilities/structured-outputs . OpenAI envelope reference: https://developers.openai.com/api/docs/guides/structured-outputs . JSON schema references must not cause network resolution.

Current shared staged changes: 97 paths, binary diff SHA84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f. Preserve all unrelated edits.
