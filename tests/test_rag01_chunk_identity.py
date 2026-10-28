"""RAG-01 — 충돌 없는 chunk identity와 재색인 검증.

docs/11_COMMERCIAL_GA_100_PLAN.md §RAG-01 수용 기준:
- 반복 heading, 60자 공통 prefix, 여러 intro, 표 혼합 문서의 모든 ID가 고유하다.
- 동일 파일 무변경 재색인은 ID가 안정적이고 duplicate가 없다.
- 수정/삭제 뒤 stale vector가 없다.
- 실제 Chroma reopen에서 모든 chunk가 검색된다.

실행: uv run --no-sync pytest tests/test_rag01_chunk_identity.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antigravity_k.engine.rag_indexer import RAGIndexer
from tests._legacy_fake_embedding import legacy_fake_binding  # noqa: F401  # r29 explicit fake binding

pytestmark = pytest.mark.usefixtures("legacy_fake_binding")

chromadb = pytest.importorskip("chromadb", reason="RAG-01 acceptance requires the rag extra")


class TestUniqueIds:
    def test_repeated_headings_get_unique_ids(self, tmp_path: Path) -> None:
        """AC-1: 반복 heading("## 개요" ×3)의 모든 chunk ID가 고유하다."""
        doc = (
            "# 가이드\n\nintro 첫머리.\n\n## 개요\n\n첫 번째 개요 내용입니다.\n\n"
            "## 상세\n\n상세 내용.\n\n## 개요\n\n두 번째 개요 내용입니다.\n\n"
            "## 마무리\n\n마무리.\n\n## 개요\n\n세 번째 개요 내용입니다.\n"
        )
        (tmp_path / "repeat.md").write_text(doc, encoding="utf-8")
        indexer = RAGIndexer(str(tmp_path), vector_store=None)
        chunks = indexer._chunk_markdown(str(tmp_path / "repeat.md"), doc)

        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), f"중복 ID: {ids}"
        # intro를 포함한 섹션 개수 검증
        assert len(chunks) >= 6

    def test_long_common_prefix_docs_get_unique_ids(self, tmp_path: Path) -> None:
        """AC-2: 60자 공통 prefix를 가진 여러 문서가 충돌하지 않는다."""
        common = "A" * 80
        for n in range(3):
            (tmp_path / f"prefix_{n}.md").write_text(
                f"# 공통\n\n{common} 문서 {n} 고유 내용.\n",
                encoding="utf-8",
            )
        indexer = RAGIndexer(str(tmp_path), vector_store=None)
        all_ids: list[str] = []
        for n in range(3):
            content = (tmp_path / f"prefix_{n}.md").read_text(encoding="utf-8")
            chunks = indexer._chunk_markdown(f"prefix_{n}.md", content)
            all_ids.extend(c.chunk_id for c in chunks)
        assert len(all_ids) == len(set(all_ids)), "파일 간 ID 충돌"

    def test_multiple_intros_unique(self, tmp_path: Path) -> None:
        """AC-3: heading 없는 여러 intro 블록(연속 일반 텍스트)도 고유하다."""
        doc = "intro 블록 하나.\n\nintro 블록 둘.\n\nintro 블록 셋.\n"
        (tmp_path / "intros.md").write_text(doc, encoding="utf-8")
        indexer = RAGIndexer(str(tmp_path), vector_store=None)
        chunks = indexer._chunk_markdown(str(tmp_path / "intros.md"), doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_mixed_table_doc_unique_ids(self, tmp_path: Path) -> None:
        """AC-4: 표 혼합 문서의 모든 ID가 고유하다."""
        doc = (
            "# 표 문서\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n본문.\n\n"
            "| c | d |\n|---|---|\n| 3 | 4 |\n\n## 개요\n\n같은 헤딩.\n\n## 개요\n\n또 같은 헤딩.\n"
        )
        (tmp_path / "tables.md").write_text(doc, encoding="utf-8")
        indexer = RAGIndexer(str(tmp_path), vector_store=None)
        chunks = indexer._chunk_markdown(str(tmp_path / "tables.md"), doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestStableReindex:
    def test_unchanged_reindex_is_stable_and_duplicate_free(self, tmp_path: Path) -> None:
        """AC-5: 동일 파일 무변경 재색인 — ID 안정 + duplicate 0."""
        from antigravity_k.engine.vector_store import VectorStore

        (tmp_path / "doc.md").write_text(
            "# 제목\n\n내용입니다.\n\n## 개요\n\n개요 내용.\n\n## 개요\n\n두 번째 개요.\n",
            encoding="utf-8",
        )
        store = VectorStore(str(tmp_path / "chroma"), collection_name="rag01")
        indexer = RAGIndexer(str(tmp_path), vector_store=store)

        _first_count = indexer.index_project()
        first_export = {item["id"] for item in store.export_all()}

        # 무변경 재색인 — 변경 감지 해시가 스킵하므로 신규 0, 저장소는 동일
        second_count = indexer.index_project()
        second_export = {item["id"] for item in store.export_all()}

        assert second_count == 0  # 무변경 → 신규 인덱싱 없음
        assert second_export == first_export
        # 강제 재색인(index_file)에서도 ID가 동일하게 재생성된다
        _ = indexer.index_file(str(tmp_path / "doc.md"))
        third_export = {item["id"] for item in store.export_all()}
        assert third_export == first_export, "재색인 시 ID가 불안정"

    def test_modify_and_delete_leave_no_stale_vectors(self, tmp_path: Path) -> None:
        """AC-6: 수정/삭제 뒤 stale vector가 없다."""
        from antigravity_k.engine.vector_store import VectorStore

        f = tmp_path / "doc.md"
        f.write_text("# v1\n\n첫 버전 내용.\n", encoding="utf-8")
        store = VectorStore(str(tmp_path / "chroma"), collection_name="rag01")
        indexer = RAGIndexer(str(tmp_path), vector_store=store)
        _ = indexer.index_project()

        # 수정 — 이전 내용의 vector가 남으면 안 된다
        f.write_text("# v2\n\n완전히 다른 두 번째 버전의 내용입니다.\n", encoding="utf-8")
        _ = indexer.index_file(str(f))
        after_modify = store.export_all()
        assert all("첫 버전" not in str(item["document"]) for item in after_modify)

        # 삭제 — 파일의 vector가 모두 사라진다
        f.unlink()
        _ = indexer.sync()
        assert store.export_all() == [], "삭제 후 stale vector 잔존"

    def test_chroma_reopen_finds_all_chunks(self, tmp_path: Path) -> None:
        """AC-7: 실제 Chroma reopen에서 모든 chunk가 검색된다."""
        from antigravity_k.engine.vector_store import VectorStore

        for n in range(3):
            (tmp_path / f"doc_{n}.md").write_text(
                f"# 문서 {n}\n\n고유 검색 대상 내용 번호 {n}.\n\n## 개요\n\n개요 {n}.\n",
                encoding="utf-8",
            )
        chroma_dir = tmp_path / "chroma"
        store = VectorStore(str(chroma_dir), collection_name="rag01")
        indexer = RAGIndexer(str(tmp_path), vector_store=store)
        indexed = indexer.index_project()
        assert indexed > 0
        expected_ids = {item["id"] for item in store.export_all()}

        # reopen — 새 VectorStore 인스턴스가 동일 컬렉션을 연다
        reopened = VectorStore(str(chroma_dir), collection_name="rag01")
        reopened_ids = {item["id"] for item in reopened.export_all()}
        assert reopened_ids == expected_ids
        assert len(reopened_ids) == indexed
