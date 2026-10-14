from __future__ import annotations

from pathlib import Path
from typing import ClassVar, final, override

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from antigravity_k.engine.context_artifact_store import ContextArtifactStore
from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory


@final
class ContextArtifactLookupError(LookupError):
    def __init__(self, ref_id: str, chunk_index: int):
        self.ref_id: str = ref_id
        self.chunk_index: int = chunk_index
        super().__init__(f"Artifact chunk not found: {ref_id}#{chunk_index}")


class _ContextArtifactReadResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ref_id: str
    chunk_index: int
    chunk_count: int
    start_line: int
    end_line: int
    content: str


class _ContextArtifactReadRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ref_id: str = Field(min_length=1)
    chunk_index: int = Field(default=0, ge=0)


@final
class ReadContextArtifactTool(BaseTool):
    """Read one bounded chunk from a tool result stored outside the model context."""

    category = ToolCategory.SEARCH
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.SAFE
    icon = "📚"
    tags = ["context", "artifact", "chunk", "resume", "read"]

    def __init__(self, project_root: str | Path):
        self._store = ContextArtifactStore(
            Path(project_root) / ".antigravity" / "context_artifacts",
        )

    @property
    @override
    def name(self) -> str:
        return "read_context_artifact"

    @property
    @override
    def description(self) -> str:
        return (
            "Read one zero-based chunk of a large prior tool result using its "
            "context_artifact_ref. Use chunk_index 0 first, then request only the next "
            "chunks needed for the task."
        )

    @property
    @override
    def parameters_schema(self) -> dict[str, JsonValue]:
        return {
            "type": "object",
            "properties": {
                "ref_id": {
                    "type": "string",
                    "description": "The context_artifact_ref from a truncated tool response.",
                },
                "chunk_index": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Zero-based bounded chunk to retrieve.",
                },
            },
            "required": ["ref_id"],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        request = _ContextArtifactReadRequest.model_validate(kwargs)
        chunk = self._store.read_chunk(request.ref_id, request.chunk_index)
        if chunk is None:
            raise ContextArtifactLookupError(request.ref_id, request.chunk_index)
        return _ContextArtifactReadResponse(
            ref_id=chunk.ref_id,
            chunk_index=chunk.index,
            chunk_count=chunk.chunk_count,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
        ).model_dump_json()
