# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# .venv/bin/python -m pytest tests/test_vault_keyword_search_api.py -q --noconftest
# The child scenario uses this repository's installed dependencies only.
# ──────────────────
from __future__ import annotations

import os
import socket
import subprocess
import sys
from collections.abc import Mapping
from contextlib import ExitStack, chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar, Final, NoReturn, Protocol
from unittest.mock import patch

import pytest
from httpx import Response

REPOSITORY: Final = Path(__file__).resolve().parents[1]


class _SearchClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, str]) -> Response: ...


def _search(client: _SearchClient, query: str) -> Response:
    return client.get("/v1/notes/search", params={"q": query})


def _block_network(_socket: socket.socket, _address: tuple[str, int] | str) -> NoReturn:
    raise ConnectionRefusedError("Notes regression does not use external providers")


def _run_isolated_scenario(query: str) -> None:
    """Patch every state root before importing production modules in a child."""
    with TemporaryDirectory(prefix="ssak-notes-search-") as directory, ExitStack() as stack:
        root = Path(directory).resolve()
        project = root / "project"
        project.mkdir()
        environment = {
            "PATH": os.defpath,
            "AGK_ENV_FILE": str(root / "absent.env"),
            "AGK_CONFIG_FILE": str(root / "absent.yaml"),
            "AGK_TASK_DB_PATH": str(root / "tasks.db"),
            "AGK_USAGE_DB": str(root / "usage.json"),
            "AGK_SEC_PIN_HASH_FILE": str(root / "auth-hash"),
            "AGK_SEC_TOKEN_SECRET_FILE": str(root / "auth-secret"),
            "AGK_MCP_CONFIG": str(root / "empty-mcp.json"),
            "ANTIGRAVITY_VAULT_PATH": str(project / "vault"),
            "AGK_ALLOWED_ROOTS": str(project),
            "AGK_SEARCH_SSAK_ENABLED": "false",
            "XDG_CACHE_HOME": str(root / "cache"),
            "HF_HOME": str(root / "hf"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "GIT_CONFIG_GLOBAL": str(root / "absent.gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Synthetic QA",
            "GIT_AUTHOR_EMAIL": "qa@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic QA",
            "GIT_COMMITTER_EMAIL": "qa@example.invalid",
        }
        for reserved in ("HOME", "CODEX_HOME"):
            if reserved in os.environ:
                environment[reserved] = os.environ[reserved]
        for name in ("project_root", "models_dir", "data_dir", "documents_dir", "vectors_dir", "logs_dir", "wiki_dir"):
            path = project if name == "project_root" else root / name
            path.mkdir(exist_ok=True)
            environment[f"AGK_PATH_{name.upper()}"] = str(path)
        _ = (root / "empty-mcp.json").write_text('{"mcpServers":{}}', encoding="utf-8")
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        _ = stack.enter_context(patch.object(Path, "home", return_value=root))
        _ = stack.enter_context(patch.object(socket.socket, "connect", new=_block_network))
        stack.enter_context(chdir(project))
        _ = stack.enter_context(patch.object(sys, "dont_write_bytecode", True))
        sys.path.insert(0, str(REPOSITORY / "src"))

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydantic import BaseModel, ConfigDict, JsonValue

        from antigravity_k.api.dependencies import get_vault_engine
        from antigravity_k.api.routes.vault_api import router
        from antigravity_k.engine.vault import VaultEngine

        class SearchResponse(BaseModel):
            model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
            query: str
            semantic_results: list[dict[str, JsonValue]]
            keyword_results: list[str]

        # Given: real Git-first notes in one isolated Vault with optional RAG off.
        engine = VaultEngine(str(project / "vault"), sync_rag=False)
        engine.write_note("nested/seed.md", {"title": "QA seed", "tags": ["qa"]}, "QA_SEED_TEXT 사과바나나")
        engine.write_note("other.md", {"title": "QA other"}, "Unrelated synthetic note")
        assert engine.search_notes("qa_seed_text") == ["nested/seed.md"]
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_vault_engine] = lambda: engine

        # When: call the production route with no substitute vector-store attribute.
        with TestClient(app, raise_server_exceptions=False) as client:
            response = _search(client, query)

        # Then: retain the API shape and real keyword result, or the query error.
        if not query:
            assert response.status_code == 400
            return
        assert response.status_code == 200, response.text
        result = SearchResponse.model_validate_json(response.text)
        assert result.query == query
        assert result.semantic_results == []
        expected = ["nested/seed.md"] if query.lower() in ("qa_seed_text", "사과바나나") else []
        assert result.keyword_results == expected


@pytest.mark.parametrize("query", ["QA_SEED_TEXT", "qa_seed_text", "사과바나나", "QA_MISSING_TEXT", ""])
def test_keyword_search_when_optional_rag_is_disabled(query: str) -> None:
    # Given: an import-clean child using the repository's installed dependencies.
    command = [sys.executable, str(Path(__file__).resolve()), query]
    # When: exercise the real Vault and route without reading developer state.
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    # Then: the child assertions prove the keyword and wire contracts.
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    _run_isolated_scenario(sys.argv[1])
