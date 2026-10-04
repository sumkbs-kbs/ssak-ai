---
title: Memory and voice delta code review
date: 2026-10-03
tags: [qa, code-review, memory, voice]
---

# Memory and voice delta review

## Scope and method

Reviewed only the requested deltas against `/tmp/ssak-external-baseline.JAxkH3`: bounded memory recall, WAV upload validation, their route integration, and their tests. Existing code outside those deltas (including pre-existing `cast`/broad exception use in `memory_provider.py`) is not a finding.

The codebase-memory graph was consulted first after the requested refresh. Its first query still reported no registered current project, so no duplicate index was created and the first pass used known-path inspection. The delayed retry succeeded for `Users-mr.k-program-coding-ssak_comp-ssak-ai-local-70b-upgrade`: it identified `MemoryManager.prefetch_all` and its system/legacy recall and stream callers. Newly added modules were not yet in the fast graph index and were inspected by bounded known-path reads.

Skill-perspective check: **ran**. I loaded `omo:programming` and its Python guidance, plus `omo:remove-ai-slops`. The new production code has no new `Any`, `cast`, `type: ignore`, or broad exception handler. The new tests are behavioral (HTTP response/call boundary and parser result/error), rather than deletion-only, prompt-text, or implementation-constant tests. No violation of either skill perspective was found in the final sources.

## Retake binding

This final retake is bound to Git `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. The previous strict-budget and WAV-parser findings are historical: both were reproduced at earlier hashes and are resolved at the source hashes below.

## Source hashes and verdicts

| File | SHA-256 | Verdict |
| --- | --- | --- |
| `src/antigravity_k/engine/memory_provider.py` | `a8b7c35beda61162a54f9c7f124c2d638605aa1f601b644802fd21efcc0e6001` | CLEAR: production integration uses the repaired composer. |
| `src/antigravity_k/engine/memory_recall_budget.py` | `033d7a8d44aacd7554e0ca9a1815179f3e0f9a002d186f8d7bd66b6783688c99` | CLEAR: final serialized context is bounded. |
| `tests/test_memory_recall_budget.py` | `50a4c30d3de8cb9ebd52a575536af4593886a7e19acd1547b2a3ad5fa5e7e2d6` | CLEAR: covers tiny conflicting positive budget, zero/no-fragment, and fitting winner preservation. |
| `src/antigravity_k/api/routes/voice_api.py` | `759d7020dad84b0f448ced8ff4659b544694b2aecfb6d34c16917d03ee59ab08` | CLEAR: streams a 25 MiB-bounded body and validates before STT. |
| `src/antigravity_k/engine/voice_audio.py` | `1837c57a51faf7ab3564c3869da3caa166f59ceb07daecb0048d0838a4c70565` | CLEAR: validates RIFF/WAVE completeness, supported PCM/IEEE float, unique `fmt `, and every data chunk's frame alignment. |
| `tests/test_voice_api.py` | `394e99522b0a03f7308ff91e2d32c6fc53d34be4ae4bebabd29d44ec7b9612a7` | CLEAR: behavioral HTTP tests prove rejection occurs before STT and body reads stream without `Request.body()`. |
| `tests/test_voice_audio.py` | `1b0e57556cb238d97889f2069ea3b0a59328322a3e5c0ccb590190e137098e1a` | CLEAR: covers float 32/64, PCM whitelist, duplicate `fmt `, and individually misaligned chunks. |

## Findings

### CRITICAL

None.

### HIGH

1. **[RESOLVED] Resolved authoritative facts could violate the configured recall limit.**

   - Code: `src/antigravity_k/engine/memory_recall_budget.py:36-50`; rendered resolved prefix: `src/antigravity_k/engine/memory_conflicts.py:76-108`.
   - Reproduction: construct two authoritative `MemoryFact` values for `preference:color` (`red` at durable-preference authority and `blue` at current-user authority), pass one ordinary `"x"` fragment, and set `MemoryRecallBudget(max_characters=10)`. The candidate is rejected by line 47, but line 50 runs conflict resolution over the empty selected set. The actual result was:

     ```text
     '[Resolved Memory Facts]\n[resolved:preference:color source=current scope=session] blue\n[memory_conflict key=preference:color suppressed=0]'
     137
     ```

   - Result: a 10-character budget yields 137 characters. This contradicts the stated strict post-resolution budget requirement and can grow without bound with resolved facts.
   - Retake result: the repaired helper performs a final length check at `memory_recall_budget.py:50-53`. Independent cases for budgets `0`, `1`, and `10` produced `""`; a budget of `1000` retained the `current_user` winner. The scoped regression suite passed: `90 passed in 1.67s`.

2. **[RESOLVED] WAV parser did not meet the requested encoding and chunk-completeness contract.**

   - Prior result: the parser accepted subsequent `fmt ` chunks, used aggregate data alignment, and rejected format code `3`.
   - Retake result: `voice_audio.py:79-94` now rejects duplicate `fmt ` and checks every data chunk; `:113-120` accepts IEEE float 32/64 and the PCM 8/16/24/32 whitelist. Independent driver results: float64 accepted; duplicate `fmt ` rejected; two individually misaligned chunks rejected. The route retains the correct ordering: body limit and validation precede `_transcribe` at `voice_api.py:43-63, 80, 90`.

### MEDIUM

None.

### LOW

None.

## Verification

- Initial targeted voice/memory run, with a temporary `HOME` established before imports: `.venv/bin/python -m pytest -q tests/test_memory_recall_budget.py tests/test_voice_audio.py tests/test_voice_api.py` — **20 passed**, one external FastAPI/Starlette deprecation warning. This passed before the memory fix and does not excuse the historical budget defect.
- Retake scoped memory run: `.venv/bin/python -m pytest -q tests/test_memory_recall_budget.py tests/test_memory_conflicts.py tests/test_preference_memory.py tests/test_project_memory.py tests/test_project_memory_aliases.py tests/test_global_memory_provider.py` — **90 passed in 1.67s**.
- Retake tiny-budget driver: budgets `0`, `1`, and `10` yielded length `0`; budget `1000` yielded the complete `current_user` winner in a 140-character context.
- Final independent voice run: `.venv/bin/python -m pytest -q tests/test_voice_audio.py tests/test_voice_api.py` — **23 passed in 1.36s**, one external FastAPI/Starlette deprecation warning.
- Final independent voice static run: `ruff check` — **All checks passed**; `basedpyright --level error` — **0 errors, 0 warnings, 0 notes**; `git diff --check` — no output.
- Inspected `voice-final-validation.md` and `voice-source.sha256`; their exact source binding matches the hashes independently calculated above. The preserved-baseline HTTP RED and parser RED are useful historical proof, while the final verdict relies on current-source tests and the independent retake.
- `git diff --check` over tracked touched files — no whitespace errors.

## Decision

- `codeQualityStatus`: **CLEAR**
- `recommendation`: **APPROVE**
- `blockers`: None.
