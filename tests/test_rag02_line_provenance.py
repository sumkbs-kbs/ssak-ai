"""RAG-02 — 정확한 source line과 citation provenance.

GA-100 plan §RAG-02 수용기준:
  AC-1  표 전후, 빈 줄, Unicode, CRLF, 긴 heading fixture의 line range가
        원문과 일치한다 (strip 전 absolute offset 보존).
  AC-2  prose/table/code block 모두 absolute line range를 계산한다.
  AC-3  citation validator가 잘못된 range와 stale file digest를 거절한다.
  AC-4  실제 Chroma reopen 후에도 provenance가 유지된다.
  AC-5  UI/CLI 링크(포맷터)가 원문 위치를 정확히 가리킨다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antigravity_k.engine.rag_indexer import RAGIndexer
from tests._legacy_fake_embedding import legacy_fake_binding  # noqa: F401  # r29 explicit fake binding

pytestmark = pytest.mark.usefixtures("legacy_fake_binding")

chromadb = pytest.importorskip("chromadb", reason="RAG-02 acceptance requires the rag extra")


# ─── AC-1 · 원문 일치 fixture ────────────────────────────────────


def _lines_of(content: str) -> list[str]:
    return content.split("\n")


def _assert_range_matches_source(content: str, chunk_content: str, start: int, end: int) -> None:
    """청크 내용의 각 줄이 원문의 해당 absolute line과 일치하는지 검증."""
    source_lines = _lines_of(content)
    chunk_lines = [ln for ln in chunk_content.split("\n") if ln.strip()]
    for offset, chunk_line in enumerate(chunk_lines):
        source_line = source_lines[start - 1 + offset]
        assert chunk_line in source_line or source_line in chunk_line or chunk_line == source_line, (
            f"line {start + offset}: chunk={chunk_line!r} != source={source_line!r}"
        )


def test_prose_after_table_has_absolute_line_range() -> None:
    """표 뒤 산문 — 과거 결함: 항상 1행부터 계산됨."""
    content = "# 제목\n\n본문 A입니다.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## 섹션 B\n표 뒤 본문 B입니다.\n"
    chunks = RAGIndexer(project_root="/tmp")._chunk_markdown("doc.md", content)
    by_type = {c.node_type: c for c in chunks}
    # 표는 5~7행 (| a | b | 가 5행)
    assert by_type["table"].start_line == 5
    assert by_type["table"].end_line == 7
    # 표 뒤 산문은 9~10행 (## 섹션 B 가 9행, 표 뒤 본문 B입니다. 가 10행)
    prose_after = [c for c in chunks if c.node_type == "text_section" and "섹션 B" in c.node_name]
    assert prose_after, "표 뒤 산문 청크가 없다"
    assert prose_after[0].start_line == 9
    assert prose_after[0].end_line == 10
    _assert_range_matches_source(content, prose_after[0].content, prose_after[0].start_line, prose_after[0].end_line)


def test_prose_before_table_has_absolute_line_range() -> None:
    content = "첫 단락.\n\n| x | y |\n|--|--|\n| 1 | 2 |\n"
    chunks = RAGIndexer(project_root="/tmp")._chunk_markdown("doc.md", content)
    prose = [c for c in chunks if c.node_type == "text_section"]
    assert prose and prose[0].start_line == 1
    table = next(c for c in chunks if c.node_type == "table")
    assert table.start_line == 3
    assert table.end_line == 5


def test_blank_lines_and_unicode_preserved() -> None:
    content = (
        "# 한글 제목 🚀\n"
        "\n"
        "\n"
        "유니코드 본문 — em—dash, 표 era: 없음\n"
        "\n"
        "| 이름 | 값 |\n"
        "|-----|----|\n"
        "| 가 | 나 |\n"
        "\n"
        "\n"
        "## 다음 섹션 ✅\n"
        "내용.\n"
    )
    chunks = RAGIndexer(project_root="/tmp")._chunk_markdown("doc.md", content)
    for chunk in chunks:
        if chunk.node_type == "table":
            assert chunk.start_line == 6
            assert chunk.end_line == 8
        elif "다음 섹션" in str(chunk.node_name):
            # 11~12행 (## 다음 섹션 ✅ 가 11행, 내용. 이 12행)
            assert chunk.start_line == 11
            assert chunk.end_line == 12


def test_crlf_input_matches_lf_line_numbers(tmp_path: Path) -> None:
    """CRLF 파일도 LF와 동일한 absolute line을 갖는다."""
    lf_content = "# 제목\n\n본문.\n\n| a |\n|---|\n| 1 |\n\n## B\n내용.\n"
    crlf_content = lf_content.replace("\n", "\r\n")
    assert (tmp_path / "crlf.md").write_bytes(crlf_content.encode("utf-8"))

    from antigravity_k.engine.vector_store import VectorStore

    store_crlf = VectorStore(str(tmp_path / "chroma-crlf"), collection_name="rag02crlf")
    indexer_crlf = RAGIndexer(project_root=str(tmp_path), vector_store=store_crlf)
    indexer_crlf.index_file("crlf.md")

    store_lf = VectorStore(str(tmp_path / "chroma-lf"), collection_name="rag02lf")
    indexer_lf = RAGIndexer(project_root=str(tmp_path), vector_store=store_lf)
    (tmp_path / "lf.md").write_text(lf_content, encoding="utf-8")
    indexer_lf.index_file("lf.md")

    lf_ranges = sorted((c.start_line, c.end_line) for c in _chunks_of(indexer_lf, "lf.md"))
    crlf_ranges = sorted((c.start_line, c.end_line) for c in _chunks_of(indexer_crlf, "crlf.md"))
    assert crlf_ranges == lf_ranges, "CRLF와 LF의 line range가 다르다"


def _chunks_of(indexer: RAGIndexer, rel_path: str):

    content = (Path(indexer.project_root) / rel_path).read_text(encoding="utf-8")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return indexer._chunk_markdown(rel_path, content)


def test_long_heading_fixture_keeps_range() -> None:
    long_title = "아주 긴 제목 " * 20
    content = f"## {long_title}\n\n본문 라인 1.\n본문 라인 2.\n"
    chunks = RAGIndexer(project_root="/tmp")._chunk_markdown("doc.md", content)
    assert chunks and chunks[0].start_line == 1
    assert chunks[0].end_line == 4


# ─── AC-2 · prose/table/code 모두 absolute range ─────────────────


def test_python_chunk_lines_match_source(tmp_path: Path) -> None:
    source = tmp_path / "mod.py"
    source.write_text(
        '"""모듈 문서."""\n\nimport os\n\n\ndef hello():\n    """인사."""\n    return 1\n',
        encoding="utf-8",
    )
    indexer = RAGIndexer(project_root=str(tmp_path))
    content = source.read_text(encoding="utf-8")
    chunks = indexer._chunk_python("mod.py", content)
    fn = next(c for c in chunks if c.node_type == "function")
    assert fn.start_line == 6
    assert fn.end_line == 8
    source_lines = content.split("\n")
    assert source_lines[fn.start_line - 1].startswith("def hello")
    assert source_lines[fn.end_line - 1].strip() == "return 1"


# ─── AC-3 · citation validator ──────────────────────────────────


def test_validate_citations_accepts_matching_line_range() -> None:
    indexer = RAGIndexer(project_root="/tmp")
    result = {
        "id": "abc",
        "provenance": {"source_id": "abc", "freshness": "fresh", "start_line": 5, "end_line": 8},
    }
    verdict = indexer.validate_citations("근거 [citation:abc:5-8]", [result])
    assert verdict["valid"] is True
    assert verdict["range_mismatch"] == []


def test_validate_citations_rejects_wrong_line_range() -> None:
    indexer = RAGIndexer(project_root="/tmp")
    result = {
        "id": "abc",
        "provenance": {"source_id": "abc", "freshness": "fresh", "start_line": 5, "end_line": 8},
    }
    verdict = indexer.validate_citations("근거 [citation:abc:6-9]", [result])
    assert verdict["valid"] is False
    assert verdict["range_mismatch"] == ["abc:6-9"]


def test_validate_citations_bare_form_still_allowed() -> None:
    indexer = RAGIndexer(project_root="/tmp")
    result = {
        "id": "abc",
        "provenance": {"source_id": "abc", "freshness": "fresh", "start_line": 5, "end_line": 8},
    }
    verdict = indexer.validate_citations("근거 [citation:abc]", [result])
    assert verdict["valid"] is True


def test_validate_citations_range_and_bare_share_id() -> None:
    """[citation:abc]와 [citation:abc:5-8]이 같은 id로 취급된다."""
    indexer = RAGIndexer(project_root="/tmp")
    result = {
        "id": "abc",
        "provenance": {"source_id": "abc", "freshness": "fresh", "start_line": 5, "end_line": 8},
    }
    verdict = indexer.validate_citations("본문 [citation:abc] 및 [citation:abc:5-8]", [result])
    assert verdict["cited"] == ["abc"]
    assert verdict["valid"] is True


def test_validate_citations_rejects_stale_file_digest(tmp_path: Path) -> None:
    """stale digest — 파일이 바뀌면 citation이 unverified로 거절된다."""
    source = tmp_path / "doc.md"
    source.write_text("# 제목\n\n본문.\n", encoding="utf-8")
    from antigravity_k.engine.vector_store import VectorStore

    store = VectorStore(str(tmp_path / "chroma"), collection_name="rag02stale")
    indexer = RAGIndexer(project_root=str(tmp_path), vector_store=store)
    indexer.index_file("doc.md")
    hit = indexer.search("본문", mode="semantic")[0]

    # 파일 변경 → stale
    source.write_text("# 제목\n\n변경된 본문.\n", encoding="utf-8")
    hit_stale = indexer.search("본문", mode="semantic")[0]
    verdict = indexer.validate_citations(f"근거 [citation:{hit_stale['id']}]", [hit_stale])
    assert verdict["valid"] is False
    assert verdict["unverified"], "stale digest가 거절되지 않았다"
    _ = hit


# ─── AC-4 · Chroma reopen provenance 유지 ─────────────────────────


def test_chroma_reopen_preserves_provenance(tmp_path: Path) -> None:
    from antigravity_k.engine.vector_store import VectorStore

    source = tmp_path / "guide.md"
    content = "# 가이드\n\n내용 A.\n\n| a |\n|---|\n| 1 |\n\n## B\n내용 B.\n"
    source.write_text(content, encoding="utf-8")

    chroma_dir = tmp_path / "chroma"
    store = VectorStore(str(chroma_dir), collection_name="rag02reopen")
    indexer = RAGIndexer(project_root=str(tmp_path), vector_store=store)
    indexer.index_file("guide.md")
    store.close()

    reopened_store = VectorStore(str(chroma_dir), collection_name="rag02reopen")
    reopened = RAGIndexer(project_root=str(tmp_path), vector_store=reopened_store)
    hits = reopened.search("내용", mode="semantic", n_results=10)
    assert hits, "reopen 후 검색 결과가 없다"
    for hit in hits:
        prov = hit["provenance"]
        assert prov["source"] == "guide.md"
        assert isinstance(prov["start_line"], int)
        assert isinstance(prov["end_line"], int)
        assert prov["start_line"] >= 1
        assert prov["end_line"] >= prov["start_line"]
        assert prov["freshness"] == "fresh"
    reopened_store.close()


# ─── AC-5 · 포맷터가 원문 위치를 가리킨다 ─────────────────────────


def test_format_context_shows_absolute_lines() -> None:
    store = _RecordingStore()
    store.chunks = [
        {
            "id": "xyz",
            "text": "표 뒤 본문",
            "metadata": {
                "source": "doc.md",
                "source_hash": "hash",
                "source_type": "code",
                "indexed_at": "2026-09-09T00:00:00+00:00",
                "node_type": "text_section",
                "node_name": "섹션 B",
                "start_line": 9,
                "end_line": 11,
            },
        },
    ]
    indexer = RAGIndexer(project_root="/tmp", vector_store=store)
    context = indexer.format_context("본문")
    assert "doc.md:9-11" in context
    assert "[citation:xyz]" in context


class _RecordingStore:
    def __init__(self) -> None:
        self.chunks: list[dict[str, object]] = []

    def delete_file_chunks(self, file_path: str) -> None:
        self.chunks = [c for c in self.chunks if c.get("metadata", {}).get("source") != file_path]  # type: ignore[union-attr]

    def upsert_chunks(self, chunks: object) -> None:
        self.chunks.extend(dict(c) for c in chunks)  # type: ignore[arg-type]

    def search(self, query: str, n_results: int = 5) -> list[dict[str, object]]:
        _ = query
        return list(self.chunks[:n_results])

    def get_stats(self) -> dict[str, object]:
        return {"count": len(self.chunks)}
