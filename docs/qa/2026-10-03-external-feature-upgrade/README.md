# Isolated manual backend QA

Run from `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai` with the existing `.venv`.
The driver declares PEP 723 metadata for documentation; use the commands below
without installing or resolving dependencies.

```sh
.venv/bin/python docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py --help
```

The `serve` and `library` commands create a unique `TemporaryDirectory`, patch
`Path.home()` before production imports, redirect config, data, home, cache, and
the task DB, and change cwd into that temporary directory. Repository source is
imported through its absolute `src` path. No user audio, model download, real STT,
search network request, user DB, vault, or production configuration is required.
The temporary directory is removed when the command exits.

## Voice and financial extraction through real HTTP routes

Create a caller-owned fixture directory and export four synthetic WAVs:

```sh
QA_DIR=$(mktemp -d /tmp/ssak-external-manual.XXXXXX)
.venv/bin/python docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py fixtures --output-dir "$QA_DIR"
.venv/bin/python docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py serve
```

Leave `serve` running and use a second shell. Set `QA_DIR` to the printed fixture
directory. The server binds only `127.0.0.1:8047`; port 8047 must be free. It mounts
the actual `system_api.router` and `voice_api.router` in a temporary FastAPI app.
The app has one QA-only observation endpoint and replaces two external ports:
`VoiceService(transcriber=...)` and `WebSearchTool.execute`. Production routers,
WAV validation, extraction, serialization, and request parsing execute normally.

```sh
curl -sS http://127.0.0.1:8047/qa/observations
curl -sS -w '\nHTTP %{http_code}\n' -X POST --data-binary "@$QA_DIR/truncated.wav" 'http://127.0.0.1:8047/api/voice/transcribe?suffix=.wav'
curl -sS -w '\nHTTP %{http_code}\n' -X POST --data-binary "@$QA_DIR/duplicatefmt.wav" 'http://127.0.0.1:8047/api/voice/transcribe?suffix=.wav'
curl -sS http://127.0.0.1:8047/qa/observations
curl -sS -w '\nHTTP %{http_code}\n' -X POST --data-binary "@$QA_DIR/pcm16.wav" 'http://127.0.0.1:8047/api/voice/transcribe?suffix=.wav'
curl -sS -w '\nHTTP %{http_code}\n' -X POST --data-binary "@$QA_DIR/float32.wav" 'http://127.0.0.1:8047/api/voice/transcribe?suffix=.wav'
curl -sS -w '\nHTTP %{http_code}\n' -H 'Content-Type: application/json' --data '{"query":"fixture financial figures"}' http://127.0.0.1:8047/api/search/extract
curl -sS -w '\nHTTP %{http_code}\n' -H 'Content-Type: application/json' --data '{"query":123}' http://127.0.0.1:8047/api/search/extract
curl -sS http://127.0.0.1:8047/qa/observations
```

Expected voice observations: malformed files return 422 while transcriber count
stays zero; valid PCM16 and float32 each return 200 with the synthetic transcript
and increase the count once. Expected extraction observations: one valid query
calls the controlled search once, numeric `query` returns 400 without another
call. Assess `numeric_data` and `extraction_log` for the source fixture's
`1조 2,345억 원`, `3.5%p`, `25bp`, `9007199254740993원`, and
`1조 0.0000000000000000000000000001만`, including source index
and raw text. Exact normalized values are respectively `1234500000000`, `3.5`,
`25`, and `9007199254740993`; preserve the last integer exactly regardless of the
wire representation's numeric or string type. The fifth normalized value is
`1000000000000.000000000000000000000001`; its `value` must be the same canonical
string. The observation endpoint includes
the original fixture and `SOURCE_PROOF` URL so outputs can be compared to inputs.
Stop the server with Ctrl+C after recording responses.

## Task race and memory composition through real libraries

```sh
.venv/bin/python docs/qa/2026-10-03-external-feature-upgrade/manual_driver.py library
```

This prints two JSON observation documents. The first uses a real temporary
`TaskStateStore` SQLite database and two independently constructed real
`BackgroundTaskRunner` instances, each with its own `TaskStateStore` on that
database. It creates a paused task with a step-7 checkpoint, then starts two
concurrent public `resume_task` calls and waits through the winner's public
`wait_task`. Expected evidence: exactly one `true`, one `false`, one
orchestrator execution, final status `done`, preserved `checkpoint output`, and
the working-memory checkpoint text in the resumed messages.

The second constructs the default `MemoryManager`, adds typed static providers
with an oversized fragment, duplicate fragments, and a later fitting fragment,
and recalls through `prefetch_all`. Expected evidence: default character budget
12,000, one duplicate occurrence, retained `backfilled recall`, and omitted
oversized content. Real `compose_bounded_recall` receives conflicting identity
facts: a one-character budget produces empty context; a 500-character budget
keeps the complete `new-name` winner with `current_user` provenance and suppresses
`old-name`. The driver reports observations; the root reviewer owns final QA.
