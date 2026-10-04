---
title: Conversation compact input validation verification
date: 2026-10-04
tags: [qa, core, conversation, validation]
---

Completed: request-boundary discovery, failing-first regression, narrow fix,
static review, related regression, and actual production HTTP/curl verification.
Parent-provided HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
The shared working tree was preserved; no Git commands or mutations were used.

## Confirmed defect and fix

The existing `ConversationCompactRequest` already requires `0 <= retain_tail <=
10000`. The route manually called `model_validate()` after parsing `Request`.
Invalid input therefore raised a Pydantic `ValidationError` inside the handler,
which the generic exception boundary returned as HTTP500 `internal_error`.

The compact handler now accepts `ConversationCompactRequest` as a typed FastAPI
body. Invalid input is rejected before handler/store execution through the
existing HTTP422 `validation_error` response. The same fix covers
`/v1/conversations/compact` and `/compact`.

The binding payload is derived with `req.model_dump(mode="json", exclude_none=True)`.
The request model forbids extras and declares every accepted body key. Explicit
`project_id`, `conversation_id`, and `expected_revision` are preserved; session
binding still reads the unchanged request header. The route still constructs
canonical `conversation_revision` from `expected_revision`. A null/omitted
project continues to use session resolution. No model constraint or compact
algorithm was changed. Zero retention remains valid.

Hypotheses distinguished by observed evidence:

- Missing size constraints: refuted by the existing model and its Pydantic error.
- Validation exception escapes the request boundary: confirmed by four baseline
  HTTP500 failures changing to four HTTP422 responses with typed-body dispatch.
- Invalid fixture revision/store state: refuted by six valid baseline cases and
  byte-identical journal/view data after corrected invalid requests.

## Test evidence

`compact-validation-red.txt`: **4 failed, 6 passed**. The four failures were
HTTP500 rather than expected422 for `-1` and `10001` on both route aliases.

`compact-validation-green.txt`: **20 passed, 1 warning**, exit0. Includes ten new
request-boundary tests plus the existing conversation API and store suites.
New cases exercise real FastAPI routing and a real persisted `ConversationStore`;
invalid input leaves every journal/view byte unchanged. Valid tails0,2,6 keep
the established revision and retained-message behavior on both route aliases.
The warning is the installed Starlette/httpx deprecation; no dependency change
or installation was performed.

Final command, from the repository root:

```bash
.venv/bin/python - <<'PY'
import os
import sys
from pathlib import Path
repo = Path.cwd()
sys.path.insert(0, str(repo / 'docs/qa/2026-10-04-full-live'))
from manual_api_fixture import isolated_home
with isolated_home() as root:
    os.environ['AGK_CONVERSATION_STORE_DIR'] = str(root / 'conversations')
    import pytest
    result = pytest.main([
        '-q', '--tb=short', '--basetemp', str(root / 'pytest'),
        '-o', 'log_level=CRITICAL',
        str(repo / 'tests/test_conversation_compact_validation.py'),
        str(repo / 'tests/test_conversation_api_ctx01.py'),
        str(repo / 'tests/test_conversation_store_ctx01.py'),
    ])
raise SystemExit(result)
PY
```

Before project imports, `isolated_home()` patches `Path.home`, changes cwd, and
sets explicit AGK config/data/task/project/cache/auth paths while preserving
`HOME` and `CODEX_HOME`. The wrapper also sets the conversation-store path,
because that legacy default uses `os.path.expanduser` rather than `Path.home`.
The route and project-binding getter share the same real temporary store.

Initial harness mistakes were corrected before counting product evidence:
the first fixture missed the project-binding store getter, causing a sandbox-
denied real-home `.cas.lock` attempt. It did not read conversation records or
successfully mutate that store. The clean RED/GREEN runs explicitly isolate it.
The first standalone curl attempt expected revision5 even though `serve` seeds
revision4; it stopped at that precondition and cleaned its server/header/home.
The final curl scenario appends the fifth synthetic turn before the exact test.

## Actual HTTP verification

`compact-validation-live.json` retains **15 actual curl requests** against the
production FastAPI app, middleware, validation handler, and real isolated stores.
The existing `manual_api_driver.py serve` supplies an ephemeral loopback port
and a synthetic0600 bearer-header file. No user credentials or model calls occur.

- Exact negative request: project `default`, conversation
  `qa-conversation-source`, expected revision5, tail-1: HTTP422 `validation_error`.
- Both aliases and tail10001 also return422; four invalid requests in total.
- Conversation snapshot/messages remain identical and revision remains5.
- Tail0: HTTP200, revision6, one summary message.
- Tail2 through `/compact`: HTTP200, revision6, three retained view messages.

Final owned server PID23976 exited0; its temporary root and header were removed.
No debugger, source instrumentation, raw app-log reads, or user-data export was
used. The actual application on port8000 was not restarted by this worker.

## Static and independent review

- Ruff: exit0, `All checks passed!` (`compact-validation-ruff.txt`).
- Basedpyright: exit0, `0 errors, 0 warnings, 0 notes`
  (`compact-validation-types.txt`).
- LSP: no error diagnostics on the source or new test.
- Independent read-only `compact_boundary_review`: PASS, no actionable findings;
  verified supported project/session/revision normalization, both aliases, and
  meaningful real-store rejection tests. Operational compaction metrics only
  increment an in-memory counter and do not write a file.
- Strict no-excuse audit reports one existing size violation:
  `conversation_api.py`281 pure LOC (reconstructed baseline284). The fix removes three lines;
  the new test is93 pure LOC and has no violation. Broad route refactoring was
  excluded from this narrow boundary fix. Evidence:
  `compact-validation-no-excuse.txt`.

Architectural review: the changed source owns the existing conversation HTTP
surface; input is now parsed once at the framework boundary. No new helper,
variant dispatch, logger, defensive catch, or type escape was introduced.

## Exact source hashes

```text
src/antigravity_k/api/routes/conversation_api.py
ba5f8cdbd77ea0445780ae65b13fb69119348d3fc39563d941948d59f2fa5f53
tests/test_conversation_compact_validation.py
2d2242c3dc54b7e5ff339715cd64e9d98008372c5b51aebd204f3df4d63ea01f
src/antigravity_k/api/contracts/conversation.py (unchanged)
7c380ce882cc9b3c99c83f863096639a57864ea90bfc9edc697585bedf38d56c
```

This evidence covers the compact boundary only. Append/fork still manually call
their models' `model_validate`; a similar invalid-payload exception mapping is a
source-only follow-up, not an observed failure or an edit in this scope.
