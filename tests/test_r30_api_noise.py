"""r30: typed API errors are handled without re-raise; non-git project status is not a 400."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from antigravity_k.api.routes import git_api


def test_typed_api_error_has_dedicated_handler() -> None:
    from antigravity_k.api.contracts.errors import APIError, ConversationNotFoundError
    from antigravity_k.api.server import app

    assert APIError in app.exception_handlers
    assert issubclass(ConversationNotFoundError, APIError)


def test_git_status_non_repo_is_normal_state(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_git(args: list[str], cwd: str = ".", timeout: int = 30) -> str:
        raise HTTPException(
            status_code=400, detail="fatal: not a git repository (or any of the parent directories): .git"
        )

    monkeypatch.setattr(git_api, "_git", fake_git)
    fn = getattr(git_api.git_status, "__wrapped__", git_api.git_status)
    result = asyncio.run(fn(path="r30-synthetic-nonrepo"))
    assert result == {"ok": False, "is_repo": False, "error": "not_a_git_repository"}


def test_git_status_other_400_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_git(args: list[str], cwd: str = ".", timeout: int = 30) -> str:
        raise HTTPException(status_code=400, detail="Git working directory does not exist.")

    monkeypatch.setattr(git_api, "_git", fake_git)
    fn = getattr(git_api.git_status, "__wrapped__", git_api.git_status)
    with pytest.raises(HTTPException):
        asyncio.run(fn(path="r30-synthetic-missing"))
