from __future__ import annotations

import re


def extract_identity_facts(text: str) -> dict[str, str]:
    patterns = (
        r"내\s*이름은\s*([가-힣A-Za-z][가-힣A-Za-z·\s]{0,8}?)\s*(?:이|가)?\s*(?:야|요|입니다|라고\s*해|라고\s*합니다)",
        r"저(?:는|은)?\s*([가-힣A-Za-z][가-힣A-Za-z·\s]{0,8}?)\s*(?:이|가)?\s*라고\s*(?:합니다|해|합니당)",
        r"제\s*이름은\s*([가-힣A-Za-z][가-힣A-Za-z·\s]{0,8}?)\s*(?:이|가)?\s*(?:에요|입니다|야)",
        r"내\s*이름(?:은|이)?\s*([가-힣A-Za-z][가-힣A-Za-z·]{0,8}?)\s*로\s*(?:바꿨|했|해)",
        r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\-]{0,19})\b",
        r"\b(?:i\s*am|i'?m)\s+([A-Z][a-z]{1,19})\b",
        r"\bcall\s+me\s+([A-Za-z][A-Za-z\-]{0,19})\b",
    )
    excluded = {"a", "an", "the", "here", "there", "fine", "good", "ok"}
    for pattern in patterns:
        if match := re.search(pattern, text):
            value = match.group(1).strip().rstrip(".!?")
            if 1 <= len(value) <= 20 and value.lower() not in excluded:
                return {"name": value}
    return {}
