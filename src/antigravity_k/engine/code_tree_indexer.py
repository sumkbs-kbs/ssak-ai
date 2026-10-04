"""Ssak-Ai: Code Tree Indexer (Freebuff-Style Proactive Context).

=============================================================
사용자 메시지 수신 시 관련 파일을 자동 탐색하기 위한 경량 코드 트리 인덱서.

Freebuff의 Tree-sitter 기반 코드 트리를 모방하되,
Python AST + regex 기반으로 구현하여 의존성 없이 동작합니다.

기능:
- 프로젝트 전체 파일 스캔 → 함수/클래스/임포트 맵 구축
- 변경 감지 (MD5 해시) → 증분 갱신
- 쿼리 기반 관련 파일 검색 (키워드 + 심볼 매칭)
- 압축된 코드 트리 문자열 생성 (전체 레포 100KB 이하 목표)
"""

import hashlib
import logging
import os
from pathlib import Path

from . import code_tree_symbol_extractor as _symbol_extractor
from .code_tree_indexer_models import CodeTreeStats, FileSymbols, SearchResult
from .code_tree_symbol_extractor import extract_symbols

__all__ = ["CodeTreeIndexer", "FileSymbols", "RE_COMMON_CLASS", "RE_INTERFACE"]

RE_PY_FUNCTION = _symbol_extractor.RE_PY_FUNCTION
RE_PY_CLASS = _symbol_extractor.RE_PY_CLASS
RE_PY_IMPORT = _symbol_extractor.RE_PY_IMPORT
_RE_JS_FN = _symbol_extractor.RE_JS_FN
_RE_JS_ARROW = _symbol_extractor.RE_JS_ARROW
_RE_GO_FN = _symbol_extractor.RE_GO_FN
_RE_RS_FN = _symbol_extractor.RE_RS_FN
_RE_OO_FN = _symbol_extractor.RE_OO_FN
_RE_SWIFT_FN = _symbol_extractor.RE_SWIFT_FN
_RE_PHP_FN = _symbol_extractor.RE_PHP_FN
_RE_RB_FN = _symbol_extractor.RE_RB_FN
_RE_CPP_EXACT = _symbol_extractor.RE_CPP_EXACT
RE_COMMON_CLASS = _symbol_extractor.RE_COMMON_CLASS
RE_INTERFACE = _symbol_extractor.RE_INTERFACE

logger = logging.getLogger("antigravity_k.code_tree_indexer")

# 인덱싱 대상 확장자
INDEXABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".scala",
    ".css",
    ".scss",
    ".html",
    ".md",
    ".yaml",
    ".yml",
    ".json",
}

# 무시할 디렉토리
IGNORE_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".egg-info",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".hypothesis",
    ".tox",
    "coverage",
    ".coverage",
    ".next",
    "out",
    ".turbo",
    ".cache",
    ".output",
    "public",
    "static",
    "assets",
    "images",
    "fonts",
    ".agent",  # 에이전트 스킬/메타데이터는 제외
}


class CodeTreeIndexer:
    """프로젝트 코드 트리를 구축하고 쿼리 기반 검색을 제공합니다.

    사용법:
        indexer = CodeTreeIndexer(project_root)
        tree_str = indexer.build_tree()          # 압축된 코드 트리 문자열
        files = indexer.search("user auth")       # 관련 파일 검색
    """

    def __init__(self, project_root: str):
        """Initialize the CodeTreeIndexer.

        Args:
            project_root: 프로젝트 루트 경로
        """
        self.project_root: str = os.path.abspath(project_root)
        self._symbols: dict[str, FileSymbols] = {}  # rel_path → FileSymbols
        self._tree_cache: str = ""
        self._file_hashes: dict[str, str] = {}  # rel_path → md5

    def build_tree(self, force: bool = False) -> str:
        """전체 프로젝트 코드 트리를 구축합니다.

        변경이 없으면 캐시를 반환합니다.

        Args:
            force: True면 강제 재구축

        Returns:
            압축된 코드 트리 문자열
        """
        if not force and self._tree_cache:
            return self._tree_cache

        self._symbols.clear()
        total_files = 0
        changed_files = 0

        for root, dirs, files in os.walk(self.project_root):
            # 무시할 디렉토리 필터링
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            rel_root = os.path.relpath(root, self.project_root)

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in INDEXABLE_EXTENSIONS:
                    continue

                fpath = os.path.join(root, fname)
                rel_path = fname if rel_root == "." else os.path.join(rel_root, fname)

                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except (OSError, UnicodeError):
                    continue

                # 변경 감지
                content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
                if self._file_hashes.get(rel_path) == content_hash and not force:
                    # 이미 있으면 기존 심볼 유지
                    if rel_path in self._symbols:
                        total_files += 1
                        continue

                self._file_hashes[rel_path] = content_hash
                changed_files += 1

                # 심볼 추출
                symbols = self._extract_symbols(rel_path, content, ext)
                if symbols:
                    self._symbols[rel_path] = symbols
                    total_files += 1

        # 압축된 트리 문자열 생성
        tree_lines: list[str] = []
        for rel_path in sorted(self._symbols.keys()):
            sym = self._symbols[rel_path]
            parts: list[str] = []

            # 클래스
            for cls in sym.classes:
                parts.append(f"cls:{cls}")
            # 함수
            for fn in sym.functions:
                parts.append(f"fn:{fn}")
            # 임포트 (요약)
            if sym.imports:
                imports_short = ", ".join(imp.split(".")[0] for imp in sym.imports[:5])
                if len(sym.imports) > 5:
                    imports_short += f" (+{len(sym.imports) - 5})"
                parts.append(f"import:{imports_short}")

            sym_str = " | ".join(parts) if parts else f"{sym.line_count} lines"
            tree_lines.append(f"{rel_path} [{sym_str}]")

        self._tree_cache = "\n".join(tree_lines)

        logger.info(
            "[CodeTree] Built tree: %s files (%s new/changed), %s KB",
            total_files,
            changed_files,
            len(self._tree_cache) // 1024,
        )
        return self._tree_cache

    def get_tree(self) -> str:
        """캐시된 코드 트리를 반환하거나, 없으면 구축합니다."""
        if not self._tree_cache:
            return self.build_tree()
        return self._tree_cache

    def search(self, query: str, max_files: int = 12) -> list[SearchResult]:
        """사용자 쿼리와 관련된 파일을 코드 트리 기반으로 검색합니다.

        매칭 전략 (가중치 순):
        1. 파일명 정확 매칭 (3점)
        2. 심볼명(클래스/함수) 매칭 (2점)
        3. 파일 경로 부분 매칭 (1점)
        4. 임포트 키워드 매칭 (1점)

        Args:
            query: 사용자 메시지 (자연어)
            max_files: 최대 반환 파일 수

        Returns:
            [{"file": "rel/path.py", "score": 5.0, "symbols": [...]}, ...]
        """
        if not self._symbols:
            _ = self.build_tree()

        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        scored: list[tuple[float, str, FileSymbols]] = []

        for rel_path, sym in self._symbols.items():
            score = 0.0
            path_lower = rel_path.lower()
            file_stem = Path(rel_path).stem.lower()

            # 1. 파일명 정확 매칭
            for token in query_tokens:
                if token == file_stem:
                    score += 3.0
                elif token in file_stem:
                    score += 1.5

            # 2. 심볼명 매칭
            for cls in sym.classes:
                cls_lower = cls.lower()
                for token in query_tokens:
                    if token == cls_lower:
                        score += 2.0
                    elif token in cls_lower:
                        score += 1.0

            for fn in sym.functions:
                fn_lower = fn.lower()
                for token in query_tokens:
                    if token == fn_lower:
                        score += 2.0
                    elif token in fn_lower:
                        score += 1.0

            # 3. 파일 경로 부분 매칭
            for token in query_tokens:
                if token in path_lower:
                    score += 1.0

            # 4. 임포트 키워드 매칭
            for imp in sym.imports:
                imp_lower = imp.lower()
                for token in query_tokens:
                    if token in imp_lower:
                        score += 0.5
                        break

            if score > 0.5:
                scored.append((score, rel_path, sym))

        # 점수 순 정렬
        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[SearchResult] = []
        for score, rel_path, sym in scored[:max_files]:
            results.append(
                {
                    "file": rel_path,
                    "score": round(score, 1),
                    "functions": sym.functions[:5],
                    "classes": sym.classes[:5],
                    "line_count": sym.line_count,
                }
            )

        return results

    def _extract_symbols(self, rel_path: str, content: str, ext: str) -> FileSymbols | None:
        """파일 확장자에 따라 심볼을 추출합니다."""
        return extract_symbols(rel_path, content, ext)

    def stats(self) -> CodeTreeStats:
        """인덱서 통계 정보를 반환합니다."""
        total_classes = sum(len(s.classes) for s in self._symbols.values())
        total_functions = sum(len(s.functions) for s in self._symbols.values())
        total_lines = sum(s.line_count for s in self._symbols.values())

        return {
            "files_indexed": len(self._symbols),
            "total_classes": total_classes,
            "total_functions": total_functions,
            "total_lines": total_lines,
            "tree_size_kb": round(len(self._tree_cache) / 1024, 1),
        }
