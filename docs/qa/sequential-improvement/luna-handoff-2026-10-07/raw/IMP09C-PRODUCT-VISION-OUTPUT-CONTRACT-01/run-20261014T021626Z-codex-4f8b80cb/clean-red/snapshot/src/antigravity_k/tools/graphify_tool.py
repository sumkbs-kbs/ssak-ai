"""Graphify Tool — AST Knowledge Graph and Hybrid Retrieval Tool.

Allows agents to query codebase symbols, explain caller/callee relationships,
find call graph paths, and perform hybrid retrieval over large codebases.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TypeAlias, cast, final, override

from antigravity_k.engine.optimizers.graphify_builder import (
    KnowledgeGraph,
    build_file_index_rows,
    build_graph,
    explain_node,
    find_path,
    hybrid_retrieve,
    query_graph,
)
from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from antigravity_k.tools.tool_path import effective_project_root

logger = logging.getLogger(__name__)
JsonMap: TypeAlias = dict[str, object]


@final
class GraphifyTool(BaseTool):
    """AST-based codebase knowledge graph and hybrid retrieval tool."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🕸️"
    tags: list[str] = ["graphify", "ast", "search", "navigation", "callgraph", "hybrid-retrieve"]

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__()
        self._project_root: str | None = project_root
        self._name: str = "graphify"
        self._description: str = (
            "Codebase knowledge graph and hybrid retrieval engine. "
            "Supports: 'hybrid_retrieve' (semantic + keyword file ranking), "
            "'query' (symbol search), 'explain' (callers/callees), and 'path' (call graph path)."
        )
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["hybrid_retrieve", "query", "explain", "path"],
                    "description": "The graph operation to execute.",
                    "default": "hybrid_retrieve",
                },
                "query": {
                    "type": "string",
                    "description": "The search term, symbol name, or natural language question.",
                },
                "target": {
                    "type": "string",
                    "description": "(Optional) Target symbol name when action is 'path'.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10).",
                    "default": 10,
                },
                "target_dir": {
                    "type": "string",
                    "description": "(Optional) Target codebase directory. Defaults to active project root.",
                },
            },
            "required": ["query"],
        }
        self._cached_graph: KnowledgeGraph | None = None
        self._cached_root: str | None = None

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
    def parameters_schema(self) -> Mapping[str, object]:
        return self._schema

    def _get_or_build_graph(self, root_dir: Path) -> KnowledgeGraph:
        root_str = str(root_dir)
        if self._cached_graph is not None and self._cached_root == root_str:
            # Incremental update retaining cached nodes and edges
            self._cached_graph = build_graph(root_dir, cached_graph=self._cached_graph)
            return self._cached_graph

        graph = build_graph(root_dir)
        self._cached_graph = graph
        self._cached_root = root_str
        return graph

    @override
    def execute(self, **kwargs: object) -> str:
        raw_query = kwargs.get("query")
        query = str(raw_query).strip() if raw_query is not None else ""
        if not query:
            return "Error: 'query' parameter is required."

        action = str(kwargs.get("action", "hybrid_retrieve")).lower()
        target = str(kwargs.get("target", "")).strip()
        top_k_raw = kwargs.get("top_k", 10)
        try:
            top_k = int(cast(int | str, top_k_raw))
        except (ValueError, TypeError):
            top_k = 10

        raw_dir = kwargs.get("target_dir")
        if isinstance(raw_dir, str) and raw_dir.strip():
            root_dir = Path(raw_dir.strip()).resolve()
        else:
            root_dir = Path(effective_project_root(self._project_root)).resolve()

        if not root_dir.exists():
            return f"Error: Target directory does not exist: {root_dir}"

        graph = self._get_or_build_graph(root_dir)

        if action == "hybrid_retrieve":
            files = hybrid_retrieve(graph, query, top_k=top_k)
            rows = build_file_index_rows(graph, files, symbols_per_file=10)
            if not rows:
                return f"No matching files or symbols found for '{query}'."
            return f"Retrieved {len(rows)} relevant files:\n" + "\n".join(f"- {r}" for r in rows)

        if action == "query":
            hits = query_graph(graph, query, limit=top_k)
            if not hits:
                return f"No symbols found matching '{query}'."
            lines = [f"- [{h.kind}] {h.name} ({h.file}:{h.line})" for h in hits]
            return f"Found {len(hits)} matching nodes:\n" + "\n".join(lines)

        if action == "explain":
            info = explain_node(graph, query)
            if not info.get("found"):
                return f"Symbol '{query}' not found in knowledge graph."
            return json.dumps(info, indent=2)

        if action == "path":
            if not target:
                return "Error: 'target' parameter is required for 'path' action."
            path = find_path(graph, query, target)
            if not path:
                return f"No path found between '{query}' and '{target}'."
            return f"Path ({len(path)} steps):\n" + " -> ".join(path)

        return f"Error: Unknown action '{action}'. Supported actions: hybrid_retrieve, query, explain, path."
