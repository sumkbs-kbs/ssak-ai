---
title: System settings and search-extraction boundary verification
date: 2026-10-04
tags: [qa, settings, extraction, boundary]
---

Two narrowly scoped production defects were reproduced and corrected. No real configuration secrets, user home state, model calls, external providers, or main-server logs were read for this investigation.

## Candidate and ownership

Root-supplied HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. The shared tree contains unrelated changes; this report covers only these source bytes:

| File | SHA-256 |
| --- | --- |
| `src/antigravity_k/api/routes/system_api.py` | `610334086c50b0b0e0ff09b57d3ae45e7b46739be8316baa7627ade67d35c7a6` |
| `tests/test_system_api_boundaries.py` | `31727d560cfffb0d299c6fd640ca73d2703f30628bdd6fc5b796e980de220c67` |

The system API module has 2,121 nonblank/noncomment lines from the preexisting combined route structure. The approved fix is two narrow paths, adding one guard and removing the incorrect path calculation; no unrelated split or style migration was attempted. The new test module has 79 nonblank/noncomment lines. Its four-fixture parametrized test uses independent pytest-managed inputs rather than a new parameter container.

## Hypotheses and observed mechanism

1. **Confirmed: settings source selection differs from runtime configuration.** `get_settings()` calculated repository-relative `config.yaml`, whereas the existing `AppConfig.config_path` already selects `AGK_CONFIG_FILE` or the workspace/package fallback. Distinct synthetic marker fixtures returned `workspace` instead of `active` before the fix. The route now consumes the public `config.config_path` property; existing secret scrubbing and environment credential status remain downstream.
2. **Refuted: the settings secret scrubber caused the wrong source selection.** The marker mismatch occurs before scrubbing. After changing only the source path, synthetic API-key/PIN values remain absent from the response.
3. **Confirmed: search producer failure text was passed to extraction as successful content.** Actual `WebSearchTool.execute()` with enabled but invalid synthetic provider settings returns an anchored `Search Error:` string. The extraction route previously parsed it and returned `ok: true` with empty lists. It now returns the existing wire-compatible failure shape `{"ok":false,"error":"search_unavailable"}` before extraction.
4. **Refuted: all empty results are provider failures.** A valid no-results response and an article quoting error tokens both remain `ok: true` with empty extracted lists. The guard checks only the producer's anchored `Search Error:` / `Error:` prefixes, not arbitrary scraped keywords.

The QA harness initially used a synthetic `SEARCH_UNAVAILABLE` sentinel. That token is absent from production and was not treated as a production contract. The harness owner replaced it with the actual producer prefix before final socket verification.

## Red to green

Before production edits, the focused route suite produced:

```text
assert 'workspace' == 'active'
KeyError: 'qa_marker'
{'ok': True, ...} != {'ok': False, 'error': 'search_unavailable'}
3 failed, 2 passed, 1 warning in 10.40s
```

After the two changes, the same five cases produced `5 passed, 1 warning in 1.46s`.

Final related regression: **122 passed, 1 warning in 9.37s**. Exact retained output is in `system-boundary-regression.log`. Coverage consists of the five new boundary cases plus existing DataExtractor and synthetic search/extraction pipeline cases. It does not claim successful real external provider access or whole-application coverage. The warning is the installed Starlette/FastAPI TestClient deprecation for `httpx`; no dependency was installed.

All project imports occurred after the QA fixture applied `Path.home()` isolation, isolated current directory, explicit AGK configuration/task/data/project/auth paths, disabled dotenv/model-network access, and preserved the inherited `HOME`/`CODEX_HOME`. The final regression also redirected `tempfile.tempdir` inside the fixture so pytest session fixture files are removed with its temporary root. Earlier default pytest fixture directories were not broadly deleted because other agents run concurrently.

Reproduction entry point, using existing dependencies only:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
repository = Path.cwd()
sys.path.insert(0, str(repository / 'docs/qa/2026-10-04-full-live'))
from manual_api_fixture import isolated_home
with isolated_home() as root:
    temporary_root = root / 'test-temporary-files'
    temporary_root.mkdir()
    with patch.object(tempfile, 'tempdir', str(temporary_root)):
        import pytest
        files = ('test_system_api_boundaries.py', 'test_data_extractor.py', 'test_search_extract_e2e.py')
        code = pytest.main([*(str(repository / 'tests' / file) for file in files), '-q', '--tb=short'])
raise SystemExit(code)
PY
```

The legacy `test_search_numeric_contract.py` directly changes `HOME`; it was not executed by this worker. Exact financial serialization was instead checked through actual socket requests below.

## Personal HTTP QA

The worker started the existing QA driver's full production FastAPI application on an ephemeral loopback port, with lifespan disabled and isolated real stores. It used curl and a synthetic bearer token stored in a 0600 temporary header file. Only the external provider seam was deterministic; extraction and route serialization were real.

| Request | Observed |
| --- | --- |
| `GET /api/settings` | Selected isolated config returned `persistent_agency.enabled: false`; no repository settings were used. Raw YAML `off` parses as `false`, which is the existing settings serialization contract. |
| `POST /api/search/extract`, `qa-numeric` | HTTP 200, `ok: true`; exact `1234500000000` KRW, `9007199254740993` KRW, `3.5` percentage points, and `25` basis points. |
| `POST /api/search/extract`, `qa-unavailable` | HTTP 200, `{"ok":false,"error":"search_unavailable"}`. |

The child exited 0; its token header and isolated application root were removed. No main port 8000 process was changed, and no tokens were printed. Root separately owns the final full socket sweep and browser checks.

## Static checks and review

- Ruff lint and format check: both files clean.
- Basedpyright: source and new test, `0 errors, 0 warnings, 0 notes`.
- MCP LSP diagnostics: both files, `No diagnostics found`.
- Programming no-excuse audit: new test, `no violations in 1 file(s)`.
- Independent read-only `boundary_static_review`: **CLEAR**, reaffirmed against both exact SHA-256 values above. It verified the real producer prefixes, re-exported class identity, public configuration path semantics, preserved secret scrubbing, and focused cases. This is narrow source review, not global repository approval.

No debugger statements, production instrumentation, dependencies, Git mutations, authentication changes, settings-write changes, or frontend edits were introduced by this worker.
