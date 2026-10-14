"""Graphify Builder — Codebase-to-Knowledge-Graph and Hybrid Retrieval Engine.

Inspired by Graphify-Labs/graphify.
AST scans code repositories into queryable nodes with docstring and constant capture,
and provides hybrid retrieval (embedding similarity + keyword ranking) for codebase navigation.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

_DEF_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function|fn|interface|type|struct|enum)\s+(\w+)",
    re.MULTILINE,
)
_IMPORT_PATTERN = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+(\w+)|import\s+([\w.]+))", re.MULTILINE)
_IGNORE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".omo",
    ".agent",
}
_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb"}


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: str
    name: str
    file: str
    line: int


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    relation: str


@dataclass(slots=True)
class KnowledgeGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [
                {"node_id": n.node_id, "kind": n.kind, "name": n.name, "file": n.file, "line": n.line}
                for n in self.nodes
            ],
            "edges": [{"source": e.source, "target": e.target, "relation": e.relation} for e in self.edges],
            "file_hashes": dict(self.file_hashes),
        }


GraphifyKnowledgeGraph = KnowledgeGraph


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _parse_python(file: Path, rel: str) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return nodes, edges

    # Module docstring
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        doc = tree.body[0].value.value.strip().splitlines()[0][:80]
        if doc:
            nodes.append(GraphNode(f"{rel}:module:0", "module", doc, rel, 0))

    # Module-level constants
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value_preview = ""
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                value_preview = " " + node.value.value[:100]
            elif isinstance(node.value, ast.JoinedStr):
                parts: list[str] = []
                for val in node.value.values:
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        parts.append(val.value)
                value_preview = " " + " ".join(parts)[:100]

            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id.startswith("_") or not target.id.isupper():
                        continue
                    label = f"{target.id}{value_preview}" if value_preview else target.id
                    nid = f"{rel}:const:{target.id}:{node.lineno}"
                    nodes.append(GraphNode(nid, "constant", label, rel, node.lineno))
        elif isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_"):
                nid = f"{rel}:const:{t.id}:{node.lineno}"
                nodes.append(GraphNode(nid, "constant", t.id, rel, node.lineno))

    # Functions, classes, and call edges
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function"
            label = item.name
            if (
                item.body
                and isinstance(item.body[0], ast.Expr)
                and isinstance(item.body[0].value, ast.Constant)
                and isinstance(item.body[0].value.value, str)
            ):
                first_line = item.body[0].value.value.strip().splitlines()[0][:60]
                if first_line:
                    label = f"{item.name} {first_line}"
            nid = f"{rel}:{item.name}:{item.lineno}"
            nodes.append(GraphNode(nid, kind, label, rel, item.lineno))

            # Scan calls inside this function
            for inner in ast.walk(item):
                if isinstance(inner, ast.Call):
                    if isinstance(inner.func, ast.Name):
                        edges.append(GraphEdge(source=nid, target=inner.func.id, relation="calls"))
                    elif isinstance(inner.func, ast.Attribute):
                        edges.append(GraphEdge(source=nid, target=inner.func.attr, relation="calls"))

        elif isinstance(item, ast.ClassDef):
            kind = "class"
            label = item.name
            if (
                item.body
                and isinstance(item.body[0], ast.Expr)
                and isinstance(item.body[0].value, ast.Constant)
                and isinstance(item.body[0].value.value, str)
            ):
                first_line = item.body[0].value.value.strip().splitlines()[0][:60]
                if first_line:
                    label = f"{item.name} {first_line}"
            nid = f"{rel}:{item.name}:{item.lineno}"
            nodes.append(GraphNode(nid, kind, label, rel, item.lineno))

            for base in item.bases:
                if isinstance(base, ast.Name):
                    edges.append(GraphEdge(source=nid, target=base.id, relation="inherits"))

    return nodes, edges


def _scan_file(file: Path, root: Path) -> tuple[list[GraphNode], list[GraphEdge], str]:
    rel = str(file.relative_to(root))
    fh = _file_hash(file)
    if file.suffix == ".py":
        nodes, edges = _parse_python(file, rel)
    else:
        nodes, edges = [], []
        text = file.read_text(encoding="utf-8", errors="replace")
        for m in _DEF_PATTERN.finditer(text):
            nid = f"{rel}:{m.group(1)}:{m.start()}"
            nodes.append(GraphNode(nid, "symbol", m.group(1), rel, m.start()))
    return nodes, edges, fh


def build_graph(
    root: Path,
    *,
    cached_graph: KnowledgeGraph | None = None,
    cached: Mapping[str, str] | None = None,
) -> KnowledgeGraph:
    """Build or update a KnowledgeGraph for the specified project directory."""
    graph = KnowledgeGraph()
    resolved_root = root.resolve()

    old_hashes: dict[str, str] = {}
    retained_nodes: dict[str, list[GraphNode]] = {}
    retained_edges: dict[str, list[GraphEdge]] = {}

    if cached_graph is not None:
        old_hashes = dict(cached_graph.file_hashes)
        for n in cached_graph.nodes:
            retained_nodes.setdefault(n.file, []).append(n)
        for e in cached_graph.edges:
            src_file = e.source.split(":", 1)[0]
            retained_edges.setdefault(src_file, []).append(e)
    elif cached:
        old_hashes = dict(cached)

    for file in resolved_root.rglob("*"):
        if any(part in _IGNORE_DIRS for part in file.parts):
            continue
        if file.suffix not in _CODE_EXTS or not file.is_file():
            continue
        rel = str(file.relative_to(resolved_root))
        fh = _file_hash(file)
        if old_hashes.get(rel) == fh and rel in retained_nodes:
            graph.nodes.extend(retained_nodes[rel])
            graph.edges.extend(retained_edges.get(rel, []))
            graph.file_hashes[rel] = fh
            continue
        nodes, edges, fh = _scan_file(file, resolved_root)
        graph.nodes.extend(nodes)
        graph.edges.extend(edges)
        graph.file_hashes[rel] = fh
    return graph


def query_graph(graph: KnowledgeGraph, term: str, *, limit: int = 20) -> list[GraphNode]:
    """Query nodes by substring matching."""
    term_lower = term.lower()
    matches = [n for n in graph.nodes if term_lower in n.name.lower()]
    return matches[:limit]


def explain_node(graph: KnowledgeGraph, name: str) -> dict[str, object]:
    """Explain a symbol node, returning its definition location, callers, and callees."""
    matches = [n for n in graph.nodes if n.name == name or n.name.startswith(f"{name} ")]
    if not matches:
        matches = query_graph(graph, name)
    if not matches:
        return {"found": False, "name": name}
    node = matches[0]
    base_name = node.name.split()[0]
    callers = [e.source for e in graph.edges if e.target in (node.node_id, node.name, base_name)]
    callees = [e.target for e in graph.edges if e.source in (node.node_id, node.name, base_name)]
    return {
        "found": True,
        "node": {
            "node_id": node.node_id,
            "kind": node.kind,
            "name": node.name,
            "file": node.file,
            "line": node.line,
        },
        "callers": callers[:10],
        "callees": callees[:10],
    }


def find_path(graph: KnowledgeGraph, source_name: str, target_name: str) -> list[str] | None:
    """Find a path between two nodes in the graph using BFS."""
    src = [n for n in graph.nodes if n.name == source_name or n.name.startswith(f"{source_name} ")]
    tgt = [n for n in graph.nodes if n.name == target_name or n.name.startswith(f"{target_name} ")]
    if not src or not tgt:
        return None

    # Build symbol lookup map
    sym_to_node_ids: dict[str, list[str]] = {}
    for n in graph.nodes:
        base_n = n.name.split()[0]
        sym_to_node_ids.setdefault(base_n, []).append(n.node_id)
        sym_to_node_ids.setdefault(n.node_id, []).append(n.node_id)

    adj: dict[str, list[str]] = {}
    for n in graph.nodes:
        adj.setdefault(n.node_id, [])

    for e in graph.edges:
        src_ids = sym_to_node_ids.get(e.source, [e.source])
        tgt_ids = sym_to_node_ids.get(e.target, [e.target])
        for s_id in src_ids:
            for t_id in tgt_ids:
                adj.setdefault(s_id, []).append(t_id)

    start_node_id = src[0].node_id
    goal_node_ids = {t.node_id for t in tgt}

    visited = {start_node_id}
    queue: list[tuple[str, list[str]]] = [(start_node_id, [start_node_id])]
    while queue:
        cur, path = queue.pop(0)
        if cur in goal_node_ids:
            return path
        for nxt in adj.get(cur, []):
            if nxt in goal_node_ids:
                return [*path, nxt]
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, [*path, nxt]))
    return None


def save_graph(graph: KnowledgeGraph, path: Path) -> None:
    """Serialize the graph to a JSON file."""
    path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")


def load_graph(path: Path) -> KnowledgeGraph:
    """Deserialize a KnowledgeGraph from a JSON file."""
    data = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    g = KnowledgeGraph()
    raw_nodes = cast(list[dict[str, object]], data.get("nodes", []))
    for n in raw_nodes:
        g.nodes.append(
            GraphNode(
                cast(str, n["node_id"]),
                cast(str, n["kind"]),
                cast(str, n["name"]),
                cast(str, n["file"]),
                cast(int, n["line"]),
            )
        )
    raw_edges = cast(list[dict[str, object]], data.get("edges", []))
    for e in raw_edges:
        g.edges.append(GraphEdge(cast(str, e["source"]), cast(str, e["target"]), cast(str, e["relation"])))
    g.file_hashes = {str(k): str(v) for k, v in cast(dict[object, object], data.get("file_hashes", {})).items()}
    return g


def embedding_retrieve(
    graph: KnowledgeGraph,
    question: str,
    top_k: int = 12,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[GraphNode]:
    """Retrieve relevant graph nodes using sentence-transformers cosine similarity."""
    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        return []

    file_docs: dict[str, list[str]] = {}
    file_nodes: dict[str, list[GraphNode]] = {}
    for n in graph.nodes:
        if n.kind in ("class", "function", "constant"):
            file_docs.setdefault(n.file, []).append(f"{n.kind} {n.name}")
            file_nodes.setdefault(n.file, []).append(n)
    if not file_docs:
        return []

    try:
        files = list(file_docs.keys())
        docs = [" ".join(file_docs[f]) for f in files]
        model = SentenceTransformer(model_name)
        doc_emb = model.encode(docs, convert_to_tensor=True, show_progress_bar=False)
        q_emb = model.encode([question], convert_to_tensor=True, show_progress_bar=False)
        sims = util.cos_sim(q_emb, doc_emb)[0]
        ranked = sorted(range(len(files)), key=lambda i: float(sims[i]), reverse=True)[:top_k]
        out: list[GraphNode] = []
        for i in ranked:
            out.extend(file_nodes[files[i]][:10])
        return out
    except Exception:
        return []


def hybrid_retrieve(
    graph: KnowledgeGraph,
    question: str,
    top_k: int = 10,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[str]:
    """Hybrid retrieval combining semantic embedding retrieval and keyword token ranking."""
    emb_files: list[str] = []
    try:
        hits = embedding_retrieve(graph, question, top_k=top_k, model_name=model_name)
        for n in hits:
            if n.file not in emb_files:
                emb_files.append(n.file)
    except Exception:
        pass

    raw_words = question.replace("?", " ").replace("-", " ").replace("_", " ").replace("/", " ").split()
    keywords = [w.lower() for w in raw_words if len(w) > 2]
    scored: dict[str, int] = {}
    for n in graph.nodes:
        name_lower = n.name.lower()
        hits_count = sum(1 for k in keywords if k in name_lower)
        if hits_count > 0:
            scored[n.file] = scored.get(n.file, 0) + hits_count

    keyword_files = [f for f, _ in sorted(scored.items(), key=lambda x: x[1], reverse=True)]
    result = emb_files + [f for f in keyword_files if f not in emb_files]
    return result[: top_k + 4]


def build_file_index_rows(graph: KnowledgeGraph, files: list[str], symbols_per_file: int = 12) -> list[str]:
    """Format retrieved files into compact, token-efficient summary lines for LLM context."""
    rows: list[str] = []
    for f in files:
        syms = [n.name.split()[0] for n in graph.nodes if n.file == f and n.kind in ("class", "function", "constant")][
            :symbols_per_file
        ]
        if not syms:
            continue
        base = f.rsplit("/", 1)[-1]
        rows.append(f"{base} ({f}): {', '.join(syms)}")
    return rows
