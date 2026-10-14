"""FileTools — 파일 I/O 도구 4종.

==============================
Claw Code의 파일 도구 아키텍처 이식:
- write_file   : 새 파일 생성 (디렉토리 자동 생성)
- edit_file     : diff 기반 정밀 편집 (old_str → new_str)
- glob_search   : 파일 패턴 검색 (수정 시간순)
- grep_search   : 코드 내 텍스트/정규식 검색
"""

import glob as glob_module
import logging
import os
import re
from dataclasses import replace
from typing import Any, TypeAlias, TypedDict, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory

logger = logging.getLogger(__name__)

ToolValue: TypeAlias = object
ToolSchema: TypeAlias = dict[str, Any]  # pyright: ignore[reportExplicitAny]


class _FileInfo(TypedDict):
    path: str
    size: int
    modified: float


@final
class WriteFileTool(BaseTool):
    """새 파일 생성 또는 덮어쓰기. 디렉토리가 없으면 자동 생성."""

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.LOW
    icon = "📝"
    tags = ["file", "write", "create"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the WriteFileTool."""
        super().__init__()
        self._name = "write_file"
        self._description = (
            "Creates a new file or overwrites an existing file with the given content. "
            "Parent directories are created automatically if they don't exist."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path for the file.",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
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
        file_path = cast(str, kwargs.get("file_path", ""))
        content = cast(str, kwargs.get("content", ""))

        try:
            dir_path = os.path.dirname(file_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                _ = f.write(content)

            return f"Successfully wrote {len(content)} chars to {file_path}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error writing file: {e}"


@final
class CreateDirectoryTool(BaseTool):
    """새로운 디렉토리를 생성합니다."""

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.LOW
    icon = "📁"
    tags = ["file", "directory", "mkdir", "create"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the CreateDirectoryTool."""
        super().__init__()
        self._name = "create_directory"
        self._description = (
            "Creates a new directory at the specified path. "
            "Parent directories are created automatically if they don't exist."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "Absolute or relative path for the new directory.",
                },
            },
            "required": ["dir_path"],
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
        dir_path = cast(str, kwargs.get("dir_path", ""))

        try:
            os.makedirs(dir_path, exist_ok=True)
            return f"Successfully created directory: {dir_path}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error creating directory: {e}"


@final
class EditFileTool(BaseTool):
    """Claw Code 스타일 diff 기반 정밀 편집.

    파일에서 old_str을 찾아 new_str로 교체합니다.
    """

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.LOW
    icon = "✂️"
    tags = ["file", "edit", "diff", "replace"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the EditFileTool."""
        super().__init__()
        self._name = "edit_file"
        self._description = (
            "Makes a targeted edit to a file by replacing an exact text match (old_str) "
            "with new content (new_str). Use for precise, surgical edits. "
            "The old_str must match exactly, including whitespace and indentation."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_str": {
                    "type": "string",
                    "description": "Exact text to find and replace. Must match precisely.",
                },
                "new_str": {
                    "type": "string",
                    "description": "New text to replace old_str with.",
                },
            },
            "required": ["file_path", "old_str", "new_str"],
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
        file_path = cast(str, kwargs.get("file_path", ""))
        old_str = cast(str, kwargs.get("old_str", ""))
        new_str = cast(str, kwargs.get("new_str", ""))

        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # 1단계: 정확 매치 (기존 동작 유지)
            count = content.count(old_str)
            if count == 1:
                new_content = content.replace(old_str, new_str, 1)
                with open(file_path, "w", encoding="utf-8") as f:
                    _ = f.write(new_content)
                old_lines = old_str.count("\n") + 1
                new_lines = new_str.count("\n") + 1
                return (
                    f"Successfully edited {file_path}: "
                    f"replaced {old_lines} lines with {new_lines} lines "
                    f"({len(old_str)} → {len(new_str)} chars)"
                )
            if count > 1:
                return (
                    f"Error: old_str found {count} times in {file_path}. "
                    f"Please provide a more unique match to avoid ambiguity."
                )

            # 2단계: 퍼지 매치 (정확 매치 실패 시 — 작업 5)
            # 공백/들여쓰기 차이를 무시하고 매칭 시도
            matched_content, match_info = self._fuzzy_replace(content, old_str, new_str)
            if matched_content is not None:
                with open(file_path, "w", encoding="utf-8") as f:
                    _ = f.write(matched_content)
                return (
                    f"Successfully edited {file_path} (fuzzy match): "
                    f"{match_info}. "
                    f"({len(old_str)} → {len(new_str)} chars)"
                )

            # 3단계: 매치 실패 — 유사 라인 제안으로 힌트 개선
            hint = self._build_no_match_hint(content, old_str)
            return hint

        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error editing file: {e}"

    @staticmethod
    def _fuzzy_replace(content: str, old_str: str, new_str: str) -> tuple[str | None, str]:
        """공백 정규화 기반 퍼지 매치로 교체를 시도합니다.

        정확 매치가 실패했을 때 호출됩니다:
          1. 라인별 앞뒤 공백 + 연속 공백 축소 정규화로 매칭
          2. 라인 기반 폴백 (첫/마지막 라인으로 블록 특정)

        Returns:
            (new_content, match_description) — 매치 실패 시 (None, "").
        """
        import re

        def normalize(text: str) -> str:
            # 각 라인 trim + 연속 공백을 단일 공백으로 + 빈 라인 제거
            lines = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()]
            return "\n".join(line for line in lines if line)

        norm_old = normalize(old_str)

        # 방법 A: 정규화된 old_str을 정규화된 content에서 찾아 원본 위치 역추적
        content_lines = content.splitlines(keepends=True)
        norm_content_lines = [re.sub(r"\s+", " ", line.strip()) for line in content_lines]

        # 정규화된 old_str의 라인 수
        norm_old_lines = [ln for ln in norm_old.split("\n") if ln]
        if not norm_old_lines:
            return None, ""

        # 슬라이딩 윈도우로 정규화된 content에서 매칭
        old_len = len(norm_old_lines)
        matches: list[int] = []
        for i in range(len(norm_content_lines) - old_len + 1):
            window = norm_content_lines[i : i + old_len]
            if window == norm_old_lines:
                matches.append(i)

        if len(matches) == 1:
            # 단일 매치 — 원본 라인 교체 (들여쓰기 보존)
            start_idx = matches[0]
            end_idx = start_idx + old_len
            original_block = "".join(content_lines[start_idx:end_idx])

            # 기준 들여쓰기: 원본 첫 라인의 들여쓰기
            orig_first_line = content_lines[start_idx]
            base_indent_match = re.match(r"(\s*)", orig_first_line)
            base_indent = base_indent_match.group(1) if base_indent_match else ""

            # new_str의 들여쓰기 정규화 후 원본 기준 들여쓰기 재적용.
            # new_str의 첫 라인에서 상대적 들여쓰기를 추출하고 base_indent에 더함.
            new_raw_lines = new_str.splitlines()
            if new_raw_lines:
                first_new = new_raw_lines[0]
                first_new_indent_match = re.match(r"(\s*)", first_new)
                first_new_indent = first_new_indent_match.group(1) if first_new_indent_match else ""
                # 첫 라인이 base_indent와 같거나 더 깊으면 상대 들여쓰기 계산
                new_lines_adjusted: list[str] = []
                for j, line in enumerate(new_raw_lines):
                    line_indent_match = re.match(r"(\s*)", line)
                    line_indent = line_indent_match.group(1) if line_indent_match else ""
                    content_part = line[len(line_indent) :]
                    # new_str의 들여쓰기가 없거나 첫 라인과 같으면 base_indent 적용,
                    # 그 외에는 new_str의 원래 들여쓰기 유지 (상대적 깊이 보존)
                    if not line_indent or j > 0 and line_indent == first_new_indent:
                        new_lines_adjusted.append(base_indent + content_part)
                    else:
                        new_lines_adjusted.append(line)
                replacement = "\n".join(new_lines_adjusted)
            else:
                replacement = new_str

            # 줄바꿈 보존 (원본 라인이 keepends이므로)
            if original_block.endswith("\n") and not replacement.endswith("\n"):
                replacement += "\n"
            offset = sum(len(ln) for ln in content_lines[:start_idx])
            end_offset = sum(len(ln) for ln in content_lines[:end_idx])
            new_content = content[:offset] + replacement + content[end_offset:]
            return new_content, f"normalized {old_len} lines (whitespace-tolerant, indent preserved)"

        # 방법 B: 단일 라인 old_str인 경우 부분 문자열 유사도
        if "\n" not in old_str.strip():
            import difflib

            # content에서 old_str과 가장 유사한 라인 찾기
            target = normalize(old_str)
            candidates: list[tuple[float, int]] = []
            for i, nline in enumerate(norm_content_lines):
                if nline and target:
                    ratio = difflib.SequenceMatcher(None, target, nline).ratio()
                    if ratio >= 0.85:
                        candidates.append((ratio, i))

            if len(candidates) == 1:
                _, idx = candidates[0]
                original_line = content_lines[idx]
                # 원본 들여쓰기 보존
                indent = re.match(r"(\s*)", original_line)
                indent_str = indent.group(1) if indent else ""
                replacement = indent_str + new_str.strip() + ("\n" if original_line.endswith("\n") else "")
                start_off = sum(len(ln) for ln in content_lines[:idx])
                end_off = sum(len(ln) for ln in content_lines[: idx + 1])
                new_content = content[:start_off] + replacement + content[end_off:]
                return new_content, f"similar line at {idx + 1} (similarity match)"

        return None, ""

    @staticmethod
    def _build_no_match_hint(content: str, old_str: str) -> str:
        """매치 실패 시 유사 라인을 제안하는 개선된 힌트를 생성합니다."""
        import difflib
        import re

        lines = old_str.strip().split("\n")
        hint_line = lines[0][:60] if lines else ""
        base_msg = f"Error: old_str not found in file. No exact or fuzzy match for: '{hint_line}...'. "

        # content에서 old_str 첫 라인과 가장 유사한 라인 3개 제안
        if not lines or not lines[0].strip():
            return base_msg + "Verify whitespace/indentation matches exactly."

        target = re.sub(r"\s+", " ", lines[0].strip())
        content_lines = content.splitlines()
        scored: list[tuple[float, int, str]] = []
        for i, cline in enumerate(content_lines):
            norm = re.sub(r"\s+", " ", cline.strip())
            if norm and target:
                ratio = difflib.SequenceMatcher(None, target, norm).ratio()
                if ratio >= 0.5:
                    scored.append((ratio, i + 1, cline.strip()[:70]))

        if scored:
            scored.sort(reverse=True)
            suggestions = scored[:3]
            sugg_str = "; ".join(f"L{n}: '{t}'" for _, n, t in suggestions)
            return base_msg + f"Did you mean one of these? {sugg_str}"

        return base_msg + "Verify whitespace/indentation matches exactly."


@final
class MultiReplaceFileContentTool(BaseTool):
    """한 파일에서 여러 개의 비연속적인 텍스트 영역을 정밀하게(라인 기반으로) 찾아 바꿉니다."""

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.MEDIUM
    icon = "🛠️"
    tags = ["file", "edit", "multi", "replace", "refactor"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the MultiReplaceFileContentTool."""
        super().__init__()
        self._name = "multi_replace_file_content"
        self._description = (
            "Edit a file by replacing multiple non-contiguous blocks of text at once. "
            "Pass an array of 'ReplacementChunks'. For each chunk, specify StartLine, EndLine, TargetContent,"
            "and ReplacementContent. "
            "This ensures exact matching and avoids ambiguous replacements."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to modify.",
                },
                "ReplacementChunks": {
                    "type": "array",
                    "description": "List of replacement chunks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "StartLine": {"type": "integer"},
                            "EndLine": {"type": "integer"},
                            "TargetContent": {
                                "type": "string",
                                "description": "Exact text to find.",
                            },
                            "ReplacementContent": {
                                "type": "string",
                                "description": "Text to replace it with.",
                            },
                            "old_str": {"type": "string"},  # Backward compatibility
                            "new_str": {"type": "string"},
                        },
                        "required": ["TargetContent", "ReplacementContent"],
                    },
                },
            },
            "required": ["file_path"],
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
        file_path = cast(str, kwargs.get("file_path", ""))
        # Backward compatibility check
        chunks = cast(list[dict[str, object]], kwargs.get("ReplacementChunks", kwargs.get("chunks", [])))

        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            lines = content.splitlines(True)  # Keep newlines

            # To avoid line number shifting issues, we should process from bottom to top or just use text replace if Start/End are used for scoping  # noqa: E501

            for idx, chunk in enumerate(chunks):
                # Backwards compatible
                target = cast(str, chunk.get("TargetContent", chunk.get("old_str", "")))
                replacement = cast(str, chunk.get("ReplacementContent", chunk.get("new_str", "")))
                start_line = cast(int, chunk.get("StartLine", 1))
                end_line = cast(int, chunk.get("EndLine", len(lines)))

                # If precise lines are given, scope the count check to those lines
                # Convert 1-indexed to 0-indexed
                start_idx = max(0, start_line - 1)
                end_idx = min(len(lines), end_line)

                scoped_text = "".join(lines[start_idx:end_idx])

                count = scoped_text.count(target)
                if count == 0:
                    return (
                        f"Error on chunk {idx + 1}: TargetContent not found in lines {start_line}-{end_line}. Aborting."
                    )
                if count > 1:
                    return (
                        f"Error on chunk {idx + 1}: TargetContent found {count} times in "
                        f"lines {start_line}-{end_line}. Be more specific. "
                        f"Aborting."
                    )

                new_scoped_text = scoped_text.replace(target, replacement, 1)
                lines[start_idx:end_idx] = [new_scoped_text]

                with open(file_path, "w", encoding="utf-8") as f:
                    _ = f.write("".join(lines))

            return f"Successfully applied {len(chunks)} replacements to {file_path}."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error applying multi-replace: {e}"


@final
class ApplyPatchTool(BaseTool):
    """apply_patch 포맷을 파싱하여 다중 파일에 정밀 패치 적용 (P0-1).

    Aider/Codex 스타일의 structured patch를 지원합니다.
    컨텍스트 라인 기반 정확 매칭 + 퍼지 폴백으로 신뢰성 높은 코드 수정.
    단일 호출로 여러 파일의 여러 hunk를 한번에 적용할 수 있습니다.
    """

    category = ToolCategory.FILE_IO
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.MEDIUM
    icon = "🔧"
    tags = ["file", "edit", "patch", "diff", "multi-file"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the ApplyPatchTool."""
        super().__init__()
        self._name = "apply_patch"
        self._description = (
            "Apply a structured patch (apply_patch format) to one or more files. "
            "Supports adding new files, updating existing files with context-based hunks, "
            "and deleting files. More reliable than edit_file for complex multi-line changes. "
            "Format:\\n"
            "*** Begin Patch\\n"
            "*** Update File: path/to/file.py\\n"
            "@@ context line\\n"
            "-old line\\n"
            "+new line\\n"
            "*** End Patch"
        )
        self._schema = {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The full apply_patch format text to apply.",
                },
            },
            "required": ["patch"],
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
    def parameters_schema(self) -> ToolSchema:
        return self._schema

    @override
    def execute(self, **kwargs: ToolValue) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        patch_text = cast(str, kwargs.get("patch", ""))
        if not patch_text.strip():
            return "Error: patch is empty"

        from antigravity_k.engine.diff_engine import DiffApplyEngine

        engine = DiffApplyEngine()

        try:
            patches = engine.parse_apply_patch(patch_text)
        except Exception as e:
            logger.exception("Patch parsing failed")
            return f"Error parsing patch: {e}"

        if not patches:
            return "Error: no file patches found in input"

        from antigravity_k.tools.tool_path import (
            ToolPathError,
            effective_project_root,
            resolve_tool_path,
        )

        root = effective_project_root()
        results: list[str] = []
        for patch in patches:
            try:
                resolved_path = resolve_tool_path(patch.file_path, root)
            except ToolPathError as exc:
                results.append(f"DENIED {patch.file_path}: {exc}")
                continue

            patch = replace(patch, file_path=resolved_path)

            if patch.is_new_file:
                # 신규 파일 생성
                if os.path.exists(patch.file_path):
                    results.append(f"SKIP {patch.file_path}: 이미 존재함")
                    continue
                os.makedirs(os.path.dirname(patch.file_path) or ".", exist_ok=True)
                with open(patch.file_path, "w", encoding="utf-8") as f:
                    _ = f.write("\n".join(patch.new_file_content))
                results.append(f"CREATED {patch.file_path}")
                continue

            if patch.is_delete_file:
                if os.path.exists(patch.file_path):
                    os.remove(patch.file_path)
                    results.append(f"DELETED {patch.file_path}")
                else:
                    results.append(f"SKIP {patch.file_path}: 없음")
                continue

            # 기존 파일 업데이트
            if not os.path.exists(patch.file_path):
                results.append(f"ERROR {patch.file_path}: 파일 없음")
                continue

            with open(patch.file_path, encoding="utf-8") as f:
                content = f.read()

            result = engine.apply_patch(patch, content)
            if result.success:
                with open(patch.file_path, "w", encoding="utf-8") as f:
                    _ = f.write(result.new_content)
                fuzzy_tag = f" (fuzzy: {result.fuzzy_matches})" if result.is_fuzzy else ""
                results.append(f"OK {patch.file_path}: {result.hunks_applied}/{result.hunks_total} hunks{fuzzy_tag}")
            else:
                results.append(f"FAIL {patch.file_path}: {result.error}")

        # 요약
        ok = sum(1 for r in results if r.startswith(("OK", "CREATED", "DELETED")))
        failed = [r for r in results if r.startswith(("FAIL", "ERROR", "DENIED"))]
        summary = f"Applied {ok}/{len(results)} operations."
        if failed:
            summary += f" {len(failed)} failed: " + "; ".join(failed[:3])
        return summary + "\n" + "\n".join(results)


@final
class GlobSearchTool(BaseTool):
    """파일 패턴 검색 (수정 시간순 정렬).

    Claw Code의 glob 도구 — 최근 수정된 파일을 우선 표시.
    """

    category = ToolCategory.SEARCH
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.SAFE
    icon = "🔍"
    tags = ["search", "glob", "files", "find"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the GlobSearchTool."""
        super().__init__()
        self._name = "glob_search"
        self._description = (
            "Searches for files matching a glob pattern (e.g., '**/*.py'). "
            "Results are sorted by modification time (newest first). "
            "Useful for discovering project structure and finding specific files."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "root": {
                    "type": "string",
                    "description": "Root directory to search from",
                    "default": ".",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum files to return",
                    "default": 50,
                },
            },
            "required": ["pattern"],
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
        pattern = cast(str, kwargs.get("pattern", ""))
        root = cast(str, kwargs.get("root", "."))
        max_results = cast(int, kwargs.get("max_results", 50))

        try:
            full_pattern = os.path.join(root, pattern)
            matches = glob_module.glob(full_pattern, recursive=True)

            # 수정 시간순 정렬 (최신 우선) — Claw Code 패턴
            file_info: list[_FileInfo] = []
            for m in matches:
                try:
                    mtime = os.path.getmtime(m)
                    size = os.path.getsize(m)
                    file_info.append(
                        {
                            "path": os.path.relpath(m, root),
                            "size": size,
                            "modified": mtime,
                        },
                    )
                except OSError:
                    continue

            file_info.sort(key=lambda x: x["modified"], reverse=True)
            file_info = file_info[:max_results]

            if not file_info:
                return f"No files found matching '{pattern}' in {root}"

            lines = [f"Found {len(file_info)} files (newest first):"]
            for f in file_info:
                size_str = self._human_size(f["size"])
                lines.append(f"  {f['path']} ({size_str})")

            return "\n".join(lines)
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error searching files: {e}"

    @staticmethod
    def _human_size(size: int | float) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.0f}{unit}"
            size /= 1024
        return f"{size:.0f}TB"


@final
class GrepSearchTool(BaseTool):
    """코드 내 텍스트/정규식 검색.

    Claw Code의 grep 도구 — 행 번호와 컨텍스트를 포함한 결과.
    """

    category = ToolCategory.SEARCH
    render_in = RenderIn.CONTEXTUAL
    risk_level = RiskLevel.SAFE
    icon = "🔎"
    tags = ["search", "grep", "text", "regex"]
    _name: str
    _description: str
    _schema: ToolSchema

    def __init__(self):
        """Initialize the GrepSearchTool."""
        super().__init__()
        self._name = "grep_search"
        self._description = (
            "Searches for text or regex patterns in files. Returns matching lines "
            "with file paths and line numbers. Supports recursive directory search."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text or regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in.",
                    "default": ".",
                },
                "include": {
                    "type": "string",
                    "description": "File extension filter (e.g., '*.py')",
                    "default": "",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return.",
                    "default": 30,
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "Treat query as regex pattern.",
                    "default": False,
                },
            },
            "required": ["query"],
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
        query = cast(str, kwargs.get("query", ""))
        path = cast(str, kwargs.get("path", "."))
        include = cast(str, kwargs.get("include", ""))
        max_results = cast(int, kwargs.get("max_results", 30))
        is_regex = cast(bool, kwargs.get("is_regex", False))

        if not query:
            return "Error: No search query provided."

        try:
            if is_regex:
                pattern = re.compile(query, re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(query), re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results: list[str] = []

        try:
            if os.path.isfile(path):
                files = [path]
            else:
                glob_pattern = os.path.join(path, "**", include or "*")
                files = glob_module.glob(glob_pattern, recursive=True)
                files = [f for f in files if os.path.isfile(f)]

            for file_path in files:
                if len(results) >= max_results:
                    break

                # 바이너리 파일 스킵
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if len(results) >= max_results:
                                break
                            if pattern.search(line):
                                rel_path = os.path.relpath(file_path, path) if os.path.isdir(path) else file_path
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                except (OSError, UnicodeDecodeError):
                    continue

            if not results:
                return f"No matches found for '{query}' in {path}"

            header = f"Found {len(results)} matches:"
            return header + "\n" + "\n".join(results)
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error searching: {e}"
