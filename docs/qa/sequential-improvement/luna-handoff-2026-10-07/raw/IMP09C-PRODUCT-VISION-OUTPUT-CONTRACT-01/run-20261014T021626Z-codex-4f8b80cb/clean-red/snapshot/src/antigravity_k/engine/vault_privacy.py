from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path

from antigravity_k.engine.atomic_write import write_text_atomically
from antigravity_k.engine.vault_privacy_contracts import (
    VaultPrivacyAction,
    VaultPrivacyError,
    VaultPrivacyFailure,
    VaultPrivacyMutation,
    VaultPrivacyResult,
)
from antigravity_k.engine.vault_privacy_git import run_vault_git as _run_git

REDACTION_MARKER = "<REDACTED>"


LockFactory = Callable[[], AbstractContextManager[None]]
PathResolver = Callable[[str], Path]
DerivativeSync = Callable[[VaultPrivacyMutation, Mapping[Path, str]], None]
SafetyCheck = Callable[[], bool]


def apply_vault_privacy_mutation(
    *,
    vault_path: Path,
    acquire_lock: LockFactory,
    resolve_path: PathResolver,
    mutation: VaultPrivacyMutation,
    sync_derivatives: DerivativeSync,
    is_safe_restore_target: SafetyCheck,
) -> VaultPrivacyResult:
    with acquire_lock():
        if not is_safe_restore_target():
            raise VaultPrivacyError(
                VaultPrivacyFailure.UNSAFE_VAULT,
                "Vault path is not safe for transactional rollback",
            )
        files = resolve_vault_privacy_paths(mutation.paths, resolve_path, require_files=True)
        replacements, replacement_count = _prepare_replacements(files, mutation)
        snapshot_commit = _create_snapshot(vault_path, mutation)
        completed = False
        try:
            _apply_files(files, replacements, mutation.action)
            sync_derivatives(mutation, replacements)
            mutation_commit = _commit_mutation(vault_path, mutation)
            completed = True
        finally:
            if not completed:
                _rollback_transaction(
                    vault_path,
                    snapshot_commit,
                    files,
                    mutation,
                    sync_derivatives,
                )

    return VaultPrivacyResult(
        action=mutation.action,
        paths=mutation.paths,
        changed_files=len(files) if mutation.action is VaultPrivacyAction.PURGE else len(replacements),
        replacement_count=replacement_count,
        snapshot_commit=snapshot_commit,
        mutation_commit=mutation_commit,
    )


def resolve_vault_privacy_paths(
    paths: tuple[str, ...],
    resolve_path: PathResolver,
    *,
    require_files: bool,
) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative_path in paths:
        candidate = Path(relative_path)
        if candidate.suffix.lower() != ".md" or any(part.casefold() in {".git", ".chroma"} for part in candidate.parts):
            raise VaultPrivacyError(
                VaultPrivacyFailure.INVALID_PATH,
                f"Only Vault Markdown notes may be changed: {relative_path}",
            )
        try:
            resolved = resolve_path(relative_path)
        except ValueError as exc:
            raise VaultPrivacyError(VaultPrivacyFailure.INVALID_PATH, str(exc)) from exc
        if require_files and not resolved.is_file():
            raise VaultPrivacyError(
                VaultPrivacyFailure.MISSING_NOTE,
                f"Vault note does not exist: {relative_path}",
            )
        files.append(resolved)
    return tuple(files)


def _prepare_replacements(
    files: tuple[Path, ...],
    mutation: VaultPrivacyMutation,
) -> tuple[dict[Path, str], int]:
    if mutation.action is VaultPrivacyAction.PURGE:
        return {}, 0

    originals = {path: path.read_text(encoding="utf-8") for path in files}
    missing_values = [value for value in mutation.values if not any(value in text for text in originals.values())]
    if missing_values:
        raise VaultPrivacyError(
            VaultPrivacyFailure.VALUE_NOT_FOUND,
            f"{len(missing_values)} requested redaction value(s) were not found",
        )

    replacements: dict[Path, str] = {}
    replacement_count = 0
    for path, original in originals.items():
        redacted = original
        for value in sorted(mutation.values, key=len, reverse=True):
            replacement_count += redacted.count(value)
            redacted = redacted.replace(value, REDACTION_MARKER)
        if redacted != original:
            replacements[path] = redacted
    return replacements, replacement_count


def _apply_files(
    files: tuple[Path, ...],
    replacements: dict[Path, str],
    action: VaultPrivacyAction,
) -> None:
    if action is VaultPrivacyAction.PURGE:
        for path in files:
            path.unlink()
        return

    # NX-08-F01: 마스킹도 같은 원자성 계약으로 저장한다(자르고 쓰지 않는다).
    # NX-10: writer 는 leaf 모듈(`atomic_write`)이 소유한다 — 예전처럼 `vault` 에서
    # 함수 내부 임포트를 하면 `vault → vault_privacy → vault` 순환이 된다.
    for path, content in replacements.items():
        write_text_atomically(path, content)


def _create_snapshot(vault_path: Path, mutation: VaultPrivacyMutation) -> str:
    _ = _run_git(vault_path, "add", "--all", "--", *mutation.paths)
    staged = _run_git(vault_path, "diff", "--cached", "--quiet", "--", *mutation.paths, check=False)
    if staged.returncode == 1:
        _ = _run_git(
            vault_path,
            "commit",
            "--only",
            "-m",
            f"[Snapshot] Before Vault {mutation.action.value}",
            "--",
            *mutation.paths,
        )
    elif staged.returncode != 0:
        raise VaultPrivacyError(VaultPrivacyFailure.GIT_FAILURE, "Unable to inspect staged Vault changes")
    head = _run_git(vault_path, "rev-parse", "HEAD")
    return head.stdout.strip()


def _commit_mutation(vault_path: Path, mutation: VaultPrivacyMutation) -> str:
    _ = _run_git(vault_path, "add", "--all", "--", *mutation.paths)
    _ = _run_git(
        vault_path,
        "commit",
        "--only",
        "-m",
        f"[Privacy] {mutation.action.value.title()} {len(mutation.paths)} Vault note(s)",
        "--",
        *mutation.paths,
    )
    return _run_git(vault_path, "rev-parse", "HEAD").stdout.strip()


def _rollback(vault_path: Path, snapshot_commit: str, paths: tuple[str, ...]) -> None:
    try:
        _ = _run_git(
            vault_path,
            "restore",
            "--source",
            snapshot_commit,
            "--staged",
            "--worktree",
            "--",
            *paths,
        )
    except VaultPrivacyError as exc:
        raise VaultPrivacyError(
            VaultPrivacyFailure.ROLLBACK_FAILURE,
            f"Vault rollback failed after mutation error: {exc}",
        ) from exc


def _rollback_transaction(
    vault_path: Path,
    snapshot_commit: str,
    files: tuple[Path, ...],
    mutation: VaultPrivacyMutation,
    sync_derivatives: DerivativeSync,
) -> None:
    _rollback(vault_path, snapshot_commit, mutation.paths)
    originals = {path: path.read_text(encoding="utf-8") for path in files}
    sync_derivatives(
        VaultPrivacyMutation(
            action=VaultPrivacyAction.REDACT,
            paths=mutation.paths,
        ),
        originals,
    )
