---
title: Voice upload validation evidence
tags: [qa, voice, http, wav]
date: 2026-10-03
---

# Voice upload validation

이 문서는 첫 구현 후보의 기록이다. 아래 15개 시험과 최초 ImportError는 최종 후보의 인수 근거로 사용하지 않는다. 원본 HTTP가 손상 WAV를 추론에 전달한 실제 실패 재현, PCM·IEEE float 보완 후 23개 시험, 최종 파일 해시는 [voice-final-validation.md](voice-final-validation.md)에 있다. 최종 독립 판정은 [memory-voice-review.md](memory-voice-review.md)를 따른다.

## Red boundary

Invocation:

```text
.venv/bin/pytest -q tests/test_voice_api.py tests/test_voice_audio.py
```

Observed before the implementation: exit `2`; `tests/test_voice_audio.py` could not import `antigravity_k.engine.voice_audio`.

## Green HTTP integration

Invocation:

```text
.venv/bin/pytest -q tests/test_voice_api.py tests/test_voice_audio.py
```

Observed after the implementation: exit `0`; `15 passed, 1 warning in 1.47s`.

The HTTP scenarios use a real `VoiceService` and a transcriber call recorder. A generated PCM RIFF/WAVE body reaches the recorder once. Empty, oversize, truncated, and bad-chunk WAV requests return `422` or `413` and leave the recorder empty. The `.webm` route still reaches the recorder unchanged. The existing malformed suffix query remains `422` before transcription.

## Static verification

```text
.venv/bin/ruff check src/antigravity_k/engine/voice_audio.py src/antigravity_k/api/routes/voice_api.py tests/test_voice_api.py tests/test_voice_audio.py
All checks passed!

.venv/bin/python -m basedpyright --level error src/antigravity_k/engine/voice_audio.py src/antigravity_k/api/routes/voice_api.py
0 errors, 0 warnings, 0 notes

.venv/bin/python -m basedpyright --level error tests/test_voice_api.py tests/test_voice_audio.py
0 errors, 0 warnings, 0 notes
```

The direct `basedpyright` executable has a stale interpreter shebang pointing at a former checkout. Running the installed module through this checkout's `.venv/bin/python` completed the same type check.
