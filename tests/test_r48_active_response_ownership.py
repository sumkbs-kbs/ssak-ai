"""Active response isolation through real authentication and in-process ASGI."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.chat_boundary_helpers import Boundary
from tests.chat_boundary_helpers import boundary as boundary


@dataclass
class ActiveCase:
    boundary: Boundary
    client: TestClient
    headers: dict[str, dict[str, str]] = field(repr=False)
    beta: str


@pytest.fixture
def active_case(boundary: Boundary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ActiveCase]:
    from antigravity_k.api import auth_policy, auth_routes, project_binding
    from antigravity_k.api.routes import agent_stream_api
    from antigravity_k.api.server import verify_access_token
    from antigravity_k.config import config

    monkeypatch.setattr(config.security, "access_pin", "r48-synthetic-pin")
    monkeypatch.setattr(config.security, "pin_hash_file", str(tmp_path / "auth-hash"))
    monkeypatch.setattr(config.security, "token_secret_file", str(tmp_path / "token-secret"))
    monkeypatch.setattr(auth_routes, "_token_service", None)
    monkeypatch.setattr(auth_routes, "_pin_hash", None)
    monkeypatch.setattr(auth_policy, "_shared_auth_policy", None)
    monkeypatch.setattr(project_binding, "_session_bindings", project_binding.SessionProjectBindingStore())
    auth_routes.init_auth_state()
    beta_root = tmp_path / "beta"
    beta_root.mkdir()
    beta = project_binding.get_project_registry().add_project(name="beta", path=str(beta_root)).id
    app = FastAPI()
    app.middleware("http")(verify_access_token)
    app.include_router(auth_routes.router)
    app.include_router(agent_stream_api.router)
    app.mount("/", boundary.app)
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"pin": "r48-synthetic-pin"})
        assert login.status_code == 200
        headers = {
            "owner": {"Authorization": "Bearer " + login.json()["access_token"], "X-AGK-Session-Id": "r48-owner"},
            "foreign": {
                "Authorization": "Bearer " + auth_routes.get_token_service().issue_token("foreign"),
                "X-AGK-Session-Id": "r48-owner",
            },
        }
        yield ActiveCase(boundary, client, headers, beta)


def _body(case: ActiveCase, **extra: object) -> dict[str, object]:
    return {
        "model": "scripted",
        "project_id": case.boundary.project_id,
        "conversation_id": "r48-active",
        "messages": [{"role": "user", "content": "synthetic owner prompt"}],
        "stream": True,
        "agent_mode": True,
        "web_search": False,
        "code_mode": False,
        **extra,
    }


@pytest.mark.parametrize("second_subject,status", [("owner", 409), ("foreign", 404)])
def test_simultaneous_start_is_rejected_before_conversation_or_classifier_changes(
    active_case: ActiveCase,
    monkeypatch: pytest.MonkeyPatch,
    second_subject: str,
    status: int,
) -> None:
    from tests.chat_boundary_helpers import ModelDouble

    case = active_case
    classifying = threading.Event()
    release = threading.Event()
    classification_calls: list[int] = []
    results: list[object] = []

    def classify(*args: object, **kwargs: object) -> str:
        classification_calls.append(1)
        if len(classification_calls) == 1:
            classifying.set()
            assert release.wait(8)
        return "GENERAL"

    monkeypatch.setattr(ModelDouble, "generate", classify)
    owner = threading.Thread(
        target=lambda: results.append(
            case.client.post("/v1/chat/completions", json=_body(case), headers=case.headers["owner"])
        ),
        daemon=True,
    )
    owner.start()
    try:
        assert classifying.wait(5)
        response = case.client.post(
            "/v1/chat/completions",
            headers=case.headers[second_subject],
            json=_body(case, conversation_id="rejected-preparation"),
        )
        assert response.status_code == status
        assert (
            case.boundary.store.get(project_id=case.boundary.project_id, conversation_id="rejected-preparation") is None
        )
        assert len(classification_calls) == 1
        assert case.boundary.runtime.calls == []
    finally:
        release.set()
        owner.join(8)
    assert not owner.is_alive()
    assert len(results) == 1 and results[0].status_code == 200


@pytest.mark.parametrize("producer", ["chat", "legacy"])
def test_authenticated_foreign_and_switched_requests_cannot_read_or_replace_active_response(
    active_case: ActiveCase,
    monkeypatch: pytest.MonkeyPatch,
    producer: str,
) -> None:
    from antigravity_k.api.routes import session_state

    case = active_case
    reached = threading.Event()
    release = threading.Event()
    results: list[object] = []

    def chunks(*args: object, **kwargs: object) -> Iterator[str]:
        yield "synthetic-owner-secret"
        reached.set()
        assert release.wait(8), "test must release the scripted provider"

    monkeypatch.setattr(case.boundary.runtime, "stream", chunks)
    if producer == "legacy":
        from types import SimpleNamespace

        from antigravity_k.api.routes import agent_stream_api

        runtime = SimpleNamespace(
            orchestrator=None,
            resolve_model=lambda: "scripted",
            start_stream=lambda *a, **kw: SimpleNamespace(task_id=None, chunks=chunks()),
            observe_interaction=lambda **kw: None,
        )
        monkeypatch.setattr(agent_stream_api, "get_agent_runtime", lambda: runtime)

    def produce() -> None:
        if producer == "chat":
            response = case.client.post("/v1/chat/completions", json=_body(case), headers=case.headers["owner"])
        else:
            response = case.client.get(
                "/api/stream_agent?q=synthetic-owner-prompt&project_id=" + case.boundary.project_id,
                headers=case.headers["owner"],
            )
        results.append(response)

    thread = threading.Thread(target=produce, daemon=True)
    thread.start()
    try:
        assert reached.wait(5)
        session = session_state.get_active_session()
        history = tuple(session.history)
        own = case.client.get("/api/agent/active", headers=case.headers["owner"])
        assert own.status_code == 200 and own.json()["history"] == ["synthetic-owner-secret"]
        # A valid foreign token is authenticated, but does not own this response.
        assert case.client.get("/api/agent/active", headers=case.headers["foreign"]).status_code == 404
        assert case.client.get("/api/agent/active").status_code == 401
        for path in ("/api/stream_agent?reconnect=true", "/v1/chat/completions/reconnect"):
            assert case.client.get(path, headers=case.headers["foreign"]).status_code == 404
            switched = {**case.headers["owner"], "X-AGK-Session-Id": "other-session"}
            assert case.client.get(path, headers=switched).status_code == 404
            assert (
                case.client.get(
                    path + ("&" if "?" in path else "?") + "project_id=" + case.beta, headers=case.headers["owner"]
                ).status_code
                == 404
            )
        replacement = _body(case, conversation_id="r48-replace", actor_subject="user", owner_subject="user")
        assert (
            case.client.post("/v1/chat/completions", json=replacement, headers=case.headers["foreign"]).status_code
            == 404
        )
        assert (
            case.client.post(
                "/v1/chat/completions",
                json=_body(case, conversation_id="r48-own-repeat"),
                headers=case.headers["owner"],
            ).status_code
            == 409
        )
        assert (
            case.client.get(
                "/api/stream_agent?q=replace&project_id=" + case.boundary.project_id, headers=case.headers["foreign"]
            ).status_code
            == 404
        )
        assert session_state.get_active_session() is session
        assert session.is_active and tuple(session.history) == history
    finally:
        release.set()
        thread.join(8)
    assert not thread.is_alive()
    assert results and results[0].status_code == 200
    assert not session_state.get_active_session().is_active


@pytest.mark.parametrize("path", ["/api/stream_agent?reconnect=true", "/v1/chat/completions/reconnect"])
def test_owner_reconnect_replays_its_bound_history(
    active_case: ActiveCase,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    from antigravity_k.api.routes import agent_stream_api, session_state

    case = active_case
    reached = threading.Event()
    release = threading.Event()
    reconnect_ready = threading.Event()
    responses: list[object] = []
    original_snapshot = session_state.active_response_snapshot

    def snapshot(request=None, **kwargs):
        result = original_snapshot(request, **kwargs)
        if request is not None and "reconnect" in str(request.url):
            reconnect_ready.set()
        return result

    def chunks(*args: object, **kwargs: object) -> Iterator[str]:
        yield "owner-reconnect-history"
        reached.set()
        assert release.wait(8)

    monkeypatch.setattr(case.boundary.runtime, "stream", chunks)
    monkeypatch.setattr(session_state, "active_response_snapshot", snapshot)
    monkeypatch.setattr(agent_stream_api, "active_response_snapshot", snapshot)
    producer = threading.Thread(
        target=lambda: case.client.post("/v1/chat/completions", json=_body(case), headers=case.headers["owner"]),
        daemon=True,
    )
    reader = threading.Thread(
        target=lambda: responses.append(case.client.get(path, headers=case.headers["owner"])), daemon=True
    )
    producer.start()
    try:
        assert reached.wait(5)
        reader.start()
        assert reconnect_ready.wait(5)
    finally:
        release.set()
        producer.join(8)
        if reader.ident is not None:
            reader.join(8)
    assert not producer.is_alive() and not reader.is_alive()
    assert len(responses) == 1 and responses[0].status_code == 200
    assert "owner-reconnect-history" in responses[0].text


def test_reconnect_snapshot_stops_before_another_generation(active_case: ActiveCase) -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    from antigravity_k.api.project_binding import bind_session_active_project, resolve_project_execution_context
    from antigravity_k.api.routes.session_state import active_response_snapshot, begin_active_response

    case = active_case
    context = resolve_project_execution_context(
        project_id=case.boundary.project_id, session_id="r48-owner", actor_subject="user", bind=False
    )
    session = begin_active_response(context)
    session.history.append("owner-only")
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-agk-session-id", b"r48-owner")],
            "query_string": b"",
            "state": {"auth_subject": "user"},
        }
    )
    initial = active_response_snapshot(request)
    assert initial is not None and initial.history == ("owner-only",)
    bind_session_active_project("r48-owner", case.beta)
    with pytest.raises(HTTPException) as denied:
        active_response_snapshot(request)
    assert denied.value.status_code == 404
    session.is_active = False
    foreign = context.model_copy(update={"actor_subject": "foreign", "session_id": "foreign-session"})
    next_session = begin_active_response(foreign)
    next_session.history.append("foreign-only")
    try:
        assert next_session is session
        assert active_response_snapshot(request, generation=initial.generation) is None
        assert initial.history == ("owner-only",)
    finally:
        session.is_active = False


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["chat", "legacy"])
async def test_existing_reconnect_never_follows_a_new_owner(
    active_case: ActiveCase,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    from starlette.requests import Request

    from antigravity_k.api.project_binding import resolve_project_execution_context
    from antigravity_k.api.routes import agent_stream_api, chat
    from antigravity_k.api.routes.session_state import begin_active_response

    context = resolve_project_execution_context(
        project_id=active_case.boundary.project_id, session_id="r48-owner", actor_subject="user", bind=False
    )
    session = begin_active_response(context)
    session.history.append("old-owner-history")
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-agk-session-id", b"r48-owner")],
            "query_string": b"",
            "state": {"auth_subject": "user"},
        }
    )

    async def next_owner(_delay: float) -> None:
        session.is_active = False
        foreign = context.model_copy(update={"actor_subject": "foreign", "session_id": "foreign-session"})
        begin_active_response(foreign).history.append("new-owner-private")

    monkeypatch.setattr(chat.asyncio, "sleep", next_owner)
    try:
        response = await (
            chat.chat_reconnect(request) if route == "chat" else agent_stream_api.stream_agent(request, reconnect=True)
        )
        frames = [frame async for frame in response.body_iterator]
        assert "old-owner-history" in "".join(frames)
        assert "new-owner-private" not in "".join(frames)
        assert session.owner is not None and session.owner.actor_subject == "foreign"
    finally:
        session.is_active = False


def test_http_does_not_adopt_unbound_internal_response(active_case: ActiveCase) -> None:
    from antigravity_k.api.routes.session_state import get_active_session

    session = get_active_session()
    session.is_active = True
    session.q = "legacy-private"
    session.history[:] = ["legacy-private-history"]
    try:
        for path in ("/api/agent/active", "/api/stream_agent?reconnect=true", "/v1/chat/completions/reconnect"):
            assert active_case.client.get(path, headers=active_case.headers["owner"]).status_code == 404
    finally:
        session.is_active = False


def test_preparation_failure_releases_only_its_reservation(
    active_case: ActiveCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from antigravity_k.api.routes import chat
    from antigravity_k.api.routes.session_state import get_active_session

    def fail(*args: object, **kwargs: object) -> object:
        assert get_active_session().is_active
        raise RuntimeError("synthetic preparation failed")

    monkeypatch.setattr(chat, "_apply_authoritative_conversation", fail)
    with pytest.raises(RuntimeError, match="synthetic preparation failed"):
        active_case.client.post("/v1/chat/completions", json=_body(active_case), headers=active_case.headers["owner"])
    assert not get_active_session().is_active
    assert active_case.boundary.runtime.calls == []


@pytest.mark.asyncio
async def test_unstarted_body_close_does_not_release_a_later_owner(active_case: ActiveCase) -> None:
    from collections.abc import AsyncGenerator

    from antigravity_k.api.project_binding import resolve_project_execution_context
    from antigravity_k.api.routes.session_state import ActiveResponseBody, begin_active_response, finish_active_response

    context = resolve_project_execution_context(
        project_id=active_case.boundary.project_id, actor_subject="user", session_id="r48-owner", bind=False
    )
    session = begin_active_response(context)
    old_generation = session.generation

    async def content() -> AsyncGenerator[str, None]:
        yield "unused"

    body = ActiveResponseBody(content(), old_generation)
    finish_active_response(old_generation)
    newer = begin_active_response(context.model_copy(update={"actor_subject": "foreign"}))
    try:
        await body.aclose()
        assert newer.is_active and newer.generation != old_generation
    finally:
        finish_active_response(newer.generation)


@pytest.mark.asyncio
async def test_failed_concurrent_close_does_not_release_a_running_body(active_case: ActiveCase) -> None:
    import asyncio
    from collections.abc import AsyncGenerator

    from antigravity_k.api.project_binding import resolve_project_execution_context
    from antigravity_k.api.routes.session_state import ActiveResponseBody, begin_active_response

    context = resolve_project_execution_context(
        project_id=active_case.boundary.project_id, actor_subject="user", session_id="r48-owner", bind=False
    )
    session = begin_active_response(context)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def content() -> AsyncGenerator[str, None]:
        entered.set()
        await release.wait()
        yield "running-owner-content"

    body = ActiveResponseBody(content(), session.generation)
    pending = asyncio.create_task(anext(body))
    await entered.wait()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await body.aclose()
        assert session.is_active
    finally:
        release.set()
        await pending
        await body.aclose()
    assert not session.is_active


@pytest.mark.asyncio
async def test_headers_disconnect_releases_unstarted_reserved_response(active_case: ActiveCase) -> None:
    import json

    from starlette.requests import ClientDisconnect

    from antigravity_k.api.routes.session_state import get_active_session

    body = json.dumps(_body(active_case)).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            assert get_active_session().is_active
            raise OSError("synthetic headers disconnect")

    with pytest.raises(ClientDisconnect):
        await active_case.boundary.app(scope, receive, send)
    assert not get_active_session().is_active
    assert get_active_session().error is None
    assert active_case.boundary.runtime.calls == []
