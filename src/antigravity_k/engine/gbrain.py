"""Global brain — persistent cross-session memory and knowledge synthesis."""

import atexit
import concurrent.futures
import json
import logging
import math
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast, final

import networkx as nx
from filelock import SoftFileLock

logger = logging.getLogger(__name__)

GraphAttributes = dict[str, str | int | float | bool]
ChromaValue = str | int | float | bool
JsonMap = dict[str, object]
RewardPair = tuple[str, str]
_REWARD_DECAY = 0.95
_REWARD_CAP = 10.0
_REWARD_STATE_VERSION = 1
_REWARD_VERSION_KEY = "_gbrain_reward_state_version"
_REWARD_TICK_KEY = "_gbrain_reward_tick"
_REWARD_PAIRS_KEY = "_gbrain_reward_pairs"
if TYPE_CHECKING:
    Graph: TypeAlias = nx.DiGraph[str, GraphAttributes]
else:
    Graph = nx.DiGraph


class _ChromaCollectionOps(Protocol):
    def count(self) -> int: ...

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, ChromaValue]],
    ) -> object: ...

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        where: dict[str, str] | None,
    ) -> JsonMap: ...

    def get(self, *, ids: list[str] | None = None, include: list[str] | None = None) -> JsonMap: ...

    def delete(self, *, ids: list[str]) -> object: ...


class _ChromaClient(Protocol):
    def get_or_create_collection(self, *, name: str) -> _ChromaCollectionOps: ...

    def close(self) -> object: ...


class _ChromaModule(Protocol):
    def PersistentClient(self, *, path: str, settings: object) -> _ChromaClient: ...


class _CollectionBoundary(Protocol):
    deleted: list[str]


class _SettingsFactory(Protocol):
    def __call__(self, *, anonymized_telemetry: bool) -> object: ...


def _read_graphml(path: str) -> Graph:
    reader = cast(Callable[[str], Graph], getattr(nx, "read_graphml"))
    return reader(path)


def _write_graphml(graph: Graph, path: str) -> object:
    writer = cast(Callable[[Graph, str], object], getattr(nx, "write_graphml"))
    return writer(graph, path)


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _as_float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, (int, float))]


def _as_graph_attributes(value: Mapping[object, object]) -> GraphAttributes:
    return {str(key): item for key, item in value.items() if isinstance(item, (str, int, float, bool))}


def _as_chroma_map(value: object) -> dict[str, ChromaValue]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {str(key): item for key, item in raw.items() if isinstance(item, (str, int, float, bool))}


def _collection_or_none(owner: object) -> _ChromaCollectionOps | None:
    value = getattr(owner, "collection", None)
    return cast(_ChromaCollectionOps, value) if value is not None else None


def _capture_collection_records(
    collection: _ChromaCollectionOps,
    ids: list[str] | None = None,
) -> dict[str, tuple[str, dict[str, ChromaValue]]]:
    """Chroma projection의 선택된 records를 실패 보상용으로 복사합니다."""
    payload = collection.get(ids=ids, include=["documents", "metadatas"])
    record_ids = _as_string_list(payload.get("ids", []))
    raw_documents = payload.get("documents", [])
    documents = cast(list[object], raw_documents) if isinstance(raw_documents, list) else []
    raw_metadatas = payload.get("metadatas", [])
    metadatas = cast(list[object], raw_metadatas) if isinstance(raw_metadatas, list) else []
    snapshot: dict[str, tuple[str, dict[str, ChromaValue]]] = {}
    for index, record_id in enumerate(record_ids):
        raw_document = documents[index] if index < len(documents) else ""
        document = raw_document if isinstance(raw_document, str) else ""
        raw_metadata = metadatas[index] if index < len(metadatas) else {}
        snapshot[record_id] = (document, _as_chroma_map(raw_metadata))
    return snapshot


def _restore_collection_records(
    collection: _ChromaCollectionOps,
    affected_ids: list[str],
    snapshot: Mapping[str, tuple[str, dict[str, ChromaValue]]],
) -> None:
    """Chroma write가 실패한 경우 그 projection을 직전 스냅샷으로 복구합니다."""
    to_delete = [record_id for record_id in affected_ids if record_id not in snapshot]
    if to_delete:
        _ = collection.delete(ids=to_delete)
    restore_ids = [record_id for record_id in affected_ids if record_id in snapshot]
    if restore_ids:
        _ = collection.upsert(
            ids=restore_ids,
            documents=[snapshot[record_id][0] for record_id in restore_ids],
            metadatas=[snapshot[record_id][1] for record_id in restore_ids],
        )


# 선택적 의존성. import 실패 시 전체 런타임 부팅을 막지 않도록 방어 로드 (graceful degradation).
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
    Settings = _Settings
    SharedSystemClient = _SharedSystemClient
    _chroma_available = True
except Exception as _chroma_exc:  # pragma: no cover - 환경 의존적 의존성 로드 실패  # noqa: BLE001
    _chroma_import_error = _chroma_exc


@final
class GBrainCorruptSnapshotError(RuntimeError):
    """Raised when an on-disk GraphML/reward snapshot cannot be loaded safely.

    Callers must not treat this as an empty healthy memory. Recovery is explicit
    (`clear_all` on a fresh store, restore from backup, or delete the corrupt file
    under operator control) — never silent empty success.
    """


class GBrain:
    """Ssak-Ai Graph + Vector Memory (GBrain).

    JSONL 파일의 한계를 극복하기 위해, 노드 간 관계(NetworkX)와 의미론적 검색(ChromaDB)을 결합합니다.

    Reward (`reward_score` / `reward_tick`) is **storage write recency/frequency
    metadata only**. It is not semantic truth, confidence, applicability,
    authority, task utility, or cognitive maturity. Promotion status:
    ``experimental_storage_metadata`` — never auto-elevates decision authority.
    """

    REWARD_SEMANTICS = "write_recency_frequency_storage_metadata"
    REWARD_PROMOTION_STATUS = "experimental_storage_metadata"
    # Selection/search consumers must not read reward as ranking authority.
    REWARD_SELECTION_CONSUMERS = ()  # empty: no production path ranks by reward_score

    def __init__(self, storage_dir: str | None = None):
        """Initialize the GBrain.

        Args:
            storage_dir (str | None): str | None storage dir.

        """
        self._mutation_lock = threading.RLock()
        self._closed = False
        self.storage_dir = Path(storage_dir) if storage_dir else Path.home() / ".antigravity" / "gbrain"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._storage_lock = SoftFileLock(str(self.storage_dir / ".gbrain.lock"), timeout=30)

        self.graph_file = self.storage_dir / "knowledge_graph.graphml"

        # 그래프와 보상 state를 같은 잠금으로 읽어 동시 writer의 중간 snapshot을 피한다.
        with self._mutation_lock, self._storage_lock:
            self.graph: Graph
            if self.graph_file.exists():
                try:
                    self.graph = nx.DiGraph(_read_graphml(str(self.graph_file)))
                    self._reward_tick, self._pair_rewards = self._load_reward_state()
                except GBrainCorruptSnapshotError:
                    raise
                except Exception as exc:
                    logger.exception("[GBrain] Failed to load graph")
                    raise GBrainCorruptSnapshotError(
                        f"corrupt or unreadable GBrain snapshot at {self.graph_file}: {exc}"
                    ) from exc
            else:
                self.graph = nx.DiGraph()
                self._reward_tick, self._pair_rewards = self._load_reward_state()

        db_path = self.storage_dir / "chroma"
        db_path.mkdir(exist_ok=True)

        self.chroma_client: _ChromaClient | None = None
        self.collection: _CollectionBoundary = cast(_CollectionBoundary, cast(object, None))

        if _chroma_available and chromadb is not None and Settings is not None:
            try:
                chroma_module = cast(_ChromaModule, chromadb)
                settings_factory = cast(_SettingsFactory, Settings)
                self.chroma_client = chroma_module.PersistentClient(
                    path=str(db_path),
                    settings=settings_factory(anonymized_telemetry=False),
                )
                self.collection = cast(
                    _CollectionBoundary,
                    cast(object, self.chroma_client.get_or_create_collection(name="gbrain_nodes")),
                )
            except Exception:
                logger.exception("[GBrain] chromadb 초기화 실패, 벡터 검색을 비활성화합니다.")
        else:
            logger.warning(
                "[GBrain] chromadb 비활성화 (%s). 벡터 검색 없이 그래프 메모리만 동작합니다.",
                type(_chroma_import_error).__name__,
            )

        # 비동기 백그라운드 저장을 위한 스레드 풀
        self._save_lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def close(self) -> None:
        """ChromaDB 클라이언트 연결과 스레드 풀을 정리합니다."""
        with self._mutation_lock:
            if self._closed:
                return
            self._closed = True
            # 스레드 풀 먼저 종료
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                logger.exception("[GBrain] executor shutdown 실패")
            # ChromaDB 클라이언트 정리
            try:
                close = getattr(self.chroma_client, "close", None)
                if callable(close):
                    _ = close()
            except Exception:
                logger.exception("[GBrain] chromadb client close 실패")
            finally:
                try:
                    clear_system_cache = getattr(SharedSystemClient, "clear_system_cache", None)
                    if callable(clear_system_cache):
                        _ = clear_system_cache()
                except Exception:
                    logger.exception("[GBrain] clear_system_cache 실패")
                self.chroma_client = None

    def __del__(self):
        # Constructor에서 reward state validation이 실패하면 executor/client가 아직 없다.
        if getattr(self, "_closed", True) or not hasattr(self, "_executor"):
            return
        self.close()

    def _load_reward_state(self) -> tuple[int, dict[RewardPair, float]]:
        """GraphML에 저장된 보상 상태를 읽고 기존 그래프는 빈 상태로 마이그레이션합니다."""
        graph_attrs = self.graph.graph
        raw_version = graph_attrs.get(_REWARD_VERSION_KEY)
        has_state = _REWARD_TICK_KEY in graph_attrs or _REWARD_PAIRS_KEY in graph_attrs
        if raw_version is None:
            if has_state:
                raise GBrainCorruptSnapshotError("GBrain reward state is incomplete: missing version")
            return 0, {}
        if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version != _REWARD_STATE_VERSION:
            raise GBrainCorruptSnapshotError(f"Unsupported GBrain reward state version: {raw_version!r}")

        raw_tick = graph_attrs.get(_REWARD_TICK_KEY)
        raw_pairs = graph_attrs.get(_REWARD_PAIRS_KEY)
        if isinstance(raw_tick, bool) or not isinstance(raw_tick, int) or raw_tick < 0:
            raise GBrainCorruptSnapshotError("GBrain reward tick must be a non-negative integer")
        if not isinstance(raw_pairs, str):
            raise GBrainCorruptSnapshotError("GBrain reward pairs must be a JSON string")
        try:
            decoded_pairs = json.loads(raw_pairs)
        except json.JSONDecodeError as exc:
            raise GBrainCorruptSnapshotError("GBrain reward pairs contain invalid JSON") from exc
        if not isinstance(decoded_pairs, list):
            raise GBrainCorruptSnapshotError("GBrain reward pairs must be a list")

        rewards: dict[RewardPair, float] = {}
        for item in decoded_pairs:
            if not isinstance(item, list) or len(item) != 3:
                raise GBrainCorruptSnapshotError("Each GBrain reward entry must contain source, target, and score")
            source_id, target_id, raw_score = item
            if not isinstance(source_id, str) or not isinstance(target_id, str):
                raise GBrainCorruptSnapshotError("GBrain reward pair endpoints must be strings")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise GBrainCorruptSnapshotError("GBrain reward score must be numeric")
            score = float(raw_score)
            pair = (source_id, target_id)
            if not math.isfinite(score) or score <= 0 or score > _REWARD_CAP or pair in rewards:
                raise GBrainCorruptSnapshotError(f"Invalid GBrain reward score for pair {pair!r}")
            rewards[pair] = score
        return raw_tick, rewards

    def _store_reward_state(self) -> None:
        """보상 상태를 GraphML에서 지원하는 scalar graph 속성으로 직렬화합니다."""
        self.graph.graph[_REWARD_VERSION_KEY] = _REWARD_STATE_VERSION
        self.graph.graph[_REWARD_TICK_KEY] = self._reward_tick
        self.graph.graph[_REWARD_PAIRS_KEY] = json.dumps(
            [[source_id, target_id, score] for (source_id, target_id), score in sorted(self._pair_rewards.items())],
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def reward_score(self, source_id: str, target_id: str) -> float:
        """방향성 pair의 현재 보상 점수를 반환합니다(노드 보상은 id, id를 사용).

        Storage metadata only — see ``REWARD_SEMANTICS``. Does not imply
        authority, confidence, or task success.
        """
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            return self._pair_rewards.get((source_id, target_id), 0.0)

    def reward_implies_authority(self) -> bool:
        """Always False: write-reward never promotes semantic truth or authority."""

        return False

    @property
    def reward_tick(self) -> int:
        """이 GBrain 저장소에서 성공적으로 기록한 쓰기 이벤트 수입니다."""
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            return self._reward_tick

    def _refresh_from_disk(self) -> None:
        """잠금 아래 최신 GraphML snapshot을 읽어 외부 인스턴스 쓰기를 반영합니다."""
        if not self.graph_file.exists():
            self.graph = nx.DiGraph()
            self._reward_tick = 0
            self._pair_rewards = {}
            return
        try:
            self.graph = nx.DiGraph(_read_graphml(str(self.graph_file)))
            self._reward_tick, self._pair_rewards = self._load_reward_state()
        except GBrainCorruptSnapshotError:
            raise
        except Exception as exc:
            raise GBrainCorruptSnapshotError(
                f"corrupt or unreadable GBrain snapshot at {self.graph_file}: {exc}"
            ) from exc

    def _record_successful_write(
        self,
        pair: RewardPair,
        mutation: Callable[[], None],
        rollback: Callable[[], None] | None = None,
    ) -> None:
        """저장소 잠금 아래 그래프 mutation과 tick·보상 저장을 공통 적용합니다."""
        with self._mutation_lock:
            if self._closed:
                raise RuntimeError("Cannot write to a closed GBrain instance")

            self._refresh_from_disk()
            graph_before = self.graph.copy()
            tick_before = self._reward_tick
            rewards_before = self._pair_rewards.copy()
            try:
                mutation()
                self._reward_tick += 1
                self._pair_rewards = {
                    current_pair: score * _REWARD_DECAY
                    for current_pair, score in self._pair_rewards.items()
                    if score * _REWARD_DECAY > 0
                }
                self._pair_rewards[pair] = min(_REWARD_CAP, self._pair_rewards.get(pair, 0.0) + 1.0)
                self._store_reward_state()
                self._save_graph().result()
            except BaseException:
                self.graph = graph_before
                self._reward_tick = tick_before
                self._pair_rewards = rewards_before
                if rollback is not None:
                    try:
                        rollback()
                    except Exception:
                        logger.exception("[GBrain] Failed to roll back external write projection")
                raise

    def _save_graph(self) -> concurrent.futures.Future[None]:
        """그래프 snapshot을 임시 파일에 기록한 뒤 원자적으로 교체하는 작업을 예약합니다."""
        # Mutation 방지를 위해 얕은 복사본을 만들어 넘깁니다.
        graph_copy = self.graph.copy()

        def write_task(g: Graph) -> None:
            with self._save_lock:
                file_descriptor, temporary_name = tempfile.mkstemp(
                    dir=self.storage_dir,
                    prefix=f".{self.graph_file.name}.",
                    suffix=".tmp",
                )
                os.close(file_descriptor)
                temporary_path = Path(temporary_name)
                try:
                    _write_graphml(g, str(temporary_path))
                    with temporary_path.open("rb") as graph_file:
                        os.fsync(graph_file.fileno())
                    os.replace(temporary_path, self.graph_file)
                    if os.name == "posix":
                        try:
                            directory_fd = os.open(self.storage_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                        except OSError:
                            logger.debug("[GBrain] Directory fsync unavailable for %s", self.storage_dir)
                        else:
                            try:
                                os.fsync(directory_fd)
                            except OSError:
                                # GraphML 교체는 이미 끝났으므로 저장 성공 여부를 되돌리지 않는다.
                                logger.debug("[GBrain] Directory fsync unavailable for %s", self.storage_dir)
                            finally:
                                os.close(directory_fd)
                except BaseException:
                    logger.exception("[GBrain] Failed to save graph")
                    raise
                finally:
                    temporary_path.unlink(missing_ok=True)

        return self._executor.submit(write_task, graph_copy)

    def add_node(
        self,
        node_id: str,
        label: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """그래프와 벡터DB에 노드를 추가합니다.

        label: "failure", "user_pref", "concept", etc.
        """
        metadata = dict(metadata or {})
        metadata["label"] = label

        # label/content은 명시 속성에 한 번만 기록한다.
        graph_meta = {
            key: value
            for key, value in metadata.items()
            if key not in ("label", "content") and isinstance(value, (str, int, float, bool))
        }
        # ChromaDB metadata values must be str, int, float or bool.
        chroma_meta = {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))}

        with self._mutation_lock, self._storage_lock:
            if self._closed:
                raise RuntimeError("Cannot write to a closed GBrain instance")
            self._refresh_from_disk()
            collection = _collection_or_none(self)
            vector_before = _capture_collection_records(collection, [node_id]) if collection is not None else {}

            def mutation() -> None:
                self.graph.add_node(node_id, label=label, content=content, **graph_meta)
                if collection is not None:
                    _ = collection.upsert(documents=[content], metadatas=[chroma_meta], ids=[node_id])

            rollback: Callable[[], None] | None = None
            if collection is not None:

                def rollback_vector() -> None:
                    _restore_collection_records(collection, [node_id], vector_before)

                rollback = rollback_vector
            self._record_successful_write((node_id, node_id), mutation, rollback=rollback)
        logger.debug("[GBrain] Added node: %s (%s)", node_id, label)

    def add_edge(self, source_id: str, target_id: str, relation: str) -> None:
        """두 노드 간에 관계를 추가합니다."""
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
                logger.warning(
                    "[GBrain] Cannot add edge: node missing (%s -> %s)",
                    source_id,
                    target_id,
                )
                return

            def mutation() -> None:
                _ = self.graph.add_edge(source_id, target_id, relation=relation)

            self._record_successful_write((source_id, target_id), mutation)

    def search_semantic(
        self,
        query: str,
        limit: int = 3,
        filter_label: str | None = None,
    ) -> list[GraphAttributes]:
        """의미론적 검색을 통해 노드를 찾습니다."""
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            return self._search_semantic_from_graph(query, limit, filter_label)

    def _search_semantic_from_graph(
        self,
        query: str,
        limit: int,
        filter_label: str | None,
    ) -> list[GraphAttributes]:
        collection = _collection_or_none(self)
        if collection is None or collection.count() == 0:
            return []

        where: dict[str, str] | None = {"label": filter_label} if filter_label else None

        results = collection.query(
            query_texts=[query],
            n_results=min(limit, collection.count()),
            where=where,
        )

        matched_nodes: list[GraphAttributes] = []
        raw_ids = results.get("ids")
        id_rows = cast(list[object], raw_ids) if isinstance(raw_ids, list) else []
        ids = [_as_string_list(row) for row in id_rows]
        raw_distances = results.get("distances")
        distance_rows = cast(list[object], raw_distances) if isinstance(raw_distances, list) else []
        distances = [_as_float_list(row) for row in distance_rows]
        if ids and ids[0]:
            for i, doc_id in enumerate(ids[0]):
                if self.graph.has_node(doc_id):
                    node_data = _as_graph_attributes(cast(Mapping[object, object], self.graph.nodes[doc_id]))
                    node_data["id"] = doc_id
                    node_data["distance"] = distances[0][i] if distances and i < len(distances[0]) else 0
                    matched_nodes.append(node_data)

        return matched_nodes

    def get_related(self, node_id: str, max_depth: int = 1) -> list[GraphAttributes]:
        """특정 노드와 연결된 그래프 이웃을 반환합니다."""
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            return self._get_related_from_graph(node_id, max_depth)

    def _get_related_from_graph(self, node_id: str, max_depth: int) -> list[GraphAttributes]:
        _ = max_depth
        if not self.graph.has_node(node_id):
            return []

        related: list[GraphAttributes] = []
        # 간단한 1-hop 조회
        for neighbor in self.graph.neighbors(node_id):
            edge_data = self.graph.get_edge_data(node_id, neighbor)
            node_data = _as_graph_attributes(cast(Mapping[object, object], self.graph.nodes[neighbor]))
            node_data["id"] = str(neighbor)
            edge_attributes = cast(Mapping[object, object], edge_data or {})
            relation = edge_attributes.get("relation", "linked")
            node_data["relation_from_source"] = str(relation)
            related.append(node_data)

        return related

    def clear_all(self) -> int:
        with self._mutation_lock, self._storage_lock:
            if self._closed:
                raise RuntimeError("Cannot clear a closed GBrain instance")
            self._refresh_from_disk()
            deleted = self.graph.number_of_nodes()
            graph_before = self.graph.copy()
            tick_before = self._reward_tick
            rewards_before = self._pair_rewards.copy()
            collection = _collection_or_none(self)
            vector_before = _capture_collection_records(collection) if collection is not None else {}
            vector_ids = list(vector_before)
            try:
                if collection is not None and vector_ids:
                    _ = collection.delete(ids=vector_ids)
                self.graph.clear()
                self._reward_tick = 0
                self._pair_rewards.clear()
                self._store_reward_state()
                self._save_graph().result()
            except BaseException:
                self.graph = graph_before
                self._reward_tick = tick_before
                self._pair_rewards = rewards_before
                if collection is not None and vector_ids:
                    try:
                        _restore_collection_records(collection, vector_ids, vector_before)
                    except Exception:
                        logger.exception("[GBrain] Failed to restore Chroma records after clear failure")
                raise
            return deleted

    def export_all(self) -> list[GraphAttributes]:
        with self._mutation_lock, self._storage_lock:
            self._refresh_from_disk()
            return [
                {"id": str(node_id), **_as_graph_attributes(cast(Mapping[object, object], data))}
                for node_id, data in self.graph.nodes(data=True)
            ]

    def redact_all(self) -> int:
        from antigravity_k.engine.secret_scanner import redact_full

        with self._mutation_lock, self._storage_lock:
            if self._closed:
                raise RuntimeError("Cannot redact a closed GBrain instance")
            self._refresh_from_disk()
            graph_before = self.graph.copy()
            reward_tick_before = self._reward_tick
            rewards_before = self._pair_rewards.copy()
            collection = _collection_or_none(self)
            vector_before = _capture_collection_records(collection) if collection is not None else {}
            vector_ids = list(vector_before)
            changed = 0
            try:
                for _node_id, raw_data in self.graph.nodes(data=True):
                    data = cast(dict[object, object], raw_data)
                    for key, value in list(data.items()):
                        if isinstance(value, str):
                            redacted = redact_full(value)
                            changed += int(redacted != value)
                            data[key] = redacted
                if collection is not None and vector_ids:
                    safe_documents = [redact_full(vector_before[record_id][0]) for record_id in vector_ids]
                    safe_metadatas: list[dict[str, ChromaValue]] = []
                    for record_id in vector_ids:
                        metadata = vector_before[record_id][1]
                        safe_metadatas.append(
                            {
                                key: redact_full(value) if isinstance(value, str) else value
                                for key, value in metadata.items()
                            }
                        )
                    _ = collection.upsert(ids=vector_ids, documents=safe_documents, metadatas=safe_metadatas)
                if changed:
                    self._store_reward_state()
                    self._save_graph().result()
            except BaseException:
                self.graph = graph_before
                self._reward_tick = reward_tick_before
                self._pair_rewards = rewards_before
                if collection is not None and vector_ids:
                    try:
                        _restore_collection_records(collection, vector_ids, vector_before)
                    except Exception:
                        logger.exception("[GBrain] Failed to restore Chroma records after redaction failure")
                raise
            return changed

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        # 현재 보존기간 기반 삭제가 구현되지 않았다. 잘못된 상태의 reward snapshot을
        # 재저장하지 않도록 retention no-op은 GraphML을 변경하지 않는다.
        return 0


# 전역 싱글톤 인스턴스
global_gbrain = GBrain()


def _close_global_gbrain():
    """프로세스 종료 시 전역 GBrain의 리소스를 정리합니다."""
    try:
        _ = global_gbrain.close()
    except Exception:
        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)


_ = atexit.register(_close_global_gbrain)
