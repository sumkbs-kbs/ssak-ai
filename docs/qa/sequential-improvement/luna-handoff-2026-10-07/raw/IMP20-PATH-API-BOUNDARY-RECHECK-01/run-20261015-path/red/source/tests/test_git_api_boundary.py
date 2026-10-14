import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, final

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from antigravity_k.api.routes import git_api
from antigravity_k.api.server import app
from antigravity_k.config import config
from antigravity_k.tools.tool_contracts import Permission, PermissionDecision, ToolInvocation


class _CompletedLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


@final
@dataclass
class _FakeCompleted:
    returncode: int = 0
    stdout: str = "ok"
    stderr: str = ""


def _git_helper(args: list[str], *, cwd: str, timeout: int | None = None) -> str:
    command = cast(Callable[..., str], getattr(git_api, "_git"))
    return command(args, cwd=cwd, timeout=timeout)


def _resolve_repo_file(file_path: str, cwd: str) -> str:
    resolver = cast(Callable[[str, str], str], getattr(git_api, "_resolve_repo_file"))
    return resolver(file_path, cwd)


def test_git_helper_rejects_working_directory_outside_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(config.paths, "project_root", project_root)

    with pytest.raises(HTTPException) as error:
        _ = _git_helper(["status"], cwd=str(outside))

    assert error.value.status_code == 403


def test_git_helper_resolves_relative_path_inside_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    repo = project_root / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(config.paths, "project_root", project_root)
    calls: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> _CompletedLike:
        calls["args"] = args
        calls["kwargs"] = kwargs
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _git_helper(["status"], cwd="repo") == "ok"
    assert calls["args"] == ["git", "status"]
    kwargs = cast(dict[str, object], calls["kwargs"])
    assert kwargs["cwd"] == str(repo.resolve())
    assert kwargs["check"] is False


def test_git_file_path_rejects_escape_from_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(config.paths, "project_root", project_root)

    with pytest.raises(HTTPException) as error:
        _ = _resolve_repo_file("../outside.txt", ".")

    assert error.value.status_code == 403


def test_git_commit_honors_permission_denial_before_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    class DenyGate:
        def decide(self, invocation: ToolInvocation) -> PermissionDecision:
            return PermissionDecision(
                spec=invocation.spec,
                permission=Permission.DENY,
                source="test",
                reason="denied by test",
            )

    monkeypatch.setattr(git_api, "_permission_gate", lambda: DenyGate(), raising=False)

    def fake_git(*_args: object, **_kwargs: object) -> str:
        return "no-op"

    monkeypatch.setattr(git_api, "_git", fake_git)
    headers = {"X-Access-Pin": config.security.access_pin}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/git/commit",
            json={"path": ".", "message": "should be denied"},
            headers=headers,
        )

    assert response.status_code == 403
