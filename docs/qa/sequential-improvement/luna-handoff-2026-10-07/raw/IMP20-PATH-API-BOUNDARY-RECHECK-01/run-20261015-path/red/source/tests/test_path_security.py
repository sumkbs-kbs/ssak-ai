from __future__ import annotations

from pathlib import Path

import pytest

from antigravity_k.api.path_security import PathSecurityError, resolve_allowed_path
from antigravity_k.config import config


def test_resolve_allowed_path_accepts_descendant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.paths, "project_root", tmp_path)

    assert resolve_allowed_path(tmp_path / "notes" / "idea.md") == tmp_path / "notes" / "idea.md"


def test_resolve_allowed_path_resolves_relative_input_from_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.paths, "project_root", tmp_path)

    assert resolve_allowed_path("notes/idea.md") == tmp_path / "notes" / "idea.md"


def test_resolve_allowed_path_rejects_absolute_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(config.paths, "project_root", workspace)

    with pytest.raises(PathSecurityError):
        resolve_allowed_path(outside)


def test_resolve_allowed_path_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(config.paths, "project_root", workspace)

    with pytest.raises(PathSecurityError):
        resolve_allowed_path(workspace / "link" / "secret.md")
