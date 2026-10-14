"""Canonical filesystem allowlist for API-controlled paths."""

from __future__ import annotations

import os
from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when an API path is outside the configured workspace roots."""


def configured_allowed_bases() -> tuple[Path, ...]:
    """Return trusted bases from config + ``AGK_ALLOWED_ROOTS`` only.

    Unlike ``allowed_roots()``, this intentionally excludes project-registry
    paths so a poisoned registry entry cannot self-allowlist as a canonical
    execution root (ARC-01 boundary).
    """
    from antigravity_k.config import config

    roots = [config.paths.project_root.expanduser().resolve()]
    configured = os.environ.get("AGK_ALLOWED_ROOTS", "")
    roots.extend(Path(item).expanduser().resolve() for item in configured.split(os.pathsep) if item.strip())
    return tuple(dict.fromkeys(roots))


def allowed_roots() -> tuple[Path, ...]:
    """Return the configured project root plus explicitly allowlisted roots and registered projects."""
    roots = list(configured_allowed_bases())
    try:
        from antigravity_k.engine.project_registry import get_project_registry

        registry = get_project_registry()
        for p in registry.list_projects():
            if p.get("path"):
                roots.append(Path(p["path"]).expanduser().resolve())
    except Exception:
        pass
    return tuple(dict.fromkeys(roots))


def resolve_allowed_path(raw_path: str | Path) -> Path:
    """Resolve a path and require it to remain below one configured root."""
    roots = allowed_roots()
    path = Path(raw_path).expanduser()
    candidate = (path if path.is_absolute() else roots[0] / path).resolve()
    for root in roots:
        try:
            _ = candidate.relative_to(root)
        except ValueError:
            continue
        return candidate
    raise PathSecurityError(f"Path is outside configured workspace roots: {candidate}")
