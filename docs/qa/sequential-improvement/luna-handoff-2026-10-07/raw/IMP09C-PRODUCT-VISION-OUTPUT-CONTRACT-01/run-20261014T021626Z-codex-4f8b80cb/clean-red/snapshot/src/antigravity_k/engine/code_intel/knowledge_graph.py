"""Knowledge Graph module."""

from collections.abc import Mapping
from enum import Enum
from typing import TypeAlias, TypedDict

from pydantic import JsonValue


class NodeType(str, Enum):
    """Nodetype.

    Bases: str, Enum
    """

    FILE = "File"
    FUNCTION = "Function"
    CLASS = "Class"
    VARIABLE = "Variable"
    MODULE = "Module"


NodePropertyValue: TypeAlias = JsonValue | NodeType
NodeProperties: TypeAlias = dict[str, NodePropertyValue]


class EdgeRecord(TypedDict):
    source: str
    target: str
    relationship: str


class KnowledgeGraphStats(TypedDict):
    total_nodes: int
    total_edges: int
    node_types: dict[NodeType, int]


class KnowledgeGraph:
    """Code-structure graph (modules, functions, call edges) for impact analysis."""

    def __init__(self):
        """Initialize the KnowledgeGraph."""
        self.nodes: dict[str, NodeProperties] = {}
        self.edges: list[EdgeRecord] = []

    def add_node(self, node_id: str, node_type: NodeType, properties: Mapping[str, JsonValue]) -> None:
        """Add node.

        Args:
            node_id (str): str node id.
            node_type (NodeType): NodeType node type.
            properties (dict[str, Any]): dict[str, Any] properties.

        """
        node: NodeProperties = dict(properties)
        node["id"] = node_id
        node["node_type"] = node_type
        self.nodes[node_id] = node

    def add_edge(self, source_id: str, target_id: str, relationship: str) -> None:
        """Add edge.

        Args:
            source_id (str): str source id.
            target_id (str): str target id.
            relationship (str): str relationship.

        """
        self.edges.append({"source": source_id, "target": target_id, "relationship": relationship})

    def get_nodes_by_type(self, node_type: NodeType) -> list[NodeProperties]:
        """Retrieve nodes by type.

        Args:
            node_type (NodeType): NodeType node type.

        Returns:
            list[dict]: The list[dict] result.

        """
        return [n for n in self.nodes.values() if n["node_type"] == node_type]

    def stats(self) -> KnowledgeGraphStats:
        """Stats.

        Returns:
            dict: The dict result.

        """
        node_types: dict[NodeType, int] = {}
        for node in self.nodes.values():
            node_type_value = node["node_type"]
            if isinstance(node_type_value, NodeType):
                node_types[node_type_value] = node_types.get(node_type_value, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": node_types,
        }
