---
title: Close nested schema dialect reference retrieval
date: 2026-10-14
tags: [structured-output, offline, review-fix]
---

Independent review found that nested $schema could switch to draft7 and its dependencies keyword could resolve a remote reference.
The input parser now rejects unsupported dialect declarations at every actual schema node and visits legacy dependencies/additionalItems.
Legal properties named $schema/$ref and annotation values retain their ordinary data meaning.
Runtime validation always receives a closed referencing.Registry; public Unresolvable errors map to StructuredOutputError and the existing route502 handler.
referencing0.37 is now a declared direct dependency; uv lock --offline retained the existing218-package resolution.

Authoritative new receipt: final-implementation-checks-v5/checks.json.
Focused tests36passed/0failed; Ruff lint/format, production basedpyright and memorycompile all exit0.
The malicious nested dialect case and legacy dependency reference case return400 before model/session/conversation calls.
The direct forged contract regression exercises nested validator evolution: closed retrieval raises the typed error, with urlopen/socket attempt count0.
35 ASGI cases have captured request/nativewire/response records; the36th is the direct closed-registry guard test recorded in JUnit.
Existing v4 receipts/source snapshots remain preserved. No actual HTTP/model inference was executed.
