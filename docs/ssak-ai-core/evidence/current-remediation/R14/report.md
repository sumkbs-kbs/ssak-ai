# R14 report — swappable Brain adapter with real Context wire

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R14-V not claimed.

## Before

`SurfaceBrainPort` sent an opaque `context_ref` into a one-sentence observation prompt. That did not substitute for structured THINK over a canonical ContextPackage.

## After

- `render_context_for_brain` expands ContextPackage goal/state/evidence into provider wire **with text snippets**, listing `omitted_required` when the declared `context_limit` cannot hold them.
- `StructuredSurfaceBrainPort` loads a ContextPackage by ref, blocks INCOMPLETE (provider call 0), blocks overflow omissions (call 0), otherwise runs `StructuredBrainClient.think` on the rendered wire.
- Unresolvable refs optionally fall back to legacy `SurfaceBrainPort` observation (`delta=None`, not material THINK).
- `dependencies._attach_cognitive_surface` wires `StructuredSurfaceBrainPort` + shadow model adapter; legacy observation retained when no package store is present.
- Acceptance nodes `test_r14_a1`…`a5`.

## Acceptance

| ID | Result |
|----|--------|
| R14-A1 | PASS — provider wire includes goal/evidence text, not IDs alone |
| R14-A2 | PASS — low context_limit → CONTEXT_OVERFLOW, call 0 |
| R14-A3 | PASS — one repair then stop (`test_r14_a3_*`) |
| R14-A4 | PASS — two providers see same fixture goal/evidence IDs |
| R14-A5 | PASS — INCOMPLETE → CONTEXT_INCOMPLETE, call 0 |
| R14-E | PASS — this evidence tree |
| R14-V | NOT independent — self-review only |

## Commands

```sh
.venv/bin/python -m pytest tests/cognitive/test_brain.py tests/cognitive/test_surface.py -q -p no:cacheprovider
# 56 passed
.venv/bin/python -m pytest tests/cognitive/test_brain.py -q -p no:cacheprovider -k r14
# 5 passed
```

## Limits

- Self-review ≠ release GO / CR-14.
- R11 experience continuity across Brain swap remains R15-A6 / R22.
- Project canonical store path is optional (`.ssak/canonical`); without it SHADOW uses legacy observation for opaque refs.
