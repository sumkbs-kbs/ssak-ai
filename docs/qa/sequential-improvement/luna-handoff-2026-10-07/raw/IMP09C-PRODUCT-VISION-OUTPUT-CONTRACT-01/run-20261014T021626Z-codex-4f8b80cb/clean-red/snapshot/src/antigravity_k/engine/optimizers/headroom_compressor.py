"""Headroom Compressor — Content-aware on-device compression layer.

Inspired by headroomlabs-ai/headroom.
Compresses text, JSON, and code representations before passing them to the model context.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from enum import StrEnum


class ContentKind(StrEnum):
    JSON = "json"
    CODE = "code"
    TEXT = "text"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class CompressionReport:
    original_chars: int
    compressed_chars: int
    kind: ContentKind
    tokens_before: int
    tokens_after: int

    @property
    def reduction_pct(self) -> float:
        if self.original_chars == 0:
            return 0.0
        return round((1 - self.compressed_chars / self.original_chars) * 100, 1)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)


_JSON_VALUE = re.compile(r"^\s*[\[{]")
_PY_KEYWORDS = ("def ", "class ", "import ", "from ", "if __name__")
_JS_KEYWORDS = ("function ", "const ", "=>", "console.", "export ")
_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _detect_kind(text: str) -> ContentKind:
    stripped = text.strip()
    if not stripped:
        return ContentKind.EMPTY
    if _JSON_VALUE.match(stripped):
        try:
            json.loads(stripped)
            return ContentKind.JSON
        except (json.JSONDecodeError, ValueError):
            pass
    if any(k in text for k in _PY_KEYWORDS) or "def " in text:
        try:
            ast.parse(text)
            return ContentKind.CODE
        except SyntaxError:
            pass
    if any(k in text for k in _JS_KEYWORDS):
        return ContentKind.CODE
    return ContentKind.TEXT


def _compress_json(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _is_docstring_stmt(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _node_text(node: ast.AST, source: str) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ast.get_source_segment(source, node) or ""


def _compress_code(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _compress_text(text)

    # Strip module-level docstring if present
    if tree.body and _is_docstring_stmt(tree.body[0]):
        tree.body = tree.body[1:]

    # Strip docstrings from functions and classes
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and _is_docstring_stmt(node.body[0]):
                node.body = node.body[1:]

    kept: list[str] = []
    for node in tree.body:
        seg = _node_text(node, text)
        if seg:
            kept.append(seg)
    return _compress_text("\n".join(kept))


def _compress_text(text: str) -> str:
    out = _WHITESPACE_RUN.sub(" ", text)
    out = _BLANK_LINES.sub("\n\n", out)
    return out.strip()


class HeadroomCompressor:
    """Content-aware compression engine."""

    def compress(self, text: str) -> tuple[str, CompressionReport]:
        original = text
        kind = _detect_kind(text)
        if kind is ContentKind.EMPTY:
            return text, CompressionReport(0, 0, kind, 0, 0)
        if kind is ContentKind.JSON:
            compressed = _compress_json(text)
        elif kind is ContentKind.CODE:
            compressed = _compress_code(text)
        else:
            compressed = _compress_text(text)
        if len(compressed) >= len(original):
            compressed = original
        return compressed, CompressionReport(
            len(original),
            len(compressed),
            kind,
            _estimate_tokens(original),
            _estimate_tokens(compressed),
        )

    def compress_messages(
        self, messages: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], list[CompressionReport]]:
        out: list[dict[str, object]] = []
        reports: list[CompressionReport] = []
        for msg in messages:
            content_obj = msg.get("content")
            if isinstance(content_obj, str) and len(content_obj) > 300:
                compressed, report = self.compress(content_obj)
                reports.append(report)
                out.append({**msg, "content": compressed})
            else:
                out.append(msg)
        return out, reports
