"""AGK_PROJECT_RAG_ENABLED policy for CONTEXT_ENRICH and project RAG wiring (fake embedding only)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from antigravity_k.api import dependencies
from antigravity_k.engine import rag_indexer as rag_module
from antigravity_k.engine.orchestrator_handlers import context_enrich_handler
from antigravity_k.engine.project_embedding_binding import PROJECT_RAG_ENABLED_ENV, project_rag_policy
from antigravity_k.engine.state_graph import StateContext
from tests.test_context_enrich_rag_chat_input import QUESTION, FakeOllama, _chat, _orch, projects  # noqa: F401

if TYPE_CHECKING:
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent

REPO = Path(__file__).resolve().parents[1]


class _SpyIndexer:
    def __init__(self) -> None:
        self.calls = 0
        self.vector_store = SimpleNamespace(embedding_binding=object())

    def format_context(self, query: str, **kwargs: object) -> str:
        self.calls += 1
        return "<relevant_code>\nSPY\n</relevant_code>"


def _bare_orch(indexer: object) -> SimpleNamespace:
    return SimpleNamespace(
        ctx=SimpleNamespace(ki_engine=SimpleNamespace(build_ki_prompt=lambda: "")),
        vault_engine=None,
        project_root=str(REPO / "nonexistent-r18"),
        manager=None,
        _rag_indexer=indexer,
    )


def _run(orch: SimpleNamespace) -> StateContext:
    msgs = [{"role": "user", "content": QUESTION}]
    ctx = StateContext(messages=msgs, user_message=QUESTION, custom_messages=list(msgs))
    context_enrich_handler(ctx, orch)
    return ctx


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "legacy"),
        ("false", "disabled"),
        ("0", "disabled"),
        ("TRUE", "enabled"),
        ("1", "enabled"),
        ("maybe", "disabled"),
        ("", "disabled"),
    ],
)
def test_policy_parse(raw: str | None, expected: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if raw is None:
        monkeypatch.delenv(PROJECT_RAG_ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, raw)
    mode, reason = project_rag_policy()
    assert mode == expected
    if raw in {"maybe", ""}:
        assert reason == "invalid_value"


class _CreationSpy:
    created = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        _CreationSpy.created += 1

    def format_context(self, query: str, **kwargs: object) -> str:
        return "<relevant_code>\nLEGACY\n</relevant_code>"


def test_false_with_indexer_no_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "false")
    spy = _SpyIndexer()
    ctx = _run(_bare_orch(spy))
    assert spy.calls == 0 and ctx.rag_context == "" and ctx.custom_messages[-1]["content"] == QUESTION


def test_false_without_indexer_no_fallback_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "false")
    monkeypatch.setattr(rag_module, "RAGIndexer", _CreationSpy)
    _CreationSpy.created = 0
    orch = _bare_orch(None)
    ctx = _run(orch)
    assert _CreationSpy.created == 0 and orch._rag_indexer is None and ctx.rag_context == ""


def test_true_without_binding_no_legacy_substitution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "true")
    monkeypatch.setattr(rag_module, "RAGIndexer", _CreationSpy)
    _CreationSpy.created = 0
    orch = _bare_orch(None)
    dependencies._attach_project_rag_indexer(  # pyright: ignore[reportPrivateUsage]
        cast("OrchestratorAgent", cast(object, orch)), str(tmp_path), embedding_binding=None
    )
    assert orch._rag_indexer is None and getattr(orch, "_project_rag_unavailable_reason") == "binding_not_ready"
    unbound = _SpyIndexer()
    unbound.vector_store = SimpleNamespace(embedding_binding=None)
    ctx = _run(orch)
    ctx2 = _run(_bare_orch(unbound))
    assert _CreationSpy.created == 0 and unbound.calls == 0
    assert ctx.rag_context == ctx2.rag_context == ""


def test_false_attach_does_not_create_indexer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "off")
    monkeypatch.setattr(rag_module, "RAGIndexer", _CreationSpy)
    _CreationSpy.created = 0
    orch = _bare_orch(None)
    dependencies._attach_project_rag_indexer(  # pyright: ignore[reportPrivateUsage]
        cast("OrchestratorAgent", cast(object, orch)), str(tmp_path)
    )
    assert _CreationSpy.created == 0 and getattr(orch, "_project_rag_unavailable_reason") == "explicit_false"


def test_true_with_valid_binding_reaches_context(projects: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setenv(PROJECT_RAG_ENABLED_ENV, "true")
    a, _b = projects
    fake = FakeOllama()
    orch = _orch(a, fake)
    _ = orch._rag_indexer.index_project()
    ctx = _chat(orch)
    assert "ALPHA-ONLY" in ctx.custom_messages[-1]["content"] and len(fake.embed_inputs) == 2


def test_unset_keeps_dev_legacy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROJECT_RAG_ENABLED_ENV, raising=False)
    monkeypatch.setattr(rag_module, "RAGIndexer", _CreationSpy)
    _CreationSpy.created = 0
    ctx = _run(_bare_orch(None))
    assert _CreationSpy.created == 1 and "LEGACY" in ctx.rag_context


LAUNCHER_LINE = 'export AGK_PROJECT_RAG_ENABLED="${AGK_PROJECT_RAG_ENABLED:-false}"'


@pytest.mark.parametrize(("user", "expected"), [(None, "false"), ("true", "true"), ("0", "0")])
def test_dmg_launcher_default_false_and_passthrough(user: str | None, expected: str) -> None:
    text = (REPO / "scripts/build_mac_dmg.sh").read_text()
    assert text.count(LAUNCHER_LINE) == 1
    env = {"PATH": "/usr/bin:/bin"}
    if user is not None:
        env["AGK_PROJECT_RAG_ENABLED"] = user
    out = subprocess.run(
        ["/bin/bash", "-c", LAUNCHER_LINE + '; printf %s "$AGK_PROJECT_RAG_ENABLED"'],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == expected
    _ = os.environ
