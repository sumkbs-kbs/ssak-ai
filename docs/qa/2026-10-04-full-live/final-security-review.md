---
title: Final current-pass security gate review
date: 2026-10-04
tags: [qa, security, final-gate, source-manifest]
recommendation: APPROVE
gateStatus: PASS
fullHead: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
sourceManifestSha256: c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5
---

# Final security review

## Recommendation

**APPROVE — PASS.**

`blockers`: none.

### CRITICAL blockers

None.

### HIGH blockers

None.

This is a leaf, read-only security review of the current-pass owned changes. It is not a whole-codebase audit and does not make findings from the repository's unrelated dirty tree.

## Immutable binding

- Full HEAD reproduced with `git rev-parse HEAD`: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- `docs/qa/2026-10-04-full-live/final-source-manifest.json` SHA-256 reproduced as `c123fe7d90b4b8a03a98d1d33ff3a36487c6238d092bd3bcaa431a75242681a5`.
- Every manifest entry was rehashed: all 56 owned production/test files, all 12 QA helper files, and `dashboard/DESIGN.md` matched its recorded SHA-256. No entry was missing or mismatched.
- `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`; the requested fallback report path is therefore used.

## Original intent

The user asked Root to exercise SSAK-AI as a real application, fix defects found across its functional families, and preserve the constitution and Brain/Body boundary, authentication and authorization behavior, project isolation, model-selection policy, and truthful reporting. The current fixes cover authenticated Skills, extraction, Wiki and palette flows; request-scoped read-only profile behavior; typed conversation validation; project-scoped settings and extraction error handling; shell-safe bridge plans with token indirection; explicit search receipts; trusted citation links; and truthful model, Studio, and job states.

## Desired outcome

The shipped application should preserve request and project scope, reject invalid mutation requests before state changes, avoid command injection and credential disclosure, avoid fabricated keys or launch claims, treat search snippets as untrusted data, link only trusted citation metadata, enforce explicitly required searches, keep read-only requests non-durable, and accurately label unavailable or unverified functionality.

## User outcome review

The reviewed artifact satisfies that outcome within its explicitly bounded live-verification scope.

- Authenticated dashboard calls use the shared request client. Skills and Publish parse external responses at the boundary and surface HTTP, authorization, malformed-response, and application-envelope failures instead of rendering false success or false emptiness. Palette note selection uses current selection/project/credential generation checks so delayed reads cannot overwrite newer state.
- Conversation append, compact, and fork routes accept typed Pydantic contracts before store mutation. Focused tests prove malformed and negative revisions return 422 without changing persisted bytes; valid requests preserve CAS revisions and explicit fork targets.
- Request-scoped read-only policy prevents `_save_profile` from creating or updating the profile file or GBrain projection while retaining in-memory session learning for a later authorized request.
- Bridge plans never embed an actual credential. Credential variables retain the literal `${SSAK_ACCESS_TOKEN:?...}` reference; model and base URL values are shell-quoted, and the Codex configuration argument is JSON-encoded then quoted. The focused regression executes generated fragments with a synthetic token and covers shell metacharacters.
- Explicit current-search wording produces a required `web_search` contract only when the tool is registered and policy permits it. A missing receipt fails the task and replaces the unsupported draft with an explicit failure. Policy denial wins over user wording.
- Citation reconstruction removes untrusted evidence blocks before extracting metadata URLs, accepts only HTTP(S) metadata lines, canonicalizes the result, and never promotes URLs embedded in result snippets. The footer uses only canonical URLs from cited source records. Tests cover injected snippet URLs, `javascript:` values, unknown citation IDs, forged footer labels, supported table headers, and unsupported table claims.
- Settings/extraction paths use the request project root, scrub secrets from returned settings, and distinguish producer-anchored search failures from legitimate empty results or articles containing error words.
- Model runtime state derives from a typed Ollama process snapshot and fails to `unknown` on unavailable or malformed process data. Studio disables unsupported export/registration instead of presenting no-effect actions as completed.
- Root's isolated production-route matrix reports 118/118 passing cases and the isolated CLI matrix reports 9/9. I independently reran `root_regression_driver.py`: 283 tests passed with one third-party Starlette/httpx deprecation warning. A read-only AST parse covered all 36 manifest Python source/test/helper files. The retained UI artifact reports 16 files and 133 tests passing, and the retained Vite build completed successfully.

## Security analysis by adversarial class

### Authentication, authorization, request binding, and stale races

No criterion-blocking defect found. The shared authenticated frontend seam is used for the changed Skills, Publish, extraction, Studio capability, Wiki read, Wiki search, and Vault sync calls. Project and selection generation guards prevent stale UI completions from taking ownership after a project, credential, or selection change. Conversation mutations bind an explicit project through the execution context before touching the store. Root's HTTP artifact includes isolated auth/project/store identities; no real home auth store or task-private content was read during this review.

### Command injection, malformed URLs, and snippet spoofing

No criterion-blocking defect found. Shell-sensitive bridge values are quoted and tested by actual shell parsing with synthetic values. Citation links are reconstructed from metadata outside untrusted evidence blocks. Invalid/non-HTTP metadata produces no invented link, and unsupported or unknown cited claims are removed by the citation fallback. The code does not execute generated bridge commands.

### Credential logging and fake-key/no-effect behavior

No criterion-blocking defect found. Bridge output contains an environment-variable reference rather than a token. The changed API clients request suppressed logging on publication/local-skill and Studio capability paths where response sensitivity matters. System settings responses retain secret scrubbing, and focused tests assert synthetic settings secrets and PINs are absent from the HTTP response. Disabled Studio operations have no launch handler and are labeled unavailable.

### File and project isolation

No criterion-blocking defect found. Vault reads and writes rely on `VaultEngine._safe_resolve` after the route rejects traversal parts; route errors preserve absolute/traversal/symlink escape failures. Search settings and extraction obtain the active request project root rather than the process working directory. The retained regression and HTTP drivers create temporary stores and project roots; their artifacts report cleanup and no access to real user stores.

## Programming and remove-ai-slops pass

I directly consulted `omo:programming` and `omo:remove-ai-slops` and did not accept prior review prose as proof. I reviewed the frozen production and test files for broad exception swallowing, unsafe TypeScript escape hatches, boundary parsing, credential interpolation, command construction, implementation-mirroring assertions, prose/prompt pins, deletion-only tests, tautologies, expected-values derived from outputs, unnecessary production extraction/normalization, and oversized modules.

No success-criterion-blocking slop or programming defect was found. The search language fixtures assert a machine-consumed routing decision and include positive, negative, quoted, optional, and denied controls. Citation tests assert persisted observable output and trusted URL provenance. Race tests use deferred responses and distinguish stale from current ownership. Conversation tests compare durable bytes across rejected requests. These are behavioral tests, not requested-removal checks.

The final code review explicitly documents the same programming/slop pass, including deletion-only, tautological, prompt/prose, unsafe-type, and unnecessary-normalization criteria. `skills-auth-code-review.md` and `studio-code-review.md` also explicitly cover both skill perspectives. The Studio CSS-class absence assertion is implementation-mirroring and the disabled epochs state is unnecessary complexity, but both are maintenance notes: neither makes the current Studio truthfulness criterion false.

Existing large modules, broad legacy boundary catches, and literal natural-language routing fixtures remain maintenance debt. They predate or surround the narrow fixes and do not prove failure of any stated current-pass success criterion, so they are notes rather than blockers.

## Checked artifacts

- `docs/qa/2026-10-04-full-live/final-source-manifest.json`
- all 56 paths in its `source_files` array
- all 12 paths in its `harness_files` array
- `dashboard/DESIGN.md`
- `docs/qa/2026-10-04-full-live/final-code-review.md`
- `docs/qa/2026-10-04-full-live/final-goal-review.md`
- `docs/qa/2026-10-04-full-live/source-inventory-review.md`
- `docs/qa/2026-10-04-full-live/core-batch-review.md`
- `docs/qa/2026-10-04-full-live/system-boundary-findings.md`
- `docs/qa/2026-10-04-full-live/skills-auth-code-review.md`
- `docs/qa/2026-10-04-full-live/studio-code-review.md`
- `docs/qa/2026-10-04-full-live/quality-verification.md`
- `docs/qa/2026-10-04-full-live/root-final-regression.log`
- `docs/qa/2026-10-04-full-live/root-final-ui-tests.log`
- `docs/qa/2026-10-04-full-live/dashboard-final-build.log`
- `docs/qa/2026-10-04-full-live/root-api-118.json`
- `docs/qa/2026-10-04-full-live/root-api-118.jsonl`
- `docs/qa/2026-10-04-full-live/root-cli-final.jsonl`
- `docs/qa/2026-10-04-full-live/root-profile-check.txt`
- `docs/qa/2026-10-04-full-live/root-live-search-retry.json`
- feature reports for bridge, conversation validation, citations, extraction, jobs, model status, notes search, profile policy, search contract, Skills auth/publish, and Studio truthfulness in the same evidence directory

No current-task notepad artifact exists. `EVIDENCE_LEDGER.md` and the feature reports are the available contemporaneous journals.

## Exact evidence gaps and non-blocking notes

1. **Final real UI search/citation retry unavailable.** The saved browser permission still denies control after the user allowed it. `root-live-search-retry.json` proves a search receipt and returned result, but the provider output did not retain the full official URL, so final clickable citation is `false`. The manifest and final goal report disclose this and do not claim a clickable citation or external-provider HTTP success. This does not violate a claimed success criterion.
2. **No browser/CDP alternate route was used.** Browser state, real home login/auth data, and task-private content remain uninspected as required.
3. **Several hardware, account, model-load, training/export, external-service, attachment/vision, native cancellation, reconnect, and scheduled-delivery scenarios remain partial or unavailable.** The final goal report and checklist describe them without promoting them to PASS.
4. **No fresh CVE/network scan was run.** The manifest contains no dependency delta or newly installed package, and the task explicitly excludes unnecessary fresh browsing.
5. **The knowledge graph was ready and used first.** It traced shell request-root binding, conversation revision checking, search settings, and citation reconstruction. Generated dashboard nodes created some noisy edges, so exact-file reads were used only after graph discovery.

## Blocker table

| Severity | violatedCriterion | Observation | evidencePointer |
| --- | --- | --- | --- |
| CRITICAL | — | None | — |
| HIGH | — | None | — |
