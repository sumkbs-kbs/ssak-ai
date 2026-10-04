---
title: Final WAV validation evidence
tags: [qa, voice, http, wav, red-green]
date: 2026-10-03
---

# Final WAV validation evidence

## Preserved-baseline HTTP RED

The original route was loaded from `/tmp/ssak-external-baseline.JAxkH3/voice_api.py` as an isolated `importlib` module before test imports. The shared source tree was not rolled back. Its `get_voice_service` dependency was replaced only with a transcriber call recorder.

```text
truncated: status=200 calls=1 transcript=baseline transcript
bad_chunk: status=200 calls=2 transcript=baseline transcript
baseline_request_body_calls=2
```

This is the behavioral RED: the preserved route accepted each invalid WAV, invoked the transcriber, and called `Request.body()` once per upload.

## Current parser RED

Before the final parser repair:

```text
.venv/bin/pytest -q tests/test_voice_audio.py
6 failed, 6 passed in 0.47s
```

The failures proved that IEEE float 32/64 WAV was rejected, 12-bit PCM was accepted, duplicate `fmt ` chunks were accepted, and two individually misaligned data chunks could pass when their aggregate length aligned.

## Current HTTP GREEN

```text
.venv/bin/pytest -q tests/test_voice_audio.py tests/test_voice_api.py
23 passed, 1 warning in 1.52s
```

The current mounted FastAPI route accepts valid PCM and IEEE float 32 WAV, rejects malformed WAV before the real `VoiceService` can call its transcriber, keeps `.webm` uploads unchanged, and reads a valid upload through `Request.stream()` while an instrumented `Request.body()` raises if called.

## Static and editor verification

```text
.venv/bin/ruff check src/antigravity_k/engine/voice_audio.py src/antigravity_k/api/routes/voice_api.py tests/test_voice_audio.py tests/test_voice_api.py
All checks passed!

.venv/bin/python -m basedpyright --level error src/antigravity_k/engine/voice_audio.py src/antigravity_k/api/routes/voice_api.py tests/test_voice_audio.py tests/test_voice_api.py
0 errors, 0 warnings, 0 notes

git diff --check
```

The LSP diagnostics tool returned `No diagnostics found` for `voice_audio.py`, `voice_api.py`, and `test_voice_audio.py`; the changed test API file also returned no error diagnostics.

## Source binding

```text
HEAD 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
voice_api.py    759d7020dad84b0f448ced8ff4659b544694b2aecfb6d34c16917d03ee59ab08
voice_audio.py  1837c57a51faf7ab3564c3869da3caa166f59ceb07daecb0048d0838a4c70565
test_voice_api.py    394e99522b0a03f7308ff91e2d32c6fc53d34be4ae4bebabd29d44ec7b9612a7
test_voice_audio.py  1b0e57556cb238d97889f2069ea3b0a59328322a3e5c0ccb590190e137098e1a
```

The selected WAV contract supports PCM 8/16/24/32 and IEEE float 32/64. Compressed and extensible WAV encodings remain intentionally unsupported and produce a typed validation error before STT.
