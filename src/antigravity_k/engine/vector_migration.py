"""Explicit, separate migration of legacy (pre-binding) Chroma collections (r31).

Legacy collections were written before collections carried an embedding identity
(Chroma's implicit default embedding). The bound :class:`VectorStore` refuses them
("no automatic migration is allowed") and that refusal stays: this module never relaxes
identity checks and never stamps an identity onto an existing collection.

Instead it rebuilds the collection *next to* the original:

1. Snapshot the original persist directory (byte copy) and read only from the snapshot,
   so opening a Chroma client can never alter the original files.
2. Re-embed every stored document with the approved binding into a fresh staging
   directory through the normal bound ``VectorStore`` write path (same ids, documents and
   metadata).
3. Verify: identity metadata, approved model, dimensions, count, id set and per-id
   document/metadata correspondence, and a self-retrieval probe.
4. Only after verification, switch by two directory renames: original ->
   ``<dir>.legacy-<stamp>`` (preserved byte-for-byte), staging -> ``<dir>``.

Failure or abort before step 4 leaves the original in place; the incomplete staging
directory is renamed aside (``.failed-<stamp>``), never deleted, and a retry starts clean.
Running again on an already-migrated directory is a no-op (idempotent).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

from antigravity_k.engine.project_embedding_binding import (
    DIMENSIONS_METADATA_KEY,
    IDENTITY_METADATA_KEY,
    ProjectEmbeddingBinding,
    ProjectEmbeddingBindingError,
)

#: The only embedding model this migration may write with (run policy).
APPROVED_EMBEDDING_MODELS: frozenset[str] = frozenset({"nomic-embed-text:latest"})

_BATCH = 64


class VectorMigrationError(RuntimeError):
    """Migration refused or failed; the original collection is untouched."""


@dataclass
class MigrationReport:
    persist_dir: str
    collection: str
    state_before: str
    outcome: str = "not_started"
    legacy_count: int = 0
    migrated_count: int = 0
    dimensions: int = 0
    model: str = ""
    original_tree_sha256: str = ""
    preserved_as: str = ""
    failed_staging: str = ""
    checks: dict[str, bool] = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def tree_sha256(root: Path) -> str:
    """Deterministic digest over relative paths and file bytes (for preservation checks)."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _open_client(path: Path) -> object:
    import chromadb

    return chromadb.PersistentClient(path=str(path))


def _close_client(client: object) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        _ = close()


def _get_collection(client: object, name: str) -> object | None:
    from chromadb.errors import NotFoundError

    try:
        return cast(Callable[..., object], getattr(client, "get_collection"))(name=name, embedding_function=None)
    except (NotFoundError, ValueError):
        return None


def _read_all(collection: object) -> tuple[list[str], list[str], list[dict[str, object]]]:
    get = cast(Callable[..., Mapping[str, object]], getattr(collection, "get"))
    data = get(include=["documents", "metadatas"])
    ids = [str(i) for i in cast(Sequence[object], data.get("ids") or [])]
    docs = [str(d) if d is not None else "" for d in cast(Sequence[object], data.get("documents") or [])]
    metas = [dict(cast(Mapping[str, object], m or {})) for m in cast(Sequence[object], data.get("metadatas") or [])]
    return ids, docs, metas


def inspect_collection(
    persist_dir: str | os.PathLike[str], collection: str, binding: ProjectEmbeddingBinding | None = None
) -> str:
    """Classify a collection without modifying the original directory.

    ``absent`` | ``legacy_empty`` | ``legacy_with_data`` | ``bound_current`` | ``bound_other_identity``.
    Reads from a temporary byte snapshot so the original is never opened by Chroma.
    """
    root = Path(persist_dir)
    if not root.is_dir():
        return "absent"
    snapshot = root.with_name(f"{root.name}.inspect-{os.getpid()}-{time.time_ns()}")
    _ = shutil.copytree(root, snapshot)
    try:
        return _classify(snapshot, collection, binding)
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)  # our own temporary copy, never the original


def _classify(path: Path, collection: str, binding: ProjectEmbeddingBinding | None) -> str:
    client = _open_client(path)
    try:
        existing = _get_collection(client, collection)
        if existing is None:
            return "absent"
        metadata = dict(cast(Mapping[str, object], getattr(existing, "metadata", None) or {}))
        if IDENTITY_METADATA_KEY not in metadata:
            count = cast(Callable[[], int], getattr(existing, "count"))()
            return "legacy_with_data" if count else "legacy_empty"
        if binding is not None and metadata.get(IDENTITY_METADATA_KEY) == binding.identity.serialized():
            return "bound_current"
        return "bound_other_identity"
    finally:
        _close_client(client)


def migrate_legacy_collection(
    persist_dir: str | os.PathLike[str],
    collection: str,
    binding: ProjectEmbeddingBinding,
    *,
    abort_after_staging: Callable[[], bool] | None = None,
) -> MigrationReport:
    """Rebuild a legacy collection with ``binding``; switch only after verification."""
    from antigravity_k.engine.vector_store import VectorStore

    root = Path(persist_dir)
    model = binding.identity.wire_model
    report = MigrationReport(persist_dir=str(root), collection=collection, state_before="unknown", model=model)
    if model not in APPROVED_EMBEDDING_MODELS:
        raise VectorMigrationError(f"embedding model {model!r} is not approved for migration")
    stamp = time.strftime("%Y%m%dT%H%M%S") + f"-{time.time_ns() % 1_000_000:06d}"
    if not root.is_dir():
        report.state_before = report.outcome = "absent"
        return report
    report.original_tree_sha256 = tree_sha256(root)
    snapshot = root.with_name(f"{root.name}.migration-src-{stamp}")
    staging = root.with_name(f"{root.name}.migration-new-{stamp}")
    _ = shutil.copytree(root, snapshot)
    try:
        report.state_before = _classify(snapshot, collection, binding)
        if report.state_before == "bound_current":
            report.outcome = "already_migrated"
            return report
        if report.state_before in {"absent", "bound_other_identity"}:
            report.outcome = "refused"
            report.detail = f"collection state {report.state_before!r} is not a legacy collection"
            return report

        client = _open_client(snapshot)
        try:
            legacy = _get_collection(client, collection)
            assert legacy is not None
            ids, docs, metas = _read_all(legacy)
        finally:
            _close_client(client)
        report.legacy_count = len(ids)

        store = VectorStore(str(staging), collection_name=collection, embedding_binding=binding)
        try:
            for start in range(0, len(ids), _BATCH):
                chunk = [
                    {"id": ids[i], "text": docs[i], "metadata": metas[i]}
                    for i in range(start, min(start + _BATCH, len(ids)))
                ]
                store.upsert_chunks(chunk)
        finally:
            store.close()

        if abort_after_staging is not None and abort_after_staging():
            raise VectorMigrationError("aborted before switch")

        _verify(staging, collection, binding, ids, docs, metas, report)
        if not all(report.checks.values()):
            raise VectorMigrationError(f"verification failed: {report.checks}")
        if tree_sha256(root) != report.original_tree_sha256:
            raise VectorMigrationError("original changed during migration; not switching")

        preserved = root.with_name(f"{root.name}.legacy-{stamp}")
        os.rename(root, preserved)
        try:
            os.rename(staging, root)
        except OSError:
            os.rename(preserved, root)
            raise
        report.preserved_as = str(preserved)
        report.outcome = "migrated"
        return report
    except Exception as error:
        if staging.exists():
            failed = staging.with_name(f"{root.name}.failed-{stamp}")
            os.rename(staging, failed)
            report.failed_staging = str(failed)
        report.outcome = "failed"
        report.detail = f"{type(error).__name__}: {error}"
        if isinstance(error, (VectorMigrationError, ProjectEmbeddingBindingError)):
            return report
        raise
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)  # our own read snapshot, never the original


def _verify(
    staging: Path,
    collection: str,
    binding: ProjectEmbeddingBinding,
    ids: list[str],
    docs: list[str],
    metas: list[dict[str, object]],
    report: MigrationReport,
) -> None:
    client = _open_client(staging)
    try:
        new = _get_collection(client, collection)
        if new is None:
            report.checks["collection_present"] = False
            return
        metadata = dict(cast(Mapping[str, object], getattr(new, "metadata", None) or {}))
        dims = metadata.get(DIMENSIONS_METADATA_KEY)
        report.dimensions = dims if isinstance(dims, int) else -1
        declared = binding.identity.configured_dimensions
        report.checks["identity_matches_binding"] = metadata.get(IDENTITY_METADATA_KEY) == binding.identity.serialized()
        report.checks["approved_model"] = binding.identity.wire_model in APPROVED_EMBEDDING_MODELS
        report.checks["dimensions_match"] = (not ids and dims == 0) or (
            isinstance(dims, int) and dims > 0 and (not declared or dims == declared)
        )
        new_ids, new_docs, new_metas = _read_all(new)
        report.migrated_count = len(new_ids)
        report.checks["count_matches"] = len(new_ids) == len(ids)
        report.checks["id_set_matches"] = set(new_ids) == set(ids)
        old = {i: (d, json.dumps(m, sort_keys=True, default=str)) for i, d, m in zip(ids, docs, metas, strict=True)}
        new_map = {
            i: (d, json.dumps(m, sort_keys=True, default=str))
            for i, d, m in zip(new_ids, new_docs, new_metas, strict=True)
        }
        report.checks["documents_and_metadata_correspond"] = old == new_map
        if ids:
            get = cast(Callable[..., Mapping[str, object]], getattr(new, "get"))
            row = get(ids=[ids[0]], include=["embeddings"])
            emb = cast(Sequence[Sequence[float]], row.get("embeddings"))
            query = cast(Callable[..., Mapping[str, object]], getattr(new, "query"))
            hit = query(query_embeddings=[list(emb[0])], n_results=min(5, len(ids)), include=["distances"])
            top = cast(Sequence[Sequence[object]], hit.get("ids") or [[]])
            dist = cast(Sequence[Sequence[float]], hit.get("distances") or [[]])
            # The stored vector must retrieve itself (ties with identical documents are allowed).
            report.checks["self_retrieval"] = bool(
                top and top[0] and ids[0] in {str(x) for x in top[0]} and dist[0] and abs(dist[0][0]) < 1e-6
            )
    finally:
        _close_client(client)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m antigravity_k.engine.vector_migration --persist-dir D --collection C [--inspect]``.

    Explicit operator action only; never run implicitly at startup. Requires the approved
    binding (``AGK_RAG_EMBEDDING=ollama``); without it nothing is written.
    """
    import argparse

    from antigravity_k.engine.project_embedding_binding import configured_embedding_binding

    parser = argparse.ArgumentParser(prog="vector_migration")
    _ = parser.add_argument("--persist-dir", required=True)
    _ = parser.add_argument("--collection", required=True)
    _ = parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    persist_dir = cast(str, args.persist_dir)
    collection = cast(str, args.collection)
    binding = configured_embedding_binding()
    if cast(bool, args.inspect):
        print(json.dumps({"state": inspect_collection(persist_dir, collection, binding)}))
        return 0
    if binding is None:
        print(json.dumps({"outcome": "refused", "detail": "approved embedding binding is not configured"}))
        return 2
    report = migrate_legacy_collection(persist_dir, collection, binding)
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    return 0 if report.outcome in {"migrated", "already_migrated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
