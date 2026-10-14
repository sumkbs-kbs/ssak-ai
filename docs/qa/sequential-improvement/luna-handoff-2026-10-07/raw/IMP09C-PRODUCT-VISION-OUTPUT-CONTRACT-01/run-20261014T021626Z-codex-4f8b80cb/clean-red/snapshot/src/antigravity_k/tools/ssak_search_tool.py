"""Ssak-Search Tool — Agent tool for live web search and fact grounding."""

from __future__ import annotations

import json
import logging
from typing import TypeAlias, cast, final, override

from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from antigravity_k.tools.ssak_search_client import search

logger = logging.getLogger(__name__)
JsonMap: TypeAlias = dict[str, object]


@final
class SsakSearchTool(BaseTool):
    """Web search tool backed by Ssak-Search deployed API."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🌐"
    tags: list[str] = ["web", "search", "ssak-search", "grounding", "internet"]

    def __init__(self) -> None:
        super().__init__()
        self._name: str = "ssak_search"
        self._description: str = (
            "Live web search engine for current external facts, documentation, and news. "
            "Returns ranked search results with titles, URLs, and snippet contents."
        )
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query keywords to find information about.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> JsonMap:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        raw_query = kwargs.get("query")
        query = str(raw_query).strip() if raw_query is not None else ""
        if not query:
            return json.dumps({"error": "Empty search query"}, ensure_ascii=False)
        max_results_val = kwargs.get("max_results", 5)
        try:
            max_results = int(cast(int, max_results_val))
        except (TypeError, ValueError):
            max_results = 5
        try:
            hits = search(query, max_results=max_results)
            formatted = [
                {
                    "title": h.title,
                    "url": h.url,
                    "content": h.content,
                    "score": h.score,
                    "domain": h.domain,
                }
                for h in hits
            ]
            return json.dumps({"query": query, "count": len(formatted), "results": formatted}, ensure_ascii=False)
        except Exception as exc:
            logger.warning("ssak_search failed: %s", exc)
            return json.dumps({"query": query, "error": str(exc), "results": []}, ensure_ascii=False)
