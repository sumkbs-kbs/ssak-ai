"""Bound RAG: startup never indexes; explicit store/search stay in the allowed synthetic root.

All embedding traffic goes to an ``httpx.MockTransport``; no real network or Ollama call.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest import mock

import httpx
import pytest

from antigravity_k.api import dependencies
from antigravity_k.engine.model_registry import ModelProfile
from antigravity_k.engine.project_embedding_binding import (
    RAG_ALLOWED_ROOT_ENV,
    RAG_EMBEDDING_ENV,
    ProjectEmbeddingBindingError,
    configured_embedding_binding,
)
from antigravity_k.engine.provider_adapters.embedding_providers import REQUEST_LIMIT_ENV, OllamaEmbeddingProvider

if TYPE_CHECKING:
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
    from antigravity_k.engine.rag_indexer import RAGIndexer

MODEL = "nomic-embed-text:latest"
DIM = 8


class FakeOllama:
    def __init__(self) -> None:
        self.embed_inputs: list[list[str]] = []
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "model": MODEL, "digest": "fake"}]})
        body = cast(dict[str, object], json.loads(request.content))
        inputs = cast(list[str], body["input"])
        self.embed_inputs.append(inputs)
        rows = [[float((hash(t) >> i) % 7 + 1) for i in range(DIM)] for t in inputs]
        return httpx.Response(200, json={"model": MODEL, "embeddings": rows})


def _registry() -> mock.MagicMock:
    profile = ModelProfile(
        name=MODEL, repo=MODEL, role="embedding", provider="ollama", api_base="http://127.0.0.1:11434", dimensions=DIM
    )
    reg = mock.MagicMock()
    reg.get_default.return_value = profile
    reg.get_model.return_value = profile
    reg.get_provider_config.return_value = {}
    return reg


@pytest.fixture
def bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FakeOllama, Path]:
    fake = FakeOllama()
    allowed = tmp_path / "allowed"
    project = allowed / "synthetic-project"
    project.mkdir(parents=True)
    for i, text in enumerate(["blue ocean waves", "red mountain rock", "green forest tree"], 1):
        (project / f"doc{i}.md").write_text(f"# doc{i}\n\n{text}\n")
    monkeypatch.setenv(RAG_EMBEDDING_ENV, "ollama")
    monkeypatch.setenv(RAG_ALLOWED_ROOT_ENV, str(allowed))
    monkeypatch.setenv(REQUEST_LIMIT_ENV, "4")
    monkeypatch.setattr(OllamaEmbeddingProvider, "requests_sent", 0)
    return fake, project


def _binding(fake: FakeOllama):
    provider = OllamaEmbeddingProvider(transport=httpx.MockTransport(fake.handler))
    binding = configured_embedding_binding(_registry(), ollama_provider=provider)
    assert binding is not None
    return binding


class _Orch:
    _rag_indexer: object = None


def _attach(project: Path, fake: FakeOllama) -> RAGIndexer:
    orch = _Orch()
    dependencies._attach_project_rag_indexer(  # pyright: ignore[reportPrivateUsage]
        cast("OrchestratorAgent", cast(object, orch)), str(project), embedding_binding=_binding(fake)
    )
    return cast("RAGIndexer", orch._rag_indexer)


def test_wired_store_search_reopen_only_synthetic(bound: tuple[FakeOllama, Path]) -> None:
    fake, project = bound
    indexer = _attach(project, fake)
    assert fake.embed_inputs == []  # wiring/attach alone sends nothing
    assert indexer.index_project() > 0
    assert len(fake.embed_inputs) == 1
    stored = " ".join(fake.embed_inputs[0])
    assert all(word in stored for word in ("blue ocean", "red mountain", "green forest"))
    results = indexer.search("ocean", n_results=3)
    assert results and len(fake.embed_inputs) == 2
    dumped = [json.dumps(r, default=str) for r in results]
    assert all(".md" in d and str(project.parent) not in d.replace(str(project), "") for d in dumped)
    reopened = _attach(project, fake)
    assert reopened.index_project() == 0  # unchanged -> no re-embed
    assert len(fake.embed_inputs) == 2
    assert OllamaEmbeddingProvider.requests_sent == 2
    assert [p for p in fake.paths if p != "/api/embed"] == []


def test_request_limit_blocks_before_sending(bound: tuple[FakeOllama, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    fake, project = bound
    monkeypatch.setenv(REQUEST_LIMIT_ENV, "1")
    indexer = _attach(project, fake)
    _ = indexer.index_project()
    with pytest.raises(Exception):
        _ = _binding(fake).embed(["over"], query=True)
    assert len(fake.embed_inputs) == 1 and OllamaEmbeddingProvider.requests_sent == 1


def test_missing_or_outside_root_rejected_without_fallback(
    bound: tuple[FakeOllama, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, project = bound
    outside = tmp_path / "outside"
    outside.mkdir()
    link = project.parent / "escape-link"
    link.symlink_to(outside, target_is_directory=True)
    for bad in (project.parent / "missing", outside, link, Path("")):
        with pytest.raises(ProjectEmbeddingBindingError):
            _ = _attach(bad, fake)
    monkeypatch.delenv(RAG_ALLOWED_ROOT_ENV)
    with pytest.raises(ProjectEmbeddingBindingError):
        _ = _attach(project, fake)
    assert fake.embed_inputs == []


def test_symlinked_file_escape_blocked(bound: tuple[FakeOllama, Path], tmp_path: Path) -> None:
    fake, project = bound
    secret = tmp_path / "outside-doc.md"
    secret.write_text("# outside\n\noutside text\n")
    (project / "leak.md").symlink_to(secret)
    indexer = _attach(project, fake)
    with pytest.raises(ValueError):
        _ = indexer.index_project()
    assert all("outside text" not in " ".join(batch) for batch in fake.embed_inputs)


def test_default_status_query_sends_no_embedding(bound: tuple[FakeOllama, Path]) -> None:
    fake, _project = bound
    from antigravity_k.api.routes import vault_api
    from antigravity_k.engine import embedding_readiness

    real_client = httpx.Client

    def client(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(fake.handler)
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    with (
        mock.patch("antigravity_k.engine.model_registry.ModelRegistry", return_value=_registry()),
        mock.patch.object(embedding_readiness.httpx, "Client", client),
    ):
        status = vault_api.vault_embedding_status()
    assert status["embedding_verified"] is False and status["app_rag_binding"] is True
    assert fake.embed_inputs == [] and "/api/embed" not in fake.paths
    assert OllamaEmbeddingProvider.requests_sent == 0


LIFESPAN_PROBE = r"""
import asyncio, json, os, sys, types
from pathlib import Path
root = Path(sys.argv[1]).resolve()
receipt = {"rag_roots": [], "index_calls": 0, "forbidden": []}
def audit(event, args):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen"}:
        receipt["forbidden"].append(event)
        raise AssertionError(event)
sys.addaudithook(audit)
os.environ.update(PYTHON_DOTENV_DISABLED="1", AGK_CONFIG_FILE=str(root / "absent.yaml"), AGK_ENV_FILE=str(root / "absent.env"),
    AGK_SERVER_HOST="127.0.0.1", AGK_PATH_PROJECT_ROOT=str(root / "allowed" / "synthetic-project"),
    AGK_RAG_EMBEDDING="ollama", AGK_RAG_ALLOWED_ROOT=str(root / "allowed"), AGK_EMBEDDING_REQUEST_LIMIT="4")
from fastapi import APIRouter, FastAPI
def module(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m
module("antigravity_k.api.routes", api_router=APIRouter())
module("antigravity_k.api.auth_routes", router=APIRouter())
module("antigravity_k.api.dependencies", bootstrap_cognitive_active=lambda app: None)
module("antigravity_k.engine.operational_metrics", compute_readiness=lambda: {})
module("antigravity_k.engine.session_manager", SessionPersistenceError=type("E", (RuntimeError,), {}))
ns = types.SimpleNamespace(shutdown=lambda: None, close=lambda: None)
module("antigravity_k.engine.hook_event_bus", init_hook_event_bus=lambda p: None, get_hook_event_bus=lambda: ns)
module("antigravity_k.engine.audit_db", init_audit_db=lambda p: None, get_audit_db=lambda: ns)
module("antigravity_k.engine.panel_activity_tracker", init_panel_activity_tracker=lambda: None)
module("antigravity_k.engine.event_bus", bridge_to_hook_event_bus=lambda project_root: None)
class Indexer:
    def __init__(self, project_root): receipt["rag_roots"].append(project_root)
    def index_project(self): receipt["index_calls"] += 1; return 0
module("antigravity_k.engine.rag_indexer", RAGIndexer=Indexer)
module("antigravity_k.engine.ide_server", IDEServer=object, IDE_AUTOSTART_ENV="AGK_IDE_SERVER_AUTOSTART", ide_autostart_requested=lambda: False)
module("antigravity_k.tools.ssak_search_runtime", shutdown_ssak_search_runtime=lambda: None)
module("antigravity_k.tools.browser_session_owner", shutdown_browser_sessions=lambda: None)
(root / "allowed" / "synthetic-project").mkdir(parents=True)
from antigravity_k.api import server
async def run():
    app = FastAPI()
    async with server.lifespan(app):
        receipt["thread"] = getattr(app.state, "rag_index_thread", None) is not None
try:
    asyncio.run(run())
finally:
    (root / "receipt.json").write_text(json.dumps(receipt))
"""


def test_real_lifespan_with_binding_does_not_index(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    script = tmp_path / "probe.py"
    script.write_text(LIFESPAN_PROBE)
    env = dict(os.environ, PYTHONPATH=str(repo / "src") + os.pathsep + str(repo), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], cwd=tmp_path, env=env, capture_output=True, timeout=60
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt == {"rag_roots": [], "index_calls": 0, "forbidden": [], "thread": False}, receipt
