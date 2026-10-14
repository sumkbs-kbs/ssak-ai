"""Safe diagnostics ZIP export for support (Phase 4 minimal slice).

Allowlist-only archive contents. Never packs ``.env`` values, PIN, bearer,
``vault_data``, ``auth_hash``, or other secret-bearing paths. Log tails are
scrubbed with ``secret_scanner.redact_full`` before write.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from antigravity_k import __version__
from antigravity_k.engine.secret_scanner import is_sensitive_file, redact_full
from antigravity_k.engine.secret_scanner_patterns import MEMORY_PATH_SEGMENTS

logger = logging.getLogger("antigravity_k.engine.diagnostics_export")

_DOTENV_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_LOG_SUFFIXES = {".log", ".txt", ".jsonl", ".out"}
_MAX_LOG_FILES = 8
_MAX_LOG_BYTES = 48_000
_FORBIDDEN_NAME_FRAGMENTS = (
    ".env",
    "vault_data",
    "auth_hash",
    "auth-hash",
    "credentials",
    "api_keys",
    "access_pin",
    "token_secret",
    "bearer",
    "id_rsa",
    ".pem",
    "master_key",
    "private_key",
)


def default_diagnostics_dir() -> Path:
    """User-writable diagnostics directory (macOS Logs preferred)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Ssak-Ai"
    return Path.home() / ".antigravity-k" / "logs"


def default_zip_path(*, now: datetime | None = None) -> Path:
    """Timestamped ZIP path under the diagnostics directory."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return default_diagnostics_dir() / f"diagnostics-{stamp}.zip"


def is_forbidden_archive_path(path_str: str) -> bool:
    """True if an archive member path looks secret-bearing (blocklist)."""
    lowered = path_str.replace("\\", "/").lower()
    base = Path(lowered).name
    if is_sensitive_file(base):
        return True
    for fragment in _FORBIDDEN_NAME_FRAGMENTS:
        if fragment in lowered:
            return True
    for segment in MEMORY_PATH_SEGMENTS:
        if segment.lower().strip("/") and segment.lower().strip("/") in lowered:
            return True
    return False


def _safe_read_text(path: Path, *, max_bytes: int) -> str:
    try:
        raw = path.read_bytes()
    except OSError as err:
        logger.debug("skip unreadable log %s: %s", path, err)
        return ""
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    return redact_full(text)


def _candidate_log_dirs() -> list[Path]:
    dirs: list[Path] = [default_diagnostics_dir(), Path.home() / ".antigravity-k" / "logs"]
    try:
        from antigravity_k.config import config

        dirs.append(Path(config.paths.logs_dir))
    except Exception:
        pass
    # De-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        try:
            resolved = d.expanduser().resolve()
        except OSError:
            resolved = d.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def collect_log_tails(
    *,
    max_files: int = _MAX_LOG_FILES,
    max_bytes: int = _MAX_LOG_BYTES,
) -> dict[str, str]:
    """Recent log file tails, scrubbed; keys are archive-relative names."""
    collected: dict[str, str] = {}
    candidates: list[tuple[float, Path]] = []
    for log_dir in _candidate_log_dirs():
        if not log_dir.is_dir():
            continue
        try:
            entries = list(log_dir.iterdir())
        except OSError:
            continue
        for path in entries:
            if not path.is_file():
                continue
            if path.suffix.lower() not in _LOG_SUFFIXES:
                continue
            if is_forbidden_archive_path(str(path)):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, path in candidates[:max_files]:
        arc_name = f"logs/{path.name}"
        if is_forbidden_archive_path(arc_name):
            continue
        text = _safe_read_text(path, max_bytes=max_bytes)
        if text:
            collected[arc_name] = text
    return collected


def collect_setting_key_names() -> list[str]:
    """Return setting **key names only** (never values).

    Prefer names present on the left-hand side of ``.env`` assignments when the
    file exists; otherwise return the known allowlist catalog names.
    """
    from antigravity_k.engine.secret_settings import ALLOWED_ENV_KEYS, resolve_env_file_path

    names: list[str] = []
    # Prefer AGK_ENV_FILE, then cwd, then source-tree root next to this package —
    # avoid DMG bundle PROJECT_ROOT when a stale PYTHONPATH shadows imports.
    candidates: list[Path] = []
    override = os.environ.get("AGK_ENV_FILE")
    if override:
        candidates.append(Path(override))
    candidates.append(Path.cwd() / ".env")
    source_root = Path(__file__).resolve().parents[3]  # .../src/antigravity_k/engine -> repo
    candidates.append(source_root / ".env")
    try:
        from antigravity_k.config import PROJECT_ROOT

        candidates.append(resolve_env_file_path(PROJECT_ROOT))
    except Exception:
        pass

    env_path: Path | None = next((p for p in candidates if p.is_file()), None)

    if env_path is not None:
        try:
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = _DOTENV_KEY_RE.match(line)
                if match is None:
                    continue
                key = match.group(1)
                # Only export allowlisted setting keys — never arbitrary env dumps
                if key in ALLOWED_ENV_KEYS and key not in names:
                    names.append(key)
        except OSError as err:
            logger.debug("could not read env key names: %s", err)

    if not names:
        names = list(ALLOWED_ENV_KEYS)
    return names


def collect_bind_info() -> dict[str, Any]:
    """Configured bind host/port (no secrets)."""
    info: dict[str, Any] = {
        "host": None,
        "port": None,
        "inference_port": None,
        "ssak_host_url": os.environ.get("SSAK_HOST_URL"),
    }
    try:
        from antigravity_k.config import config

        info["host"] = config.server.host
        info["port"] = config.server.port
        info["inference_port"] = config.server.inference_port
    except Exception as err:
        info["config_error"] = type(err).__name__
    return info


def collect_environment_manifest() -> dict[str, Any]:
    """App/Python/OS versions and build provenance (no secrets)."""
    build: dict[str, Any] = {}
    try:
        from antigravity_k.build_info import get_build_info

        build = dict(get_build_info())
    except Exception:
        build = {"version": __version__}
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "build": build,
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "bind": collect_bind_info(),
        "setting_key_names": collect_setting_key_names(),
        "setting_key_values_included": False,
        "allowlist_note": (
            "Archive is allowlist-only: versions, OS, scrubbed log tails, "
            "setting key names, bind host/port, recent error codes. "
            "Never includes .env values, PIN, bearer, vault_data, auth_hash."
        ),
    }


def collect_recent_error_codes(*, limit: int = 20) -> list[dict[str, str]]:
    """Recent journal error codes/types only (messages scrubbed + truncated)."""
    rows: list[dict[str, str]] = []
    try:
        from antigravity_k.engine.agent_error_journal import get_agent_error_journal

        journal = get_agent_error_journal()
        for err in journal.list_errors(limit=limit):
            msg = redact_full(err.message or "")
            if len(msg) > 120:
                msg = msg[:117] + "..."
            rows.append(
                {
                    "error_id": err.error_id,
                    "timestamp": err.timestamp,
                    "component": err.component,
                    "error_code": err.error_type,
                    "message": msg,
                }
            )
    except Exception as err:
        logger.debug("error journal unavailable: %s", err)
    return rows


def export_diagnostics_zip(
    output: Path | str | None = None,
    *,
    max_log_files: int = _MAX_LOG_FILES,
    max_log_bytes: int = _MAX_LOG_BYTES,
) -> Path:
    """Build an allowlist diagnostics ZIP and return its path.

    Raises:
        ValueError: if the chosen output path looks secret-bearing.
        OSError: on write failure.
    """
    zip_path = Path(output).expanduser() if output else default_zip_path()
    if is_forbidden_archive_path(str(zip_path)):
        raise ValueError(f"refusing suspicious diagnostics path: {zip_path}")

    zip_path.parent.mkdir(parents=True, exist_ok=True)

    members: dict[str, str] = {
        "manifest.json": json.dumps(collect_environment_manifest(), indent=2, ensure_ascii=False) + "\n",
        "setting_keys.json": json.dumps(
            {"setting_key_names": collect_setting_key_names(), "values_included": False},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "error_codes.json": json.dumps(
            {"recent_error_codes": collect_recent_error_codes()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    }
    members.update(collect_log_tails(max_files=max_log_files, max_bytes=max_log_bytes))

    for name in members:
        if is_forbidden_archive_path(name):
            raise ValueError(f"refusing to pack forbidden member: {name}")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)

    return zip_path


__all__ = [
    "collect_bind_info",
    "collect_environment_manifest",
    "collect_log_tails",
    "collect_recent_error_codes",
    "collect_setting_key_names",
    "default_diagnostics_dir",
    "default_zip_path",
    "export_diagnostics_zip",
    "is_forbidden_archive_path",
]
