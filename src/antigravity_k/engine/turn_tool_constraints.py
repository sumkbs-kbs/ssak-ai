"""Explicit negative tool instructions from the current user turn."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
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
FILE_CONTENT_READ_TOOLS: Final = frozenset(
    {"read_file", "read_hash_file", "hex_dump", "grep_search", "ast_grep", "git_diff"}
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
_READ_BAN_END_KO: Final = r"(?:마(?:세요|십시오|라)?|말(?:고|라|아(?:\s*(?:줘|주세요))?))(?=$|[\s.!?,;])"
_NO_FILE_READ: Final = re.compile(
    r"(?<!\w)(?:파일(?:들|\s*내용|\s*본문)?|원본(?:\s*파일)?)(?:은|는|을|를)?\s*"
    r"(?:다시\s*)?(?:읽|열)지\s*" + _READ_BAN_END_KO + r"|"
    r"(?<!\w)read_file(?:\s*도구)?(?:은|는|을|를)?\s*"
    r"(?:(?:호출|사용|실행)하지|쓰지)\s*" + _READ_BAN_END_KO + r"|"
    r"(?<!\w)read_file(?:\s*도구)?\s*없이(?=$|[\s.!?,;])|"
    r"\b(?:do\s+not|don['’]t|never|must\s+not)\s+(?:call|use|invoke)\s+read_file\b|"
    r"\b(?:do\s+not|don['’]t|never|must\s+not)\s+(?:read|open|re-?read)\s+"
    r"(?:(?:any|the)\s+)?(?:source\s+)?files?(?![\w/\\-]|\.[a-z0-9])|"
    r"\bwithout\s+(?:reading|opening|re-?reading)\s+(?:(?:any|the)\s+)?(?:source\s+)?files?(?![\w/\\-]|\.[a-z0-9])|"
    r"(?:^|[.!?;\n])\s*no\s+file\s+reads?(?=\s*(?:[.!?;\n]|$))",
)
_SCOPED_READ_TARGET: Final = re.compile(
    r"(?<!\w)(?:다른|추가|새|새로운|나머지|특정|해당|이|그|저|__read_path_ref__|[^\s]+\.[a-z0-9]+)\s+$"
)
_SUPPLIED_CONTEXT_KO: Final = re.compile(
    r"(?:(?:이미|앞서|방금)\s*)?(?:제공된|전달된|주어진)\s*(?:기억|메모리|문맥|컨텍스트|정보)"
    r"(?P<instruction>[^.!?;\n]{0,100})"
)
_ANSWER_REQUEST_KO: Final = re.compile(
    r"(?:답|답변|응답)(?:해(?:줘(?:요)?|주세요|요)?|하세요|하라)(?=[\s,.!?;]|$)"
)
_SUPPLIED_CONTEXT_ONLY_EN: Final = re.compile(
    r"\b(?:answer|reply|respond)\s+(?:directly\s+)?(?:only|solely)\s+from\s+(?:the\s+)?"
    r"(?:(?:already\s+)?(?:supplied|provided)|given)\s+(?:memory|context)\b|"
    r"\buse\s+(?:only|solely)\s+(?:the\s+)?(?:(?:already\s+)?(?:supplied|provided)|given)\s+"
    r"(?:memory|context)\b[^.!?;\n]{0,60}\b(?:answer|reply|respond)\b"
)
_POSITIVE_TOOL_OR_READ_REQUEST: Final = re.compile(
    r"\b(?:call|invoke|run)\s+(?:the\s+)?[a-z][a-z0-9_.:-]*\b|"
    r"\buse\s+(?:the\s+)?(?!(?:only|solely|provided|supplied|given|already|memory|context)\b)[a-z][a-z0-9_.:-]*\b|"
    r"\ballow\s+(?:the\s+)?[a-z][a-z0-9_.:-]*\b|"
    r"(?<!\w)[a-z][a-z0-9_.:-]*(?:\s*도구)?(?:의|은|는|을|를)?\s*"
    r"(?:(?:사용|호출|실행)(?:은|는|을|를)?\s*)?(?:허용합니다|허용해(?:줘|주세요)?|허용하라)(?=[\s,.!?;]|$)|"
    r"\b(?:read|open)\s+(?:the\s+)?[^\s]+\.[a-z0-9]+\b|"
    r"(?<!\w)[a-z][a-z0-9_.:-]*(?:\s*도구)?(?:을|를|로)?\s*"
    r"(?:(?:호출|실행|사용|확인)해(?:줘|주세요|라)?)(?=[\s,.!?;]|$)|"
    r"(?<!\w)[a-z][a-z0-9_.:-]*로\s+[^.!?;\n]{0,60}(?:읽어|열어)(?:줘|주세요)|"
    r"[^\s]+\.[a-z0-9]+(?:을|를)?\s*(?:읽어|열어)(?:줘|주세요)"
)


def _requires_supplied_context_only(active: str, global_read_ban: bool, positive_active: str) -> bool:
    """A narrow answer contract, never inferred from a read ban or recall alone."""
    if not global_read_ban:
        return False
    for match in _POSITIVE_TOOL_OR_READ_REQUEST.finditer(positive_active):
        prefix = positive_active[:match.start()]
        if not re.search(r"(?:do\s+not|don['’]t|never|must\s+not)\s+$", prefix):
            return False
    for match in _SUPPLIED_CONTEXT_ONLY_EN.finditer(active):
        if not re.search(r"(?:do\s+not|don['’]t|never|must\s+not)\s+$", active[:match.start()]):
            return True
    for match in _SUPPLIED_CONTEXT_KO.finditer(active):
        instruction = match['instruction']
        source_only = re.match(r"(?:만(?:으로|을|를)?|(?:으로|에서)만)(?=\s|답|사용|활용|보고)", instruction)
        answer_only = re.match(r"(?:으로|에서)\s*[^\s,.!?;]{1,20}만\s*", instruction)
        if source_only:
            # Require a positive answer/use-then-answer directive immediately
            # after the exclusive source. A later answer clause cannot turn
            # "memory only: do NOT use it; answer from general knowledge" into
            # an opposite current-user instruction.
            prefix = re.match(
                r"\s*(?:(?:(?:사용|활용)(?:해서|하여|하고|해)|보고|참고해서)\s*)?"
                r"(?:[^\s,.!?;]{1,20}만\s*)?", instruction[source_only.end():],
            )
            if prefix and _ANSWER_REQUEST_KO.match(instruction, source_only.end() + prefix.end()):
                return True
        if answer_only and _ANSWER_REQUEST_KO.match(instruction, answer_only.end()):
            return True
    return False


def _has_global_read_ban(active: str) -> bool:
    for match in _NO_FILE_READ.finditer(active):
        if "read_file" in match.group():
            continue
        # "Other files must not be read; read this file" is not a global ban.
        if _SCOPED_READ_TARGET.search(active[:match.start()]):
            continue
        following = active[match.end():]
        global_location = re.match(
            r"\s+(?:in\s+(?:this|the current)\s+project|from\s+(?:the\s+)?(?:local\s+)?(?:disk|filesystem))"
            r"(?=\s*(?:[,.!?;]|$))", following,
        )
        if not global_location and re.match(
            r"\s+(?:(?:named|called|matching|under|in|from|except|unless|__read_path_ref__)\b|[^\s;]+\.[a-z0-9]+)",
            following,
        ):
            continue
        # A source-specific prohibition followed by a different requested read
        # needs a path-scoped policy, not this global read_file constraint.
        if ("원본" in match.group() or "source" in match.group()) and re.search(
            r"(?:읽어|열어)\s*(?:줘|주세요)|(?:^|[.;!?\n])\s*(?:then\s+|please\s+)?(?:read|open)\b", following
        ):
            continue
        return True
    return False


@dataclass(frozen=True, slots=True)
class TurnToolConstraints:
    """Narrow prohibitions; quoted examples and descriptive wording do not bind."""

    no_tools: bool = False
    no_search: bool = False
    no_file_mutation: bool = False
    no_file_read: bool = False
    no_file_content_read: bool = False
    provided_memory_only: bool = False

    @classmethod
    def from_request(cls, request: str) -> TurnToolConstraints:
        # A named inline tool can be the subject of an instruction. Enclosing
        # quotes, fences and blockquotes are still removed as untrusted examples.
        normalized = re.sub(r"(?<!`)`read_file`(?!`)", "read_file", request.casefold())
        active = _QUOTED_MATERIAL.sub(" ", normalized)
        # Inline named tools may be positive current-user requests. Preserve
        # only their identifier; surrounding quotes/fences still lack authority.
        positive_active = _QUOTED_MATERIAL.sub(
            " ", re.sub(r"(?<!`)`([a-z][a-z0-9_.:-]*)`(?!`)", r"\1", normalized)
        )
        # A quoted reference can limit a prohibition (including names such as
        # LICENSE). Keep its scope, never its content as executable authority.
        read_active = _QUOTED_MATERIAL.sub(
            lambda match: " " if match.group().lstrip().startswith(("```", "~~~", ">")) else " __read_path_ref__ ",
            normalized,
        )
        # "read_file 도구는 호출하지 마" names one tool. Its inner "도구는"
        # must not also be interpreted as an independent ban on every tool.
        all_tools_active = _NO_FILE_READ.sub(" ", active)
        global_read_ban = _has_global_read_ban(read_active)
        named_read_ban = any("read_file" in match.group() for match in _NO_FILE_READ.finditer(read_active))
        return cls(
            bool(_NO_TOOLS.search(all_tools_active)), bool(_NO_SEARCH.search(active)), bool(_NO_FILE_MUTATION.search(active)),
            global_read_ban or named_read_ban, global_read_ban,
            _requires_supplied_context_only(active, global_read_ban, positive_active),
        )

    def denial(self, tool_name: str) -> str | None:
        if self.provided_memory_only:
            return "[USER TOOL CONSTRAINT] Answer only from already supplied memory/context; no tool or approval request is permitted."
        if self.no_tools:
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited all tool calls in this turn."
        if self.no_file_content_read and tool_name in FILE_CONTENT_READ_TOOLS:
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited file-content reads in this turn."
        if self.no_file_read and tool_name == "read_file":
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited read_file calls in this turn."
        if self.no_search and tool_name == "web_search":
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited additional search in this turn."
        if self.no_file_mutation and tool_name in FILE_MUTATION_TOOLS:
            return "[USER TOOL CONSTRAINT] The user explicitly prohibited file changes, including saved artifacts."
        return None

    def allows_schema(self, schema: Mapping[str, JsonValue]) -> bool:
        function = schema.get("function")
        name = function.get("name") if isinstance(function, dict) else schema.get("name")
        return not (self.no_tools or self.provided_memory_only) and (not isinstance(name, str) or self.denial(name) is None)

    def guidance(self) -> str:
        instructions: list[str] = []
        if self.provided_memory_only:
            instructions.append(
                "Answer directly using only the memory/context already supplied in this turn. "
                "Do not invoke any tools, impact analysis, artifact lookup, Git, directory search, delegation or MCP. "
                "Tool-result hashes and source labels are evidence labels, not requests to retrieve an artifact. "
                "If that context is insufficient, state the evidence gap in chat without attempting verification."
            )
        if self.no_tools:
            instructions.append("Do not invoke any tools. Answer directly in chat from the available context.")
        if self.no_search:
            instructions.append("Do not perform additional web searches.")
        if self.no_file_mutation:
            instructions.append("Do not create, edit, delete or save files, directories or artifacts. Reply in chat.")
        if self.no_file_content_read:
            instructions.append("Do not read file contents through read_file, read_hash_file, hex_dump, grep_search, ast_grep or git_diff. Use supplied context; state any evidence gap instead.")
        elif self.no_file_read:
            instructions.append("Do not invoke read_file. Use supplied context; state any evidence gap instead of reading a file.")
        return "[CURRENT USER TOOL CONSTRAINT]\n" + "\n".join(instructions) if instructions else ""


_active_turn_constraints: ContextVar[TurnToolConstraints | None] = ContextVar("active_turn_tool_constraints", default=None)


def current_turn_tool_constraints() -> TurnToolConstraints:
    """Return only the immutable constraints scoped by the current trusted turn."""
    return _active_turn_constraints.get() or TurnToolConstraints()


@contextmanager
def bind_turn_tool_constraints(constraints: TurnToolConstraints) -> Iterator[None]:
    """Expose parsed original-user constraints during synchronous prompt construction."""
    token = _active_turn_constraints.set(constraints)
    try:
        yield
    finally:
        _active_turn_constraints.reset(token)
