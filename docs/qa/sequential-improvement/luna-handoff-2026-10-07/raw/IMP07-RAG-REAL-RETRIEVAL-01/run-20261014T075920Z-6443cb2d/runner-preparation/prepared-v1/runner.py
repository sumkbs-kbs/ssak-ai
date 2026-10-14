from __future__ import annotations

import argparse
import importlib
import json
import resource
import shutil
import sys
import struct
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

import httpx

from control import (
    BASE,
    DIGEST,
    MODEL,
    Budget,
    Query,
    WireTransport,
    install_socket_guard,
    load_freeze,
    save,
    score,
    sha,
    validate_oracles,
    verify_manifest,
)


class SourceMetadata(TypedDict):
    source: str


class StoredRow(TypedDict):
    id: str
    document: str
    metadata: SourceMetadata
    embedding: list[float]


class Snapshot(TypedDict):
    collection_metadata: dict[str, object]
    rows: list[StoredRow]


class Match(TypedDict):
    id: str
    text: str
    metadata: SourceMetadata


class QueryResult(TypedDict):
    query_id: str
    project_id: str
    text: str
    matches: list[Match]
    elapsed_seconds: float


def snapshot(store) -> Snapshot:
    store.get_stats()
    collection = store.collection
    if collection is None:
        raise ValueError("Open collection unavailable for vector audit")
    rows = collection.get(include=["documents", "metadatas", "embeddings"])
    embeddings = rows["embeddings"]
    ordered = sorted(range(len(rows["ids"])), key=lambda index: rows["ids"][index])
    return {
        "collection_metadata": dict(collection.metadata or {}),
        "rows": [
            {
                "id": rows["ids"][i],
                "document": rows["documents"][i],
                "metadata": rows["metadatas"][i],
                "embedding": [float(value) for value in embeddings[i]],
            }
            for i in ordered
        ],
    }


def file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def make_registry(path: Path, *, peer: bool = False):
    from antigravity_k.engine.model_registry import ModelRegistry

    name = "fixture-precomputed-three-dimensions" if peer else MODEL
    config = {
        "models": {
            "embedding": [
                {
                    "name": name,
                    "repo": name,
                    "provider": "ollama",
                    "role": "embedding",
                    "dimensions": 3 if peer else 0,
                    "api_base": BASE,
                }
            ]
        }
    }
    save(path, config)
    return ModelRegistry(config_path=str(path)), name


def semantic(fixture: Path, out: Path, budget: Budget, wire: WireTransport):
    from antigravity_k.engine.embeddings import EmbeddingEngine
    from antigravity_k.engine.project_embedding_binding import ProjectEmbeddingBinding
    from antigravity_k.engine.provider_adapters.embedding_providers import (
        OllamaEmbeddingProvider,
    )
    from antigravity_k.engine.rag_indexer import RAGIndexer
    from antigravity_k.engine.vector_store import VectorStore

    def metadata(label: str, endpoint: str):
        budget.phase = label
        with httpx.Client(
            transport=wire, trust_env=False, follow_redirects=False, timeout=10
        ) as client:
            response = client.get(BASE + endpoint)
            response.raise_for_status()
            return response.json()

    def check_digest(payload) -> None:
        matches = [row for row in payload.get("models", []) if row.get("name") == MODEL]
        if len(matches) != 1 or matches[0].get("digest") != DIGEST:
            raise ValueError(
                "Installed model digest unavailable or changed; no inference permitted"
            )

    registry, name = make_registry(out / "owned-model-profile.json")
    engine = EmbeddingEngine(
        registry=registry, ollama_provider=OllamaEmbeddingProvider(transport=wire)
    )
    binding = ProjectEmbeddingBinding(
        engine, name, document_prefix="search_document: ", query_prefix="search_query: "
    )
    save(out / "binding.json", json.loads(binding.identity.serialized()))
    queries, oracles = validate_oracles(fixture)
    for source, destination in [
        ("corpus-a", "project-a"),
        ("corpus-b", "project-b"),
        ("outside-projects", "outside-projects"),
    ]:
        shutil.copytree(fixture / source, out / destination)
    a_root, b_root = out / "project-a", out / "project-b"
    a_path, b_path = out / "persist-a", out / "persist-b"
    sentinel_before = file_hashes(out / "outside-projects")
    stores = []

    def open_store(root: Path, persist: Path):
        store = VectorStore(
            str(persist), collection_name="project_sources", embedding_binding=binding
        )
        stores.append(store)
        return store, RAGIndexer(str(root), store)

    def query(indexer, item: Query, project: str) -> QueryResult:
        started = time.monotonic()
        before = sum(budget.counts.values())
        matches = indexer.search(item["text"], n_results=5, mode="semantic")
        if sum(budget.counts.values()) != before + 1:
            raise ValueError(
                "Each nonempty semantic query must make exactly one embedding request"
            )
        result: QueryResult = {
            "query_id": item["id"],
            "project_id": project,
            "text": item["text"],
            "matches": matches,
            "elapsed_seconds": time.monotonic() - started,
        }
        with (out / "query-results.jsonl").open("a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result

    try:
        check_digest(metadata("pre-tags", "/api/tags"))
        a, ai = open_store(a_root, a_path)
        b, bi = open_store(b_root, b_path)
        budget.phase = "index-a"
        a_chunks = ai.index_project()
        budget.phase = "index-b"
        b_chunks = bi.index_project()
        original_a, original_b = snapshot(a), snapshot(b)
        save(out / "initial-a-store.json", original_a)
        save(out / "initial-b-store.json", original_b)
        if {row["metadata"]["source"] for row in original_a["rows"]} != {
            p.name for p in a_root.glob("*.md")
        }:
            raise ValueError("A source coverage differs from frozen corpus")
        if {row["metadata"]["source"] for row in original_b["rows"]} != {
            p.name for p in b_root.glob("*.md")
        }:
            raise ValueError("B source coverage differs from frozen corpus")
        expected_vectors = {}
        for receipt_path in sorted((out / "wire").glob("*.receipt.json")):
            receipt = json.loads(receipt_path.read_text())
            if receipt["phase"] not in ("index-a", "index-b"):
                continue
            stem = receipt_path.name.split(".")[0]
            request = json.loads((out / "wire" / (stem + ".request.bin")).read_text())
            response = json.loads((out / "wire" / (stem + ".response.bin")).read_text())
            for text, vector in zip(
                request["input"], response["embeddings"], strict=True
            ):
                expected_vectors[
                    (receipt["phase"], text.removeprefix("search_document: "))
                ] = [struct.unpack("f", struct.pack("f", value))[0] for value in vector]
        representation = []
        for phase, payload in [("index-a", original_a), ("index-b", original_b)]:
            for row in payload["rows"]:
                matches = (
                    expected_vectors.get((phase, row["document"])) == row["embedding"]
                )
                representation.append(
                    {
                        "phase": phase,
                        "id": row["id"],
                        "source": row["metadata"]["source"],
                        "dimensions": len(row["embedding"]),
                        "canonical_text_and_float32_match": matches,
                    }
                )
        save(out / "wire-to-storage-map.json", representation)
        if not representation or not all(
            row["canonical_text_and_float32_match"] for row in representation
        ):
            raise ValueError("Canonical stored text or quantized wire vectors differ")
        budget.phase = "queries-a"
        scores = []
        leakage = []
        allowed_a = {(row["id"], row["document"]) for row in original_a["rows"]}
        for item in queries:
            result = query(ai, item, "fixture-alder-a")
            paths = [
                row.get("metadata", {}).get("source", "") for row in result["matches"]
            ]
            scores.append(
                {
                    "query_id": item["id"],
                    "group": item["group"],
                    "language": item["language"],
                    **score(paths, oracles[item["id"]]["source_path"]),
                }
            )
            leakage.extend(
                row
                for row in result["matches"]
                if (row["id"], row["text"]) not in allowed_a
            )
        metrics = {}
        for group in ("controlled", "exploratory"):
            subset = [row for row in scores if row["group"] == group]
            metrics[group] = {
                key: sum(row[key] for row in subset) / len(subset)
                for key in ("recall_at_5", "mrr_at_5", "ndcg_at_5")
            }
        save(
            out / "initial-metrics.json",
            {
                "scores": scores,
                "metrics": metrics,
                "controlled_all_ten": metrics["controlled"]["recall_at_5"] == 1,
            },
        )
        budget.phase = "queries-b"
        allowed_b = {(row["id"], row["document"]) for row in original_b["rows"]}
        for item in (queries[0], queries[5]):
            result = query(bi, item, "fixture-birch-b")
            leakage.extend(
                row
                for row in result["matches"]
                if (row["id"], row["text"]) not in allowed_b
            )
        shutil.copyfile(
            fixture / "mutation/01-room-cancellations.md",
            a_root / "01-room-cancellations.md",
        )
        (a_root / "06-lost-keys.md").unlink()
        budget.phase = "mutation"
        changed_chunks = ai.sync()
        a.close()
        a, ai = open_store(a_root, a_path)
        changed = snapshot(a)
        save(out / "mutated-reopened-a-store.json", changed)
        deleted_absent = not any(
            row["metadata"]["source"] == "06-lost-keys.md" for row in changed["rows"]
        )
        edited_rows = [
            row
            for row in changed["rows"]
            if row["metadata"]["source"] == "01-room-cancellations.md"
        ]
        edit_current = (
            bool(edited_rows)
            and all("48 hours" not in row["document"] for row in edited_rows)
            and any("24 hours" in row["document"] for row in edited_rows)
        )
        budget.phase = "queries-mutated"
        post_queries = [
            query(ai, item, "fixture-alder-a") for item in (queries[0], queries[5])
        ]
        post_deleted_absent = all(
            row["metadata"]["source"] != "06-lost-keys.md"
            for result in post_queries
            for row in result["matches"]
        )
        b_before = snapshot(b)
        b.close()
        b_hashes_before = file_hashes(b_path)
        purged = a.clear()
        a.close()
        a, ai = open_store(a_root, a_path)
        residual = a.get_stats()["count"]
        b_hashes_after = file_hashes(b_path)
        b, bi = open_store(b_root, b_path)
        b_after = snapshot(b)
        sentinel_after = file_hashes(out / "outside-projects")
        lifecycle = {
            "indexed_chunks_a": a_chunks,
            "indexed_chunks_b": b_chunks,
            "mutation_chunks": changed_chunks,
            "deleted_source_absent": deleted_absent,
            "edited_source_current": edit_current,
            "postquery_deleted_absent": post_deleted_absent,
            "purged_chunks": purged,
            "purge_residual": residual,
            "b_logical_equal": b_before == b_after,
            "b_file_hashes_before": b_hashes_before,
            "b_file_hashes_after": b_hashes_after,
            "b_file_hashes_equal": b_hashes_before == b_hashes_after,
            "b_graph_coverage": "UNVERIFIED_NO_GRAPH_CREATED_BY_THIS_INTERFACE",
            "sentinel_unchanged": sentinel_before == sentinel_after,
            "leaked_rows": leakage,
        }
        save(out / "project-lifecycle.json", lifecycle)
        check_digest(metadata("post-tags", "/api/tags"))
        save(out / "post-models.json", metadata("post-ps", "/api/ps"))
        passed = (
            metrics["controlled"]["recall_at_5"] == 1
            and not leakage
            and deleted_absent
            and edit_current
            and post_deleted_absent
            and residual == 0
            and b_before == b_after
            and b_hashes_before == b_hashes_after
            and sentinel_before == sentinel_after
        )
        return {
            "status": "PASS_SCOPED" if passed else "FAIL",
            "semantic_quality_pass": metrics["controlled"]["recall_at_5"] == 1,
            "metrics": metrics,
            "lifecycle": lifecycle,
            "graph_coverage": "UNVERIFIED",
            "original_full_imp07_closed": False,
        }
    finally:
        for store in stores:
            store.close()
        save(
            out / "semantic-close.json",
            [
                {
                    "closed": store._closed,
                    "client_is_none": store.client is None,
                    "collection_is_none": store.collection is None,
                }
                for store in stores
            ],
        )


def peers(out: Path):
    from antigravity_k.engine.embeddings import EmbeddingEngine
    from antigravity_k.engine.project_embedding_binding import ProjectEmbeddingBinding
    from antigravity_k.engine.vector_store import VectorStore

    vectors = [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 1, 0],
        [1, 0, 1],
        [0, 1, 1],
        [1, 1, 1],
        [-1, 1, 0],
    ]
    registry, name = make_registry(out / "peer-profile.json", peer=True)

    class PrecomputedEngine(EmbeddingEngine):
        def embed(self, text, model_name, *, allow_fallback=True):
            if (
                model_name != name
                or allow_fallback is not False
                or not isinstance(text, list)
            ):
                raise ValueError("Peer fixture binding contract violated")
            return [
                [float(v) for v in vectors[int(item.removeprefix("peer-")) - 1]]
                for item in text
            ]

    binding = ProjectEmbeddingBinding(PrecomputedEngine(registry=registry), name)
    deadline = time.monotonic() + 30
    clients = []
    events = []
    expected = {f"peer-{number}" for number in range(1, 9)}
    try:
        for cycle in range(2):
            concurrent_reads: dict[int, list[str]] = {}
            gate = threading.Barrier(8, timeout=max(0.01, deadline - time.monotonic()))

            def worker(number: int):
                gate.wait()
                store = VectorStore(
                    str(out / "persist-peers"),
                    collection_name="peers",
                    embedding_binding=binding,
                )
                clients.append(store)
                store.upsert_chunks(
                    [
                        {
                            "id": f"peer-{number}",
                            "text": f"peer-{number}",
                            "metadata": {"source": f"peer-{number}"},
                        }
                    ]
                )
                gate.wait()
                concurrent_reads[number] = sorted(
                    str(row["id"]) for row in store.export_all()
                )
                return store

            pool = ThreadPoolExecutor(max_workers=8)
            try:
                futures = [pool.submit(worker, number) for number in range(1, 9)]
                active = [
                    future.result(timeout=max(0.01, deadline - time.monotonic()))
                    for future in futures
                ]
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            sets = [{row["id"] for row in store.export_all()} for store in active]
            client_ids = [id(store.client) for store in active]
            active[0].close()
            survivors = [
                {row["id"] for row in store.export_all()} for store in active[1:]
            ]
            events.append(
                {
                    "cycle": cycle + 1,
                    "client_identities": client_ids,
                    "concurrent_reads": concurrent_reads,
                    "concurrent_reads_complete": len(concurrent_reads) == 8
                    and all(set(ids) == expected for ids in concurrent_reads.values()),
                    "all_eight_ids_visible": all(ids == expected for ids in sets),
                    "closed_peer_state": {
                        "closed": active[0]._closed,
                        "client_none": active[0].client is None,
                        "collection_none": active[0].collection is None,
                    },
                    "seven_survive_close": all(ids == expected for ids in survivors),
                }
            )
            for store in active:
                store.close()
            save(out / "peer-cycles.json", events)
        return {
            "status": "PASS_SCOPED"
            if all(
                row["all_eight_ids_visible"]
                and row["seven_survive_close"]
                and row["concurrent_reads_complete"]
                for row in events
            )
            else "FAIL",
            "events": events,
            "semantic_quality_evidence": False,
            "dimensions": 3,
            "model": name,
            "native_write_atomicity_claimed": False,
        }
    finally:
        for store in clients:
            store.close()


class Arguments(argparse.Namespace):
    freeze: Path = Path()
    execution: Path = Path()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    args = Arguments()
    _ = parser.parse_args(namespace=args)
    out = args.execution.resolve()
    fixture = Path(__file__).resolve().parent.parent
    if out.parent != fixture or not out.name.startswith("execution-"):
        raise ValueError("Runtime output must be a fresh owned execution directory")
    freeze = load_freeze(args.freeze, fixture)
    verify_manifest(fixture, "fixture-manifest.sha256")
    network = install_socket_guard(out / "network.jsonl")
    targets = [
        "embeddings",
        "project_embedding_binding",
        "vector_store",
        "rag_indexer",
        "model_registry",
        "provider_adapters.embedding_providers",
        "long_context_fusion",
    ]
    modules = {
        name: importlib.import_module("antigravity_k.engine." + name)
        for name in targets
    }
    imported = {
        name: str(Path(module.__file__).resolve())
        for name, module in modules.items()
        if isinstance(module.__file__, str)
    }
    if len(imported) != len(targets):
        raise ValueError("Target module has no source path")
    if any(path not in freeze.sources for path in imported.values()):
        raise ValueError("Actual imported module missing from source freeze")
    module_preimages = {}
    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if (
            module_name.startswith("antigravity_k")
            and isinstance(module_file, str)
            and Path(module_file).is_file()
        ):
            module_preimages[str(Path(module_file).resolve())] = sha(Path(module_file))
    save(
        out / "actual-imports-before.json",
        {"targets": imported, "product_imported_preimages": module_preimages},
    )
    budget = Budget()
    (out / "wire").mkdir()
    wire = WireTransport(out / "wire", budget)
    errors: list[dict[str, str]] = []
    result: dict[str, object] = {
        "status": "INCONCLUSIVE",
        "semantic": None,
        "peer": None,
        "errors": errors,
    }
    try:
        save(
            out / "phase.json",
            {"name": "semantic", "started_monotonic": time.monotonic()},
        )
        semantic_result = semantic(fixture, out, budget, wire)
        result["semantic"] = semantic_result
        prior_http = wire.sequence
        budget.phase = "peer"
        save(
            out / "phase.json", {"name": "peer", "started_monotonic": time.monotonic()}
        )
        peer_result = peers(out)
        result["peer"] = peer_result
        if wire.sequence != prior_http:
            raise ValueError("Peer fixture attempted HTTP")
        result["status"] = (
            "PASS_SCOPED"
            if semantic_result["status"] == "PASS_SCOPED"
            and peer_result["status"] == "PASS_SCOPED"
            else "FAIL"
        )
    except Exception as exc:
        errors.append(
            {
                "phase": budget.phase,
                "exception": type(exc).__name__,
                "message": str(exc),
            }
        )
        traceback.print_exc()
    finally:
        result.update(
            inferences_by_phase=dict(budget.counts),
            embedding_requests=sum(budget.counts.values()),
            additional_metadata_requests=budget.metadata,
            historical_metadata_requests=4,
            all_new_http_requests=wire.sequence,
            all_http_client_close_calls=wire.client_close_calls,
            network_counts=dict(network),
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            configured_dimensions=0,
            upstream_numeric_representation="JSON numeric -> Python float64",
            stored_numeric_representation="Binding quantizes values to float32; Chroma exports numeric arrays",
            chat_requests=0,
            pull_requests=0,
            unload_requests=0,
        )
        after = {path: sha(Path(path)) for path in module_preimages}
        source_after = {path: sha(Path(path)) for path in freeze.sources}
        save(out / "sources-after.json", {"imported": after, "frozen": source_after})
        result["source_unchanged"] = (
            module_preimages == after and freeze.sources == source_after
        )
        if not result["source_unchanged"] or network["denied"]:
            result["status"] = "INCONCLUSIVE"
        save(out / "result.json", result)
    return 0 if result["status"] == "PASS_SCOPED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
