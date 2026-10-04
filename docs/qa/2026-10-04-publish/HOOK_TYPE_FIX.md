---
title: Chat TDD stream payload type fix
tags: [qa, typing, tdd, publish]
date: 2026-10-04
---

# Hook type fix

## Failure

The repository's pinned pre-commit Mypy run reported:

```text
src/antigravity_k/api/routes/chat.py:1050: error: Dict entry 0 has incompatible type "str": "str"; expected "str": "dict[str, str]"  [dict-item]
Found 1 error in 1 file (checked 570 source files)
```

The captured hook output is `/tmp/ssak-publish-commit-runtime-20261004.txt`.

The affected branch creates either a status payload (`dict[str, str]` value) or a final-content payload (`str` value) under the same dynamic channel key. The annotation inferred from the first conditional arm was too narrow for the second arm.

## Fix

`src/antigravity_k/api/routes/chat.py` now explicitly declares the payload as:

```text
dict[str, str | dict[str, str]]
```

The JSON output and both channel shapes are unchanged. This is a boundary typing correction only.

## Verification evidence

- Isolated TDD boundary tests:
  - Command: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest -q tests/test_chat_tdd_boundary.py`
  - Artifact: `.omo/evidence/hook-type-fix-chat-tdd-20261004.txt`
  - Result: `15 passed, 1 warning in 1.40s`
- Ruff:
  - Command: `.venv/bin/ruff check src/antigravity_k/api/routes/chat.py`
  - Artifact: `.omo/evidence/hook-type-fix-ruff-20261004.txt`
  - Result: `All checks passed!`
- Repository Mypy with the installed local checker:
  - Command: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m mypy --ignore-missing-imports --no-strict-optional --exclude 'tests/|legacy_|demo/' src/antigravity_k`
  - Artifact: `.omo/evidence/hook-type-fix-mypy-20261004.txt`
  - Result: `Success: no issues found in 570 source files`
- Diff check:
  - Command: `git diff --check -- src/antigravity_k/api/routes/chat.py`
  - Artifact: `.omo/evidence/hook-type-fix-diff-check-20261004.txt`
  - Result: exit code `0`, no output.

Current source SHA-256:

```text
4923ccab7de132b21d9d388423f8a1f96ca398db5057ef960db7930fcd33d67e  src/antigravity_k/api/routes/chat.py
```

No Git commit or push was performed by this worker.
