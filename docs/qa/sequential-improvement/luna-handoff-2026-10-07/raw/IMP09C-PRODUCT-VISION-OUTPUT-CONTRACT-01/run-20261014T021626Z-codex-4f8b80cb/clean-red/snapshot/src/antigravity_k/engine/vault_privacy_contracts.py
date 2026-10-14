from dataclasses import dataclass
from enum import StrEnum
from typing import final, override


class VaultPrivacyAction(StrEnum):
    REDACT = "redact"
    PURGE = "purge"


class VaultPrivacyFailure(StrEnum):
    UNSAFE_VAULT = "unsafe_vault"
    INVALID_PATH = "invalid_path"
    MISSING_NOTE = "missing_note"
    VALUE_NOT_FOUND = "value_not_found"
    GIT_FAILURE = "git_failure"
    FILE_FAILURE = "file_failure"
    ROLLBACK_FAILURE = "rollback_failure"


@final
class VaultPrivacyError(RuntimeError):
    failure: VaultPrivacyFailure
    detail: str

    def __init__(self, failure: VaultPrivacyFailure, detail: str) -> None:
        self.failure = failure
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class VaultPrivacyMutation:
    action: VaultPrivacyAction
    paths: tuple[str, ...]
    values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VaultPrivacyResult:
    action: VaultPrivacyAction
    paths: tuple[str, ...]
    changed_files: int
    replacement_count: int
    snapshot_commit: str
    mutation_commit: str
    history_retained_for_rollback: bool = True
