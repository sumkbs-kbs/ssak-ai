from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send

if TYPE_CHECKING:
    from antigravity_k.engine.conversation_store import ConversationStore
    from antigravity_k.tools.web_search import WebSearchTool


class ModelDouble:
    def generate(self, *, prompt: str, target: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        return "SEARCH" if max_tokens == 10 else "provider-answer"

    def stream_generate(self, *, prompt: str, target: str, task_type: str = "") -> Iterator[str]:
        yield "provider-answer"


class RuntimeDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[Mapping[str, str], ...]] = []
        self.search_denials: list[str | None] = []
        self.code_denials: list[str | None] = []
        self.side_effects_allowed: list[bool] = []
        self.chunks: list[str] = ["runtime-answer"]
        self.event_modes: list[bool] = []
        self.error: RuntimeError | None = None

    def stream(self, messages: Sequence[Mapping[str, str]], target_model: str) -> Iterator[str]:
        from antigravity_k.engine.chat_stream_events import chat_stream_events_enabled
        from antigravity_k.engine.tool_policy import request_allows_side_effects, tool_policy_denial

        self.calls.append(tuple(messages))
        self.search_denials.append(tool_policy_denial("web_search", None))
        self.code_denials.append(tool_policy_denial("run_bash_command", None))
        self.side_effects_allowed.append(request_allows_side_effects())
        self.event_modes.append(chat_stream_events_enabled())
        yield from self.chunks
        if self.error is not None:
            raise self.error


@dataclass(frozen=True, slots=True)
class Boundary:
    app: FastAPI
    client: TestClient
    store: ConversationStore
    runtime: RuntimeDouble
    searches: list[str]
    project_id: str


async def paused_chat_stream(boundary: Boundary, body: bytes) -> StreamingResponse:
    from antigravity_k.api.routes import chat

    responses: list[StreamingResponse] = []

    class PausedResponse(StreamingResponse):
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            responses.append(self)

    scope: Scope = {
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

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        del message

    with pytest.MonkeyPatch.context() as transport:
        transport.setattr(chat, "StreamingResponse", PausedResponse)
        await boundary.app(scope, receive, send)
    assert len(responses) == 1
    return responses[0]


@pytest.fixture
def boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Boundary]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from antigravity_k.api import dependencies, project_binding
    from antigravity_k.api.contracts.errors import ExecutionContextError
    from antigravity_k.api.error_handler import global_exception_handler
    from antigravity_k.api.routes import chat, session_state
    from antigravity_k.config import config
    from antigravity_k.engine import conversation_store
    from antigravity_k.engine.audit_logger import AuditLogger
    from antigravity_k.engine.conversation_store import ConversationStore
    from antigravity_k.engine.project_registry import ProjectRegistry
    from antigravity_k.engine.protocol_translator import ProtocolTranslator
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.tools.web_search import WebSearchTool

    monkeypatch.setattr(config.paths, "project_root", tmp_path.resolve())
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)
    registry = ProjectRegistry(storage_path=tmp_path / "projects.json")
    project = registry.add_project(name="chat-boundary", path=str(tmp_path))
    store = ConversationStore(storage_dir=tmp_path / "conversations")
    session = SessionManager(base_dir=str(tmp_path / "sessions"))
    audit = AuditLogger(log_dir=tmp_path / "audit")
    runtime = RuntimeDouble()
    searches: list[str] = []

    def search(_tool: WebSearchTool, *, query: str) -> str:
        searches.append(query)
        return "https://example.com/result"

    monkeypatch.setattr(project_binding, "get_project_registry", lambda: registry)
    monkeypatch.setattr(conversation_store, "_store_singleton", store)
    monkeypatch.setattr(dependencies, "get_session_manager", lambda: session)
    monkeypatch.setattr(chat, "get_audit_logger", lambda: audit)
    monkeypatch.setattr(chat, "get_agent_runtime", lambda: runtime)
    monkeypatch.setattr(session_state, "_active_session", session_state.ActiveAgentSession())
    monkeypatch.setattr(WebSearchTool, "execute", search)
    app = FastAPI()
    app.add_exception_handler(ExecutionContextError, global_exception_handler)
    app.include_router(chat.router)
    app.dependency_overrides[chat.get_model_manager] = ModelDouble
    app.dependency_overrides[chat.get_translator] = ProtocolTranslator
    with TestClient(app) as client:
        yield Boundary(app, client, store, runtime, searches, project.id)
