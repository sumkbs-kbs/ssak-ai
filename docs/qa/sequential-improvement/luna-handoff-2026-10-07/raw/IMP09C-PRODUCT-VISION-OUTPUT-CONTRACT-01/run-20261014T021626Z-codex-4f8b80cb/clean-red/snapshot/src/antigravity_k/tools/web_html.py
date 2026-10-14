from __future__ import annotations

import re
from typing import Final

from scrapling.parser import Selector

_DROPPED_TAGS: Final[frozenset[str]] = frozenset(
    {
        "head",
        "script",
        "style",
        "template",
        "noscript",
        "nav",
        "footer",
        "aside",
        "form",
        "input",
        "button",
        "select",
        "textarea",
    },
)
_BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "caption",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "thead",
        "tr",
        "ul",
    },
)
_HTML_MARKUP: Final[re.Pattern[str]] = re.compile(r"<\s*(?:[!?]|/?[A-Za-z][\w:-]*(?:\s|/?>))")
_HIDDEN_STYLE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\s*(?:!important\s*)?(?:;|$)",
    re.IGNORECASE,
)


def _is_semantic(node: Selector) -> bool:
    return node.tag in {"article", "main"} or str(node.attrib.get("role", "")).strip().lower() == "main"


def _is_excluded(node: Selector) -> bool:
    attributes = node.attrib
    return (
        node.tag in _DROPPED_TAGS
        or "hidden" in attributes
        or str(attributes.get("aria-hidden", "")).strip().lower() == "true"
        or _HIDDEN_STYLE.search(str(attributes.get("style", ""))) is not None
        or (node.tag == "header" and not any(_is_semantic(parent) for parent in node.iterancestors()))
    )


def _render_node(node: Selector, *, preserve_whitespace: bool = False) -> str:
    if node.tag == "#text":
        text = str(node.text)
        return text if preserve_whitespace else re.sub(r"\s+", " ", text)
    if _is_excluded(node):
        return ""
    if node.tag == "br":
        return "\n"
    preserve = preserve_whitespace or node.tag == "pre"
    content = "".join(_render_node(child, preserve_whitespace=preserve) for child in node.xpath("./node()"))
    if node.tag in {"td", "th"}:
        return content.strip() + "\t"
    if node.tag in _BLOCK_TAGS:
        return "\n" + content + "\n"
    return content


def _clean_layout(text: str) -> str:
    lines = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", lines).strip()


def html_to_text(html_text: str, max_chars: int = 5000) -> str:
    """Extract readable body text with a deterministic character cap.

    Inline adjacency, code indentation, and table cell separators survive. Empty
    semantic areas fall back to the body; nonpositive caps return an empty string.
    Parsing performs no network requests and uses no adaptive selector storage.
    """
    if max_chars <= 0 or not html_text.strip():
        return ""
    if _HTML_MARKUP.search(html_text) is None:
        return re.sub(r"\s+", " ", html_text).strip()[:max_chars]

    document = Selector(html_text, adaptive=False, huge_tree=False)
    candidates = document.xpath("descendant-or-self::*[self::article or self::main or @role='main']")
    roots = [
        node
        for node in candidates
        if not _is_excluded(node)
        and not any(_is_excluded(parent) or _is_semantic(parent) for parent in node.iterancestors())
    ]
    parts = [_clean_layout(_render_node(root)) for root in roots]
    content = "\n\n".join(part for part in parts if part)
    if not content:
        bodies = document.xpath("//body")
        content = _clean_layout("\n\n".join(_render_node(body) for body in bodies or [document]))
    return content[:max_chars]
