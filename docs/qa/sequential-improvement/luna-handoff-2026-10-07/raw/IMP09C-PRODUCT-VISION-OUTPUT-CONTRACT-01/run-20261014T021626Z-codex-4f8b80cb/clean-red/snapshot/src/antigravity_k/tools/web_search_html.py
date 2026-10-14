from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final, override
from urllib.parse import parse_qs, urljoin, urlsplit

from .web_search_quality import is_public_http_url

_TITLE_CLASSES: Final = frozenset({"result__a", "result-link"})
_SNIPPET_CLASSES: Final = frozenset({"result__snippet", "result-snippet"})
_VOID_TAGS: Final = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


@dataclass(frozen=True, slots=True)
class DuckDuckGoResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True, slots=True, eq=False)
class _Element:
    tag: str
    attributes: tuple[tuple[str, str | None], ...]
    parent: _Element | None
    text_parts: list[str] = field(default_factory=list)

    def attribute(self, name: str) -> str:
        return next((value or "" for key, value in self.attributes if key == name), "")

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attribute("class").split())

    @property
    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())


class _ResultDocument(HTMLParser):
    """Accumulate element ancestry and result text while parsing provider HTML."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[_Element] = []
        self.stack: list[_Element] = []
        self.feed(markup)
        self.close()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(tag, tuple(attrs), self.stack[-1] if self.stack else None)
        self.elements.append(element)
        if tag == "br":
            self.handle_data(" ")
        if tag not in _VOID_TAGS:
            self.stack.append(element)

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    @override
    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    @override
    def handle_data(self, data: str) -> None:
        if any(element.tag in {"script", "style"} for element in self.stack):
            return
        for element in self.stack:
            if element.classes & (_TITLE_CLASSES | _SNIPPET_CLASSES):
                element.text_parts.append(data)


def _has_challenge(document: _ResultDocument) -> bool:
    for element in document.elements:
        identifiers = element.classes | {element.attribute("id")}
        if any(identifier.startswith("anomaly-modal") for identifier in identifiers):
            return True
        if element.tag == "form" and (
            element.attribute("id") in {"challenge-form", "img-form"} or "/anomaly.js" in element.attribute("action")
        ):
            return True
        if element.tag == "input" and element.attribute("name").startswith("image-check_"):
            return True
    return False


def is_duckduckgo_challenge(markup: str) -> bool:
    """Detect DDG's challenge controls without matching words in search results."""
    return _has_challenge(_ResultDocument(markup))


def _result_scope(element: _Element) -> _Element | None:
    parent = element.parent
    while parent is not None:
        if "result" in parent.classes or "web-result" in parent.classes:
            return parent
        parent = parent.parent
    return None


def _public_result_url(href: str) -> str:
    try:
        candidate = urljoin("https://duckduckgo.com/", href.strip())
        if not is_public_http_url(candidate):
            return ""
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            host in {"duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com"}
            and parsed.path.rstrip("/") == "/l"
        ):
            candidate = parse_qs(parsed.query).get("uddg", [""])[0]
    except ValueError:
        return ""
    return candidate if is_public_http_url(candidate) else ""


def parse_duckduckgo_results(markup: str, limit: int = 24) -> list[DuckDuckGoResult]:
    """Parse HTML and Lite results, binding snippets to their owning result."""
    document = _ResultDocument(markup)
    if limit <= 0 or _has_challenge(document):
        return []
    titles = [
        (index, element)
        for index, element in enumerate(document.elements)
        if element.tag == "a" and element.classes & _TITLE_CLASSES
    ]
    snippets = [
        (index, element) for index, element in enumerate(document.elements) if element.classes & _SNIPPET_CLASSES
    ]
    results: list[DuckDuckGoResult] = []
    for position, (start, title) in enumerate(titles):
        scope = _result_scope(title)
        end = titles[position + 1][0] if position + 1 < len(titles) else len(document.elements)
        snippet = next(
            (
                element.text
                for index, element in snippets
                if (
                    _result_scope(element) is scope
                    if scope is not None
                    else start < index < end and _result_scope(element) is None
                )
            ),
            "",
        )
        url = _public_result_url(title.attribute("href")) if title.attribute("href") else ""
        if title.text and url:
            results.append(DuckDuckGoResult(title.text, url, snippet))
            if len(results) == limit:
                break
    return results
