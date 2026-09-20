"""Vector Store module."""

import logging
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType
from typing import Protocol, cast, final

# 선택적 의존성. import 실패 시 전체 런타임 부팅을 막지 않도록 방어 로드.
# chromadb는 VectorStore 인스턴스 생성 시점에만 필요하다.
chromadb: object | None = None
SharedSystemClient: object | None = None
Settings: object | None = None
_chroma_available = False
_chroma_import_error: BaseException | None = None

try:
    import chromadb as _chromadb
    from chromadb.api.shared_system_client import SharedSystemClient as _SharedSystemClient
    from chromadb.config import Settings as _Settings

    chromadb = _chromadb
    SharedSystemClient = _SharedSystemClient
    Settings = _Settings
    _chroma_available = True
except Exception as _chroma_exc:  # pragma: no cover - 환경 의존적 의존성 로드 실패  # noqa: BLE001
    _chroma_import_error = _chroma_exc

logger = logging.getLogger(__name__)


MetadataValue = str | int | float | bool


class _CollectionLike(Protocol):
    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, MetadataValue]],
    ) -> object: ...

    def query(self, *, query_texts: list[str], n_results: int) -> dict[str, object]: ...

    def get(self, include: list[str] | None = None) -> dict[str, object]: ...

    def delete(
        self,
        *,
        where: dict[str, str] | None = None,
        ids: list[str] | None = None,
    ) -> object: ...

    def count(self) -> int: ...


class _ClientLike(Protocol):
    def get_or_create_collection(self, *, name: str) -> _CollectionLike: ...


@final
class VectorStore:
    """ChromaDB-backed vector store for RAG chunk storage and retrieval."""

    def __init__(self, persist_directory: str, collection_name: str = "vault_notes"):
        """Initialize the VectorStore.

        Args:
            persist_directory (str): str persist directory.
            collection_name (str): str collection name.

        """
        import os

        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        self._closed = False
        self.client: _ClientLike | None = None
        self.collection: _CollectionLike | None = None

        if not _chroma_available:
            message = f"VectorStore requires chromadb but it is unavailable: {type(_chroma_import_error).__name__}: {_chroma_import_error}"
            raise RuntimeError(message)

        chroma_module = chromadb
        if chroma_module is None:
            raise RuntimeError("ChromaDB module is unavailable")
        persistent_client = cast(Callable[..., _ClientLike], getattr(chroma_module, "PersistentClient"))
        try:
            self.client = persistent_client(path=self.persist_directory)
        except KeyError:
            # ChromaDB SharedSystemClient 캐시 충돌 시 Settings 으로 재시도
            logger.warning("ChromaDB 캐시 충돌 감지, Settings 모드로 재초기화합니다.")
            settings_factory = cast(Callable[..., object], Settings)
            settings = settings_factory(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.persist_directory,
                anonymized_telemetry=False,
            )
            try:
                self.client = persistent_client(
                    path=self.persist_directory,
                    settings=settings,
                )
            except Exception:
                # 최종 폴백: 인메모리 클라이언트
                logger.exception("PersistentClient 실패, 인메모리 ChromaDB로 폴백합니다.")
                client_factory = cast(Callable[[], _ClientLike], getattr(chroma_module, "Client"))
                self.client = client_factory()

        # Get or create the collection.
        client = self.client
        self.collection = client.get_or_create_collection(name=collection_name)
        logger.info(
            "Initialized ChromaDB VectorStore at %s, collection: %s",
            persist_directory,
            collection_name,
        )

    def close(self) -> None:
        """ChromaDB 클라이언트 연결을 정리합니다."""
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            close = getattr(self.client, "close", None)
            if callable(close):
                _ = close()
        except Exception:
            logger.exception("VectorStore: chromadb client close 실패")
        finally:
            try:
                clear_system_cache = getattr(SharedSystemClient, "clear_system_cache", None)
                if callable(clear_system_cache):
                    _ = clear_system_cache()
            except Exception:
                logger.exception("VectorStore: clear_system_cache 실패")
            self.client = None

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_collection(self) -> _CollectionLike:
        collection = self.collection
        if collection is None:
            raise RuntimeError("VectorStore collection is unavailable")
        return collection

    def upsert_chunks(self, chunks: Sequence[Mapping[str, object]]) -> None:
        """Upsert a list of chunk dictionaries into ChromaDB.

        Each chunk should have 'id', 'text', and 'metadata'.
        """
        if not chunks:
            return

        ids = [str(chunk["id"]) for chunk in chunks]
        documents = [str(chunk["text"]) for chunk in chunks]

        # Chroma metadata requires values to be str, int, float, or bool.
        # We need to sanitize the metadata dictionaries.
        metadatas: list[dict[str, MetadataValue]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata")
            metadata_map: Mapping[object, object] = (
                cast(Mapping[object, object], metadata) if isinstance(metadata, Mapping) else {}
            )
            safe_meta: dict[str, MetadataValue] = {}
            for raw_key, v in metadata_map.items():
                k = str(raw_key)
                if isinstance(v, (str, int, float, bool)):
                    safe_meta[k] = v
                elif isinstance(v, list):
                    # Convert list to comma-separated string
                    safe_meta[k] = ", ".join(str(x) for x in cast(list[object], v))
                else:
                    safe_meta[k] = str(v)
            metadatas.append(safe_meta)
        _ = self._require_collection().upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Upserted %s chunks into ChromaDB.", len(chunks))

    def store_embedding(self, source_table: str, source_id: int, text: str) -> bool:
        self.upsert_chunks(
            [
                {
                    "id": f"{source_table}:{source_id}",
                    "text": text,
                    "metadata": {"source_table": source_table, "source_id": source_id},
                },
            ],
        )
        return True

    def search_similar(
        self,
        query: str,
        source_table: str,
        top_k: int = 10,
    ) -> list[dict[str, object]]:
        matches = self.search(query, n_results=top_k)
        results: list[dict[str, object]] = []
        for match in matches:
            raw_metadata = match.get("metadata", {})
            metadata: Mapping[str, object] = (
                cast(Mapping[str, object], raw_metadata) if isinstance(raw_metadata, Mapping) else {}
            )
            if metadata.get("source_table") != source_table:
                continue
            distance = match.get("distance")
            distance_value = float(distance) if isinstance(distance, (int, float)) else None
            similarity = 1.0 / (1.0 + distance_value) if distance_value is not None else 0.0
            results.append(
                {
                    "source_id": metadata.get("source_id"),
                    "similarity": similarity,
                },
            )
        return results

    def delete_embedding(self, source_table: str, source_id: int) -> bool:
        """한 임베딩만 지운다 — 색인에서 **그 항목 하나**를 무효화하는 유일한 방법이다.

        `clear()` 를 대신 쓰면 안 된다: 그 컬렉션에는 vault note 청크까지 들어 있어서, 기억 하나를
        지우는 일이 **남의 색인**을 지운다. 그래서 삭제는 `{source_table}:{source_id}` id 하나로 한다.

        돌려주는 값은 "지웠다" 가 아니라 "지우려 시도했고 실패가 없었다" 는 뜻이다(색인에 원래
        없던 항목을 지워도 참이다) — 색인의 진실은 `search_similar` 로 확인한다.
        """
        embedding_id = f"{source_table}:{source_id}"
        try:
            _ = self._require_collection().delete(ids=[embedding_id])
        except Exception:
            logger.exception("Failed to delete embedding %s", embedding_id)
            return False
        return True

    def fit_tfidf(self, documents: list[str]) -> None:
        _ = documents
        return None

    def get_stats(self) -> dict[str, object]:
        count = self.collection.count() if self.collection is not None else 0
        return {"available": True, "persist_directory": self.persist_directory, "count": count}

    def delete_file_chunks(self, file_path: str) -> None:
        """Delete all chunks belonging to a specific file.

        Useful when a file is deleted or completely rewritten.
        """
        try:
            self.delete_file_chunks_strict(file_path)
            logger.info("Deleted chunks for file: %s", file_path)
        except Exception:
            logger.exception("Error deleting chunks for %s", file_path)

    def delete_file_chunks_strict(self, file_path: str) -> None:
        _ = self._require_collection().delete(where={"source": file_path})

    def clear(self) -> int:
        ids = cast(list[str], self._require_collection().get().get("ids") or [])
        if ids:
            _ = self._require_collection().delete(ids=ids)
        return len(ids)

    def export_all(self) -> list[dict[str, object]]:
        payload = self._require_collection().get(include=["documents", "metadatas"])
        ids = cast(list[str], payload.get("ids") or [])
        documents = cast(list[str], payload.get("documents") or [])
        metadatas = cast(list[dict[str, object]], payload.get("metadatas") or [])
        return [
            {
                "id": node_id,
                "document": documents[index] if index < len(documents) else "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
            for index, node_id in enumerate(ids)
        ]

    def redact_all(self) -> int:
        from antigravity_k.engine.secret_scanner import redact_full

        payload = self._require_collection().get(include=["documents", "metadatas"])
        ids = cast(list[str], payload.get("ids") or [])
        documents = cast(list[str], payload.get("documents") or [])
        metadatas = cast(list[dict[str, object]], payload.get("metadatas") or [])
        safe_documents = [redact_full(document or "") for document in documents]
        safe_metadatas: list[dict[str, object]] = [
            {key: redact_full(value) if isinstance(value, str) else value for key, value in metadata.items()}
            for metadata in metadatas
        ]
        changed = sum(old != new for old, new in zip(documents, safe_documents, strict=False))
        if ids:
            collection = self._require_collection()
            _ = collection.upsert(
                ids=ids,
                documents=safe_documents,
                metadatas=cast(list[dict[str, MetadataValue]], safe_metadatas),
            )
        return changed

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        return 0

    def search(self, query: str, n_results: int = 5) -> list[dict[str, object]]:
        """Search for the most relevant chunks given a query string."""
        results = self._require_collection().query(query_texts=[query], n_results=n_results)

        # Format results
        formatted_results: list[dict[str, object]] = []
        ids_val = cast(list[list[str]], results.get("ids") or [])
        if ids_val and ids_val[0]:
            for i in range(len(ids_val[0])):
                docs_val = cast(list[list[str]], results.get("documents") or [])
                metadatas = cast(list[list[dict[str, object]]], results.get("metadatas") or [])
                metadata_val: dict[str, object] = {}
                if metadatas:
                    try:
                        metadata_val = dict(metadatas[0][i]) if len(metadatas) > 0 else {}
                    except (IndexError, TypeError):
                        metadata_val = {}
                distances = cast(list[list[float]], results.get("distances") or [])
                distance_val: float | None = None
                if distances:
                    try:
                        distance_val = float(distances[0][i])
                    except (IndexError, TypeError):
                        distance_val = None
                formatted_results.append(
                    {
                        "id": ids_val[0][i] if ids_val else "",
                        "text": docs_val[0][i] if docs_val else "",
                        "metadata": metadata_val,
                        "distance": distance_val,
                    },
                )
        return formatted_results
