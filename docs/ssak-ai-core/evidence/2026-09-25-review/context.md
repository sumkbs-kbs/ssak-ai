---
title: Cognitive Core local context consistency review
date: 2026-09-25
status: FAIL-current-summary-consistency
tags: [cognitive-core, review, context, evidence]
---

# Context consistency review

Verdict: **FAIL for consistency of current summaries**. This does not mean the implementation fails. This leaf reviewed documentation only; runtime and source verification belong to the execution/review lanes. Exact HEAD at start and finish: `6be0263d121c1e2a7ade92d3127af226c5e0581f`. Existing dirty `evidence/state_claims.json` and other reviewers' output were preserved. No source, constitutional text, or historical evidence was changed.

## Findings requiring documentation work

1. `IMPLEMENTATION_REPORT.md` §§6–10 still presents design-only delivery, no runtime, no migration, no runtime tests and no benchmark. It is dated September 22, but its title and current-status wording make it unsuitable as the current implementation report. Preserve it as an explicitly dated design snapshot or add a current status section that points to the later implementation evidence.
2. `ARCHITECTURE_REVIEW.md:1004–1016` lists stale remaining conditions: baseline/benchmark/model reconciliation, Vault concurrency, provider context window, and all T11 surface QA. September 24 additions in the checklist and T11 §§5–7 report many of those closed. Reconcile the remaining-condition table with the newest scoped evidence, without converting module PASS to integrated PASS.
3. `ACCEPTANCE_CHECKLIST.md:54–55` marks T03 complete and says A–D fulfilled, but its immediately following paragraph still says the real provider-window check is NOT_RUN and the row must not be checked. README:72 reports that window check completed. Update the stale paragraph to cite the actual later observation.
4. `evidence/T11_surface.md:4,12–14,185–195` and many roadmap bullets retain original partial status. Later §§5–7 explicitly close shadow wiring, real-model comparison, and resume/cancel. Keep the dated history, but place a latest-status pointer at the top so readers do not re-open completed work. The latest section at line 303 explicitly leaves ACTIVE verification.
5. `evidence/T13_live_pilot.md:13,41–44,102` says there is no live provider in the environment. T11:241–243 explicitly corrects that assumption and records a functioning local Ollama provider. Provider-port integration and pilot execution can still be unmet; provider absence is no longer a supported blocking explanation.
6. The current `state_claims.json` has four corrected claims, zero stale/unknown, 17 covered documents and seven mentions. Its green result only checks a narrow class of test-node status sentences. It does not validate the prose contradictions above and must not be described as a complete semantic documentation audit.

## Genuine remaining acceptance work

| Requirement | Current evidence boundary | Concrete close condition |
|---|---|---|
| T01b/T11 authenticated ACTIVE path | T11 latest section leaves ACTIVE; checklist leaves issuer authenticity and actual surface bypass behavior | Observe the authorized ACTIVE route with real tool executor, governance/readiness enforcement, receipt, canonical records, and denial/revocation cases. A stub-port unit test is insufficient. |
| T02/P11 API/CLI canonical integration | Checklist:52–53 closes actual Vault concurrency but leaves user-route integration; T11 shadow is observational | Trace and exercise actual API/CLI execution through canonical persistence, including restart/recovery, then distinguish routes still deliberately legacy. |
| T12 real-data migration dry-run | At this review's 2026-09-25 snapshot, T12 used synthetic SQLite; this historical finding was superseded by the 2026-09-26 registered agency.db full dry-run in [new evidence](migration-real-post-independent-review-2026-09-26.json) | Registered snapshot: 56,961 events fully rehearsed read-only with source/hash/count invariance and rollback rehearsal. Remains unobserved: objective/task rows (0 in source), other DB distributions, destructive apply and operations approval. |
| T13 live pilot | Harness and deterministic fixture pass; actual provider trial remains NOT_RUN | Connect a real trial port, pre-register live spec/splits/metrics, record actual provider/model/hardware/decoding and bounded budget, execute paired Fresh/Mature trials, report distributions and limitations separately from fixtures. |
| Current-tree verification | Historical reports use earlier SHAs/digests | Re-run required applicable gates on the final tree and preserve observed failures with their ownership; do not copy old PASS counts. |
| Final summary synchronization | Findings above | One current remaining-work table, consistent checklist/report/README/architecture review, historical snapshots labeled as history. |

The table identifies requirements documented as unmet, not a source-code assertion that every feature is absent. The main source review must resolve which are implementation gaps versus verification-only gaps.

## Human-only decisions and deliberate deferrals

- Constitutional meaning, protected authority, human ceiling, project premise changes require explicit human decision under README:24. None is necessary merely to synchronize documentation or verify existing behavior.
- Production activation and any new authority grant are distinct from an isolated test under an already authorized grant. Historical wording “person decision required” must be interpreted against the current user's authorization, rather than used automatically to stop all engineering work.
- Destructive/in-place migration is NOT_RUN and explicitly refused by the existing dry-run contract. Real-data read-only rehearsal is a separate, non-destructive task.
- Formal human Architecture Review sign-off cannot be fabricated by the agent. The agent can complete the evidence package and accurately report its own technical review.
- Live pilot provider/budget selection needs a concrete bound; a previously authorized local provider need not be requested again. Confirmatory statistical claims require a separately registered sample design. Pilot-only reporting remains valid and must not masquerade as confirmation.
- Advanced graph/meta-learning/default multi-brain and widening learned policies into Core remain deferred; lack of live evidence is not grounds to invent complexity.
- Vector/RAG index rebuild is explicitly outside T12's canonical-index scope. sdist byte reproducibility is a documented backend limitation with a bounded exception, not a cognitive-core feature backlog. Cross-scope regression ordering/intermittent test-process termination are separate observed limitations, not permission to mark old failures green.

## Reviewed snapshot digests

Read-only commands: `git rev-parse HEAD`; document listing and focused `rg`, `awk`, `sed`, `cat`; `git status --short docs/ssak-ai-core`; `shasum -a 256` for the following snapshots. All commands completed with exit 0. No runtime tests were run by this leaf.

| Document | SHA-256 |
|---|---|
| IMPLEMENTATION_REPORT.md | ca6394b8d93e8d3e7a7237fde8f7004a1a9f04bed2f8e0b2c36ec637cea4b4a2 |
| IMPLEMENTATION_ROADMAP.md | a1dc9933bdf93215ff655e326767429c670383613c2ee9ee333d6bfae48b3437 |
| ACCEPTANCE_CHECKLIST.md | bca2ba8d86ff1f68c95ad298f7157997b7df85501266be83800439b0f89ab2ed |
| ARCHITECTURE_REVIEW.md | 8d4c66ab2c181eabeebd2aebbefd06fb5d6af6efd47efccfe53616e24db77dd4 |
| evidence/T11_surface.md | 3f4a4c3bff518df23c630d59e46006fd2bebb4acaf17c2dd37901d84a0f88e52 |
| evidence/T13_live_pilot.md | ac687e346de2f29960eb4363a5617b2238c788c0df69bd6b4b7b32c455f08fac |
| evidence/T12_migration.md | ae3e5b5b54a27818742c9a2c26140626148bad1e4557204dd0ac2c8fa18b0877 |
| evidence/state_claims.json | 9f32560bab8fdadd17275c3d75f875ebe41591ae91b3ccfc65ebc05dc56fbd27 |
