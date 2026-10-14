---
title: Native direct provider failure root surface verification
date: 2026-10-14
status: pass-scoped
tags: [qa, provider, surface-verification]
---

# Root verification

`controlled-wire-v2/` records one ASGI product POST through the real translator, manager, native provider and egress helper to an owned loopback HTTP server. The server returned HTTP 503 exactly once. Product status was 502 with `provider_transport_error` and numeric upstream status 503. There was one failed usage record, zero successful usage records, zero assistant records and zero retry attempts. The observer exited 0 and closed its owned server. No real Ollama or model inference occurred; this is not external product HTTP/auth/Uvicorn/lifespan acceptance.

The earlier `controlled-wire/` request exposed the helper's automatic 503 retry and was terminated with external exit 143. Its first request, acceptance and partial state are preserved. Local complete stdout/stderr capture was not configured; the retry warning is available in the native tool transcript. Additional provider receipt and internal cleanup were not observed. This earlier execution is **FAIL_RETRY_BOUNDARY_OBSERVED**, never a PASS.

`lifecycle-regression-v2/` records six passing existing cancellation, ownership, approval-pause and store-reopen selectors. Physical connection attempts and source drift were zero. The metadata terminal alone was substituted; real SQLite, runtime threads and the owned sleep subprocess were exercised. This does not prove a complete OS restart scenario.

The earlier `lifecycle-regression/` has six pytest passes but six blocked localhost:11434 attempts and overall exit 1. Those results remain unchanged. The later harness explicitly substitutes only capability metadata POST `/api/show` and records those mock calls.

The Starlette TestClient deprecation warning is preserved. Existing unrelated staged changes were not included in this feature.
