# Independent acceptance metadata contract review

codeQualityStatus: CLEAR
recommendation: APPROVE
verdict: APPROVED_SCOPED_OFFLINE
blockers: []

## Scope

Reviewed sealed run `docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-ACCEPTANCE-METADATA-CONTRACT-01/run-20261014T043024Z-codex-86e22b4940`. Only implementation change is run_harness.py:1267, replacing stale `format: "omitted"` with `json.loads(SCHEMA_JSON)`. One dedicated test was added. No product source or historical live evidence was changed. No notepad was supplied. This reviewer read source/artifacts and calculated hashes; did not execute tests, harness, HTTP, servers or inference. Only this external report was written.

## Findings by severity

CRITICAL: none. HIGH: none. MEDIUM: none. LOW: none promoted.

The earlier preflight review missed this inherited stale acceptance field; it was a metadata defect despite the correctly schema-bound planned acceptance, request and native format guard. The original live acceptance remains immutable. This correction changes future metadata generation and must not be represented as a rerun or retroactive rewrite of the historical live record. The metadata field is not the native input classifier; actual live success requires its own raw-request/response/gate validation, independently of this offline repair.

## Verified writer behavior

At run_harness.py:1256-1272 the supervisor builds acceptance with the schema object, serializes it once, calls write_once, and enters frozen state. Product reservation follows at line 1285; provider reservation/wire occurs later through the existing callback. Existing write_once uses exclusive creation and preserves no-overwrite behavior.

The new test drives real supervise_once, immutable writer and journal with an in-memory adapter. The expected complete schema is independently declared and compared with saved acceptance, request envelope, profile, planned acceptance and schema file. Interceptors observe identical saved acceptance bytes at both reservations and both mock wire entries; frozen precedes reserved and dispatched. The test verifies one mock product and provider call, zero socket attempts, unchanged binding/parent acceptance, and FileExistsError on overwrite with original bytes retained. This is behavioral artifact coverage rather than a source-text or requested-removal assertion.

## Artifact verification

- Harness SHA: bb7634481545055b56e691c5fe96992e29d9a1787eef041d29e6d037a199d01b.
- Test SHA: 28e9c308a46ed3fd168024439300e7f15a062703178a5dea9457af934f3574aa.
- Green captured acceptance SHA: dd684fe0aa0feaf68042251f3a190c16ecdec5d35e424ddb4039294fa3d369da.
- Inspected red/green command receipts, source hashes, JUnit and stdout: one failing test before, one passing test after. Four final static commands exit zero; captured lint/format/type outputs agree. Compile is an in-memory compile with empty stdout, not missing success text.
- All 90 sealed artifact file hashes match.
- All 144 parent baseline entries and all 28 protected source hashes match current bytes.
- Staged paths remain 97; independently calculated `git diff --cached --binary` SHA is 84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f, matching baseline.

The fixture retains `INCONCLUSIVE_CLEANUP_NOT_CONFIRMED` and cleanup_failed state because OfflineAdapter supplies no OS exit/reap facts. That is not a cleanup PASS and does not negate the independently observed metadata-specific PASS. Two recorded test invocations total two mock product/provider calls each; none are live inference.

## Skill perspective and disposition

Applied previously loaded omo:programming and omo:remove-ai-slops perspectives. No material violation: minimal writer repair, existing serialization/immutable writer reused, real artifact ordering and rejection tested. No deletion-only, prompt-prose, tautological or implementation-constant-only test substituted for behavior. No new parsing abstraction, untyped escape hatch or production normalization was introduced.

Approve this scoped offline metadata correction. It issues no live authorization, upgrades no historical failure, claims no OS cleanup verification, and leaves overall IMP09 PARTIAL / ledger NOT_RECOVERED unchanged.
