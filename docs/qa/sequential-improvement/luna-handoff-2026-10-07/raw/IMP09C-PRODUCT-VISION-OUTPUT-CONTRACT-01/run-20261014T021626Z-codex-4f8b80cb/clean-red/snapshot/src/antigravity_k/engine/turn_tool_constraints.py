"""Explicit negative tool instructions from the current user turn."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import JsonValue

FILE_MUTATION_TOOLS: Final = frozenset(
    {
        "write_file",
        "edit_file",
        "replace_file_content",
        "multi_replace_file_content",
        "write_artifact",
        "create_directory",
        "apply_patch",
    }
)
_QUOTED_MATERIAL: Final = re.compile(
    r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|\"[^\"]*\"|"
    r"(?<!\w)'[^']*'(?!\w)|“[^”]*”|‘[^’]*’|(?m:^\s*>[^\n]*)",
)
_NO_TOOLS: Final = re.compile(
    r"도구(?:\s*(?:와|나|및|·)\s*검색)?(?:는|를|은|을)?\s*"
    r"(?:없이|(?:사용|호출)하지\s*(?:마|말)|쓰지\s*(?:마|말))|"
    r"\bwithout\s+(?:(?:using|invoking|calling)\s+)?(?:any\s+)?tools\b|"
    r"\b(?:do\s+not|don['’]t|never|must\s+not)\s+(?:use|invoke|call)\s+(?:any\s+)?tools\b",
)
_NO_SEARCH: Final = re.compile(
    r"(?:웹\s*검색|추가\s*검색|검색)(?:은|을|는)?\s*(?:없이|하지\s*(?:마|말))|"
    r"(?:추가\s*)?검색(?:과|및)\s*파일\s*(?:변경|수정)(?:은|는)?\s*하지\s*(?:마|말)|"
    r"\b(?:do\s+not|don['’]t|never|must\s+not)\s+(?:search\b|(?:use|run)\s+(?:a\s+)?web\s+search\b)|"
    r"\bwithout\s+(?:additional\s+|web\s+)?search(?:ing)?\b",
)
_NO_FILE_MUTATION: Final = re.compile(
    r"(?:파일(?:\s*(?:과|및|·|,)\s*설정)?|설정)(?:들을?|은|는|을|를)?\s*"
    r"(?:(?:변경|수정|생성|삭제|저장)(?:은|는|을|를)?\s*하지\s*(?:마|말)|"
    r"(?:변경|수정|생성|삭제|저장)하지\s*(?:마|말)|(?:만들|건드리)지\s*(?:마|말))|"
    r"\b(?:do\s+not|don['’]t|never|must\s+not)\s+(?:create|write|modify|change|edit|delete|save|touch)\s+"
    r"(?:any\s+|the\s+|new\s+)?files?\b|"
    r"\bwithout\s+(?:modifying|changing|writing|creating|editing|deleting)\s+(?:any\s+)?files?\b|"
    r"(?:^|[.!?;\n])\s*no\s+file\s+(?:changes|writes|modifications)\s*(?=[.!?;\n]|$)",
)


@dataclass(frozen=True, slots=True)
class TurnToolConstraints:
    """Narrow prohibitions; quoted examples and descriptive wording do not bind."""

    no_tools: bool = False
    no_search: bool = False
    no_file_mutation: bool = False

    @classmethod
    def from_request(cls, request: str) -> TurnToolConstraints:
        active = _QUOTED_MATERIAL.sub(" ", request.casefold())
        return cls(
            bool(_NO_TOOLS.search(active)), bool(_NO_SEARCH.search(active)), bool(_NO_FILE_MUTATION.search(active))
        )

    def denial(self, tool_name: str) -> str | None:
        if self.no_tools:
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited all tool calls in this turn."
        if self.no_search and tool_name == "web_search":
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited additional search in this turn."
        if self.no_file_mutation and tool_name in FILE_MUTATION_TOOLS:
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited file changes, including saved artifacts."
        return None

    def allows_schema(self, schema: Mapping[str, JsonValue]) -> bool:
        function = schema.get("function")
        name = function.get("name") if isinstance(function, dict) else schema.get("name")
        return not self.no_tools and (not isinstance(name, str) or self.denial(name) is None)

    def guidance(self) -> str:
        instructions: list[str] = []
        if self.no_tools:
            instructions.append("Do not invoke any tools. Answer directly in chat from the available context.")
        if self.no_search:
            instructions.append("Do not perform additional web searches.")
        if self.no_file_mutation:
            instructions.append("Do not create, edit, delete or save files, directories or artifacts. Reply in chat.")
        return "[CURRENT USER TOOL CONSTRAINT]\n" + "\n".join(instructions) if instructions else ""
