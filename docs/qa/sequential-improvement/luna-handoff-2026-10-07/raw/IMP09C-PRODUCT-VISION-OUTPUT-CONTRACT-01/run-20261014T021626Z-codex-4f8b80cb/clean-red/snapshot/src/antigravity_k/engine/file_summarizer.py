"""Ssak-Ai: File Summarizer (Freebuff-Style Content Summary).

=============================================================
CodeTreeIndexer가 선정한 관련 파일의 핵심 내용을 요약하여
컨텍스트에 주입합니다. Freebuff의 Gemini Flash 역할을 대체합니다.

요약 전략:
- 50줄 이하 → 전체 내용 포함
- 50~200줄 → 함수 시그니처 + 클래스 헤더 + 주요 로직 요약
- 200줄 이상 → 파일 트리 + 키-값 쌍 요약
"""

import logging
import os
from collections.abc import Mapping, Sequence
from typing import Protocol, cast, final, runtime_checkable

logger = logging.getLogger("antigravity_k.file_summarizer")

# 파일당 최대 요약 문자 수
MAX_SUMMARY_CHARS = 1500
# 최대 요약 파일 수
MAX_SUMMARIZE_FILES = 8


@runtime_checkable
class _ModelManagerLike(Protocol):
    def generate(self, **kwargs: object) -> str: ...


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    return [item for item in raw_items if isinstance(item, str)]


@final
class FileSummarizer:
    """파일 내용을 경량 요약하여 컨텍스트에 주입합니다.

    LLM 호출 없이 규칙 기반 요약으로 Freebuff의 Gemini Flash를 대체합니다.
    필요시 model_manager.generate()를 사용한 LLM 요약으로 업그레이드 가능.
    """

    def __init__(self, model_manager: object | None = None):
        """Initialize the FileSummarizer.

        Args:
            model_manager: 선택적 ModelManager (LLM 요약 시 사용)
        """
        self.model_manager: object | None = model_manager

    def summarize_files(
        self,
        file_list: Sequence[Mapping[str, object]],
        project_root: str,
        query: str = "",
    ) -> str:
        """관련 파일 목록을 요약하여 컨텍스트 문자열로 반환합니다.

        Args:
            file_list: CodeTreeIndexer.search() 결과 리스트
            project_root: 프로젝트 루트 경로
            query: 원래 사용자 쿼리 (선택적)

        Returns:
            요약된 컨텍스트 문자열 (마크다운 형식)
        """
        _ = query
        if not file_list:
            return ""

        context_parts = ["<auto_context>"]
        total_chars = 0

        for entry in file_list[:MAX_SUMMARIZE_FILES]:
            rel_path_value = entry.get("file", "unknown")
            rel_path = rel_path_value if isinstance(rel_path_value, str) else "unknown"
            abs_path = rel_path
            if not os.path.isabs(rel_path):
                abs_path = os.path.join(project_root, rel_path)

            if not os.path.isfile(abs_path):
                context_parts.append(f"\n📄 **{rel_path}** _(파일 없음)_")
                continue

            try:
                with open(abs_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                context_parts.append(f"\n📄 **{rel_path}** _(읽기 실패)_")
                continue

            # 요약 생성
            summary = self._summarize_single_file(
                rel_path,
                content,
                _string_list(entry.get("functions", [])),
                _string_list(entry.get("classes", [])),
            )

            entry_str = f"\n📄 **{rel_path}**\n{summary}\n"

            if total_chars + len(entry_str) > MAX_SUMMARY_CHARS * 2:
                break

            context_parts.append(entry_str)
            total_chars += len(entry_str)

        context_parts.append("\n</auto_context>")

        result = "\n".join(context_parts)

        # 전체가 너무 길면 자르기
        if len(result) > MAX_SUMMARY_CHARS * 2:
            result = result[: MAX_SUMMARY_CHARS * 2] + "\n\n... _(context truncated)_\n</auto_context>"

        return result

    def _summarize_single_file(
        self,
        rel_path: str,
        content: str,
        known_functions: list[str],
        known_classes: list[str],
    ) -> str:
        """단일 파일을 규칙 기반으로 요약합니다.

        Args:
            rel_path: 상대 경로
            content: 파일 전체 내용
            known_functions: 알려진 함수 목록
            known_classes: 알려진 클래스 목록

        Returns:
            요약 텍스트
        """
        lines = content.split("\n")
        total_lines = len(lines)

        # 50줄 이하 → 전체 내용
        if total_lines <= 50:
            return self._wrap_code(content)

        ext = os.path.splitext(rel_path)[1].lower()

        # 50~200줄 → 핵심 구조만
        if total_lines <= 200:
            return self._extract_key_structure(content, lines, ext, known_functions, known_classes)

        # 200줄 이상 → 심볼 기반 요약
        return self._summarize_large_file(
            content,
            lines,
            ext,
            known_functions,
            known_classes,
            total_lines,
        )

    def _extract_key_structure(
        self,
        content: str,
        lines: list[str],
        ext: str,
        known_functions: list[str],
        known_classes: list[str],
    ) -> str:
        """파일에서 핵심 구조(시그니처, 클래스 헤더)만 추출합니다."""
        _ = (content, known_functions, known_classes)
        extracted: list[str] = []
        char_count = 0

        # 클래스/함수 시그니처 추출
        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip blank/comments
            if not stripped or stripped.startswith(("#", "//", "/*", "*", "<!--")):
                continue

            # Keep function/class signatures and key decorators
            is_key_line = False
            if stripped.startswith(("def ", "class ", "async def ")):
                is_key_line = True
            elif ext in (".py",) and stripped.startswith(("@", "from ", "import ")):
                is_key_line = True
            elif stripped.startswith(("function ", "export function", "export class", "interface ")):
                is_key_line = True
            elif stripped.startswith(("pub fn ", "fn ", "pub struct", "pub enum")):
                is_key_line = True
            elif stripped.startswith(("public ", "private ", "protected ", "func ")):
                is_key_line = True

            if is_key_line:
                next_line = ""
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                entry = f"{line.rstrip()}\n"
                if next_line and (next_line.startswith(('"""', "'''", "//", "/*"))):
                    entry += f"{next_line}\n"

                if char_count + len(entry) > MAX_SUMMARY_CHARS:
                    extracted.append("  ... (truncated)")
                    break

                extracted.append(entry.rstrip())
                char_count += len(entry)

        if not extracted:
            # 시그니처를 못 찾았으면 앞 30줄
            preview = "\n".join(lines[:30])
            return self._wrap_code(preview)

        return "```\n" + "\n".join(extracted) + "\n```"

    def _summarize_large_file(
        self,
        content: str,
        lines: list[str],
        ext: str,
        known_functions: list[str],
        known_classes: list[str],
        total_lines: int,
    ) -> str:
        """큰 파일을 통계 기반으로 요약합니다."""
        _ = ext
        parts = [f"_{total_lines} lines, {len(content)} chars_"]

        if known_functions:
            fn_list = ", ".join(known_functions[:10])
            if len(known_functions) > 10:
                fn_list += f" (+{len(known_functions) - 10})"
            parts.append(f"**Functions:** {fn_list}")

        if known_classes:
            cls_list = ", ".join(known_classes[:5])
            if len(known_classes) > 5:
                cls_list += f" (+{len(known_classes) - 5})"
            parts.append(f"**Classes:** {cls_list}")

        # 첫 15줄 프리뷰
        preview = "\n".join(lines[:15])
        parts.append(f"```\n{preview}\n...\n```")

        return "\n".join(parts)

    def llm_summarize(self, file_path: str, content: str, query: str = "") -> str:
        """LLM을 사용한 고급 요약 (model_manager가 있을 때 사용).

        Args:
            file_path: 파일 경로
            content: 파일 내용
            query: 사용자 쿼리

        Returns:
            LLM 요약 텍스트
        """
        manager = self.model_manager
        if not isinstance(manager, _ModelManagerLike):
            return self._summarize_single_file(file_path, content, [], [])

        lines = content.split("\n")
        if len(lines) <= 50:
            return self._wrap_code(content)

        # 내용이 너무 길면 앞뒤로 자름
        max_chars = 8000
        if len(content) > max_chars:
            content = content[: max_chars // 2] + "\n\n... (중간 생략) ...\n\n" + content[-max_chars // 2 :]

        prompt = f"""Summarize this source file for an AI coding agent that needs to understand it for context.

Query: {query or "(no specific query)"}

File: {file_path}

```{content}```

Provide only the essential facts in 3-5 bullet points:
- What this file does (purpose)
- Key functions/classes (names only)
- Key imports/dependencies
"""
        try:
            summary = manager.generate(
                prompt=prompt,
                target="default",
                max_tokens=256,
            )
            return summary.strip()
        except Exception:
            logger.debug("LLM summary failed, falling back to rule-based")
            return self._summarize_single_file(file_path, content, [], [])

    @staticmethod
    def _wrap_code(content: str) -> str:
        """내용을 코드 블록으로 감쌉니다."""
        max_preview = MAX_SUMMARY_CHARS
        if len(content) > max_preview:
            content = content[:max_preview] + "\n... (truncated)"
        return f"```\n{content}\n```"
