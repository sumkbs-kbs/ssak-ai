# Independent additive-wire compatibility rereview

**Scoped verdict: PASS.** Base HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, dirty source hashes below. Read-only source review and executable verification; no source edits or live database use.

The `to_wire` adjustment removes only absent newly additive payload fields from Record serialization: Experience `episode_reference`/`evidence_refs`, BrainJudgment `delta`, and ExecutionReceipt `detail`. It uses each payload's `model_fields_set`, not value comparison or global `exclude_unset`. Consequently, legacy absent fields remain absent, explicitly authored default values remain present, and nondefault material delta/provenance/result detail remain present. All pre-existing default serialization remains unchanged. Direct payload serialization preserves its established model_dump behavior.

Read all ten dedicated compatibility cases. The decisive integration case persists pre-upgrade Experience bytes through the real CanonicalStore, reopens the store under current code, and resolves a previously issued content-digest ContextHandle. It now returns OK and raw-file digest verification agrees. Other cases assert exact old-wire roundtrip equality and digest equality for all three affected entity types, plus preservation of explicitly authored defaults and nondefaults.

Independent command:

```
PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/cognitive/test_additive_wire_compatibility.py \
  tests/cognitive/test_observation_atomicity.py \
  tests/cognitive/test_active_expansion.py \
  tests/cognitive/test_active_composition.py \
  tests/cognitive/test_surface_lifecycle.py \
  -q -p no:cacheprovider
```

**38 passed in 11.22s**, one pre-existing FastAPI/httpx deprecation warning. This also rechecks process-crash recovery/CAS, persisted read result detail reaching RETHINK and surviving reopened storage, authenticated installed composition, canonical readiness/digest/head blockers, and recovery Experience replay/deferred selection.

Final dependency hashes:

```
afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945  src/antigravity_k/engine/cognitive/models.py
38c31ac70f2854681fcaa16bd3f3b255daebbe451e7802503bf3bcfd18f58fca  tests/cognitive/test_additive_wire_compatibility.py
a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7  src/antigravity_k/engine/cognitive/action_types.py
f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c  src/antigravity_k/engine/cognitive/action_recovery_records.py
```

All other recovery, migration, and composition source hashes in the preceding final reports were rechecked and are unchanged. This final model hash supersedes the historical `0a600600...` model pin in those reports. No broader live-provider or operational approval is inferred.

## Bounded historical receipt recovery probe

**No issue found.** Used a temporary real CanonicalStore and current SQLite journal. Initial dispatch persisted an ExecutionReceipt in pre-upgrade wire form with `detail` absent. Reopened the store, submitted a current successful observation, then replayed that same original request. Observed:

```
accepted True replay True old_bytes_identical True old_republished False new_rows 2 verified_records 4 revision 1
```

Assertions verified: original receipt file bytes unchanged; original wire still lacks `detail`; original receipt ID never passed to the current sink; exactly two new rows (new receipt and Observation); new receipt has a different ID, supersedes the historical receipt, and preserves current observation detail; replay reuses the same new receipt; all four canonical records pass digest verification.

Source explanation: recovery retains the loaded original receipt Record in the reconstructed run. Reconciliation gives the updated receipt a new stable ID. `append_records` reuses existing canonical rows and sends only missing IDs to the sink. Thus decoding an absent old `detail` to the in-memory empty default does not republish a differently serialized record under the historical ID. No source changes or live data were involved.
