from __future__ import annotations

from typing import TypedDict, final


@final
class FileSymbols:
    """파일별 추출 심볼 정보."""

    __slots__ = ("file_path", "functions", "classes", "imports", "line_count", "char_count")

    file_path: str
    functions: list[str]
    classes: list[str]
    imports: list[str]
    line_count: int
    char_count: int

    def __init__(
        self,
        file_path: str,
        functions: list[str] | None = None,
        classes: list[str] | None = None,
        imports: list[str] | None = None,
        line_count: int = 0,
        char_count: int = 0,
    ) -> None:
        self.file_path = file_path
        self.functions = [] if functions is None else functions
        self.classes = [] if classes is None else classes
        self.imports = [] if imports is None else imports
        self.line_count = line_count
        self.char_count = char_count


class SearchResult(TypedDict):
    file: str
    score: float
    functions: list[str]
    classes: list[str]
    line_count: int


class CodeTreeStats(TypedDict):
    files_indexed: int
    total_classes: int
    total_functions: int
    total_lines: int
    tree_size_kb: float
