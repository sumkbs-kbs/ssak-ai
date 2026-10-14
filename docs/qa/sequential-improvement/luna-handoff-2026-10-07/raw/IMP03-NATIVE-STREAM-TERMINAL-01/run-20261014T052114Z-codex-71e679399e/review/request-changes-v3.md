---
title: Native streaming terminal independent review v3
date: 2026-10-14
status: request-changes
tags: [qa, provider, independent-review]
---

# Request changes

Read-only reviewer: `/root/closeout_code_audit`. No reproduction, test, network call or file write by the reviewer.

**HIGH / codeQualityStatus BLOCK:** A valid JSON frame with an invalid content value, such as `{"message":{"content":["partial"]},"done":true}`, bypasses the new typed protocol path. `inference_providers.py:743` uses `cast(str, msg["content"])` without runtime validation. A list can reach `model_manager.py:860`, where text accumulation raises `TypeError`. The generic Messages handler at `messages_api.py:340` turns that exception into ordinary error text and later emits successful `message_delta/message_stop` at lines 432-439.

Required repair: validate supplied native content at the wire boundary, raise `NativeProtocolError("invalid_stream")`, and prove both direct routes have no success terminal, successful usage or persistence for malformed content.

Other reviewed evidence is consistent: current six-file SHA binding, 101-pass JUnit, four static exits 0, no socket attempts; controlled native HTTP200 followed by missing terminal yields typed SSE failure, one provider POST, failed usage 1, success/persistence/retry 0. The stale console label is separately disclosed. Incomplete-tool buffering and opener-only fallback avoid the reviewed tool dispatch/replay cases.

The 101-pass root and 92-pass clean publication candidates remain historical evidence pending the required repair. Their test-count difference is nine unrelated existing Messages tests present only in the dirty root. Full agent SSE, authentication/lifespan, real model behavior and full IMP-03 acceptance remain outside this review.
