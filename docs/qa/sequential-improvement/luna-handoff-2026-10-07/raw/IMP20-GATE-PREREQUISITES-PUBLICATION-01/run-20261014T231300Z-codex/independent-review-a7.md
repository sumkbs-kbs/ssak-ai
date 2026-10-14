# Scoped final gate review

recommendation: APPROVE
scopeVerdict: APPROVE_SCOPED
blockers: []

Candidate: `f3a42e6f08ecdc112d8e651862fe99b2b02e2afe..a7c1dc2f`, candidate-git-boundary worktree. Read-only review; no tests, builds, network requests, or provider calls repeated. No ulw-loop plan exists; this is the requested fallback report path.

## Original intent and desired outcome

originalIntent: Continue the user's prioritized remediation with independently reviewable evidence, preserving unrelated edits and historical failures.
desiredOutcome: Correct path/API test isolation without changing authorization policy, refresh generated Python supply artifacts for the current lock, and repair dashboard contrast/navigation/telemetry contracts with honest scoped verification.
userOutcomeReview: These three bounded outcomes are supported. This does not approve all 23 release gates, an eight-hour soak, general availability, or a fresh 57-case final-source browser suite.

## Criteria and direct findings

- C1, authorization unchanged and tests exercise real denial: committed diff changes only the three test fixtures for this scope. Explicit workspace allowlists prevent inherited broad runtime roots from invalidating outside-path fixtures. Absolute/symlink rejection remains; the positive explicit allowlist test covers allowed siblings. Git denial observes zero actual subprocess calls; the initialized empty repository reaches one actual failing Git command and HTTP 400. No production path_security/git_api delta. Stored JUnit independently parsed: red 4 failures, green 4 passes, related 13 passes, zero errors. These are overlapping selectors, not 17 unique cases.
- C2, current-lock supply metadata: three bound hashes (lock, Python SBOM, notices) match committed a7. Generated differences are dependency version/addition changes consistent with the preceding lock remediation. Recorded generator and 27-test JUnit are present; JUnit has zero failures/errors. Dashboard SBOM is outside this delta.
- C3, user-visible dashboard behavior: semantic navigation selectors replace stale names and forced clicking; mobile menu opening remains a real click. Ancestor inert checks reflect inherited browser inert semantics and retain focus-cycle, restoration, and zero-inert-after-close checks. Telemetry tests open the disclosure and require visibility before reading. The uptime clamp prevents a newly received observation from subtracting negative elapsed time; the new regression exercises observable 14M59S versus 15M00S and subsequent elapsed advancement, rather than asserting the implementation expression. Contrast changes reuse existing semantic CSS tokens. No accessibility rule suppression or weakened telemetry expected value appears in the diff.
- C4, source/build/evidence identity: all 44 path packet, 17 SBOM packet, and 361 dashboard packet manifest entries independently match byte sizes and SHA-256. Path green binding 5 entries, SBOM binding 3 entries, and current primary-review binding 475 entries match committed a7 bytes. All 106 recorded bundle files match committed bytes. Independently recomputed the 326-file dashboard/src digest using the documented sorted tuple repr method; it matches 4c68417e510b71c009d11027c938fed8d1c739cc3f55f7ed659f9a1aea652aea and the build pin. Exact `pnpm run build` receipt records exit 0; it was not rerun by this reviewer.
- C5, honest scoped outcomes and preservation: raw browser output retains 56 passed/1 failed before the uptime correction. Final C10 raw output records one passing browser selector; unit raw logs retain the failing reproduction and final 12 passes. The primary a7 observation records visible LIVE disclosure/uptime, palette focus/inert/Escape, and navigation to an empty chat input. Its cleanup is explicitly exit -15/reaped true, not graceful exit 0. Earlier manual eight-observation matrix records no serious/critical axe findings but belongs to the earlier source. No final full-suite inference is made.

## Programming and remove-ai-slops pass

Consulted both installed skills and directly inspected the complete non-generated committed diff plus the telemetry component. No new broad catch, unsafe cast, type suppression, needless production extraction, parsing, or normalization was introduced. The uptime boundary test can fail on the former implementation (raw failure confirms this). Path tests preserve real authorization and Git behavior, not mocked successful outputs. Existing reading-style test now checks a positive CSS width and actual width/min-width token consumption instead of an obsolete 240px literal; this remains source-structure coverage rather than layout proof, and actual browser layout observations provide the matching surface evidence. Existing oversized files and unrelated legacy tests are not new blockers for these criteria. No deletion-only, removal-pin, or tautological new test found.

No separate code-review report with explicit skill coverage exists in the supplied packet inventory. This direct pass supplies that coverage; absence of a duplicate report is not a blocker.

## Checked artifact paths

Base: `docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/` under the ROOT repository.

- `IMP20-PATH-API-BOUNDARY-RECHECK-01/run-20261015-path/`: result.json, handoff-ko.md, artifact-manifest.json, red/green/regression JUnit, green/source-binding.json, patch-reconstruction.json, protected-source-check.json.
- `IMP20-DEPENDENCY-SBOM-REFRESH-01/run-20261014T231100Z-codex/`: result.json, handoff-ko.md, artifact-manifest.json, checks-attempt-1 JUnit/source binding, generation receipt.
- `IMP20-DASHBOARD-RELEASE-SURFACE-01/run-20261014T230500Z-surface/`: result.json, handoff-ko.md, artifact-manifest.json, patch-reconstruction.json, build-source-v3.json, bundle-reproduction.json, build-reproduce-1/checks.json, browser-attempt-1/browser.stdout.txt, browser-c10-attempt-2/{checks.json,browser.stdout.txt}, telemetry-unit-{red,green}.txt, manual-attempt-5/manual-observations.json, primary-review-current/{source-binding.json,observations.json,cleanup.json}.

## Notes and exact evidence limits

- The handoff's shorthand `manual-observations.json` is actually at `manual-attempt-5/manual-observations.json`; it exists and is manifest-bound. Optional link clarification, not a missing artifact.
- Full final-source browser 57-case coverage, native model inference, whole release gates, and soak are not established here. The current-source primary manual pass is desktop-only; OS light preference was not an independently implemented light application theme.
- Original parent accessibility/witness attachments were unavailable after an earlier replacement; their raw historical logs and this scope's new failed C10 attachments are preserved. No assertion of restored original attachments is approved.
- Patch reconstruction receipts were inspected and bound; no patch application was repeated. Build success and manual interactions are audited from saved receipts/observations, not rerun by this reviewer.
- Graph lookup reported this project unindexed; parent documented an earlier 300-second indexing timeout, so exact committed Git paths were used without repeating indexing.

No criterion-specific blocker found. APPROVE_SCOPED for this immutable range only.
