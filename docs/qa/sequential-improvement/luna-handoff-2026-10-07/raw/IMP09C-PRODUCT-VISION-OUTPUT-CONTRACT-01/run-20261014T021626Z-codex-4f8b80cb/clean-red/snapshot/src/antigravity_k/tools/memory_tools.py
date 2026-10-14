"""Memory Tools module."""

import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

ToolValue: TypeAlias = object
ToolSchema: TypeAlias = dict[str, object]


class _VectorStoreLike(Protocol):
    def upsert_chunks(self, chunks: Sequence[Mapping[str, object]]) -> None: ...

    def search(self, query: str, n_results: int = 5) -> list[dict[str, object]]: ...


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _as_positive_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


@final
class StoreKnowledgeTool(BaseTool):
    """지식을 벡터 저장소에 영구적으로 기록합니다."""

    category: ToolCategory = ToolCategory.SYSTEM
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "💾"
    tags: list[str] = ["memory", "knowledge", "save", "store"]
    _name: str
    _description: str
    _schema: ToolSchema
    project_root: str
    _vector_store: _VectorStoreLike | None

    def __init__(self, project_root: str | None = None):
        """Initialize the StoreKnowledgeTool.

        Args:
            project_root (str): str project root.

        """
        super().__init__()
        self._name = "store_knowledge"
        self._description = (
            "Store a piece of knowledge permanently in the project's long-term memory (Vector Store). Useful for"
        )
        "remembering user preferences, architectural decisions, or bugs across sessions."
        self._schema = {
            "type": "object",
            "properties": {
                "knowledge_text": {"type": "string", "description": "The information to remember."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tags categorizing this knowledge.",
                },
            },
            "required": ["knowledge_text"],
        }
        self.project_root = project_root or os.getcwd()
        self._vector_store = None

    def _get_vector_store(self) -> _VectorStoreLike:
        if not self._vector_store:
            from antigravity_k.engine.vector_store import VectorStore

            db_path = os.path.join(self.project_root, ".antigravity", "vault_data")
            self._vector_store = cast(
                _VectorStoreLike,
                VectorStore(
                    persist_directory=db_path,
                    collection_name="agent_knowledge",
                ),
            )
        return self._vector_store

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        knowledge_text = _as_text(kwargs.get("knowledge_text"))
        tags = _as_tags(kwargs.get("tags"))

        try:
            store = self._get_vector_store()
            chunk_id = f"knowledge_{uuid.uuid4().hex[:8]}"
            metadata: dict[str, object] = {"type": "agent_knowledge"}
            if tags:
                metadata["tags"] = ", ".join(tags)

            chunk: dict[str, object] = {"id": chunk_id, "text": knowledge_text, "metadata": metadata}
            store.upsert_chunks([chunk])
            return f"Successfully stored knowledge. ID: {chunk_id}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error storing knowledge: {e}"


@final
class SearchKnowledgeTool(BaseTool):
    """벡터 저장소에서 지식을 검색합니다."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🧠"
    tags: list[str] = ["memory", "knowledge", "search", "retrieve"]
    _name: str
    _description: str
    _schema: ToolSchema
    project_root: str
    _vector_store: _VectorStoreLike | None

    def __init__(self, project_root: str | None = None):
        """Initialize the SearchKnowledgeTool.

        Args:
            project_root (str): str project root.

        """
        super().__init__()
        self._name = "search_knowledge"
        self._description = (
            "Search the project's long-term memory for previously stored knowledge using semantic search."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or concept to look for.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        }
        self.project_root = project_root or os.getcwd()
        self._vector_store = None

    def _get_vector_store(self) -> _VectorStoreLike:
        if not self._vector_store:
            from antigravity_k.engine.vector_store import VectorStore

            db_path = os.path.join(self.project_root, ".antigravity", "vault_data")
            self._vector_store = cast(
                _VectorStoreLike,
                VectorStore(
                    persist_directory=db_path,
                    collection_name="agent_knowledge",
                ),
            )
        return self._vector_store

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> ToolSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        query = _as_text(kwargs.get("query"))
        max_results = _as_positive_int(kwargs.get("max_results"), 5)

        try:
            store = self._get_vector_store()
            results = store.search(query, n_results=max_results)

            if not results:
                return "No relevant knowledge found."

            formatted = ["Found knowledge:"]
            for r in results:
                formatted.append(f"- {r['text']}")

            return "\n".join(formatted)
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error searching knowledge: {e}"
