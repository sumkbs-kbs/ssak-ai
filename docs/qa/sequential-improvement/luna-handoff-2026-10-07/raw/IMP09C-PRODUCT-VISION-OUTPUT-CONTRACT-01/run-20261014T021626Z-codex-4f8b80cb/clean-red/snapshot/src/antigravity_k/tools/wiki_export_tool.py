"""Wiki Export Tool module."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from typing import TypeAlias, cast, override

from antigravity_k.tools.base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

JsonMap: TypeAlias = dict[str, object]


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _as_map(value: object) -> JsonMap:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items()}


class WikiExportTool(BaseTool):
    """WikiExportTool: 에이전트가 학습한 내용이나 아키텍처 결정을.

    사용자의 로컬 지식베이스(Wiki)에 마크다운 파일로 내보냅니다.
    """

    category: ToolCategory = ToolCategory.FILE_IO
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "📝"
    tags: list[str] = ["wiki", "knowledge", "export", "markdown", "obsidian"]

    def __init__(self):
        """Initialize the WikiExportTool."""
        super().__init__()
        self._name: str = "export_to_wiki"
        self._description: str = (
            "Export structured knowledge, troubleshooting logs, or architectural "
            "decisions to a Markdown file in the user's Wiki directory."
        )
        self._schema: JsonMap = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the wiki page.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tags for the YAML frontmatter (e.g., ['architecture', 'troubleshooting']).",
                },
                "content": {
                    "type": "string",
                    "description": "The full Markdown content of the wiki page.",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional specific filename (without .md). If not provided, title will be used.",
                },
            },
            "required": ["title", "content"],
        }

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
        title = _as_text(kwargs.get("title"))
        tags = _as_string_list(kwargs.get("tags", []))
        content = _as_text(kwargs.get("content"))
        filename_raw = _as_text(kwargs.get("filename"))

        # Create safe filename
        if not filename_raw:
            filename_raw = title.replace(" ", "_").replace("/", "-")

        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_filename = f"{date_str}_{filename_raw}.md"

        # Determine target directory
        # 1. Try to read from config.yaml if available
        project_root = os.getcwd()
        wiki_dir = os.path.join(
            project_root,
            "wiki_exports",
        )  # Default to workspace local folder to avoid permission errors

        try:
            import yaml

            config_path = os.path.join(project_root, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    config = _as_map(cast(object, yaml.safe_load(f)))
                    configured_dir = _as_text(config.get("wiki_dir"))
                    if configured_dir:
                        wiki_dir = configured_dir
        except Exception:
            logger.exception("Could not read wiki_dir from config")

        # Fallback if the configured absolute path isn't writable or doesn't exist
        if not os.path.exists(wiki_dir):
            try:
                os.makedirs(wiki_dir, exist_ok=True)
            except OSError:
                logger.exception("Unhandled exception")
                wiki_dir = project_root

        target_path = os.path.join(wiki_dir, safe_filename)

        # Build YAML Frontmatter
        frontmatter = f"---\ntitle: {title}\n"
        if tags:
            tags_str = ", ".join(tags)
            frontmatter += f"tags: [{tags_str}]\n"
        frontmatter += f"date: {date_str}\n---\n\n"

        full_content = frontmatter + content

        try:
            with open(target_path, "w", encoding="utf-8") as f:
                _ = f.write(full_content)
            return f"✅ Successfully exported knowledge to Wiki at: {target_path}"
        except OSError:
            # Fallback to root if permission denied
            fallback_path = os.path.join(project_root, safe_filename)
            try:
                with open(fallback_path, "w", encoding="utf-8") as f:
                    _ = f.write(full_content)
                return f"⚠️ Permission denied to write to {wiki_dir}. Saved to fallback path: {fallback_path}"
            except OSError as e2:
                logger.exception("Unhandled exception")
                return f"❌ Failed to export wiki: {e2}"
