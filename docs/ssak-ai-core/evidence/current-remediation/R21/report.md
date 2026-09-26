# R21 report — current-bytes migration rehearsal

Status: **PASS (self-review limitation)** — 2026-09-26 KST  
Reviewer: implementer (same agent). Independent R21-V not claimed.

## Before

- Historical 56,961-event dry-run PASS existed, but R00 pin comparison showed 4/8 migration-related files drifted.
- Objectives/tasks were 0 in the registered source — not an operational distribution proof for those paths.
- Reusing the old PASS number without a current-code rehearsal would violate R21.

## After

1. **Source bytes (read-only):** `.antigravity_k/agency.db`  
   - sha256 `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5` (26,206,208 bytes)  
   - Pre/post identical; `source_unchanged=true`; `destructive_executed=false`
2. **Dry-run (separate target under `/tmp/ssak-r21-migr-*`):** exit 0, ~168.25s  
   - imported/mapping/canonical/index/digests/replay/rollback = **56,961**  
   - mapping_digest `sha256:3c4271900dae4066df40159f5f1b4d7fd9e6aadfe743bc491497a855d5a4d999`  
   - content_digest now `sha256:c6783079…` (R04 lineage; **not** historical `7d69ed65…`)
3. **Distribution (explicit):** real observed = events 56961, objectives **0**, tasks **0**.  
   - Report `distribution` field labels unobserved objective/task paths; synthetic coverage stays in `tests/cognitive/test_migration.py`.
4. **Code:** `MigrationReport.distribution` + R21 unit tests; pytest migration+adapter **38 passed**.

## Acceptance

| ID | Result |
|----|--------|
| R21-A1 | PASS — file sha256 + report source_unchanged; logical counts preserved |
| R21-A2 | PASS — real vs synthetic labeled in report + evidence |
| R21-A3 | PASS — idempotent_replay true; mapping stable on second run (suite + report) |
| R21-A4 | PASS — rollback_rehearsed true; source still readable (sha unchanged) |
| R21-E | PASS — this folder |
| R21-V | NOT independent — self-review only |

## Limits

- **Not** operational cutover / `--apply` (CLI still refuses).
- Objective/task **real** rows still absent — synthetic tests only for those paths.
- Vector/RAG/index semantic completeness not claimed beyond rebuild+digest counts.
- Self-review ≠ CR-14 / release GO.
- Mapping digest differs from historical run (new target root / current code) — expected; source file hash is the durable pin.

## Commands

```sh
shasum -a 256 .antigravity_k/agency.db
.venv/bin/python scripts/migrate_legacy_to_canonical.py \
  --source .antigravity_k/agency.db \
  --target /tmp/ssak-r21-migr-XXXX/canonical \
  --output /tmp/.../migration-report.json
.venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
```
