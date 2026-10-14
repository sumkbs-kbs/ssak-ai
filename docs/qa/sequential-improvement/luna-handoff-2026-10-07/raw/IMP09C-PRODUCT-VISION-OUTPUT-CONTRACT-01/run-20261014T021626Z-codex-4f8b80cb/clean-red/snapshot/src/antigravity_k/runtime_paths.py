"""Runtime path resolution for repository and installed-package deployments."""

from __future__ import annotations

from importlib.resources import files as resource_files
from pathlib import Path


def default_config_path(project_root: Path | None = None) -> Path:
    """Prefer a workspace config and fall back to the packaged default."""
    root = project_root or Path(__file__).resolve().parents[2]
    workspace_config = root / "config.yaml"
    if workspace_config.is_file():
        return workspace_config
    packaged_config = resource_files("antigravity_k").joinpath("config.yaml")
    if packaged_config.is_file():
        return Path(str(packaged_config))
    return workspace_config
