---
title: Tool-loop quality progress regression fix
tags: [qa, runtime, quality-gate, publish]
date: 2026-10-04
---

# Quality progress regression

## Scope

- Production file: `src/antigravity_k/engine/tool_loop.py`
- Existing regression scenario: `tests/test_chat_stream_producers.py::test_tool_loop_quality_status_is_progress_when_answer_is_evaluated`
- No test file change was needed; the existing test provided the failing-first regression guard.

## Diagnosis

The failure was reproduced with:

```text
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/test_chat_stream_producers.py::test_tool_loop_quality_status_is_progress_when_answer_is_evaluated
```

Captured red output is stored at `/tmp/ssak-quality-fix-red.txt` and ended with:

```text
E       assert []
1 failed in 1.02s
```

Three independent hypotheses were checked:

1. The quality gate might return a non-`QualityScore` value.
2. A zero-retry gate might return a real A-grade score with no user message.
3. The direct post-loop call might be missing a stream event context.

The runtime probe resolved these hypotheses with the exact values:

```text
quality_type= QualityScore
grade= excellent score= 1.0 user_message= '' should_retry= False
authoritative= False
chunks= [] last_output= 'short'
```

The quality gate correctly returned `QualityScore(A, 1.0)`, but `QualityGate.evaluate()` intentionally leaves `user_message` empty for A-grade results. `_post_loop_checks()` only yielded when that field was non-empty, so evaluation completed without a typed progress event.

## Fix

`_post_loop_checks()` now always emits one `ProgressChunk` for a concrete `QualityScore`. It preserves the gate-provided message for B/C/F results and derives the existing grade/percentage format for A results:

```text
📊 *품질: excellent (100%)*
```

The change is five added lines and one changed branch in `tool_loop.py`. Duck-typed test doubles with an explicit message keep the previous path.

## Verification evidence

Focused red-to-green scenario:

- Red artifact: `/tmp/ssak-quality-fix-red.txt`, `1 failed in 1.02s`.
- Green invocation: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/test_chat_stream_producers.py::test_tool_loop_quality_status_is_progress_when_answer_is_evaluated`.
- Green artifact: `/tmp/ssak-quality-fix-focused.txt`, `1 passed in 1.00s`.

Related stream and quality regression suite:

- Invocation: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q tests/test_chat_stream_producers.py tests/test_tool_loop.py tests/test_quality_output_contract.py tests/test_stream_whitespace_boundary.py tests/test_direct_stream_channels.py`.
- Artifact: `.omo/evidence/quality-fix-isolated-regression-20261004.txt`.
- Observable: `176 passed in 1.47s`.

Direct matching-surface probe:

- Invocation: the isolated `ToolLoopEngine._post_loop_checks([], 'chat', 'short', 'explain the calculation')` driver in the shell command recorded during this attempt.
- Observable: `chunk_count= 1`, `progress_types= ['ProgressChunk']`, `progress_text= ['📊 *품질: excellent (100%)*']`, `last_output= short`.

Static checks:

- Ruff invocation: `.venv/bin/ruff check src/antigravity_k/engine/tool_loop.py tests/test_chat_stream_producers.py`.
- Artifact: `.omo/evidence/quality-fix-ruff-20261004.txt`; observable: `All checks passed!`.
- Mypy invocation: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m mypy --ignore-missing-imports --no-strict-optional --exclude 'tests/|legacy_|demo/' src/antigravity_k/engine/tool_loop.py`.
- Artifact: `.omo/evidence/quality-fix-mypy-20261004.txt`; observable: `Success: no issues found in 1 source file`.

Current working-file hashes at handoff:

- SHA-256 evidence: `.omo/evidence/quality-fix-source-sha256-20261004.txt`
- `src/antigravity_k/engine/tool_loop.py`: `01042b76bfca7a2391ed1882005820078248c15b23ea548c320db7956fd76560`
- `tests/test_chat_stream_producers.py`: current content was unchanged by this fix; its repository state remains shared with the parent commit scope.

The focused regression was also rerun through the same isolated launcher:

- Invocation: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q tests/test_chat_stream_producers.py::test_tool_loop_quality_status_is_progress_when_answer_is_evaluated`.
- Artifact: `.omo/evidence/quality-fix-isolated-focused-20261004.txt`.
- Observable: `1 passed in 0.84s`.

No commit or Git push was performed by this worker.
