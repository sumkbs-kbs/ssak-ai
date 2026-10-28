"""r36: search-disabled send boundary + resume-prefix / terminal-ownership regressions.

Synthetic data only; network transports are replaced by counters (nothing is sent).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from antigravity_k.engine.task_execution_context import (
    TaskExecutionContext,
    resume_output_prefix,
    runner_owns_terminal,
    with_resume_prefix,
)
from antigravity_k.engine.task_runner import BackgroundTaskRunner
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.tools.egress_policy import EgressPolicyError, validate_search_egress_url

# ─── egress: AGK_SEARCH_ENABLED=false at the send boundary ─────────────────────


@pytest.fixture
def sends(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def _sync(self, request):  # type: ignore[no-untyped-def]
        seen.append(str(request.url))
        raise AssertionError("transport reached")

    async def _async(self, request):  # type: ignore[no-untyped-def]
        seen.append(str(request.url))
        raise AssertionError("transport reached")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _async)
    monkeypatch.setenv("AGK_SEARCH_ENABLED", "false")
    monkeypatch.delenv("AGK_SEARCH_OFFLINE", raising=False)
    return seen


def test_send_boundary_rejects_when_disabled(sends: list[str]) -> None:
    with pytest.raises(EgressPolicyError):
        validate_search_egress_url("https://search.example.invalid/q")
    assert sends == []


def test_web_search_tool_sync_paths_send_nothing(sends: list[str]) -> None:
    from antigravity_k.tools.web_search_tool import WebSearchTool

    tool = WebSearchTool()
    assert "disabled" in tool.execute(query="synthetic r36 query")
    # retry / fallback engines called directly (bypassing execute) still stop at the hook
    for name in ("_sync_search_jina", "_sync_search_searxng", "_sync_search_duckduckgo"):
        fn = getattr(tool, name)
        try:
            fn("synthetic r36 query")
        except Exception:
            pass
    assert sends == []


def test_async_engine_search_and_fallbacks_send_nothing(sends: list[str]) -> None:
    from antigravity_k.tools.web_search_engine import PageScraper, WebSearchEngine

    engine = WebSearchEngine()
    try:
        asyncio.run(engine.search("synthetic r36 query", use_cache=False, force_refresh=True))
    except Exception:
        pass
    scraper = PageScraper()
    for name in dir(scraper):
        if "jina" in name and callable(getattr(scraper, name)):
            try:
                res = getattr(scraper, name)("https://page.example.invalid/x")
                if asyncio.iscoroutine(res):
                    asyncio.run(res)
            except Exception:
                pass
    assert sends == []


def test_ssak_search_client_sends_nothing(sends: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.tools import ssak_search_client as ssc

    opened: list[object] = []
    monkeypatch.setattr(
        ssc, "safe_urlopen", lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(AssertionError())
    )
    try:
        ssc.search("synthetic r36 query")
    except Exception:
        pass
    assert opened == [] and sends == []


def test_chat_fast_search_gate_uses_send_boundary_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.tools.web_search_tool import web_search_disabled

    monkeypatch.setenv("AGK_SEARCH_ENABLED", "false")
    assert web_search_disabled() is True
    monkeypatch.setenv("AGK_SEARCH_ENABLED", "true")
    monkeypatch.setenv("AGK_SEARCH_OFFLINE", "1")
    assert web_search_disabled() is True


# ─── resume prefix / terminal ownership ────────────────────────────────────────


def _wait(pred, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def _tool_loop_terminal(orch: object, status: str, output: str) -> None:
    """Call the REAL ToolLoopEngine._transition_task_state with a minimal self."""
    shim = SimpleNamespace(orch=orch)
    shim._task_execution_context = lambda: ToolLoopEngine._task_execution_context(shim)  # type: ignore[attr-defined]
    shim._state_store = ToolLoopEngine._state_store  # type: ignore[attr-defined]
    ToolLoopEngine._transition_task_state(shim, status, output=output)  # type: ignore[arg-type]


class _Orch:
    vault_engine = None

    def __init__(self, lines: list[str], *, fail_at: int | None = None) -> None:
        self.lines = lines
        self.fail_at = fail_at
        self.gate = threading.Semaphore(0)
        self.task_execution_context: TaskExecutionContext | None = None
        self.seen_prefix: list[tuple[str, str]] = []
        self.status_at_tool_done: list[str] = []
        self.other_owns: list[bool] = []

    @contextmanager
    def bind_task_execution(self, task_id, state_store) -> Iterator[None]:  # type: ignore[no-untyped-def]
        self.task_execution_context = TaskExecutionContext(task_id, state_store)
        try:
            yield
        finally:
            self.task_execution_context = None

    def run_stream(self, messages, target_model) -> Iterator[str]:  # type: ignore[no-untyped-def]
        self.seen_prefix.append(resume_output_prefix.get())
        prior = "".join(m["content"] for m in messages if m["role"] == "assistant")
        start = prior.count(". item ")
        segment = []
        for i in range(start, len(self.lines)):
            assert self.gate.acquire(timeout=5)
            if self.fail_at is not None and i == self.fail_at:
                raise RuntimeError("synthetic failure")
            segment.append(self.lines[i])
            yield self.lines[i]
        ctx = self.task_execution_context
        assert ctx is not None
        self.other_owns.append(runner_owns_terminal("task_other") or with_resume_prefix("task_other", "x") != "x")
        _tool_loop_terminal(self, "done", "".join(segment))  # tool loop's own (segment-only) DONE write
        rec = ctx.state_store.get_task(ctx.task_id)
        self.status_at_tool_done.append(rec["status"] if rec else "?")
        yield "\n[post-stage review]\n"  # cov_verify / quality_check output after the loop


LINES = [f"{i + 1}. item {i + 1}\n" for i in range(6)]


def _status(r: BackgroundTaskRunner, tid: str) -> str:
    rec = r.state_store.get_task(tid)
    return rec["status"] if rec else "?"


def test_restart_resume_keeps_prefix_and_runner_owns_done(tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    r1 = BackgroundTaskRunner(db_path=db)
    o1 = _Orch(LINES)
    tid = r1.submit_task("synthetic r36 resume task", orchestrator=o1, target_model="fake")
    _wait(lambda: _status(r1, tid) == "running")
    o1.gate.release(3)
    _wait(
        lambda: (
            (r1.state_store.get_task(tid) or {}).get("output", "").count(". item ") >= 0 and len(o1.seen_prefix) == 1
        )
    )
    time.sleep(0.2)
    assert r1.pause_task(tid) == "pausing"
    o1.gate.release(1)
    _wait(lambda: _status(r1, tid) == "paused")
    phase1 = r1.state_store.get_task(tid)["output"]  # type: ignore[index]
    assert phase1

    r2 = BackgroundTaskRunner(db_path=db)
    o2 = _Orch(LINES)
    assert r2.resume_task(tid, orchestrator=o2, target_model="fake")
    o2.gate.release(len(LINES))
    _wait(lambda: _status(r2, tid) == "done")
    final = r2.state_store.get_task(tid)["output"]  # type: ignore[index]
    assert final.startswith(phase1)
    assert [ln for ln in final.splitlines() if ". item " in ln] == [ln.rstrip("\n") for ln in LINES]
    assert "[post-stage review]" in final  # DONE carries output produced after the tool loop
    assert o2.status_at_tool_done == ["running"]  # tool-loop DONE deferred to the runner
    assert o2.seen_prefix[0][0] == tid and o2.seen_prefix[0][1] == phase1
    assert o2.other_owns == [False]  # other (subagent) task ids are never affected


def test_prefix_reset_after_failure_and_no_leak_to_next_task(tmp_path: Path) -> None:
    r = BackgroundTaskRunner(db_path=str(tmp_path / "t.db"))
    bad = _Orch(LINES, fail_at=1)
    t1 = r.submit_task("synthetic r36 failing task", orchestrator=bad, target_model="fake")
    bad.gate.release(5)
    _wait(lambda: _status(r, t1) == "failed")
    assert resume_output_prefix.get() == ("", "")  # caller context untouched
    good = _Orch(LINES)
    t2 = r.submit_task("synthetic r36 next task", orchestrator=good, target_model="fake")
    good.gate.release(len(LINES))
    _wait(lambda: _status(r, t2) == "done")
    assert good.seen_prefix == [(t2, "")]  # no owner/prefix leaked from t1


def test_concurrent_tasks_do_not_mix(tmp_path: Path) -> None:
    r = BackgroundTaskRunner(db_path=str(tmp_path / "t.db"))
    oa, ob = _Orch(LINES), _Orch(LINES)
    ta = r.submit_task("synthetic r36 task A", orchestrator=oa, target_model="fake")
    tb = r.submit_task("synthetic r36 task B", orchestrator=ob, target_model="fake")
    for _ in LINES:
        oa.gate.release(1)
        ob.gate.release(1)
    _wait(lambda: _status(r, ta) == "done" and _status(r, tb) == "done")
    assert oa.seen_prefix == [(ta, "")] and ob.seen_prefix == [(tb, "")]
    assert oa.status_at_tool_done == ["running"] and ob.status_at_tool_done == ["running"]
    for tid in (ta, tb):
        out = r.state_store.get_task(tid)["output"]  # type: ignore[index]
        assert out.count(". item ") == len(LINES) and "[post-stage review]" in out


# ─── B: vault routes resolve the project vault the orchestrator reads ─────────


def _req(headers: dict[str, str] | None = None, query: str = ""):  # type: ignore[no-untyped-def]
    from starlette.requests import Request

    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {"type": "http", "method": "POST", "path": "/api/vault/write", "headers": raw, "query_string": query.encode()}
    )


def test_vault_route_explicit_project_id_wins() -> None:
    # r37: an explicit id is no longer accepted unvalidated — an unregistered id is a 404, never a
    # silent fallback (registered-id routing is covered by tests/test_r37_prereq.py real routes).
    from fastapi import HTTPException

    from antigravity_k.api.routes.vault_api import _resolve_vault_project_id

    for req in (_req({"X-AGK-Project-Id": "proj_r36"}), _req(query="project_id=proj_q")):
        with pytest.raises(HTTPException) as exc:
            _ = _resolve_vault_project_id(req)
        assert exc.value.status_code == 404


def test_vault_route_without_identity_uses_registry_active_project(monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.api import project_binding
    from antigravity_k.api.routes import vault_api
    from antigravity_k.engine import project_registry

    monkeypatch.setattr(project_binding, "get_session_active_project", lambda _sid: None)
    from antigravity_k.engine.project_embedding_binding import IMPLICIT_DEFAULT_PROJECT_ID

    active = SimpleNamespace(id="proj_alpha_r36")
    monkeypatch.setattr(
        project_registry, "get_project_registry", lambda: SimpleNamespace(get_active_project=lambda: active)
    )
    assert vault_api._resolve_vault_project_id(_req()) == "proj_alpha_r36"
    active.id = IMPLICIT_DEFAULT_PROJECT_ID
    assert vault_api._resolve_vault_project_id(_req()) is None  # implicit default -> ambient vault (unchanged)
