"""Ssak-Ai: RAG Indexer.

===========================
프로젝트 소스 파일을 AST 기반으로 함수/클래스 단위 청크로 분할하고
VectorStore에 인덱싱하여, 오케스트레이터가 질문과 관련된 코드를
자동으로 컨텍스트에 주입할 수 있게 합니다.

격차 해소 대상: 컨텍스트 윈도우 한계 (4K~32K → 사실상 무제한)

SurfSense 양분 이식:
- Hybrid Search + RRF (Reciprocal Rank Fusion)
- Table-Aware Markdown Chunking
"""

import ast
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeAlias, cast

from antigravity_k.engine.long_context_fusion import LongContextFusion

logger = logging.getLogger("antigravity_k.rag_indexer")

# 인덱싱 대상 확장자
INDEXABLE_EXTENSIONS = {".py", ".js", ".ts", ".css", ".html", ".md", ".yaml", ".yml"}

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
}

# 청크 최대 길이 (토큰 기준 근사치, 1 토큰 ≈ 4 chars)
MAX_CHUNK_CHARS = 3000  # ~750 tokens
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


_CITATION_RANGE_RE = re.compile(
    r"\[citation:(?P<id>[^\]\s:]+):(?P<start>\d+)-(?P<end>\d+)\]",
)


def _citation_line_ranges(response: str, source_id: str) -> list[tuple[int, int]]:
    """응답에서 특정 source_id에 붙은 :start-end 범위들을 추출한다."""
    return [
        (int(m.group("start")), int(m.group("end")))
        for m in _CITATION_RANGE_RE.finditer(response)
        if m.group("id") == source_id
    ]


def _normalize_citation_id(raw: str) -> str:
    """[citation:id]와 [citation:id:12-20]을 같은 id로 정규화한다."""
    return re.sub(r":\d+-\d+$", "", raw)


def _as_record(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


class VectorStoreLike(Protocol):
    persist_directory: str

    def get_stats(self) -> dict[str, object]: ...

    def search(self, query: str, n_results: int = 5) -> list[dict[str, object]]: ...

    def upsert_chunks(self, chunks: Sequence[Mapping[str, object]]) -> None: ...

    def delete_file_chunks(self, file_path: str) -> None: ...


@dataclass
class CodeChunk:
    """코드 청크 단위."""

    chunk_id: str
    file_path: str
    node_type: str  # "function", "class", "module_header", "text_section"
    node_name: str
    content: str
    start_line: int
    end_line: int
    metadata: dict[str, object] = field(default_factory=dict)


class RAGIndexer:
    """프로젝트 코드를 청크 단위로 분할하고 VectorStore에 인덱싱합니다."""

    def __init__(
        self,
        project_root: str,
        vector_store: object | None = None,
        batch_size: int = 256,
        manifest_path: str | None = None,
    ):
        """Initialize the RAGIndexer.

        Args:
            project_root (str): str project root.
            vector_store: vector store.

        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.project_root: str = os.path.abspath(project_root)
        self.vector_store: VectorStoreLike | None = cast(VectorStoreLike | None, vector_store)
        self.batch_size: int = batch_size
        store_directory = getattr(vector_store, "persist_directory", None)
        self._manifest_path: Path | None = (
            Path(manifest_path)
            if manifest_path
            else (Path(store_directory) / "rag-manifest.json" if isinstance(store_directory, str) else None)
        )
        self._file_hashes: dict[str, str] = {}
        self._long_context_fusion: LongContextFusion = LongContextFusion()
        self._load_manifest()

    def _load_manifest(self) -> None:
        if self._manifest_path is None or not self._store_has_chunks() or not self._manifest_path.is_file():
            return
        try:
            payload = cast(object, json.loads(self._manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            logger.warning("[RAGIndexer] Could not load manifest: %s", self._manifest_path)
            return
        files = _as_record(payload).get("files")
        if isinstance(files, dict):
            file_map = cast(dict[object, object], files)
            self._file_hashes = {str(path): value for path, value in file_map.items() if isinstance(value, str)}

    def _store_has_chunks(self) -> bool:
        if self.vector_store is None:
            return False
        stats_fn = cast(Callable[[], dict[str, object]] | None, getattr(self.vector_store, "get_stats", None))
        if not callable(stats_fn):
            return False
        stats = stats_fn()
        count = stats.get("count")
        return isinstance(count, int) and count > 0

    def _persist_manifest(self) -> None:
        if self._manifest_path is None:
            return
        payload = {"version": 1, "files": self._file_hashes}
        try:
            self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._manifest_path.with_suffix(".tmp")
            _ = temporary_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            _ = temporary_path.replace(self._manifest_path)
        except OSError:
            logger.warning("[RAGIndexer] Could not persist manifest: %s", self._manifest_path)

    def index_project(self, subdirs: list[str] | None = None) -> int:
        """프로젝트 전체 또는 지정된 하위 디렉토리를 인덱싱합니다.

        Returns:
            인덱싱된 총 청크 수

        """
        if subdirs:
            scan_dirs = [os.path.join(self.project_root, d) for d in subdirs]
        else:
            scan_dirs = [self.project_root]

        all_chunks: list[CodeChunk] = []
        changed_files: list[str] = []

        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            for root, dirs, files in os.walk(scan_dir):
                # 무시할 디렉토리 필터링
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

                for fname in files:
                    ext = Path(fname).suffix.lower()
                    if ext not in INDEXABLE_EXTENSIONS:
                        continue

                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.project_root)

                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception:
                        logger.exception("Unhandled exception")
                        continue

                    # 변경 감지 (해시 비교)
                    content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
                    if self._file_hashes.get(rel_path) == content_hash:
                        continue  # 변경 없음 → 스킵
                    self._file_hashes[rel_path] = content_hash
                    changed_files.append(rel_path)

                    # 파일 유형별 청킹
                    if ext == ".py":
                        chunks = self._chunk_python(rel_path, content)
                    elif ext == ".md":
                        chunks = self._chunk_markdown(rel_path, content)
                    else:
                        chunks = self._chunk_generic(rel_path, content)

                    self._annotate_chunks(chunks, content_hash)
                    all_chunks.extend(chunks)

        if self.vector_store:
            delete_chunks = getattr(self.vector_store, "delete_file_chunks", None)
            if callable(delete_chunks):
                for rel_path in changed_files:
                    _ = delete_chunks(rel_path)
        if self.vector_store and all_chunks:
            store_chunks = [
                {
                    "id": c.chunk_id,
                    "text": c.content,
                    "metadata": {
                        "source": c.file_path,
                        "node_type": c.node_type,
                        "node_name": c.node_name,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        **c.metadata,
                    },
                }
                for c in all_chunks
            ]
            for start in range(0, len(store_chunks), self.batch_size):
                self.vector_store.upsert_chunks(
                    cast(Sequence[Mapping[str, object]], store_chunks[start : start + self.batch_size])
                )
            logger.info("[RAGIndexer] Indexed %s chunks from project", len(store_chunks))

        self._persist_manifest()
        return len(all_chunks)

    def sync(self, subdirs: list[str] | None = None) -> int:
        """파일 시스템 변경사항(추가/수정/삭제)을 인덱스에 동기화합니다."""
        if subdirs:
            scan_dirs = [os.path.join(self.project_root, d) for d in subdirs]
        else:
            scan_dirs = [self.project_root]

        current_files: set[str] = set()
        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            for root, dirs, files in os.walk(scan_dir):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for fname in files:
                    ext = Path(fname).suffix.lower()
                    if ext in INDEXABLE_EXTENSIONS:
                        fpath = os.path.join(root, fname)
                        rel_path = os.path.relpath(fpath, self.project_root)
                        current_files.add(rel_path)

        if subdirs:
            normalized_scopes = {
                os.path.normpath(os.path.relpath(os.path.join(self.project_root, subdir), self.project_root))
                for subdir in subdirs
            }

            def in_scope(rel_path: str) -> bool:
                return "." in normalized_scopes or any(
                    rel_path == scope or rel_path.startswith(f"{scope}{os.sep}") for scope in normalized_scopes
                )

            manifest_files = {rel_path for rel_path in self._file_hashes if in_scope(rel_path)}
        else:
            manifest_files = set(self._file_hashes)
        deleted_files = manifest_files - current_files
        for rel_path in deleted_files:
            del self._file_hashes[rel_path]
            if self.vector_store:
                self.vector_store.delete_file_chunks(rel_path)
                logger.debug("[RAGIndexer] Removed chunks for deleted file: %s", rel_path)

        # 추가/수정된 파일 처리 (기존 로직 재사용)
        return self.index_project(subdirs)

    def index_file(self, file_path: str) -> int:
        """단일 파일을 (재)인덱싱합니다. 도구로 파일 수정 시 호출."""
        abs_path = file_path
        if not os.path.isabs(file_path):
            abs_path = os.path.join(self.project_root, file_path)

        if not os.path.isfile(abs_path):
            return 0

        rel_path = os.path.relpath(abs_path, self.project_root)
        ext = Path(abs_path).suffix.lower()

        try:
            with open(abs_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            logger.exception("Unhandled exception")
            return 0

        # RAG-02 — CRLF 입력의 라인 계산 일관성: 개행을 LF로 정규화한다.
        # (원본 파일은 수정하지 않고, 청킹/라인 계산에만 정규화된 텍스트를 쓴다.)
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        self._file_hashes[rel_path] = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

        # 기존 청크 삭제
        if self.vector_store:
            self.vector_store.delete_file_chunks(rel_path)

        # 재청킹
        if ext == ".py":
            chunks = self._chunk_python(rel_path, content)
        elif ext == ".md":
            chunks = self._chunk_markdown(rel_path, content)
        else:
            chunks = self._chunk_generic(rel_path, content)

        self._annotate_chunks(chunks, self._file_hashes[rel_path])
        if self.vector_store and chunks:
            store_chunks = [
                {
                    "id": c.chunk_id,
                    "text": c.content,
                    "metadata": {
                        "source": c.file_path,
                        "node_type": c.node_type,
                        "node_name": c.node_name,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        **c.metadata,
                    },
                }
                for c in chunks
            ]
            for start in range(0, len(store_chunks), self.batch_size):
                self.vector_store.upsert_chunks(
                    cast(Sequence[Mapping[str, object]], store_chunks[start : start + self.batch_size])
                )

        self._persist_manifest()

        return len(chunks)

    def _annotate_chunks(self, chunks: list[CodeChunk], source_hash: str) -> None:
        """청크 메타데이터 부여 + RAG-01 ID 고유성 보장.

        청킹 단계에서 이미 ordinal 기반 ID를 받지만, 함수/클래스 겹침 등
        어떤 경로로도 중복이 남지 않도록 여기서 최종 방어선을 둔다.
        중복 발견 시 ordinal+content digest로 재파생 — dedupe 접미사가
        무변경 재색인의 ID 안정성을 깨지 않도록 _make_unique_id를 쓴다.
        """
        indexed_at = datetime.now(UTC).isoformat()
        seen_ids: set[str] = set()
        for index, chunk in enumerate(chunks):
            if chunk.chunk_id in seen_ids:
                chunk.chunk_id = self._make_unique_id(
                    chunk.file_path,
                    f"dedupe_{chunk.node_type}_{index}",
                    chunk.content,
                    index,
                    seen_ids,
                )
            seen_ids.add(chunk.chunk_id)
            chunk.metadata.update(
                {
                    "source_hash": source_hash,
                    "source_type": "code",
                    "indexed_at": indexed_at,
                },
            )

    def _attach_provenance(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
        enriched: list[dict[str, object]] = []
        for result in results:
            metadata = _as_record(result.get("metadata"))
            source_value = metadata.get("source")
            source = source_value if isinstance(source_value, str) else None
            source_hash_value = metadata.get("source_hash")
            source_hash = source_hash_value if isinstance(source_hash_value, str) else None
            freshness = "unknown"

            if source:
                source_path = source if os.path.isabs(source) else os.path.join(self.project_root, source)
                if not os.path.isfile(source_path):
                    freshness = "missing"
                elif source_hash:
                    try:
                        current_hash = hashlib.md5(Path(source_path).read_bytes(), usedforsecurity=False).hexdigest()
                    except OSError:
                        freshness = "unavailable"
                    else:
                        freshness = "fresh" if current_hash == source_hash else "stale"

            enriched_result = dict(result)
            enriched_result["provenance"] = {
                "source_id": result.get("id"),
                "source": source,
                "source_type": metadata.get("source_type", "code"),
                "node_type": metadata.get("node_type"),
                "node_name": metadata.get("node_name"),
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
                "source_hash": source_hash,
                "indexed_at": metadata.get("indexed_at"),
                "freshness": freshness,
            }
            enriched.append(enriched_result)
        return enriched

    def validate_citations(
        self,
        response: str,
        results: list[dict[str, object]],
        require_citation: bool = True,
    ) -> dict[str, object]:
        cited: list[str] = list(
            dict.fromkeys(
                _normalize_citation_id(raw) for raw in re.findall(r"\[citation:([^\]\s]+)\]", response or "")
            ),
        )
        eligible: dict[str, str] = {}
        eligible_line_ranges: dict[str, tuple[int, int] | None] = {}
        for result in results:
            provenance = _as_record(result.get("provenance"))
            source_id = provenance.get("source_id") or result.get("id")
            if source_id:
                eligible[str(source_id)] = str(provenance.get("freshness", "unknown"))
                start = provenance.get("start_line")
                end = provenance.get("end_line")
                eligible_line_ranges[str(source_id)] = (
                    (int(start), int(end)) if isinstance(start, int) and isinstance(end, int) else None
                )

        # RAG-02 — citation 뒤 :start-end line range를 검증한다.
        #   [citation:<id>:12-20]  → provenance의 start_line/end_line과 일치해야
        #   [citation:<id>]        → range 없음 (범위 검증 대상 아님)
        range_mismatch: list[str] = []
        for source_id in cited:
            expected = eligible_line_ranges.get(source_id)
            if expected is None:
                continue  # unknown/unverified로 이미 분류됨
            start, end = expected
            for lo, hi in _citation_line_ranges(response or "", source_id):
                if lo > hi or lo != start or hi != end:
                    range_mismatch.append(f"{source_id}:{lo}-{hi}")

        unknown = [source_id for source_id in cited if source_id not in eligible]
        unverified = [source_id for source_id in cited if source_id in eligible and eligible[source_id] != "fresh"]
        missing_citation = bool(results) and require_citation and not cited
        return {
            "valid": not unknown and not unverified and not missing_citation and not range_mismatch,
            "required": bool(results) and require_citation,
            "cited": cited,
            "unknown": unknown,
            "unverified": unverified,
            "range_mismatch": range_mismatch,
            "missing_citation": missing_citation,
        }

    def search(self, query: str, n_results: int = 5, mode: str = "hybrid") -> list[dict[str, object]]:
        """질문과 관련된 코드 청크를 검색합니다.

        Args:
            query: 검색 질의
            n_results: 반환할 결과 수
            mode: 검색 모드 — "semantic", "keyword", "hybrid" (기본)

        """
        if not self.vector_store:
            return []

        if mode == "keyword":
            results = self._keyword_search(query, n_results)
        elif mode == "semantic":
            results = self.vector_store.search(query, n_results=n_results)
        elif mode == "long_context":
            results = self.search_long_context(query, n_results=n_results)
        else:  # hybrid (default)
            results = self._hybrid_search_rrf(query, n_results)

        return self._attach_provenance(results)

    def search_long_context(
        self,
        query: str,
        n_results: int = 5,
        candidate_pool: int = 128,
    ) -> list[dict[str, object]]:
        if not self.vector_store or n_results <= 0 or candidate_pool <= 0:
            return []
        pool = min(candidate_pool, self._long_context_fusion.config.candidate_pool)
        result_limit = min(n_results, pool)
        if result_limit <= 0:
            return []
        semantic_results = [
            result for result in self.vector_store.search(query, n_results=pool) if not self._is_stale_result(result)
        ]
        sparse_results = [
            result for result in self._keyword_search(query, n_results=pool) if not self._is_stale_result(result)
        ]
        ranked = self._long_context_fusion.rank(
            query,
            cast(Sequence[Mapping[str, JsonValue]], sparse_results),
            cast(Sequence[Mapping[str, JsonValue]], semantic_results),
            n_results=result_limit,
            candidate_pool=candidate_pool,
        )
        return cast(list[dict[str, object]], ranked)

    def _keyword_search(self, query: str, n_results: int = 5) -> list[dict[str, object]]:
        """키워드 기반 정확 매칭 검색 (식별자, 함수명, 클래스명 등)."""
        if not self.vector_store:
            return []

        all_chunks = cast(Sequence[Mapping[str, object]] | None, getattr(self.vector_store, "_chunks", None))
        if all_chunks is None:
            # VectorStore가 내부 청크 목록을 노출하지 않으면 시맨틱으로 폴백
            return self.vector_store.search(query, n_results=n_results)

        query_tokens = self._query_tokens(query)
        query_token_set = set(query_tokens)
        normalized_query = " ".join(query_tokens)
        scored: list[tuple[float, dict[str, object]]] = []
        for chunk in all_chunks:
            text = str(chunk.get("text", ""))
            meta = _as_record(chunk.get("metadata"))
            node_name = str(meta.get("node_name", ""))
            source = str(meta.get("source", ""))
            text_tokens = set(self._query_tokens(text))
            node_tokens = set(self._query_tokens(node_name))
            source_tokens = set(self._query_tokens(Path(source).stem))

            # 식별자 정확 매칭 보너스
            score = 0.0
            for token in query_tokens:
                if token in node_tokens:
                    score += 5.0
                elif token in node_name.lower():
                    score += 2.0
                if token in text_tokens:
                    score += 1.0
                if token in source_tokens:
                    score += 0.5

            if source_tokens:
                source_overlap = len(query_token_set & source_tokens)
                score += 2.0 * source_overlap / len(source_tokens)
                if source_tokens <= query_token_set:
                    score += 4.0

            normalized_name = " ".join(self._query_tokens(node_name))
            normalized_text = " ".join(self._query_tokens(text))
            if normalized_query and normalized_query == normalized_name:
                score += 8.0
            elif normalized_query and normalized_query in normalized_text:
                score += 2.0

            if score > 0:
                scored.append((score, dict(chunk)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:n_results]]

    def _hybrid_search_rrf(self, query: str, n_results: int = 5) -> list[dict[str, object]]:
        """Hybrid Search with Reciprocal Rank Fusion (SurfSense 패턴).

        시맨틱 검색과 키워드 검색 결과를 RRF 공식으로 융합합니다.
        RRF score = 1/(k + rank_semantic) + 1/(k + rank_keyword)
        """
        k = 60  # RRF 상수 (SurfSense 동일)
        fetch_n = max(n_results * 6, 20)

        # 두 검색 채널 실행
        vector_store = self.vector_store
        if vector_store is None:
            return []
        expanded_query = self._expand_query(query)
        semantic_channels = [(1.0, vector_store.search(query, n_results=fetch_n))]
        if expanded_query and expanded_query != query.strip().lower():
            semantic_channels.append((0.7, vector_store.search(expanded_query, n_results=fetch_n)))
        keyword_results = self._keyword_search(query, fetch_n)

        # 청크 ID → RRF 점수 계산
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, dict[str, object]] = {}

        for channel_weight, semantic_results in semantic_channels:
            for rank, result in enumerate(semantic_results):
                if self._is_stale_result(result):
                    continue
                cid = str(result.get("id") or hashlib.sha256(str(result.get("text", "")).encode()).hexdigest()[:16])
                node_weight = self._retrieval_node_weight(query, result)
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + node_weight * channel_weight / (k + rank + 1)
                _ = chunk_map.setdefault(cid, result)

        for rank, result in enumerate(keyword_results):
            if self._is_stale_result(result):
                continue
            cid = str(result.get("id") or hashlib.sha256(str(result.get("text", "")).encode()).hexdigest()[:16])
            node_weight = self._retrieval_node_weight(query, result)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + node_weight * 1.2 / (k + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = result

        # RRF 점수 기준 정렬
        sorted_ids = sorted(rrf_scores, key=lambda cid: (-rrf_scores[cid], cid))
        selected: list[dict[str, object]] = []
        selected_ids: set[str] = set()
        source_counts: dict[str, int] = {}

        for allow_duplicate in (False, True):
            for cid in sorted_ids:
                if cid in selected_ids:
                    continue
                candidate = chunk_map.get(cid)
                if candidate is None:
                    continue
                result = candidate
                metadata = _as_record(result.get("metadata"))
                source = str(metadata.get("source") or cid)
                source_count = source_counts.get(source, 0)
                if source_count >= 2 or (not allow_duplicate and source_count > 0):
                    continue
                selected.append(result)
                selected_ids.add(cid)
                source_counts[source] = source_count + 1
                if len(selected) >= n_results:
                    return selected
        return selected

    @staticmethod
    def _retrieval_node_weight(query: str, result: dict[str, object]) -> float:
        metadata = _as_record(result.get("metadata"))
        if metadata.get("node_type") != "module_header":
            return 1.0
        query_tokens = set(RAGIndexer._query_tokens(query))
        source_tokens = set(RAGIndexer._query_tokens(str(metadata.get("source", ""))))
        node_tokens = set(RAGIndexer._query_tokens(str(metadata.get("node_name", ""))))
        return 1.0 if query_tokens <= source_tokens or query_tokens <= node_tokens else 0.35

    @staticmethod
    def _query_tokens(value: str) -> tuple[str, ...]:
        raw_tokens: list[str] = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[가-힣]{2,}", str(value))
        tokens: list[str] = []
        for raw_token in raw_tokens:
            split_token = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw_token)
            split_token = split_token.replace("_", " ").replace("-", " ")
            tokens.extend(part.lower() for part in split_token.split() if len(part) > 1)
        return tuple(dict.fromkeys(tokens))

    @staticmethod
    def _expand_query(query: str) -> str:
        aliases: dict[str, tuple[str, ...]] = {
            "artifact": ("chunk", "manifest"),
            "compaction": ("compress", "compact"),
            "context": ("memory", "window"),
            "provenance": ("citation", "source"),
            "recall": ("retrieve", "restore"),
            "retrieval": ("search", "retrieve"),
        }
        expanded = dict.fromkeys(RAGIndexer._query_tokens(query))
        for token in tuple(expanded):
            expanded.update(dict.fromkeys(aliases.get(token, ())))
        return " ".join(expanded)

    def _is_stale_result(self, result: dict[str, object]) -> bool:
        metadata = _as_record(result.get("metadata"))
        source = metadata.get("source")
        expected_hash = metadata.get("source_hash")
        if not isinstance(source, str) or not isinstance(expected_hash, str):
            return False
        source_path = Path(source) if os.path.isabs(source) else Path(self.project_root) / source
        if not source_path.is_file():
            return False
        try:
            current_hash = hashlib.md5(source_path.read_bytes(), usedforsecurity=False).hexdigest()
        except OSError:
            return False
        return current_hash != expected_hash

    def format_context(
        self,
        query: str,
        n_results: int = 5,
        max_chars: int = 6000,
        mode: str = "hybrid",
        candidate_pool: int | None = None,
    ) -> str:
        """검색 결과를 오케스트레이터에 주입할 컨텍스트 문자열로 포맷합니다."""
        if mode == "long_context" and candidate_pool is not None:
            results = self.search_long_context(query, n_results=n_results, candidate_pool=candidate_pool)
        else:
            results = self.search(query, n_results=n_results, mode=mode)
        if not results:
            return ""

        lines = [
            "<relevant_code>",
            "Cite code evidence with [citation:<source_id>] when relying on these snippets.",
        ]
        total_chars = 0
        for r in results:
            text = r.get("text", "")
            meta = _as_record(r.get("metadata", {}))
            source = meta.get("source", "unknown")
            node_name = meta.get("node_name", "")
            start = meta.get("start_line", "?")
            end = meta.get("end_line", "?")
            provenance = _as_record(r.get("provenance"))
            source_id = provenance.get("source_id") or r.get("id")
            citation = f" [citation:{source_id}]" if source_id else ""
            freshness = provenance.get("freshness", "unknown")

            header = f"# {source}:{start}-{end} ({node_name}){citation} [freshness:{freshness}]"
            entry = f"{header}\n{text}\n"

            if total_chars + len(entry) > max_chars:
                break
            lines.append(entry)
            total_chars += len(entry)

        lines.append("</relevant_code>")
        return "\n".join(lines)

    # ─── Python AST 기반 청킹 ─────────────────────────────────

    def _chunk_python(self, rel_path: str, content: str) -> list[CodeChunk]:
        """Python 파일을 AST로 파싱하여 함수/클래스 단위로 분할합니다."""
        chunks: list[CodeChunk] = []
        lines = content.split("\n")

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # AST 파싱 실패 시 일반 청킹으로 폴백
            return self._chunk_generic(rel_path, content)

        # 모듈 수준 docstring + import 블록
        header_end = 0
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                header_end = max(header_end, node.end_lineno or node.lineno)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                header_end = max(header_end, node.end_lineno or node.lineno)
            else:
                break

        if header_end > 0:
            header_text = "\n".join(lines[:header_end])
            if header_text.strip():
                chunks.append(
                    CodeChunk(
                        chunk_id=self._make_id(rel_path, "header"),
                        file_path=rel_path,
                        node_type="module_header",
                        node_name="imports",
                        content=header_text,
                        start_line=1,
                        end_line=header_end,
                    ),
                )

        # 함수/클래스 노드 추출
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function_chunk(chunks, rel_path, lines, node)
            elif isinstance(node, ast.ClassDef):
                self._extract_class_chunk(chunks, rel_path, lines, node)

        # 청크가 없으면 파일 전체를 하나의 청크로
        if not chunks:
            chunks = self._chunk_generic(rel_path, content)

        return chunks

    def _extract_function_chunk(
        self,
        chunks: list[CodeChunk],
        rel_path: str,
        lines: list[str],
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """함수 노드를 청크로 추출합니다."""
        start = node.lineno - 1  # 0-indexed
        end = node.end_lineno or node.lineno
        text = "\n".join(lines[start:end])

        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS] + "\n# ... (truncated)"

        chunks.append(
            CodeChunk(
                chunk_id=self._make_id(rel_path, f"fn_{node.name}"),
                file_path=rel_path,
                node_type="function",
                node_name=node.name,
                content=text,
                start_line=node.lineno,
                end_line=end,
                metadata={"decorators": [self._decorator_name(d) for d in node.decorator_list]},
            ),
        )

    def _extract_class_chunk(
        self, chunks: list[CodeChunk], rel_path: str, lines: list[str], node: ast.ClassDef
    ) -> None:
        """클래스 노드를 청크로 추출합니다. 메서드는 개별 청크로 분리."""
        # 클래스 시그니처 + docstring
        class_start = node.lineno - 1
        first_method_line = None
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first_method_line = item.lineno - 1
                break

        if first_method_line is not None:
            class_header = "\n".join(lines[class_start:first_method_line])
        else:
            end = node.end_lineno or node.lineno
            class_header = "\n".join(lines[class_start:end])

        if class_header.strip():
            chunks.append(
                CodeChunk(
                    chunk_id=self._make_id(rel_path, f"cls_{node.name}"),
                    file_path=rel_path,
                    node_type="class",
                    node_name=node.name,
                    content=class_header[:MAX_CHUNK_CHARS],
                    start_line=node.lineno,
                    end_line=first_method_line or (node.end_lineno or node.lineno),
                ),
            )

        # 메서드들을 개별 청크로
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function_chunk(chunks, rel_path, lines, item)
                # 메서드 청크에 클래스 이름 메타데이터 추가
                if chunks:
                    chunks[-1].metadata["class"] = node.name
                    chunks[-1].node_name = f"{node.name}.{item.name}"
                    chunks[-1].chunk_id = self._make_id(rel_path, f"cls_{node.name}_fn_{item.name}")

    # ─── Markdown 청킹 (Table-Aware, SurfSense 패턴) ────────

    # Markdown 테이블 블록 감지 정규식
    _TABLE_BLOCK_RE: re.Pattern[str] = re.compile(
        r"(?:(?:^|\n)(?=[ \t]*\|)(?:[ \t]*\|[^\n]*\n)+)",
        re.MULTILINE,
    )

    def _chunk_markdown(self, rel_path: str, content: str) -> list[CodeChunk]:
        """Table-aware Markdown 청킹.

        SurfSense의 chunk_text_hybrid() 패턴을 적용하여:
        1. Markdown 테이블 블록은 분할하지 않고 통째로 하나의 청크로 보존
        2. 테이블 사이의 일반 텍스트는 기존 헤딩 기반 청킹 적용
        """
        chunks: list[CodeChunk] = []
        cursor = 0
        table_idx = 0

        for match in self._TABLE_BLOCK_RE.finditer(content):
            # 테이블 이전의 일반 텍스트 → 헤딩 기반 청킹
            raw_prose = content[cursor : match.start()]
            prose = raw_prose.strip()
            if prose:
                abs_start = content[:cursor].count("\n") + 1
                chunks.extend(
                    self._chunk_markdown_prose(rel_path, prose, raw_prose, abs_start),
                )

            # 테이블 블록 → 통째로 하나의 청크
            raw_block = match.group(0)
            table_block = raw_block.strip()
            if table_block:
                # RAG-02 — raw_block은 선행 "\n"을 포함할 수 있다(파일 시작 "^" 앵커
                # 제외). 첫 행의 absolute line은 블록 본문 시작 지점에서 센다.
                block_body_start = match.start() + (1 if raw_block.startswith("\n") else 0)
                line_offset = content[:block_body_start].count("\n") + 1
                table_lines = table_block.count("\n") + 1
                chunks.append(
                    CodeChunk(
                        chunk_id=self._make_id(rel_path, f"table_{table_idx}"),
                        file_path=rel_path,
                        node_type="table",
                        node_name=f"table_{table_idx}",
                        content=table_block[:MAX_CHUNK_CHARS],
                        start_line=line_offset,
                        end_line=line_offset + table_lines - 1,
                    ),
                )
                table_idx += 1

            cursor = match.end()

        # 마지막 테이블 이후의 텍스트
        raw_trailing = content[cursor:]
        trailing = raw_trailing.strip()
        if trailing:
            abs_start = content[:cursor].count("\n") + 1
            chunks.extend(
                self._chunk_markdown_prose(rel_path, trailing, raw_trailing, abs_start),
            )

        return chunks if chunks else self._chunk_generic(rel_path, content)

    def _chunk_markdown_prose(
        self,
        rel_path: str,
        prose: str,
        prose_source: str = "",
        abs_start_line: int = 1,
    ) -> list[CodeChunk]:
        """Markdown 산문(비-테이블) 텍스트를 헤딩 기준으로 분할합니다.

        RAG-01: 반복 heading("## 개요"가 문서에 3번)도 고유 ID를 갖도록
        정규화된 heading 경로 + 섹션 ordinal을 ID 원료로 사용한다.

        RAG-02: ``prose_source``는 strip 전 원문 조각, ``abs_start_line``은
        그 조각이 원문에서 시작하는 1-based absolute line이다. 라인 계산은
        strip 전 기준으로 수행해, 표 뒤 산문·빈 줄 등 어떤 입력이어도
        start_line/end_line이 원문 absolute line과 일치한다. 인자 생략 시
        ``prose`` 자체가 원문 전체로 간주된다 (하위 호환).
        """
        prose_source = prose_source or prose
        chunks: list[CodeChunk] = []
        current_section = ""
        current_title = "intro"
        section_start = 1
        section_ordinal = 0
        used_ids: set[str] = set()

        # RAG-02 — strip 전 원문 위치에서 absolute line number를 직접 계산한다.
        # 각 prose 라인의 absolute line = abs_start_line + (strip으로 사라진
        # 선행 개행 수) + (0-based 라인 인덱스). 마지막 라인의 개행은 라인
        # 종결자로 취급한다 (개행이 있으면 다음 "빈" 라인을 가리키지 않음).
        leading_newlines = len(prose_source) - len(prose_source.lstrip("\n"))
        prose_lines = prose.split("\n")
        if prose_lines and prose_lines[-1] == "":
            prose_lines.pop()  # strip된 prose는 후행 개행을 갖지 않는다 — 방어
        last_line_abs = abs_start_line + leading_newlines + len(prose_lines) - 1

        def _emit(end_line: int) -> None:
            nonlocal section_ordinal
            if not current_section.strip():
                return
            chunk = CodeChunk(
                chunk_id=self._make_unique_id(
                    rel_path,
                    f"sec_{section_ordinal:03d}_{current_title}",
                    current_section,
                    section_ordinal,
                    used_ids,
                ),
                file_path=rel_path,
                node_type="text_section",
                node_name=current_title,
                content=current_section[:MAX_CHUNK_CHARS],
                start_line=abs_start_line + leading_newlines + section_start - 1,
                end_line=end_line,
            )
            used_ids.add(chunk.chunk_id)
            chunks.append(chunk)
            section_ordinal += 1

        for i, line in enumerate(prose_lines, 1):
            if line.startswith("#"):
                _emit(abs_start_line + leading_newlines + i - 2)  # 이전 라인 (0행은 스킵)
                current_title = line.lstrip("#").strip()[:60]
                current_section = line + "\n"
                section_start = i
            else:
                current_section += line + "\n"

        _emit(last_line_abs)

        return chunks

    # ─── 일반 텍스트 청킹 ────────────────────────────────────

    def _chunk_generic(self, rel_path: str, content: str) -> list[CodeChunk]:
        """확장자에 무관하게 고정 크기로 분할합니다."""
        chunks: list[CodeChunk] = []
        lines = content.split("\n")
        total_lines = len(lines)

        # ~50줄 단위로 분할
        chunk_size = 50
        for i in range(0, total_lines, chunk_size):
            chunk_lines = lines[i : i + chunk_size]
            text = "\n".join(chunk_lines)
            if not text.strip():
                continue

            chunks.append(
                CodeChunk(
                    chunk_id=self._make_id(rel_path, f"chunk_{i}"),
                    file_path=rel_path,
                    node_type="text_section",
                    node_name=f"lines_{i + 1}_{min(i + chunk_size, total_lines)}",
                    content=text[:MAX_CHUNK_CHARS],
                    start_line=i + 1,
                    end_line=min(i + chunk_size, total_lines),
                ),
            )

        return chunks

    # ─── 유틸리티 ─────────────────────────────────────────────

    @staticmethod
    def _make_id(file_path: str, suffix: str) -> str:
        """안정적인 청크 ID를 생성합니다."""
        raw = f"{file_path}::{suffix}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _make_unique_id(
        file_path: str,
        suffix: str,
        content: str,
        ordinal: int,
        used: set[str],
    ) -> str:
        """RAG-01 — 충돌 없는 고유 청크 ID.

        ID 구성: canonical file + structural suffix + ordinal + content digest.
        반복 heading("## 개요"가 3번)·60자 공통 prefix·여러 intro가 같은 suffix로
        수렴해도 ordinal이 갈라놓고, 동일 ordinal 재충돌은 content digest가 갈라놓는다.
        무변경 재색인에서는 같은 입력 → 같은 ID (stable).
        """
        base = f"{file_path}::{ordinal:04d}::{suffix}"
        digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        candidate = RAGIndexer._make_id(base, digest)
        # digest까지 충돌하는 극단 케이스 — ordinal 재스캔으로 마무리
        bump = 0
        while candidate in used:
            bump += 1
            candidate = RAGIndexer._make_id(f"{base}#{bump}", digest)
        return candidate

    @staticmethod
    def _decorator_name(node: ast.expr) -> str:
        """데코레이터 이름을 추출합니다."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return RAGIndexer._decorator_name(node.func)
        return "unknown"
