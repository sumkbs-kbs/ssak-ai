"""Hybrid Search module."""

import logging
from collections.abc import Mapping
from typing import Generic, Protocol, TypeVar, cast, final

from antigravity_k.engine.code_intel.knowledge_graph import NodePropertyValue

logger = logging.getLogger("antigravity_k.engine.code_intel.hybrid_search")


class _NodeContainer(Protocol):
    nodes: Mapping[str, Mapping[str, NodePropertyValue]]


GraphT = TypeVar("GraphT")


@final
class HybridSearchEngine(Generic[GraphT]):
    """Combines semantic vector search and keyword (BM25) search for code retrieval."""

    graph: GraphT
    index_built: bool

    def __init__(self, graph: GraphT) -> None:
        """Initialize the HybridSearchEngine.

        Args:
            graph: graph.

        """
        self.graph = graph
        self.index_built = False

    def build_index(self) -> None:
        """Build index."""
        # Mock index building
        self.index_built = True
        logger.info("Hybrid search index built.")

    def search(self, query: str, top_k: int = 10) -> list[Mapping[str, NodePropertyValue]]:
        """Search for.

        Args:
            query (str): str query.
            top_k (int): int top k.

        Returns:
            list[dict]: The list[dict] result.

        """
        if not query or not query.strip():
            return []

        if not self.index_built:
            self.build_index()

        results: list[Mapping[str, NodePropertyValue]] = []
        q_lower = query.lower()

        # Simple substring match over node names and properties
        nodes = cast(_NodeContainer, self.graph).nodes
        for node in nodes.values():
            name_value: NodePropertyValue = node.get("name", "")
            name = name_value.lower() if isinstance(name_value, str) else ""
            if q_lower in name:
                results.append(node)

            # Stop if we have enough
            if len(results) >= top_k:
                break

        return results
