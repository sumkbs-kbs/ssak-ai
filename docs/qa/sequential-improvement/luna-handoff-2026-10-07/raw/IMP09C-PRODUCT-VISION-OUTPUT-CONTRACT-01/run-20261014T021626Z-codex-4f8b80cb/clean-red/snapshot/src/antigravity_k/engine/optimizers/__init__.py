"""Optimizers package — On-device context compression, directive shaping, and codebase knowledge graphs."""

from antigravity_k.engine.optimizers.graphify_builder import (
    GraphEdge,
    GraphifyKnowledgeGraph,
    GraphNode,
    KnowledgeGraph,
    build_file_index_rows,
    build_graph,
    embedding_retrieve,
    explain_node,
    find_path,
    hybrid_retrieve,
    load_graph,
    query_graph,
    save_graph,
)
from antigravity_k.engine.optimizers.headroom_compressor import (
    CompressionReport,
    ContentKind,
    HeadroomCompressor,
)
from antigravity_k.engine.optimizers.ponytail_shaper import (
    LAZY_SENIOR_DIRECTIVE,
    apply_ponytail,
    ponytail_system_prefix,
)

__all__ = [
    "CompressionReport",
    "ContentKind",
    "GraphEdge",
    "GraphNode",
    "GraphifyKnowledgeGraph",
    "HeadroomCompressor",
    "KnowledgeGraph",
    "LAZY_SENIOR_DIRECTIVE",
    "apply_ponytail",
    "build_file_index_rows",
    "build_graph",
    "embedding_retrieve",
    "explain_node",
    "find_path",
    "hybrid_retrieve",
    "load_graph",
    "ponytail_system_prefix",
    "query_graph",
    "save_graph",
]
