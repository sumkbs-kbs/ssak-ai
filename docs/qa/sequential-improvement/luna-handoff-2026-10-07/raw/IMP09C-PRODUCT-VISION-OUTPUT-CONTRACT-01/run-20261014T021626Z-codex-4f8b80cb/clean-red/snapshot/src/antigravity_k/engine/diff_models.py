from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Hunk:
    context_before: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    additions: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)

    @property
    def is_pure_addition(self) -> bool:
        return not self.removals and bool(self.additions)

    @property
    def is_pure_removal(self) -> bool:
        return not self.additions and bool(self.removals)

    @property
    def old_block(self) -> list[str]:
        return self.context_before + self.removals + self.context_after

    @property
    def new_block(self) -> list[str]:
        return self.context_before + self.additions + self.context_after


@dataclass(frozen=True, slots=True)
class FilePatch:
    file_path: str
    hunks: list[Hunk] = field(default_factory=list)
    is_new_file: bool = False
    is_delete_file: bool = False
    new_file_content: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.hunks and not self.is_new_file and not self.is_delete_file


@dataclass(frozen=True, slots=True)
class ApplyResult:
    success: bool
    file_path: str
    new_content: str = ""
    hunks_applied: int = 0
    hunks_total: int = 0
    error: str = ""
    fuzzy_matches: int = 0

    @property
    def is_fuzzy(self) -> bool:
        return self.fuzzy_matches > 0
