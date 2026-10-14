import json
import re
from itertools import pairwise
from typing import Final, cast

_STRUCTURED_TOOL_RESPONSE: Final[re.Pattern[str]] = re.compile(
    r"""<tool_response>\s*\n\[TOOL_EVIDENCE\]\s*(?P<metadata>\{[^\r\n]*\})\s*\n\[UNTRUSTED_TOOL_RESULT\]\s*\n(?P<evidence>.*?)\n\[/UNTRUSTED_TOOL_RESULT\]\s*\n</tool_response>""",
    re.DOTALL,
)


def compact_structured_tool_response(content: str, max_evidence_chars: int = 640) -> str | None:
    matches = list(_STRUCTURED_TOOL_RESPONSE.finditer(content))
    if not matches:
        return None

    boundaries = [content[: matches[0].start()]]
    boundaries.extend(content[left.end() : right.start()] for left, right in pairwise(matches))
    boundaries.append(content[matches[-1].end() :])
    if any(boundary.strip() for boundary in boundaries):
        return None

    compacted = [_compact_match(match, max_evidence_chars) for match in matches]
    if any(response is None for response in compacted):
        return None
    return "\n".join(response for response in compacted if response is not None)


def _compact_match(match: re.Match[str], max_evidence_chars: int) -> str | None:
    try:
        metadata = cast(object, json.loads(match.group("metadata")))
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None
    metadata = cast(dict[str, object], metadata)

    evidence = match.group("evidence").strip()
    if len(evidence) <= max_evidence_chars:
        compacted_evidence = evidence
    else:
        head_chars = max_evidence_chars * 3 // 5
        tail_chars = max_evidence_chars - head_chars
        omitted_chars = len(evidence) - max_evidence_chars
        compacted_evidence = f"{evidence[:head_chars]}\n...[{omitted_chars} chars omitted]...\n{evidence[-tail_chars:]}"

    metadata_text = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "<tool_response>\n"
        f"[TOOL_EVIDENCE] {metadata_text}\n"
        "[UNTRUSTED_TOOL_RESULT]\n"
        f"{compacted_evidence}\n"
        "[/UNTRUSTED_TOOL_RESULT]\n"
        "</tool_response>"
    )
