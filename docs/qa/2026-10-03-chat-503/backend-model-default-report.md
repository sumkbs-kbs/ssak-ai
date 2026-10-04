---
title: Configured local model default regression fix
tags: [qa, models, regression]
date: 2026-10-03
---

The local model endpoint now recommends the configured reasoning profile when
it matches a discovered reasoning, coding, or general model with a known positive
parameter count. Matching uses the existing registry alias resolution and returns
the discovered model ID. The original running/size fallback remains intact when
the configured profile is unavailable. All discovered models remain selectable.

Changed files:
- `src/antigravity_k/api/routes/models_api.py`: 15 insertions, 2 deletions.
- `tests/test_local_models_default.py`: 13 deterministic HTTP regression cases.

Evidence:
- `backend-model-default-red.txt`: 8 expected assertion failures (125B chosen
  instead of configured 27B), 5 fallback cases passed.
- `backend-model-default-focused.txt`: 13 passed.
- `backend-model-default-green.txt`: 66 passed, 1 failed across the new tests,
  registry, local discovery, and model policy suites.
- `backend-model-default-config-drift.txt`: the independent config equality
  node reproduces the same unrelated failure alone.
- `backend-model-default-types.txt`: 0 errors, 0 warnings, 0 notes using
  `.venv/bin/python -m basedpyright --level error` on the changed route module.
- Ruff check, Ruff format check, `git diff --check`, and `py_compile` passed.
- `backend-model-default.patch`: complete route and new-test diff.
- `backend-model-default-hashes.txt`: SHA-256 fingerprints of changed code and
  both untouched config files.

Existing failure:
`tests/test_model_registry.py::test_bundled_default_config_matches_repository_default`.
The bundled `src/antigravity_k/config.yaml` contains an additional search section.
Both config files have empty staged and unstaged diffs and clean scoped status.
Neither was edited for this fix.

Review: model recommendation remains inside the existing endpoint, uses typed
discovery/profile objects, introduces no casts, catches, helpers, parameters,
or external writes, and has a failing-before/passing-after HTTP regression.
The existing route module is 348 nonblank/noncomment lines; the new test module
is 110. The inherited route size was retained to respect the explicitly narrow
bug-fix scope. No staging, commit, build, model loading, or global configuration
changes were performed. Tests isolated `Path.home` through `SSAK_QA_HOME` and the
provided sitecustomize helper.

Live backend restart and fresh-browser 27B reply validation are owned by the lead.
