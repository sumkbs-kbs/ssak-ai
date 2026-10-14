"""Canonical tool path resolution under request project root (WS-02).

PermissionGate and tool open/subprocess paths must use the same absolute
resolved path. Relative inputs join the request-scoped canonical root — never
the process cwd. Escapes via ``..``, symlink-out, or mixed separators are
rejected.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PATH_ARG_KEYS: tuple[str, ...] = (
    "file_path",
    "path",
    "target",
    "dir_path",
    "cwd",
)

SHELL_CWD_TOOLS: frozenset[str] = frozenset(
    {
        "run_bash_command",
        "bash",
        "run_persistent_command",
    }
)

ROOT_DEFAULT_PATH_TOOLS: frozenset[str] = frozenset(
    {
        "list_directory",
        "glob_search",
        "grep_search",
        "git_status",
        "git_diff",
        "git_commit",
        "git_log",
    }
)


class ToolPathError(ValueError):
    """Raised when a tool path escapes the canonical project root."""

    def __init__(self, message: str, *, raw_path: str = "", project_root: str = "") -> None:
        super().__init__(message)
        self.raw_path = raw_path
        self.project_root = project_root


@dataclass(frozen=True, slots=True)
class ResolvedToolPath:
    """One path argument rewritten to an absolute path under the project root."""

    arg_key: str
    raw_path: str
    inspected_path: str
    executed_path: str
    project_root: str

    @property
    def correlated(self) -> bool:
        return self.inspected_path == self.executed_path


_audit_lock = threading.Lock()
_audit_enabled: bool = False
_audit_events: list[dict[str, Any]] = []


def enable_path_audit_capture() -> list[dict[str, Any]]:
    """Enable in-memory path audit capture (tests). Clears prior events."""
    global _audit_enabled
    with _audit_lock:
        _audit_events.clear()
    _audit_enabled = True
    return _audit_events


def disable_path_audit_capture() -> None:
    global _audit_enabled
    _audit_enabled = False


def get_path_audit_events() -> list[dict[str, Any]]:
    with _audit_lock:
        return list(_audit_events)


def record_path_audit(event: Mapping[str, Any]) -> None:
    """Record a correlated inspected/executed path audit event."""
    payload = dict(event)
    if _audit_enabled:
        with _audit_lock:
            _audit_events.append(payload)
    try:
        from antigravity_k.engine.event_bus import global_event_bus

        global_event_bus.publish("ToolPathAudit", **payload)
    except Exception:
        logger.debug("ToolPathAudit event publish skipped", exc_info=True)


def effective_project_root(fallback: str | None = None) -> str:
    """Return request-scoped canonical root, else fallback, else process cwd."""
    try:
        from antigravity_k.api.project_binding import get_request_project_root

        bound = get_request_project_root()
        if bound:
            return os.path.realpath(bound)
    except Exception:
        logger.debug("request project root unavailable", exc_info=True)

    if fallback:
        return os.path.realpath(os.path.abspath(fallback))
    return os.path.realpath(os.getcwd())


def _normalize_separators(raw: str) -> str:
    """Normalize mixed separators so ``\\`` cannot hide ``..`` on POSIX."""
    if os.name == "nt":
        return raw.replace("/", "\\")
    if "\\" in raw:
        return raw.replace("\\", "/")
    return raw


def _is_under_root(resolved: str, root_real: str) -> bool:
    if resolved == root_real:
        return True
    prefix = root_real.rstrip(os.sep) + os.sep
    return resolved.startswith(prefix)


def resolve_tool_path(raw_path: str, project_root: str) -> str:
    """Resolve ``raw_path`` to an absolute real path under ``project_root``.

    Relative paths join ``project_root`` (never process cwd). Absolute paths and
    symlink targets must remain inside the root after ``realpath``. Missing leaf
    paths (writes) resolve via the nearest existing parent.
    """
    if raw_path is None or not str(raw_path).strip():
        raise ToolPathError(
            "Tool path must not be empty",
            raw_path=str(raw_path),
            project_root=project_root,
        )

    raw = str(raw_path)
    if "\x00" in raw:
        raise ToolPathError("Tool path must not contain NUL", raw_path=raw, project_root=project_root)

    root_abs = os.path.abspath(project_root)
    if not os.path.isdir(root_abs):
        raise ToolPathError(
            "Project root is not an existing directory",
            raw_path=raw,
            project_root=project_root,
        )
    root_real = os.path.realpath(root_abs)

    normalized = _normalize_separators(os.path.expanduser(raw))
    if os.path.isabs(normalized):
        candidate = normalized
    else:
        candidate = os.path.join(root_real, normalized)

    lexical = os.path.normpath(candidate)

    if os.path.lexists(lexical):
        resolved = os.path.realpath(lexical)
    else:
        parent = os.path.dirname(lexical)
        trail: list[str] = []
        remainder = os.path.basename(lexical)
        if remainder and remainder != os.curdir:
            trail.append(remainder)
        while parent and parent != os.path.dirname(parent) and not os.path.isdir(parent):
            trail.insert(0, os.path.basename(parent))
            parent = os.path.dirname(parent)
        if parent and os.path.isdir(parent):
            parent_real = os.path.realpath(parent)
        else:
            parent_real = root_real
        resolved = os.path.normpath(os.path.join(parent_real, *trail)) if trail else parent_real

    if not _is_under_root(resolved, root_real):
        raise ToolPathError(
            f"Tool path escapes project root: {raw}",
            raw_path=raw,
            project_root=root_real,
        )
    return resolved


_APPLY_PATCH_PATH_PREFIXES: tuple[str, ...] = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Delete File: ",
)

_SHELL_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_REDIRECTION_OPERATORS: frozenset[str] = frozenset({">", ">>", "<", "<>"})


def extract_apply_patch_paths(patch_text: str) -> list[str]:
    """Return file paths declared in apply_patch headers (parse-based)."""
    if not patch_text or not str(patch_text).strip():
        return []
    try:
        from antigravity_k.engine.diff_engine import DiffApplyEngine

        patches = DiffApplyEngine().parse_apply_patch(str(patch_text))
    except Exception:
        logger.debug("apply_patch parse failed during path extract", exc_info=True)
        return []
    return [p.file_path for p in patches if getattr(p, "file_path", None)]


def rewrite_apply_patch_text(
    patch_text: str,
    project_root: str,
    *,
    tool_name: str = "apply_patch",
) -> tuple[str, list[ResolvedToolPath]]:
    """Resolve every apply_patch file path under ``project_root`` and rewrite headers.

    Raises ``ToolPathError`` if any declared path escapes the canonical root.
    """
    raw_text = str(patch_text)
    paths = extract_apply_patch_paths(raw_text)
    if not paths:
        return raw_text, []

    root_real = os.path.realpath(os.path.abspath(project_root))
    rewritten = raw_text
    resolutions: list[ResolvedToolPath] = []

    for raw_path in paths:
        resolved = resolve_tool_path(raw_path, root_real)
        replaced = False
        for prefix in _APPLY_PATCH_PATH_PREFIXES:
            needle = f"{prefix}{raw_path}"
            if needle in rewritten:
                rewritten = rewritten.replace(needle, f"{prefix}{resolved}", 1)
                replaced = True
                break
        if not replaced:
            # Parser saw the path; keep execute-time resolve as backstop.
            logger.debug("apply_patch header for %r not rewritten in text", raw_path)

        item = ResolvedToolPath(
            arg_key="patch",
            raw_path=raw_path,
            inspected_path=resolved,
            executed_path=resolved,
            project_root=root_real,
        )
        resolutions.append(item)
        record_path_audit(
            {
                "tool": tool_name,
                "arg_key": "patch",
                "raw_path": raw_path,
                "inspected_path": resolved,
                "executed_path": resolved,
                "project_root": root_real,
                "correlated": True,
            }
        )

    return rewritten, resolutions


def _is_shell_escape_path_candidate(token: str) -> bool:
    """True when a shell token may reference a filesystem path outside cwd semantics."""
    if not token or token.startswith("-"):
        return False
    # expandvars first: ``$HOME/x`` and ``${HOME}/x`` must resolve to the real
    # absolute path before the containment check, otherwise the lexical pass
    # would pass a token that the shell later expands outside the root (FR-02).
    expanded = os.path.expandvars(os.path.expanduser(token))
    normalized = _normalize_separators(expanded)
    if os.path.isabs(normalized):
        return True
    if normalized.startswith("~"):
        return True
    parts = normalized.replace("\\", "/").split("/")
    return ".." in parts


def iter_shell_escape_path_candidates(command: str) -> list[str]:
    """Extract absolute / ``..`` / ``~/`` path tokens from a shell command."""
    if not command or not str(command).strip():
        return []
    try:
        lexer = shlex.shlex(str(command), posix=os.name != "nt", punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = str(command).split()

    out: list[str] = []
    seen: set[str] = set()
    for index, tok in enumerate(tokens):
        if not tok:
            continue
        if _SHELL_ENV_ASSIGN_RE.match(tok):
            continue
        candidate = tok
        if tok in _SHELL_REDIRECTION_OPERATORS:
            if index + 1 >= len(tokens):
                continue
            candidate = tokens[index + 1]
        if not _is_shell_escape_path_candidate(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


_SHELL_SUBSTITUTION_RE = re.compile(r"\$\(|`")


def assert_shell_command_paths_in_root(command: str, project_root: str) -> None:
    """Raise ``ToolPathError`` if the command references a path outside ``project_root``.

    Command substitution (``$(...)`` / backticks) is rejected outright: its
    result cannot be resolved statically, so the boundary cannot be argued from
    token inspection alone. The OS sandbox remains the executing boundary; this
    check provides the fast, explicit denial.
    """
    if _SHELL_SUBSTITUTION_RE.search(str(command or "")):
        raise ToolPathError(
            "Shell command uses command substitution; statically unresolvable commands are denied",
            raw_path=str(command)[:200],
            project_root=project_root,
        )
    root_real = os.path.realpath(os.path.abspath(project_root))
    for raw in iter_shell_escape_path_candidates(command):
        # Resolve the *expanded* form: ``resolve_tool_path`` itself performs no
        # variable expansion, so ``$HOME/x`` must be expanded here or it would
        # be treated as an in-root relative path (FR-02).
        expanded = os.path.expandvars(os.path.expanduser(raw))
        resolve_tool_path(expanded, root_real)


def rewrite_tool_args(
    tool_name: str,
    args: Mapping[str, object],
    project_root: str,
) -> tuple[dict[str, object], list[ResolvedToolPath]]:
    """Rewrite path-bearing tool args to absolute paths under ``project_root``.

    Injects explicit ``cwd`` for shell tools so subprocess never inherits an
    ambient process cwd that differs from the bound project.
    """
    root_real = os.path.realpath(os.path.abspath(project_root))
    rewritten: dict[str, object] = dict(args)
    resolutions: list[ResolvedToolPath] = []

    if tool_name == "apply_patch":
        patch_val = rewritten.get("patch")
        if isinstance(patch_val, str) and patch_val.strip():
            new_patch, patch_resolutions = rewrite_apply_patch_text(
                patch_val,
                root_real,
                tool_name=tool_name,
            )
            rewritten["patch"] = new_patch
            resolutions.extend(patch_resolutions)

    if tool_name in SHELL_CWD_TOOLS and "cwd" not in rewritten:
        rewritten["cwd"] = root_real

    if tool_name in SHELL_CWD_TOOLS:
        command_val = rewritten.get("command")
        if isinstance(command_val, str) and command_val.strip():
            assert_shell_command_paths_in_root(command_val, root_real)

    if tool_name in ROOT_DEFAULT_PATH_TOOLS:
        raw_path = rewritten.get("path", ".")
        if raw_path is None or (isinstance(raw_path, str) and raw_path.strip() in {"", "."}):
            rewritten["path"] = root_real

    for key in PATH_ARG_KEYS:
        if key not in rewritten:
            continue
        value = rewritten[key]
        if not isinstance(value, str) or not value.strip():
            continue
        resolved = resolve_tool_path(value, root_real)
        rewritten[key] = resolved
        item = ResolvedToolPath(
            arg_key=key,
            raw_path=value,
            inspected_path=resolved,
            executed_path=resolved,
            project_root=root_real,
        )
        resolutions.append(item)
        record_path_audit(
            {
                "tool": tool_name,
                "arg_key": key,
                "raw_path": value,
                "inspected_path": resolved,
                "executed_path": resolved,
                "project_root": root_real,
                "correlated": True,
            }
        )

    if tool_name in SHELL_CWD_TOOLS and not any(r.arg_key == "cwd" for r in resolutions):
        cwd_val = str(rewritten.get("cwd", root_real))
        resolved_cwd = resolve_tool_path(cwd_val, root_real)
        rewritten["cwd"] = resolved_cwd
        resolutions.append(
            ResolvedToolPath(
                arg_key="cwd",
                raw_path=cwd_val,
                inspected_path=resolved_cwd,
                executed_path=resolved_cwd,
                project_root=root_real,
            )
        )
        record_path_audit(
            {
                "tool": tool_name,
                "arg_key": "cwd",
                "raw_path": cwd_val,
                "inspected_path": resolved_cwd,
                "executed_path": resolved_cwd,
                "project_root": root_real,
                "correlated": True,
            }
        )

    return rewritten, resolutions


__all__ = [
    "PATH_ARG_KEYS",
    "ROOT_DEFAULT_PATH_TOOLS",
    "SHELL_CWD_TOOLS",
    "ResolvedToolPath",
    "ToolPathError",
    "assert_shell_command_paths_in_root",
    "disable_path_audit_capture",
    "effective_project_root",
    "enable_path_audit_capture",
    "extract_apply_patch_paths",
    "get_path_audit_events",
    "iter_shell_escape_path_candidates",
    "record_path_audit",
    "resolve_tool_path",
    "rewrite_apply_patch_text",
    "rewrite_tool_args",
]
