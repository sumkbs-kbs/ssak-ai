"""Init Deep Tool module."""

import logging
import os
from pathlib import Path
from typing import override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)


class InitDeepContextTool(BaseTool):
    """InitDeepContextTool: Crawls a workspace and automatically generates hierarchical `AGENTS.md`.

    files to keep agent context window localized and prevent bloating.
    """

    category: ToolCategory = ToolCategory.CODE_EXEC
    render_in: RenderIn = RenderIn.TOOLBAR
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "🧠"
    tags: list[str] = ["context", "agents.md", "init", "deep"]

    def __init__(self):
        """Initialize the InitDeepContextTool."""
        super().__init__()
        self._name: str = "init_deep_context"
        self._description: str = (
            "Generates hierarchical AGENTS.md files across the project directories to provide localized context "
            "for AI agents, preventing context bloat."
        )
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "root_path": {
                    "type": "string",
                    "description": "The root path to start generating AGENTS.md files from.",
                },
            },
            "required": ["root_path"],
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
    def parameters_schema(self) -> dict[str, object]:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        raw_root_path = kwargs.get("root_path")
        root_path = raw_root_path if isinstance(raw_root_path, str) else ""
        if not root_path or not os.path.exists(root_path):
            return f"Error: Invalid root path {root_path}"

        ignore_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            ".antigravity",
            "dist",
            "build",
        }
        generated_count = 0

        try:
            for current_dir, dirs, files in os.walk(root_path):
                # Filter out ignored directories
                dirs[:] = [d for d in dirs if d not in ignore_dirs]

                # We want to create an AGENTS.md in the current directory
                # if it contains code files (e.g., .py, .js, .ts, .go, .rs, etc.)
                # For simplicity, we just create it if there are any non-hidden files.
                valid_files = [f for f in files if not f.startswith(".")]

                if valid_files:
                    agents_file = Path(current_dir) / "AGENTS.md"
                    if not agents_file.exists():
                        relative_path = os.path.relpath(current_dir, root_path)
                        if relative_path == ".":
                            relative_path = "root"

                        content = f"""# {relative_path.capitalize()} Context

This is an auto-generated AGENTS.md file for the `{relative_path}` directory.
Agents working in this directory should read this file to understand local architectural rules and context.

## Local Guidelines
- Add specific business logic rules here.
- Document cross-file dependencies within this module.
"""
                        with agents_file.open("w", encoding="utf-8") as file:
                            _ = file.write(content)
                        generated_count += 1

            return f"Successfully generated {generated_count} AGENTS.md files starting from {root_path}."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error generating deep context: {e}"
