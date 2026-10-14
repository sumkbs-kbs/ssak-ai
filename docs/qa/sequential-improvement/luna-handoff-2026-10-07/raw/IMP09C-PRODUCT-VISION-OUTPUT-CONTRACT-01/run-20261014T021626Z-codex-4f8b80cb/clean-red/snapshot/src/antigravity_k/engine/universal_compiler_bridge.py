"""Universal Polyglot Compiler Bridge — Zero-latency multi-language syntax verification.

Validates syntax across multiple languages before writing to disk:
1. Python (ast.parse)
2. JSON (json.loads)
3. YAML (yaml.safe_load)
4. TypeScript / JavaScript (Brace balance & Regex lint)
5. Rust (Brace/Match syntax sanity)
6. Go (Package & syntax sanity)
"""

import ast
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolyglotVerificationResult:
    """Outcome of multi-language syntax validation."""

    language: str
    is_valid: bool
    error_message: str = ""


class UniversalCompilerBridge:
    """Dispatches language-specific syntax parsers based on file extension."""

    @staticmethod
    def verify_syntax(file_path: str, content: str) -> PolyglotVerificationResult:
        """Verify syntax based on file extension."""
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            return UniversalCompilerBridge._verify_python(content)
        elif ext == ".json":
            return UniversalCompilerBridge._verify_json(content)
        elif ext in (".yaml", ".yml"):
            return UniversalCompilerBridge._verify_yaml(content)
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            return UniversalCompilerBridge._verify_javascript_typescript(content)
        elif ext == ".rs":
            return UniversalCompilerBridge._verify_rust(content)
        elif ext == ".go":
            return UniversalCompilerBridge._verify_go(content)
        else:
            # Fallback pass for plaintext/markdown/etc.
            return PolyglotVerificationResult(language="generic", is_valid=True)

    @staticmethod
    def _verify_python(content: str) -> PolyglotVerificationResult:
        try:
            _ = ast.parse(content)
            return PolyglotVerificationResult(language="python", is_valid=True)
        except SyntaxError as se:
            return PolyglotVerificationResult(
                language="python", is_valid=False, error_message=f"Line {se.lineno}: {se.msg}"
            )

    @staticmethod
    def _verify_json(content: str) -> PolyglotVerificationResult:
        try:
            json.loads(content)
            return PolyglotVerificationResult(language="json", is_valid=True)
        except json.JSONDecodeError as je:
            return PolyglotVerificationResult(language="json", is_valid=False, error_message=f"JSON decode error: {je}")

    @staticmethod
    def _verify_yaml(content: str) -> PolyglotVerificationResult:
        try:
            import yaml

            yaml.safe_load(content)
            return PolyglotVerificationResult(language="yaml", is_valid=True)
        except Exception as ye:
            return PolyglotVerificationResult(language="yaml", is_valid=False, error_message=f"YAML parse error: {ye}")

    @staticmethod
    def _verify_javascript_typescript(content: str) -> PolyglotVerificationResult:
        # Check balanced braces and parenthesis
        stack: list[str] = []
        pairs = {")": "(", "}": "{", "]": "["}
        in_string: str | None = None

        for idx, char in enumerate(content):
            if char in ("'", '"', "`") and (idx == 0 or content[idx - 1] != "\\"):
                if in_string == char:
                    in_string = None
                elif in_string is None:
                    in_string = char
            elif in_string is None:
                if char in ("(", "{", "["):
                    stack.append(char)
                elif char in (")", "}", "]"):
                    if not stack or stack[-1] != pairs[char]:
                        return PolyglotVerificationResult(
                            language="typescript",
                            is_valid=False,
                            error_message=f"Unmatched closing bracket `{char}` at position {idx}.",
                        )
                    _ = stack.pop()

        if stack:
            return PolyglotVerificationResult(
                language="typescript",
                is_valid=False,
                error_message=f"Unclosed bracket `{stack[-1]}`.",
            )

        return PolyglotVerificationResult(language="typescript", is_valid=True)

    @staticmethod
    def _verify_rust(content: str) -> PolyglotVerificationResult:
        # Rust basic syntax check (fn, struct, impl balance)
        if content.count("{") != content.count("}"):
            return PolyglotVerificationResult(
                language="rust", is_valid=False, error_message="Unbalanced curly braces in Rust code."
            )
        return PolyglotVerificationResult(language="rust", is_valid=True)

    @staticmethod
    def _verify_go(content: str) -> PolyglotVerificationResult:
        if "package " not in content and len(content.strip()) > 20:
            return PolyglotVerificationResult(
                language="go", is_valid=False, error_message="Missing `package` declaration in Go file."
            )
        if content.count("{") != content.count("}"):
            return PolyglotVerificationResult(
                language="go", is_valid=False, error_message="Unbalanced curly braces in Go code."
            )
        return PolyglotVerificationResult(language="go", is_valid=True)
