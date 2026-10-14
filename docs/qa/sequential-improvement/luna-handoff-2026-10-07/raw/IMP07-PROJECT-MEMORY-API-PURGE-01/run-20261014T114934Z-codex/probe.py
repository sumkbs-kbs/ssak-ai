from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, cast

import httpx

ROOT = Path(sys.argv[1]).resolve()
GUARD_ROOT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(GUARD_ROOT))
from startup_probe.guard import Guard

guard = Guard(ROOT)
guard.install()
observed: dict[str, Any] = {
    "request_identity": [],
    "purge_coroutine_resume_events": [],
    "asgi_requests": [],
    "model_quality": "NOT_EVALUATED",
    "fixture_vectors": "precomputed 3D; not neural embeddings",
}


def profile(frame, event, arg):
    guard.profile(frame, event, arg)
    if (
        frame.f_code.co_filename.endswith("/api/dependencies.py")
        and frame.f_code.co_name == "_resolve_project_runtime_identity"
        and event == "return"
    ):
        observed["request_identity"].append(arg)
    if (
        frame.f_code.co_filename.endswith("/api/routes/system_api.py")
        and frame.f_code.co_name == "purge_memory"
        and event == "call"
    ):
        observed["purge_coroutine_resume_events"].append({"line": frame.f_lineno, "lasti": frame.f_lasti})


sys.setprofile(profile)
threading.setprofile(profile)


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def files(path):
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


def rows(collection) -> dict[str, Any]:
    payload = collection.get(include=["documents", "metadatas", "embeddings"])
    embeddings = payload["embeddings"]
    return {
        "ids": payload["ids"],
        "documents": payload["documents"],
        "metadatas": payload["metadatas"],
        "embeddings": embeddings.tolist() if embeddings is not None else [],
    }


async def scenario():
    import chromadb

    from antigravity_k.api import dependencies, server
    from antigravity_k.engine.gbrain import GBrain, global_gbrain
    from antigravity_k.engine.project_embedding_binding import (
        DIMENSIONS_METADATA_KEY,
        IDENTITY_METADATA_KEY,
        ConfiguredEmbeddingIdentity,
    )
    from antigravity_k.engine.project_memory_paths import project_gbrain_dir, project_rag_vector_dir
    from antigravity_k.engine.project_registry import get_project_registry

    assert not server.app.dependency_overrides
    registry = get_project_registry()
    project_a = ROOT / "projects/A"
    project_b = ROOT / "projects/B"
    project_a.mkdir(parents=True)
    project_b.mkdir(parents=True)
    a = registry.add_project("owned A", str(project_a))
    b = registry.add_project("owned B", str(project_b))
    active = registry.switch_project(a.id)
    assert active is not None and active.id == a.id
    observed["project_a"] = {"id": a.id, "root": str(project_a)}
    observed["project_b"] = {"id": b.id, "root": str(project_b)}
    observed["configured_default_root"] = str(server.config.paths.project_root)
    global_gbrain.graph.add_node("global-sentinel", owner="global")
    global_gbrain._save_graph().result()
    outside = ROOT / "outside.txt"
    outside.write_text("must remain unchanged")
    brains = {}
    vectors = {}
    identity = ConfiguredEmbeddingIdentity(
        version=1,
        provider="ollama",
        profile_name="precomputed-purge-fixture",
        wire_model="precomputed-3d-fixture",
        endpoint="http://127.0.0.1:1",
        configured_dimensions=3,
        document_prefix="",
        query_prefix="",
    )
    for label, project in (("A", project_a), ("B", project_b)):
        brain = GBrain(str(project_gbrain_dir(project)))
        brain.graph.add_node(label + "-node", owner=label)
        brain.graph.add_node(label + "-peer", owner=label)
        brain.graph.add_edge(label + "-node", label + "-peer", relation="fixture")
        brain._save_graph().result()
        from chromadb.api.models.Collection import Collection

        cast(Collection, cast(object, brain.collection)).upsert(
            ids=[label + "-graph-vector"],
            documents=[label + " native graph projection"],
            embeddings=[[1.0, 2.0, 3.0]],
            metadatas=[{"owner": label}],
        )
        brains[label] = brain
        client = chromadb.PersistentClient(path=str(project_rag_vector_dir(project)))
        collection = client.create_collection(
            name="project_code",
            embedding_function=None,
            metadata={IDENTITY_METADATA_KEY: identity.serialized(), DIMENSIONS_METADATA_KEY: 3},
        )
        collection.upsert(
            ids=[label + "-row-1", label + "-row-2"],
            documents=[label + " one", label + " two"],
            metadatas=[
                {"owner": label, "source": str(project / "one.md")},
                {"owner": label, "source": str(project / "two.md")},
            ],
            embeddings=[[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]],
        )
        vectors[label] = (client, collection)
    before: dict[str, Any] = {
        "a_graph": brains["A"].export_all(),
        "b_graph": brains["B"].export_all(),
        "a_vectors": rows(vectors["A"][1]),
        "b_vectors": rows(vectors["B"][1]),
        "b_graph_vectors": rows(brains["B"].collection),
        "b_files": files(project_b),
        "global_graph_sha": hashlib.sha256(global_gbrain.graph_file.read_bytes()).hexdigest(),
        "outside_sha": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    write("before.json", before)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app, raise_app_exceptions=False),
        base_url="http://127.0.0.1",
        follow_redirects=False,
    ) as client:
        response = await client.request("DELETE", "/api/memory", json={"scope": "all"})
        observed["asgi_requests"].append(
            {"method": "DELETE", "path": "/api/memory", "authorized": False, "status": response.status_code}
        )
        assert response.status_code == 401
        response = await client.post("/api/auth/login", json={"pin": os.environ["AGK_SEC_ACCESS_PIN"]})
        observed["asgi_requests"].append({"method": "POST", "path": "/api/auth/login", "status": response.status_code})
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        write(
            "purge-attempt.json",
            {
                "method": "DELETE",
                "path": "/api/memory",
                "scope": "all",
                "expected_active_project": a.id,
                "retry_budget": 0,
            },
        )
        response = await client.request(
            "DELETE", "/api/memory", json={"scope": "all"}, headers={"Authorization": "Bearer " + token}
        )
        (ROOT / "response.bin").write_bytes(response.content)
        observed["asgi_requests"].append(
            {
                "method": "DELETE",
                "path": "/api/memory",
                "authorized": True,
                "status": response.status_code,
                "body_sha256": hashlib.sha256(response.content).hexdigest(),
            }
        )
        observed["purge_status"] = response.status_code
    after_b_files = files(project_b)
    reopened = GBrain(str(project_gbrain_dir(project_a)))
    after: dict[str, Any] = {
        "a_graph": reopened.export_all(),
        "a_graph_vectors": rows(reopened.collection),
        "a_vectors": rows(vectors["A"][1]),
        "b_vectors": rows(vectors["B"][1]),
        "b_graph": brains["B"].export_all(),
        "b_graph_vectors": rows(brains["B"].collection),
        "b_files_before_reopen": after_b_files,
        "global_graph_sha": hashlib.sha256(global_gbrain.graph_file.read_bytes()).hexdigest(),
        "outside_sha": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    write("after.json", after)
    observed["a_residual_graph_nodes"] = len(after["a_graph"])
    observed["a_residual_graph_vectors"] = len(after["a_graph_vectors"]["ids"])
    observed["a_residual_project_vectors"] = len(after["a_vectors"]["ids"])
    observed["b_graph_and_vectors_preserved"] = all(
        before[key] == after[key] for key in ("b_graph", "b_vectors", "b_graph_vectors")
    )
    observed["b_persisted_files_preserved"] = before["b_files"] == after["b_files_before_reopen"]
    observed["outside_and_global_graph_preserved"] = (
        before["global_graph_sha"] == after["global_graph_sha"] and before["outside_sha"] == after["outside_sha"]
    )
    assert (
        observed["b_graph_and_vectors_preserved"]
        and observed["b_persisted_files_preserved"]
        and observed["outside_and_global_graph_preserved"]
    )
    assert [a.id, str(project_a)] in observed["request_identity"] or (a.id, str(project_a)) in observed[
        "request_identity"
    ]
    dependencies.reset_runtime_dependencies()
    reopened.close()
    for brain in brains.values():
        brain.close()
    global_gbrain.close()
    observed["classification"] = (
        "PASS_SCOPED_ASGI_AUTH_PROJECT_PURGE"
        if response.status_code == 200
        and all(
            observed[key] == 0
            for key in ("a_residual_graph_nodes", "a_residual_graph_vectors", "a_residual_project_vectors")
        )
        else "FAIL_OBSERVED_PROJECT_PURGE"
    )


try:
    asyncio.run(scenario())
finally:
    guard.save()
    write("observations.json", observed)
