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
    # r36: a write tool. SAFE made PermissionGate auto-ALLOW, contradicting security_policy
    # (write_artifact: ASK_EACH_TIME). MEDIUM = same class as write_file -> PROMPT unless auto-pilot.
    risk_level: RiskLevel = RiskLevel.MEDIUM
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
        # r36: no silent cwd fallback. Root = request/task-bound project root, else explicit root.
        self._explicit_root: str | None = project_root
        self.project_root: str = project_root or ""

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
            from antigravity_k.tools.tool_path import effective_project_root

            bound = None
            try:
                from antigravity_k.api.project_binding import get_request_project_root

                bound = get_request_project_root()
            except Exception:
                bound = None
            if not bound and not self._explicit_root:
                return "Error: write_artifact has no bound project root; refusing to write into the process cwd."
            root = effective_project_root(self._explicit_root)
            artifacts_dir = os.path.join(root, "artifacts")
            os.makedirs(artifacts_dir, exist_ok=True)

            file_path = os.path.join(artifacts_dir, artifact_name)

            # r35: the real app write path. Same journal + race-free write as ArtifactEngine:
            # intent/executed records per (task, name), dir_fd-relative atomic replace (no symlink
            # follow), resume skips a completed write, an unknown state is HELD (never auto-rerun).
            from antigravity_k.engine import tool_execution_journal as tej

            outcome, exec_id = tej.journaled_write(artifacts_dir, file_path, content)
            if outcome == "held_unknown":
                return (
                    f"Error: artifact '{artifact_name}' is in an unknown state (exec {exec_id}); "
                    "the write was NOT repeated. Human review required."
                )
            if outcome == "skipped_completed":
                return (
                    f"[ARTIFACT ALREADY WRITTEN: {artifact_name}] completed earlier in this task "
                    f"(exec {exec_id}); not written again."
                )

            # This special format will be parsed by the frontend to render the artifact UI
            metadata = _as_map(kwargs.get("ArtifactMetadata", {}))
            req_feedback = bool(metadata.get("RequestFeedback", False))
            art_type = _as_text(metadata.get("ArtifactType"), artifact_type)

            result_str = (
                f"[ARTIFACT GENERATED: {artifact_name} (Type: {art_type})]\nSuccessfully saved to {file_path}. "
            )
            # r42: verified facts come from re-reading the written file (no symlink follow).
            try:
                import hashlib

                fd = os.open(file_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as fh:
                    written = fh.read()
                result_str += (
                    f"\n[VERIFIED FILE] sha256={hashlib.sha256(written).hexdigest()} bytes={len(written)} "
                    "(computed from the written file; quote these values, do not estimate)"
                )
            except OSError:
                result_str += "\n[VERIFIED FILE] unavailable (file could not be re-read); do not state a hash or size."
            if req_feedback:
                result_str += "\n[PLANNING_MODE: WAITING_FOR_USER_APPROVAL]"

            return result_str
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error generating artifact: {e}"
