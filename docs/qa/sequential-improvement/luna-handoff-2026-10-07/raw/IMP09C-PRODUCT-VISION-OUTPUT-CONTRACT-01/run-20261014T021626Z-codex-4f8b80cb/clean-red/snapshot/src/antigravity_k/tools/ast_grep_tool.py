import logging
import subprocess
from collections.abc import Mapping
from typing import override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)


class ASTGrepTool(BaseTool):
    """
    ASTGrepTool: Leverages the `ast-grep` (sg) CLI for semantic, AST-based
    code search and structural replacement, heavily reducing regex fragility.
    """

    category: ToolCategory = ToolCategory.CODE_EXEC
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.MEDIUM
    icon: str = "🌲"
    tags: list[str] = ["ast", "grep", "search", "replace", "refactor"]

    def __init__(self):
        super().__init__()
        self._name: str = "ast_grep"
        self._description: str = "Performs structural code search or replacement using ast-grep (sg). Uses AST patterns instead of raw regex."  # noqa: E501
        self._schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The AST pattern to search for (e.g., 'def $FUNC($ARGS): $BODY').",
                },
                "lang": {"type": "string", "description": "The programming language (e.g., python, typescript, rust)."},
                "replace": {
                    "type": "string",
                    "description": "Optional: The replacement pattern. If omitted, performs a dry-run search.",
                },
                "target_dir": {
                    "type": "string",
                    "description": "The directory or file to run the search against.",
                    "default": ".",
                },
            },
            "required": ["pattern", "lang"],
        }

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def description(self) -> str:
        return self._description

    @property
    @override
    def parameters_schema(self) -> Mapping[str, object]:
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        pattern_value = kwargs.get("pattern")
        lang_value = kwargs.get("lang")
        replace_value = kwargs.get("replace")
        target_value = kwargs.get("target_dir", ".")
        pattern = pattern_value if isinstance(pattern_value, str) else ""
        lang = lang_value if isinstance(lang_value, str) else ""
        replace = replace_value if isinstance(replace_value, str) else ""
        target_dir = target_value if isinstance(target_value, str) else "."

        if not pattern or not lang:
            return "Error: Both 'pattern' and 'lang' are required."

        # Base ast-grep command
        cmd: list[str] = ["sg", "-p", pattern, "-l", lang]

        if replace:
            # Add replace flag (in-place modification can be dangerous, so usually we need hits first,
            # but for this tool we allow in-place via -U if requested)
            cmd.extend(["-r", replace, "-U"])

        cmd.append(target_dir)

        try:
            # We assume `ast-grep` (sg) is installed in the environment.
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0 and result.stderr:
                return f"ast-grep execution failed:\n{result.stderr}"

            output = result.stdout
            if not output:
                return "No matches found."

            return output
        except FileNotFoundError:
            return "Error: 'sg' (ast-grep) command not found. Please install ast-grep (e.g., `npm install -g @ast-grep/cli` or `brew install ast-grep`)."  # noqa: E501
        except subprocess.TimeoutExpired:
            return "Error: ast-grep execution timed out."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error executing ast-grep: {e}"
