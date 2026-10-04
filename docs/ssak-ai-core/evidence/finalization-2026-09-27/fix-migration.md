# R04 migration lineage and R21 current-byte rehearsal

Completed 2026-09-27. Only production change: `src/antigravity_k/engine/cognitive/migration.py`. Tests: appended one WAL regression to `tests/cognitive/test_migration.py`; added `tests/cognitive/test_migration_snapshot_lineage.py`. No commits, central documentation edits, source checkpoints, source writes, or source deletion.

## Root cause and fix

The prior runner hashed a coherent read transaction, but import, replay, and rollback subsequently reopened the live SQLite database. A real WAL writer could change A→B→A; the first report passed while its mapping represented B, and a normal rerun against restored A failed with a mapping conflict.

`run()` now obtains one private SQLite backup through a read-only source connection. The plan's logical content digest/counts are computed from that backup; all import, replay, and rollback readers receive that same private backup explicitly. Its files are removed by TemporaryDirectory on completion/failure. The report retains the original source path and physical bundle observation. The final live-source logical digest comparison is separate: persistent external changes still produce source_unchanged=false and passed=false.

Physical file_bundle_digest remains an independent byte observation, not an assertion that transient live writes never happened. source_unchanged describes logical equality between captured input and final observation; an A→B→A sequence can satisfy it safely because B never enters the migration.

## Tests and toggle evidence

- `migration-red.txt`: failing-before-fix real-WAL regression.
- `migration-lineage-toggle-red.txt`: disables only immutable capture in an in-memory test subclass; exact A→B→A first report passes, then ordinary replay fails at `assert second.passed` with a changed-after-mapping conflict. Production files remain untouched.
- `migration-green.txt`: `42 passed in 1.76s` across migration, adapter, and dedicated lineage tests.
- `migration-ruff.txt`: scoped Ruff check passed.
- Dedicated coverage proves exact A→B→A replay stability and the distinct persistent-live-change failure.

Focused command: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_migration.py tests/cognitive/test_migration_snapshot_lineage.py tests/cognitive/test_legacy_adapter.py -q`.

## Actual R21 source rehearsal

`migration-current-audit.py` invoked the real migration CLI against `.antigravity_k/agency.db` and a fresh disposable target outside the repository. It independently recomputed every event mapping digest from the original source JSON payload, event type, parent, and legacy key and compared those digests to the produced mapping. Source opened read-only; no checkpoint or apply. The private backup, canonical output, and rollback corpus were removed; retained artifacts contain only aggregate counts/hashes.

`migration-current-results.json` records:

- CLI exit 0; passed=true; no errors; 194.942 seconds.
- Events imported/indexed/digest-verified/rollback-rehearsed: **56,961** each; idempotent replay=true.
- Objectives/tasks: **0/0**, explicitly marked unobserved operational paths; their coverage is synthetic, not claimed real.
- Full payload provenance: **56,961/56,961** mapping digests match independent source payload hashes.
- Provenance aggregate SHA256: `f07a70cc4dcc41be25556d0d2eb62ecd7a51f2dbb2dd8baf106ec44598ace3a3`.
- Source file SHA256 before=after: `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5`.
- Source logical content digest: `sha256:c67830796c6e976768f94f9b02cb6bf266a89b8a0b3338d39d540cfbb80f1e34`.
- Current migration.py SHA256 before=after: `22ea2874342c0654df30382c81efea9d9f63f5603b19673a02d847250c920fb2`.
- Current adapter/store/protected-target/CLI/test hashes before=after also recorded.

Canonical EventPayload intentionally contains structural event metadata rather than original text; this verification establishes full original-payload **mapping provenance**, not a claim that the canonical event record stores the original text verbatim.

## Remaining scope

No known migration blocker. Parent owns broader suite, cross-worker review, final evidence integration, and any commits. Formatting-only edits were not applied after current-byte audit; scoped lint passed. Do not attribute synthetic objective/task coverage to the real source.
