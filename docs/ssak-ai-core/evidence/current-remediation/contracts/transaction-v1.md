# C04 v1 — Canonical transaction identity

Producer → consumer: **R03 → R09/R11/R21**. Contract version: 1.0, documented 2026-09-27 from current dirty tree over HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.

Status: **scoped independent PASS for unchanged transaction identity and corrected immutable snapshot lineage at the review hashes**. Documentation reviewer: final_context (independent baseline provenance reviewer, now documentation reconciler). This authorship is not producer/consumer V approval. Baseline review found defects; later fixes and targeted implementer greens require current-hash final review. See [finalization review](../../finalization-2026-09-27/FINALIZATION_REVIEW.md). Historical evidence remains intact.

## Authority, inputs, outputs and invariants

CanonicalStore is the durable owner. stage(records, transaction_id, episode_id) binds a transaction to normalized content identity under the store SoftFileLock. Restaging identical content is idempotent; reusing an ID for different content conflicts. Only committed manifest visibility is eligible for Context/index/replay. A foreign pending transaction cannot be committed by substituting different content.

Stage files, canonical publication and Git commit can fail at distinct stages. recover resumes the original transaction without deleting evidence or changing identity. Consumers use committed IDs/receipts instead of assuming their attempted IDs committed. Migration pins logical content separately from file-bundle evidence and carries mapping identity with the target root. A valid-looking mapping manifest must still belong to the same registered source lineage; legitimate logical source append can resume, unrelated source cannot borrow it. The supported lock/snapshot proof is single-host local storage; no distributed NFS guarantee is asserted.

## Refusal and failure behavior

TransactionConflictError, TransactionNotFoundError, DuplicateRecordError, CanonicalDigestError and GitCommitError remain explicit. A migration conflict must imply passed=false.

## Exact interface inventory

Declarations below are extracted from the current source. Referenced Record/enums remain defined in the original modules; this document introduces no duplicate runtime type. Constructor/configuration details remain in the linked source and verification fixtures.

### src/antigravity_k/engine/cognitive/store.py

```python
def canonical_digest(wire: Mapping[str, object]) -> str: ...
```

### src/antigravity_k/engine/cognitive/store.py

```python
@dataclass(frozen=True, slots=True)
class ManifestEntry:
    record_id: str
    entity_type: str
    project_id: str
    relative_path: str
    digest: str
    wire: Mapping[str, object]
    def to_json(self) -> dict[str, object]: ...
    @staticmethod
    def from_json(value: Mapping[str, object]) -> ManifestEntry: ...
```

### src/antigravity_k/engine/cognitive/store.py

```python
@dataclass(frozen=True, slots=True)
class TransactionManifest:
    transaction_id: str
    created_at: str
    status: str
    episode_id: str | None
    entries: tuple[ManifestEntry, ...]
    def content_identity(self) -> tuple[str | None, tuple[str, ...]]: ...
    def to_json(self) -> dict[str, object]: ...
    @staticmethod
    def from_json(value: Mapping[str, object]) -> TransactionManifest: ...
```

### src/antigravity_k/engine/cognitive/store.py

```python
@dataclass(frozen=True, slots=True)
class CommitReceipt:
    transaction_id: str
    committed_ids: tuple[str, ...]
    git_commit: str | None
    reused_commit: bool
```

### src/antigravity_k/engine/cognitive/store.py

```python
@final
class CanonicalStore:
    def __init__(self, root: str | Path, *, git_committer: GitCommitter | None=None, git_enabled: bool=True, lock_timeout: float=30.0, write_guard: ProtectedWriteGuard | None=None) -> None: ...
    @property
    def lock_path(self) -> Path: ...
    @property
    def staging_dir(self) -> Path: ...
    @property
    def committed_dir(self) -> Path: ...
    @property
    def index_path(self) -> Path: ...
    def staged_manifest_path(self, transaction_id: str) -> Path: ...
    def committed_manifest_path(self, transaction_id: str) -> Path: ...
    def record_path(self, record_id: str) -> Path: ...
    def committed_manifests(self) -> tuple[TransactionManifest, ...]: ...
    def is_committed(self, record_id: str) -> bool: ...
    def read(self, record_id: str) -> Record | None: ...
    def read_many(self, record_ids: Iterable[str], *, committed_snapshot: Mapping[str, ManifestEntry] | None=None) -> Mapping[str, Record]: ...
    def list_committed(self, project_id: str | None=None) -> tuple[Record, ...]: ...
    def count_committed(self) -> int: ...
    def resolve(self, target_id: str) -> ResolvedTarget | None: ...
    def resolve_many(self, target_ids: Iterable[str], *, committed_snapshot: Mapping[str, ManifestEntry] | None=None) -> Mapping[str, ResolvedTarget]: ...
    def verify_digests(self) -> int: ...
    def rebuild_index(self) -> int: ...
    def stage(self, records: Sequence[Record], *, transaction_id: str | None=None, episode_id: str | None=None) -> TransactionManifest: ...
    def commit(self, transaction_id: str, *, message: str | None=None) -> CommitReceipt: ...
    def commit_records(self, records: Sequence[Record], *, episode_id: str | None=None, transaction_id: str | None=None, message: str | None=None, approvals: Sequence[HumanApproval]=()) -> CommitReceipt: ...
    def recover(self) -> tuple[str, ...]: ...
```

## Serialized boundary example

Illustrative partial mapping (not a complete valid Record envelope and not an execution result):

```json
{
  "transaction_id": "stable-transaction-id",
  "episode_id": "episode-1",
  "content_identity": "sha256:normalized-record-content"
}
```

Canonical records serialize through models.to_wire/from_wire; dataclass boundaries use their as_mapping methods or declared fields. Do not feed this abbreviated example directly to a production route.

## Executable producer/consumer verification

From repository root, using its existing environment:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest tests/cognitive/test_store.py tests/cognitive/test_migration.py tests/cognitive/test_migration_snapshot_lineage.py tests/cognitive/test_legacy_adapter.py -q -p no:cacheprovider
```

This command is a verification recipe, **not a new reported test run**. Existing concrete test scenarios include:

- `tests/cognitive/test_store.py :: test_r03_a1_second_stage_with_different_content_conflicts`
- `tests/cognitive/test_store.py :: test_r03_a2_identical_restage_is_idempotent`
- `tests/cognitive/test_store.py :: test_r03_a3_concurrent_different_payload_one_wins`
- `tests/cognitive/test_store.py :: test_r03_a3_cross_process_different_payload_one_wins`
- `tests/cognitive/test_store.py :: test_r03_a4_crash_recover_preserves_original_digest`
- `tests/cognitive/test_migration_snapshot_lineage.py :: test_original_payload_mapping_survives_live_wal_aba`
- `tests/cognitive/test_migration_snapshot_lineage.py :: test_live_wal_change_is_reported_separately_from_frozen_import`

Acceptance requires matching source/test hashes, observed success and refusal paths, and a separate reviewer recording scope and verdict. Full consumer/provider/deployment claims require their actual surface artifact; a producer suite cannot fill an unexecuted consumer slot.

## Pin and compatibility policy

Source and test SHA256 values are in [contract snapshot](contract-source-manifest.json), keyed by this contract ID. The original common specification digest is included there. Source freeze is bound to the final-source-manifest fingerprint below. Any later changed dependency invalidates this frozen snapshot until reviewed again. Consumers pin contract version plus that entry's source/test/spec digests; a breaking semantic change requires producer and consumer review together. Optional additive fields preserve old records; unsupported schema/ambiguous authority must not silently adapt. Frozen source fingerprint: `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2` over 1465 source/test/script/config files. This snapshot does not certify later dirty changes.
