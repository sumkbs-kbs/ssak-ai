from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class VaultCommitError(RuntimeError):
    pass


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def commit_output(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stdout + result.stderr
    return output.strip()


def _called_process_output(exc: subprocess.CalledProcessError) -> str:
    return str(exc).strip()


def _backup_main_index(repository: Path) -> Path | None:
    main_index = repository / ".git" / "index"
    if not main_index.exists():
        return None
    backup = repository / ".git" / "agk-vault-index-backup"
    _ = shutil.copy2(main_index, backup)
    return backup


def _restore_main_index(repository: Path, backup: Path | None) -> None:
    main_index = repository / ".git" / "index"
    if backup is None:
        main_index.unlink(missing_ok=True)
        return
    os.replace(backup, main_index)


@contextmanager
def vault_stage_transaction(repository: Path, file_path: str) -> Generator[dict[str, str] | None]:
    """Stage one new note without exposing it through the user's Git index."""
    tracked = subprocess.run(
        ["git", "ls-files", "--", file_path],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    if tracked.stdout.splitlines() == [file_path]:
        yield None
        return

    temporary_index = repository / ".git" / "agk-vault-index"
    subprocess_env = os.environ.copy()
    subprocess_env["GIT_INDEX_FILE"] = str(temporary_index)
    index_backup = _backup_main_index(repository)
    try:
        temporary_index.unlink(missing_ok=True)
        _ = _run_git(repository, ["add", "--", file_path], env=subprocess_env)
        yield subprocess_env
    except subprocess.CalledProcessError as exc:
        output = _called_process_output(exc)
        raise VaultCommitError(f"git add failed for {file_path}: {output}") from exc
    finally:
        _restore_main_index(repository, index_backup)
        temporary_index.unlink(missing_ok=True)
