"""Artifact Tools module."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import TypeAlias, cast, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

JsonMap: TypeAlias = dict[str, object]


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_map(value: object) -> JsonMap:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


class WriteArtifactTool(BaseTool):
    """지정된 프로젝트 폴더 내부의 artifacts/ 디렉토리에 마크다운 아티팩트를 저장합니다."""

    category: ToolCategory = ToolCategory.FILE_IO
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "📄"
    tags: list[str] = ["artifact", "markdown", "write", "document", "plan"]

    def __init__(self, project_root: str | None = None):
        """Initialize the WriteArtifactTool.

        Args:
            project_root (str): str project root.

        """
        super().__init__()
        self._name: str = "write_artifact"
        self._description: str = "Write a structured markdown artifact (like an implementation plan, review report, or task list). This will save the"  # noqa: E501
        "artifact directly into the 'artifacts/' directory of the current project. When in Planning Mode, set RequestFeedback to true to pause and ask for user approval."  # noqa: E501
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "artifact_name": {
                    "type": "string",
                    "description": "Name of the artifact file (e.g., 'implementation_plan.md', 'review_report.md').",
                },
                "content": {
                    "type": "string",
                    "description": "The markdown content of the artifact.",
                },
                "artifact_type": {
                    "type": "string",
                    "description": "Backward-compatible artifact type hint such as html, markdown, or react.",
                },
                "ArtifactMetadata": {
                    "type": "object",
                    "description": "Metadata for the artifact, used for Planning Mode and task tracking.",
                    "properties": {
                        "ArtifactType": {
                            "type": "string",
                            "enum": [
                                "implementation_plan",
                                "walkthrough",
                                "task",
                                "other",
                            ],
                            "description": "Type of artifact.",
                        },
                        "RequestFeedback": {
                            "type": "boolean",
                            "description": "Set to true to request user feedback/approval on this artifact.",
                        },
                        "Summary": {
                            "type": "string",
                            "description": "Detailed multi-line summary of the artifact file.",
                        },
                    },
                    "required": ["ArtifactType", "Summary"],
                },
            },
            "required": ["artifact_name", "content"],
        }
        self.project_root: str = project_root or os.getcwd()

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
    def parameters_schema(self) -> Mapping[str, object]:
        """Parameters Schema.

        Returns:
            Mapping[str, object]: The tool parameter schema.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> object:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            object: The execution result.

        """
        artifact_name = _as_text(kwargs.get("artifact_name", ""))
        content = _as_text(kwargs.get("content", ""))
        artifact_type = _as_text(kwargs.get("artifact_type", "generic"), "generic")

        # Ensure name is safe
        artifact_name = os.path.basename(artifact_name)

        # Add extension if not present based on type
        if "." not in artifact_name:
            if artifact_type in ["html", "react"]:
                artifact_name += ".html"
            else:
                artifact_name += ".md"

        try:
            artifacts_dir = os.path.join(self.project_root, "artifacts")
            os.makedirs(artifacts_dir, exist_ok=True)

            file_path = os.path.join(artifacts_dir, artifact_name)

            with open(file_path, "w", encoding="utf-8") as f:
                _ = f.write(content)

            # This special format will be parsed by the frontend to render the artifact UI
            metadata = _as_map(kwargs.get("ArtifactMetadata", {}))
            req_feedback = bool(metadata.get("RequestFeedback", False))
            art_type = _as_text(metadata.get("ArtifactType"), artifact_type)

            result_str = (
                f"[ARTIFACT GENERATED: {artifact_name} (Type: {art_type})]\nSuccessfully saved to {file_path}. "
            )
            if req_feedback:
                result_str += "\n[PLANNING_MODE: WAITING_FOR_USER_APPROVAL]"

            return result_str
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error generating artifact: {e}"
