"""Robust Tool Parser — Self-healing tool call parser for 27B-class models.

27B models often produce slight formatting glitches in function calls:
- Missing closing braces or quotes
- Single quotes instead of double quotes in JSON
- Trailing commas
- Python-style booleans (True/False) or None instead of true/false/null
- Raw code or backticks inside JSON strings

This parser deterministically repairs these patterns without re-prompting the LLM.
"""

import ast
import json
import logging
import re
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

_TOOL_CALL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"<tool_call>\s*(?P<body>\{.*?\})\s*</tool_call>",
    re.DOTALL,
)

_BACKTICK_TOOL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(?P<body>\{\s*\"name\"\s*:\s*\"[^\"]+\".*?\})\s*```",
    re.DOTALL,
)

# 말단 fence 미종료 변형: ```json\n{...} 뒤에 닫는 fence 없이 (그리고 종종
# 짝 없는 </tool_call>만 붙은) 생성이 끝나는 경우 — 27B급 모델의 실측 변형
# (2026-09-04 Codex E2E에서 발견). 닫는 fence가 있으면 위 정규식이 먼저 매치되고,
# 이 패턴은 최후 폴백으로만 쓰인다.
_BACKTICK_UNTERMINATED_REGEX: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(?P<body>\{\s*\"name\"\s*:\s*\"[^\"]+\".*?)\s*(?:</tool_call>)?\s*$",
    re.DOTALL,
)

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonMap = dict[str, JsonValue]

_JSON_MAP_ADAPTER: Final[TypeAdapter[JsonMap]] = TypeAdapter(JsonMap)


@dataclass(frozen=True, slots=True)
class ParsedToolCall:
    """Standardized tool call output."""

    name: str
    arguments: JsonMap
    raw_content: str
    repaired: bool = False


class RobustToolParser:
    """Extracts and heals tool calls from model generation streams."""

    @staticmethod
    def extract_tool_calls(text: str) -> list[ParsedToolCall]:
        """Extract all valid or repairable tool calls from model output.

        Args:
            text: Raw generation output from LLM.

        Returns:
            List of parsed and repaired ParsedToolCall objects.
        """
        calls: list[ParsedToolCall] = []

        # 1. Search for explicit <tool_call> tags
        for match in _TOOL_CALL_REGEX.finditer(text):
            body = match.group("body").strip()
            parsed, repaired = RobustToolParser._parse_or_repair_json(body)
            if parsed:
                name = parsed.get("name")
                args = parsed.get("arguments") or {}
                if name and isinstance(name, str) and isinstance(args, dict):
                    calls.append(
                        ParsedToolCall(
                            name=name,
                            arguments=args,
                            raw_content=match.group(0),
                            repaired=repaired,
                        )
                    )

        # 2. If no <tool_call> tags found, fallback to backtick JSON blocks with "name"
        if not calls:
            for match in _BACKTICK_TOOL_REGEX.finditer(text):
                body = match.group("body").strip()
                parsed, repaired = RobustToolParser._parse_or_repair_json(body)
                if parsed:
                    name = parsed.get("name")
                    args = parsed.get("arguments") or {}
                    if name and isinstance(name, str) and isinstance(args, dict):
                        calls.append(
                            ParsedToolCall(
                                name=name,
                                arguments=args,
                                raw_content=match.group(0),
                                repaired=repaired,
                            )
                        )

        # 3. 최후 폴백: 닫는 fence 없이 끝난 미종료 코드펜스 (말단 변형)
        if not calls:
            for match in _BACKTICK_UNTERMINATED_REGEX.finditer(text):
                body = match.group("body").strip()
                parsed, repaired = RobustToolParser._parse_or_repair_json(body)
                if parsed:
                    name = parsed.get("name")
                    args = parsed.get("arguments") or {}
                    if name and isinstance(name, str) and isinstance(args, dict):
                        calls.append(
                            ParsedToolCall(
                                name=name,
                                arguments=args,
                                raw_content=match.group(0),
                                repaired=True,
                            )
                        )

        return calls

    @staticmethod
    def _parse_or_repair_json(raw: str) -> tuple[JsonMap | None, bool]:
        """Attempt strict json.loads, then aggressive structural repair."""
        # 1. Direct strict parse
        try:
            return _JSON_MAP_ADAPTER.validate_json(raw), False
        except (ValidationError, json.JSONDecodeError):
            logger.debug("Strict tool-call JSON parsing failed", exc_info=True)

        # 2. Fix Python booleans, None, and trailing commas
        cleaned = raw
        cleaned = re.sub(r":\s*True\b", ": true", cleaned)
        cleaned = re.sub(r":\s*False\b", ": false", cleaned)
        cleaned = re.sub(r":\s*None\b", ": null", cleaned)
        cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)  # remove trailing commas

        try:
            return _JSON_MAP_ADAPTER.validate_json(cleaned), True
        except (ValidationError, json.JSONDecodeError):
            logger.debug("Repaired tool-call JSON parsing failed", exc_info=True)

        # 3. Python literal eval fallback for single quotes
        try:
            return _JSON_MAP_ADAPTER.validate_python(ast.literal_eval(raw)), True
        except (SyntaxError, ValueError, TypeError, ValidationError):
            logger.debug("Python literal tool-call parsing failed", exc_info=True)

        # 4. Greedy bracket closer
        open_braces = cleaned.count("{")
        close_braces = cleaned.count("}")
        if open_braces > close_braces:
            fixed = cleaned + ("}" * (open_braces - close_braces))
            try:
                return _JSON_MAP_ADAPTER.validate_json(fixed), True
            except (ValidationError, json.JSONDecodeError):
                logger.debug("Bracket-repaired tool-call parsing failed", exc_info=True)

        logger.debug("Failed to parse/repair tool call JSON: %s", raw[:120])
        return None, False
