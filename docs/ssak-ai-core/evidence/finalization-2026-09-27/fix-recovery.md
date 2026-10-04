# R10 recovery publication fix

Status: implemented; 56 targeted action tests pass.

## Changed behavior

- Observation publication now acquires SQLite `BEGIN IMMEDIATE`, checks the expected receipt/revision/status, appends canonical records, and only then commits the authoritative receipt/observation projection. Conflicting concurrent first observations have one winner.
- Sink errors and process death leave the existing pending projection unchanged. Stable UUID5 identities derive from the project/action/expected receipt/observation digest. Retrying after canonical append reuses the original stored records and timestamps and repairs the projection.
- An identical request with the original expected receipt is accepted as an idempotent replay; replay may also refer to the current projected receipt for existing callers. Changed observation or observed_at remains a distinct request. A stale conflicting request is refused.
- Receipt-less claimed actions accept an empty expected receipt ID. Recovery uses the already durable intent to reconstruct canonical records and an UNKNOWN base receipt without dispatching.
- Late dispatch receipt attachment cannot overwrite any published observation revision. In-process receipt inspection updates only after successful publication.
- Existing late-observation history remains append-only and does not mutate a settled projection.

## Files

- `src/antigravity_k/engine/cognitive/action_journal.py`: typed observation publication, serialized canonical-before-projection update, late receipt guard.
- `src/antigravity_k/engine/cognitive/action_lifecycle.py`: reconciliation can prepare a stable receipt without performing persistence/publication.
- `src/antigravity_k/engine/cognitive/actions.py`: delegates the extracted recovery operation; dispatch edits owned by other workers preserved.
- `src/antigravity_k/engine/cognitive/action_recovery.py`: recovery orchestration, replay identity, CAS retry, receipt-less recovery.
- `src/antigravity_k/engine/cognitive/action_recovery_records.py`: record conversion and observation digest.
- `tests/cognitive/test_observation_atomicity.py`: eight regressions using real CanonicalStore and SQLite.

## Evidence

Before fix, deterministic tests showed two conflicting first observations accepted; observation append failure left status `settled`; retry of the exact original request was rejected; receipt-less claim could not recover. New tests were run failing before the corresponding fixes. The late receipt overwrite and local cache regressions also failed first.

Final command:

`PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_observation_atomicity.py tests/cognitive/test_action_safety.py tests/cognitive/test_actions.py -q`

Result: `56 passed in 4.34s`.

Included actual OS-process tests: two independent processes forced to read the same initial receipt, and an independent process using `os._exit(23)` after canonical commit but before SQLite projection commit. Restart retry reuses original canonical timestamps/IDs; projection revision advances exactly once.

Ruff check on all six changed/created files: clean. `python -m basedpyright` on recovery/record/journal modules: 0 errors, 24 warnings (SQLite dynamic rows, protected context helpers, existing concatenation/unused-return conventions). The direct basedpyright executable has a stale interpreter path; invoking its installed module works.

## Scope / review notes

Journal publication assumes a single local SQLite journal paired with its canonical store. It does not claim distributed multi-host transaction semantics. Canonical records can exist ahead of the projection after an interrupted publication; retries retain those immutable records. No remote effects are dispatched by recovery.

Recovery uses existing typed dataclasses/Pydantic records; no new raw untyped input boundary or broad exception catch. Module responsibilities: journal publication, reconciliation preparation, recovery orchestration, record conversion. New/modified pure LOC: journal 216, lifecycle 149, recovery 243, record helpers 54, regression tests 198. Journal/recovery are in the warning band; further growth should split the specific touched responsibility. No temporary debug instrumentation, services, or commits were created.

API coordination: composition worker was informed that empty expected receipt identifies receipt-less claim recovery and that exact original-request replay now returns success instead of stale conflict.

## Final schema initialization race correction

A subsequent full-suite run exposed a separate schema startup race: concurrent processes both inspected columns before either completed ALTER TABLE, causing `duplicate column name: observation_digest` and blocking the one-effect process test. Parent stopped the then-running v6 inference attempt before this source update.

Correction: `_ensure_schema` now owns an explicit `BEGIN IMMEDIATE` transaction spanning table creation, column inspection, and all migrations. Its context commits schema changes before the caller starts claim insertion, receipt attachment, or observation publication. This also makes read-triggered legacy upgrades durable. All journal call sites use fresh connections before entering this helper; no active DML transaction is committed by it.

New `tests/cognitive/test_action_journal_schema.py` covers independent processes initializing a fresh database and upgrading the legacy three-column schema. A SQLite trace hook synchronizes the pre-fix first ALTER only when no explicit transaction exists, making the former TOCTOU fail deterministically. Both cases failed before the fix with duplicate-column errors (`observation_digest`, `action_record_id`). They pass after the fix and assert original intent data survives migration.

Validation: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_action_journal_schema.py tests/cognitive/test_action_safety.py tests/cognitive/test_observation_atomicity.py -q` → **37 passed in 4.27s**. Ruff for the journal and new test file: clean. Source freeze sent to parent, live owner, and independent reviewer; no further source changes planned.
