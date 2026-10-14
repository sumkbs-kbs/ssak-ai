# /// script
# requires-python = ">=3.13"
# dependencies = ["chromadb==1.5.9"]
# ///
# How to run: node supervisor.mjs uses the existing project Python; never install.
"""One native Chroma lifecycle probe using only precomputed embeddings."""

from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from typing import Final

RUN: Final = Path(os.environ["CHROMA_QA_RUN"])
PROJECT: Final = RUN / "runtime/project"
PERSIST: Final = RUN / "runtime/persist"
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def phase(name: str, **details: JsonValue) -> None:
    print(json.dumps({"phase": name, "pid": os.getpid(), **details}), flush=True)


phase("before_import")
from chromadb.api.models.Collection import Collection

from antigravity_k.engine.rag_indexer import RAGIndexer
from antigravity_k.engine.vector_store import VectorStore

phase("imports_complete", chromadb_version=version("chromadb"))
modules = []
for name, module in tuple(sys.modules.items()):
    filename = getattr(module, "__file__", None)
    if filename and (name.startswith("chromadb") or name in {"antigravity_k.engine.vector_store", "antigravity_k.engine.rag_indexer", "antigravity_k.engine.chroma_lifecycle", "antigravity_k.engine.long_context_fusion"}):
        file = Path(filename)
        if file.is_file():
            modules.append({"module": name, "path": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
(RUN / "module-bindings.json").write_text(json.dumps(modules, indent=2))


def open_store(label: str, expected: int) -> VectorStore:
    phase(f"{label}:before_vector_store")
    store = VectorStore(str(PERSIST), collection_name="project_code")
    phase(f"{label}:constructed", client_id=id(store.client), collection_id=id(store.collection), closed=store._closed)
    phase(f"{label}:before_rag_indexer")
    indexer = RAGIndexer(project_root=str(PROJECT), vector_store=store)
    phase(f"{label}:rag_indexer_constructed", indexer_id=id(indexer))
    phase(f"{label}:before_get_stats")
    stats = store.get_stats()
    assert stats["count"] == expected, stats
    phase(f"{label}:count_verified", count=expected, client_id=id(store.client), collection_id=id(store.collection), closed=store._closed)
    return store


def close_store(label: str, store: VectorStore) -> None:
    phase(f"{label}:before_close", client_id=id(store.client), collection_id=id(store.collection), closed=store._closed)
    store.close()
    assert store._closed and store.client is None
    phase(f"{label}:closed", closed=store._closed, client_is_none=store.client is None, collection_id=id(store.collection))


first = open_store("fresh_empty", 0)
close_store("fresh_empty", first)
second = open_store("reopened_empty", 0)
phase("before_precomputed_upsert")
match second.collection:
    case Collection() as collection:
        collection.upsert(ids=["owned-precomputed-row"], embeddings=[[1.0, 0.0, 0.0]], documents=["owned deterministic fixture"])
    case _:
        raise RuntimeError("Native collection is required for the precomputed fixture")
assert second.get_stats()["count"] == 1
phase("precomputed_count_verified", count=1)
close_store("reopened_empty", second)
third = open_store("reopened_persisted", 1)
close_store("reopened_persisted", third)
phase("PASS_FRESH_OWNED_NATIVE_LIFECYCLE")
