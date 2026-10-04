# Experience canonical replay fix

Owned repository: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.
Changed `src/antigravity_k/engine/cognitive/experience.py`, `models.py` ExperiencePayload fields only, and new `tests/cognitive/test_experience_roundtrip.py`.

## Confirmed defects and repair

Five failing-first regression tests established: full canonical replay lost episode and evidence IDs; regenerated candidate IDs prevented retry deduplication; ingested committed records were queued for publication; legacy context references were fabricated as episode IDs; conflicting same-ID ingestion silently returned earlier content without reporting the conflict.

ExperiencePayload now carries additive optional `episode_reference` and default-empty `evidence_refs`. Core records emit typed evidence relations alongside all previous lineage relations. Full roundtrip retains every core field and its digest. `ExperienceCore.material_digest()` excludes only the candidate experience ID; selection reuses the committed core identity when all historical content matches. Distinct material/new identity appends another core without changing prior digest history. Same-ID changed history is rejected.

Ingestion uses the canonical episode field, accepts independently supplied legacy episode metadata, and refuses conflicting supplied metadata. Legacy records without episode metadata are readable but explicitly marked INCOMPLETE with missing `episode_reference`; no context ID is guessed as an episode. Ingested records remain inspectable in ledger records while their IDs are already marked sunk. Mixed pending new records and committed history drain correctly.

## Validation

- Initial dedicated suite: 5 failures, each matching the defects above (after correcting the test's project ID fixture).
- Dedicated tests plus episode and real-store tests: **68 passed**.
- Broader run including models: **128 passed, 1 unrelated architecture failure**. That failure flags imports in `live_trial_adapter.py` and `live_trial_model.py`, reported to parent for integration.
- Ruff checks for experience implementation and dedicated tests: passed.
- Real CanonicalStore commit/reopen/replay test persists one Experience plus one Evidence, returns the same selected Experience identity after restart, and queues zero duplicate publication.
- No debugger instrumentation or temporary runtime files left. No commits.

## API and review notes

Callers must use the ExperienceCore returned from `form_experience`, because a retry's candidate ID may be discarded in favor of the existing committed identity. `digest()` remains the full historical identity digest; `material_digest()` is the retry comparison helper.

Existing experience module remains oversized (718 nonblank/noncomment lines; test 134). Limited bugfix ownership and the programming skill's existing-codebase rule preserve surrounding module structure; broad extraction was not mixed into this concurrency-sensitive fix. New code retains the module's existing domain contracts and adds no provider/UI imports, semantic authority, interpretation promotion, or Constitution changes.

## Independent runtime linkage audit and integrity repair

Read current runtime bytes after parent changes. Confirmed think and rethink replace the effective request plan before Experience formation; dedicated test uses distinct old/revised IDs and verifies judgment, decision, governance, action, observation, outcome, and evidence retain the revised plan.

Source contract: `COGNITIVE_DATA_MODEL.md` line 53 requires missing Experience references to be INCOMPLETE with missing_references and excludes these from successful learning input. `EXPERIENCE_AND_LEARNING.md` Historical Core specifies Context/Judgment/Action/Observation/Evidence. This does not require every phase to occur in every episode.

Parent delegated only runtime `form_experience_core` and `_episode` integrity regions. Added optional missing_references to core formation. `_episode` marks missing links only for applicable reached phases: context after THINK; judgment when a judgment was returned; decision with readiness; governance when GOVERN occurred; action with ActionRun; observation when actual observation exists; outcome when comparison exists; evidence when selection establishes expected evidence. No artificial record IDs or reference targets are created.

Failing-first runtime regressions reproduced four false COMPLETE cases (context, decision, observation, outcome). Parent independently added actual synchronous Observation publication and plan linkage, which resolved the observation case through real provenance. Remaining missing refs are explicitly INCOMPLETE. A separate test verifies GOVERN without canonical governance record is incomplete, while simple episodes do not require an unperformed expansion GOVERN reference.

Final combined runtime validation: `uv run pytest tests/cognitive/test_runtime_experience_lineage.py tests/cognitive/test_experience_roundtrip.py tests/cognitive/test_episode.py -q --no-cov` → **51 passed**. Ruff runtime and dedicated lineage test checks passed. Root owns the downstream rule refusing INCOMPLETE cores as successful learning input. No global heuristic added to direct ExperienceCore construction, because it cannot infer which episode phases actually occurred.

## Learning provenance boundary

Parent delegated the follow-on real gap in `learning.py`: EpisodeObservation could claim an arbitrary Experience ID, and aggregation/proposal/validation never resolved its historical integrity. Added the optional `experience_lookup: Callable[[str], ExperienceCore | None]` constructor dependency to ExperienceEvaluator, CandidateProposer, and HeldOutValidator. A shared checker resolves every claimed ID and rejects an absent lookup/core, mismatched returned identity, non-COMPLETE integrity or missing references, mismatched episode, or observation evidence outside the core's evidence refs. The check runs independently at aggregation, candidate proposal, and held-out validation so manually built summaries/candidates cannot bypass it. No caller-controlled completeness boolean was introduced.

Mechanical EpisodeObservation values with `experience_id=None` continue to support isolated comparisons and existing synthetic fixture evaluation. This is deliberately not a semantic judgment or a global requirement to fabricate all optional phase records. Existing growth fixture observations have no Experience claims and need no new resolver. The live worker owns wiring all three LiveLearning constructors to its real ledger's `core` method.

Failing-first dedicated binding suite: eight failures and one existing mechanical-comparison pass before implementation. Expanded suite now covers the validator's independent refusal and a real ledger rehydration lookup. Dedicated binding + existing learning tests: **41 passed**. Ruff checks passed. Broad growth suite reached an unrelated runtime/FixtureThink protocol mismatch (`feedback` argument), reported to parent; it did not fail the new learning checks. No existing test assertions were removed or Experience IDs stripped to evade validation.

## Backward canonical wire compatibility — final model freeze

Parent identified an additive-schema compatibility risk. Reproduction removed only newly introduced fields from otherwise complete historical wire payloads: Experience `episode_reference`/`evidence_refs`, BrainJudgment `delta`, and ExecutionReceipt `detail`. Current parsing plus old `to_wire` injected defaults and changed immutable canonical digests. Exact downstream consumer is ContextBuilder.resolve_handle (`context.py`): it compares the digest of reserialized loaded records against issued handle content_digest.

Failing-first evidence: three absent-field roundtrip tests failed, three explicit-default tests already passed. A real CanonicalStore persisted the old wire with a scoped pre-upgrade serializer; after reopening with current code, an already-issued handle returned DIGEST_MISMATCH despite valid raw store digests. This was the fourth failing regression. The scoped serializer patch only constructs authentic historical bytes; context resolution and store reopening use real current implementations.

Minimal fix: `models.to_wire` excludes only these additive field names when absent from payload.model_fields_set. Explicit defaults and authored nondefault values remain unchanged; all older default fields retain their prior serialization semantics. No global exclude_unset, no schema-major bypass, no disk rewrite. Existing direct EntityPayload serialization used by context-budget tests remains supported and is now accurately included in the function signature.

Final validation: **10 dedicated compatibility tests passed** (absent fields, explicit defaults, nondefaults, actual issued-handle recovery); **128 tests passed** across compatibility, models, context, store, and Experience roundtrip suites. Ruff models/test checks passed. Model freeze communicated to parent, live worker, and final reviewers/QA. No further model/source edits planned.
