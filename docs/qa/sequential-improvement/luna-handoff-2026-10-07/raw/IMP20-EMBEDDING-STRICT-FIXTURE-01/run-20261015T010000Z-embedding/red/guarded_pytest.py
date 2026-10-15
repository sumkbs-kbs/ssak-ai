# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest", "fastapi"]
# ///
# Run: candidate/.venv/bin/python -B guarded_pytest.py PHASE
"""Run copied tests with socket/process denial and captured ASGI responses."""

from __future__ import annotations

import json
import socket
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import Client, Request, Response

BASE = Path(__file__).resolve().parent
PHASE = sys.argv[1]
OUT = BASE / PHASE
COUNTS = {"network_attempts": 0, "listen_attempts": 0, "process_attempts": 0}
RESPONSES: list[dict[str, str | int]] = []


def audit(event: str, args: tuple[socket.socket, ...]) -> None:
    if event in {"socket.connect", "socket.bind"}:
        sock = args[0]
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            key = "network_attempts" if event == "socket.connect" else "listen_attempts"
            COUNTS[key] += 1
            raise AssertionError(f"Unexpected network operation: {event}")
    if event in {"subprocess.Popen", "os.system", "os.fork", "os.posix_spawn"}:
        COUNTS["process_attempts"] += 1
        raise AssertionError(f"Unexpected process operation: {event}")


@asynccontextmanager
async def offline_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


class Plugin:
    @pytest.fixture(autouse=True)
    def offline_boundary(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        from antigravity_k.api.server import app

        monkeypatch.setattr(app.router, "lifespan_context", offline_lifespan)
        original_send = Client.send

        def capture(client: Client, request: Request, **kwargs) -> Response:
            response = original_send(client, request, **kwargs)
            RESPONSES.append({
                "method": request.method,
                "path": request.url.path,
                "request": request.content.decode(),
                "status": response.status_code,
                "response": response.content.decode(),
            })
            return response

        monkeypatch.setattr(Client, "send", capture)
        yield


sys.addaudithook(audit)
selector = (
    [str(BASE / "preimage/test_api_server.py") + "::test_embeddings_endpoint_uses_local_fallback"]
    if PHASE == "red"
    else [
        str(BASE / "postimage/test_api_server.py") + "::test_embeddings_endpoint_rejects_unavailable_model_without_fallback",
        str(BASE / "adjacent/test_embeddings_model_contract.py"),
    ]
)
args = [
    "-q", "-p", "no:cacheprovider", "--confcutdir", str(BASE),
    "--rootdir", str(BASE), "--basetemp", str(OUT / "runtime/pytest"),
    "--junitxml", str(OUT / "junit.xml"), "-o", "junit_family=legacy", *selector,
]
code = pytest.main(args, plugins=[Plugin()])
(OUT / "observations.json").write_text(json.dumps({"counts": COUNTS, "responses": RESPONSES}, indent=2) + "\n")
raise SystemExit(code)
