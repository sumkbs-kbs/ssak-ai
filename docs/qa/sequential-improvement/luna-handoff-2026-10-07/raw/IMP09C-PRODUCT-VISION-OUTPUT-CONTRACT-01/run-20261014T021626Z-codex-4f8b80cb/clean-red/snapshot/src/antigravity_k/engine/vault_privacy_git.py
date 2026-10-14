from __future__ import annotations

import subprocess
from pathlib import Path

from antigravity_k.engine.vault_privacy_contracts import VaultPrivacyError, VaultPrivacyFailure


def run_vault_git(
    vault_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=vault_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise VaultPrivacyError(
            VaultPrivacyFailure.GIT_FAILURE,
            f"Vault Git command failed: git {args[0]}",
        )
    return result


def validate_snapshot_paths(vault_path: Path, snapshot_commit: str, paths: tuple[str, ...]) -> None:
    for relative_path in paths:
        result = run_vault_git(
            vault_path,
            "cat-file",
            "-e",
            f"{snapshot_commit}:{relative_path}",
            check=False,
        )
        if result.returncode != 0:
            raise VaultPrivacyError(
                VaultPrivacyFailure.MISSING_NOTE,
                f"Vault snapshot does not contain note: {relative_path}",
            )


def _scope_modes(vault_path: Path, paths: tuple[str, ...]) -> dict[str, int]:
    """복구 전 파일 권한 (NX-08-D1: git 복구는 실행 비트만 복원한다)."""
    import stat

    modes: dict[str, int] = {}
    for relative_path in paths:
        try:
            modes[relative_path] = stat.S_IMODE((vault_path / relative_path).stat().st_mode)
        except OSError:
            continue
    return modes


def restore_vault_privacy_paths(vault_path: Path, snapshot_commit: str, paths: tuple[str, ...]) -> str:
    import os

    original_modes = _scope_modes(vault_path, paths)
    _ = run_vault_git(
        vault_path,
        "restore",
        "--source",
        snapshot_commit,
        "--staged",
        "--worktree",
        "--",
        *paths,
    )
    # 복구는 내용만 되돌린다 — 복구가 권한을 널히지 않게 한다(NX-08-D1).
    for relative_path, mode in original_modes.items():
        try:
            os.chmod(vault_path / relative_path, mode)
        except OSError:
            continue
    _ = run_vault_git(
        vault_path,
        "commit",
        "--only",
        "-m",
        f"[Privacy] Restore {len(paths)} Vault note(s) from {snapshot_commit[:12]}",
        "--",
        *paths,
    )
    return run_vault_git(vault_path, "rev-parse", "HEAD").stdout.strip()
