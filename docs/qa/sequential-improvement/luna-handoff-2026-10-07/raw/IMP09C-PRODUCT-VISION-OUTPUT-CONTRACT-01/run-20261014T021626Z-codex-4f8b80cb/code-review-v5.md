---
title: Structured output v5 independent code review
date: 2026-10-14
tags: [code-review, structured-output, offline]
---

codeQualityStatus: CLEAR
recommendation: APPROVE
blockers: []

Scope: IMP-09-C-PRODUCT-VISION-OUTPUT-CONTRACT-01, final v5 task-only.patch against captured dirty preimages. Approval is for this offline implementation, not actual model semantic quality, full repository gates, or publication.

## Findings by severity

- CRITICAL: None.
- HIGH: None remaining. Prior v4 H1 is resolved in the inspected v5 candidate.
- MEDIUM: None.
- LOW: No actionable correctness finding. Coverage limits below remain explicit.

## Prior H1 resolution

`src/antigravity_k/engine/structured_output.py:84` checks dialect declarations at each visited schema node. The walker includes dependencies and additionalItems as well as the supported draft2020-12 schema-bearing keywords. It inspects child schemas under properties without treating the property names as keywords; annotations and ordinary $ref/$schema property names remain data. Actual reference keywords are rejected before dispatch.

`src/antigravity_k/engine/structured_output.py:67` explicitly constructs Draft202012Validator with Registry(), whose default retrieval callback raises NoSuchResource without transport. The installed jsonschema/validators.py:339-347 carries initializer fields, including registry, through evolve; descend at 416-423 also supplies the existing resolver. referencing/_core.py:293-294 and 329 establish fail-closed retrieval. jsonschema/exceptions.py:241 confirms the wrapper subclasses public Unresolvable, so the new catch correctly converts resolution failures to StructuredOutputError. No known nested-dialect/external-fetch bypass remains in this inspected path. This is a bounded source review, not an exhaustive adversarial security proof.

The direct forged-contract regression drives nested Draft7 dependencies with trapped urllib/socket transport and expects a typed failure. The two ASGI regressions reject nested dialect/dependency reference requests before manager/provider/session/conversation calls. The positive data-property tests prevent overbroad keyword rejection.

## Source and artifact verification

Read work-scope.md, implementation-handoff.md, implementation-correction-v5.md, final-implementation-checks-v5/checks.json, the complete task-only.patch, current source, and installed validator/resolver source. Reconstructed the complete six-file unified patch from source-preimage/ and current files: exact equality with task-only.patch. Independently recomputed all six SHA-256 values and compared each current file with final-implementation-checks-v5/source-postimage/: all equal.

Owned files: chat.py, protocol_translator.py, structured_output.py, tests/test_chat_structured_output_contract.py, pyproject.toml, uv.lock. Dependency patch declares jsonschema >=4.26.0,<5.0 and referencing >=0.37.0,<0.38 without package version upgrades in the lockfile diff.

Read all five stdout/stderr pairs referenced by checks.json: focused 36 passed; Ruff lint/format, production basedpyright and memory compile exit0. Independently parsed JUnit: 36 tests, zero failures/errors/skips. Read and counted all 35 capture JSON artifacts: 14 real-manager calls and 14 native-provider terminal-mock calls. The remaining case is the direct closed-registry test. Two warnings are disclosed: existing asyncio_mode configuration and Starlette TestClient httpx deprecation.

The route rejects incompatible explicit structured modes before conversation/session operations; defaults public structured requests to direct mode; bypasses auto-intent, slash/self-capability and image-default routing; preserves selected model; normalizes native format; validates returned content before session assistant persistence; maps strict output failures to HTTP502. Legacy omitted/null/text behavior has representative coverage. No fenced-output stripping was added.

## Skill-perspective check

Ran the programming and remove-ai-slops perspectives after loading both SKILL.md files and the programming Python reference. No goal-relevant substantive violation found: request envelope parsing and model-output JSON/schema checking occur at trust boundaries required by this goal; dependency-backed validation avoids a bespoke schema validator. Schema text provides a stable immutable contract representation. Parsing at both route and independently callable translator boundaries is small duplication, not a separate speculative abstraction.

Reviewed production code and tests for removal-only tests, deletion pins, tautological assertions, implementation-constant mirrors, brittle prompt/prose tests, needless extraction/normalization, untyped escape hatches, and speculative abstractions. None found in the new production contract. Tests assert HTTP outcomes, preserved images/model selection, native wire format, counts of inference calls, rejection before side effects, and closed transport. Mocking is at the terminal transport plus isolated fixture dependencies; this proves routing/validation, not live model behavior. Existing large route/translator modules and the sizeable unannotated pytest fixture remain repository-style limitations; expanding this patch into unrelated refactoring is unwarranted.

## Exact limits and handoff

No tests, network calls, live models, production edits, or shared-file edits were performed by this reviewer. Verification was read-only inspection, artifact parsing/hash comparison, and source tracing. Historical actual-Vision FAIL_SEMANTIC is unchanged and was not rerun. Full application lifecycle/auth, actual Ollama schema conformance, and full-suite regression are not established here. Negative output tests assert HTTP502 but do not directly inspect persisted session storage; validation-before-persistence is independently source-traced. Slash/self-capability bypass is source-traced rather than separately represented in this focused suite.

The original implementation-handoff.md identifies v4; implementation-correction-v5.md explicitly supersedes its authoritative receipt. Do not cite v4 as final. No dedicated notepad path was supplied or present in the owned run root; work-scope and both handoff/correction documents provide the task record.

ULW status returned ULW_LOOP_PLAN_MISSING. Preserve the earlier v4 .omo review as requested; this v5 report has a unique owned-run path and a versioned fallback copy at .omo/evidence/IMP-09-C-PRODUCT-VISION-OUTPUT-CONTRACT-01-v5-code-review.md.
