# Final-byte R21 rehearsal

The registered 56,961-event source passed a fresh real CLI dry-run after the final models.to_wire change. Previous migration-current-* evidence remains historical and unchanged.

- CLI exit 0; passed=true; complete=true; errors empty.
- Imported/indexed/digest-verified/rollback records: 56,961 each.
- Idempotent replay=true; rollback rehearsed=true; source unchanged=true.
- All 56,961 original JSON payload mapping digests independently matched.
- Objectives/tasks 0/0: unobserved real paths, covered synthetically only.
- Source SHA256 before=after: `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5`.
- Models SHA256 before=after: `afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945`.
- All seven recorded code/test pins before=after; exact pins in migration-final-results.json.
- Total reported migration duration: 227.338 seconds.
- No source writes/checkpoints/apply; temporary backup, canonical target, and rollback corpus removed. Only aggregate hashes/counts retained.

Artifacts: migration-final-audit.py, migration-final-audit.log, migration-final-results.json. No repository code changed for this rerun.
