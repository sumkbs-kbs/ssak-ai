"""r29: no hidden Chroma ONNX download / substitute embedding; folder browser allowed-root contract; segment audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antigravity_k.engine import llm_input_audit as audit
from antigravity_k.engine.embedding_guard import EmbeddingNotReadyError


@pytest.fixture
def download_boundary(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fake download/embedding boundary: any use of Chroma's default ONNX model is recorded and fails."""
    from chromadb.utils.embedding_functions import onnx_mini_lm_l6_v2 as onnx

    calls: list[str] = []

    def _no_download(self: object, *a: object, **k: object) -> None:
        calls.append("download")
        raise AssertionError("Chroma default ONNX download attempted")

    def _no_embed(self: object, *a: object, **k: object) -> None:
        calls.append("embed")
        raise AssertionError("Chroma default ONNX embedding used")

    monkeypatch.setattr(onnx.ONNXMiniLM_L6_V2, "_download_model_if_not_exists", _no_download)
    monkeypatch.setattr(onnx.ONNXMiniLM_L6_V2, "_download", _no_download)
    monkeypatch.setattr(onnx.ONNXMiniLM_L6_V2, "__call__", _no_embed)
    return calls


def test_unbound_vector_store_fails_explicitly_without_download(tmp_path: Path, download_boundary: list[str]) -> None:
    from antigravity_k.engine.vector_store import VectorStore

    store = VectorStore(str(tmp_path / "vs"), collection_name="agent_knowledge")
    with pytest.raises(EmbeddingNotReadyError):
        store.search("anything", n_results=3)
    with pytest.raises(EmbeddingNotReadyError):
        store._upsert(store._require_collection(), ["a"], ["doc"], [{"source": "s"}])  # pyright: ignore[reportPrivateUsage]
    assert download_boundary == []


def test_gbrain_vector_side_not_ready_without_download(tmp_path: Path, download_boundary: list[str]) -> None:
    from antigravity_k.engine.gbrain import GBrain

    brain = GBrain(storage_dir=str(tmp_path / "gb"))
    try:
        assert brain.collection is None and brain.vector_not_ready_reason
        with pytest.raises(EmbeddingNotReadyError):
            brain.search_semantic("anything", limit=2)
    finally:
        brain.close()
    assert download_boundary == []


def test_segment_attribution_hashes_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "a.jsonl"
    monkeypatch.setenv(audit.AUDIT_PATH_ENV, str(out))
    monkeypatch.setenv(audit.EXPECT_ENV, "FAKE-FACT-9")
    monkeypatch.setenv(audit.FORBID_ENV, "FAKE-OTHER-1")
    audit.register_segments(
        {
            "question": "q without fact",
            "rag_code": "<relevant_code>x FAKE-FACT-9</relevant_code>",
            "file_selection": "",
        },
        rag_status="injected",
    )
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q without fact<relevant_code>x FAKE-FACT-9</relevant_code>"},
    ]
    audit.audit_wire_messages(model="m", provider="ollama", purpose="stream", messages=msgs)
    recs = [json.loads(line) for line in out.read_text().splitlines()]
    assert recs[0]["kind"] == "context_segments" and recs[0]["segments"]["rag_code"]["expect_fact_contained"] is True
    wire = recs[1]["assembled_segments"]
    assert wire["rag_code"]["present_in_input"] is True and wire["question"]["expect_fact_contained"] is False
    assert [m["role"] for m in recs[1]["per_message"]] == ["system", "user"]
    assert "FAKE-FACT-9" not in out.read_text()


@pytest.fixture
def browse_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from antigravity_k.api.routes import filesystem
    from antigravity_k.api.server import app
    from antigravity_k.config import config
    from antigravity_k.engine.api_cache import api_cache

    ws, allowed, outside, home = (tmp_path / n for n in ("ws", "allowed", "outside", "home"))
    for d in (ws, allowed / "alpha", allowed / "beta", outside / "secret", home):
        d.mkdir(parents=True)
    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(allowed))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    getattr(api_cache, "_entries").clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Access-Pin": config.security.access_pin})
        yield c, allowed, outside
    getattr(api_cache, "_entries").clear()


def test_browse_allowed_root_lists_projects_and_rejects_outside(browse_client) -> None:  # type: ignore[no-untyped-def]
    c, allowed, outside = browse_client
    r = c.get("/api/fs/browse", params={"dir": str(allowed)})
    assert r.status_code == 200
    body = r.json()
    assert {i["name"] for i in body["items"]} == {"alpha", "beta"}
    assert any(s["kind"] == "allowed_root" and s["path"] == str(allowed.resolve()) for s in body["shortcuts"])
    assert not any(s["kind"] == "home" for s in body["shortcuts"])  # HOME not allowed -> not offered
    assert body["parent"] is None  # parent of the allowed root is outside -> not navigable
    assert c.get("/api/fs/browse", params={"dir": str(outside)}).status_code == 403
    assert c.get("/api/fs/browse", params={"dir": str(allowed / ".." / "outside")}).status_code == 403


def test_r29_graphify_semantic_disabled_no_model_load(monkeypatch):
    import sys
    import types

    from antigravity_k.engine.optimizers import graphify_builder as gb

    st = types.ModuleType("sentence_transformers")
    st.SentenceTransformer = lambda *a, **k: (_ for _ in ()).throw(AssertionError("model load attempted"))
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    assert gb.embedding_retrieve(object(), "q") == []
