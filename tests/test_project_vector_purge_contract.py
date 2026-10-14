from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from chromadb.api.shared_system_client import SharedSystemClient
from chromadb.errors import NotFoundError

from antigravity_k.engine import vector_store


class Collection:
    metadata = {"ssak_embedding_identity": "bound identity"}

    def __init__(self, ids: list[str], fail: bool = False):
        self.ids = ids.copy()
        self.fail = fail
        self.deleted: list[list[str]] = []

    def get(self, *, include: list[str]) -> dict[str, list[str]]:
        assert include == []
        return {"ids": self.ids.copy()}

    def delete(self, *, ids: list[str]) -> None:
        if self.fail:
            raise RuntimeError("delete failed")
        self.deleted.append(ids.copy())
        self.ids = [item for item in self.ids if item not in ids]


class Client:
    def __init__(self, collection: Collection, failure: Exception | None = None):
        self.collection = collection
        self.failure = failure
        self.requests: list[str] = []
        self.closed = 0

    def get_collection(self, *, name: str, embedding_function: None) -> Collection:
        assert embedding_function is None
        self.requests.append(name)
        if self.failure is not None:
            raise self.failure
        return self.collection

    def close(self) -> None:
        self.closed += 1


def install(monkeypatch: pytest.MonkeyPatch, client: Client, expected_path: Path) -> None:
    def persistent(*, path: str) -> Client:
        assert Path(path) == expected_path
        return client

    monkeypatch.setattr(vector_store, "_chroma_available", True)
    monkeypatch.setattr(vector_store, "chromadb", SimpleNamespace(PersistentClient=persistent))

    def deny_cache_clear() -> None:
        raise AssertionError("purge must preserve other native clients")

    monkeypatch.setattr(SharedSystemClient, "clear_system_cache", deny_cache_clear)


def test_purge_bound_existing_ids_without_embedding_or_cache_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    collection = Collection(["a-one", "a-two"])
    client = Client(collection)
    install(monkeypatch, client, tmp_path)
    assert vector_store.clear_persisted_collection(str(tmp_path), "project_code") == 2
    assert collection.ids == [] and collection.deleted == [["a-one", "a-two"]]
    assert client.requests == ["project_code"] and client.closed == 1
    assert collection.metadata == {"ssak_embedding_identity": "bound identity"}


def test_purge_empty_collection_does_not_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    collection = Collection([])
    client = Client(collection)
    install(monkeypatch, client, tmp_path)
    assert vector_store.clear_persisted_collection(str(tmp_path), "project_code") == 0
    assert collection.deleted == [] and client.closed == 1


def test_missing_collection_is_not_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = Client(Collection([]), NotFoundError("collection absent"))
    install(monkeypatch, client, tmp_path)
    assert vector_store.clear_persisted_collection(str(tmp_path), "absent") == 0
    assert client.requests == ["absent"] and client.closed == 1


def test_missing_path_is_not_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "absent"
    monkeypatch.setattr(vector_store, "chromadb", None)
    assert vector_store.clear_persisted_collection(str(path), "project_code") == 0
    assert not path.exists()


@pytest.mark.parametrize("stage", ["get", "delete"])
def test_purge_failure_is_propagated_and_owned_client_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
):
    client = Client(Collection(["one"], fail=stage == "delete"), RuntimeError("get failed") if stage == "get" else None)
    install(monkeypatch, client, tmp_path)
    with pytest.raises(RuntimeError, match=stage + " failed"):
        vector_store.clear_persisted_collection(str(tmp_path), "project_code")
    assert client.closed == 1 and client.collection.ids == ["one"]


def test_persistent_open_failure_does_not_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fail(*, path: str):
        calls.append(path)
        raise KeyError("native state collision")

    monkeypatch.setattr(vector_store, "_chroma_available", True)
    monkeypatch.setattr(vector_store, "chromadb", SimpleNamespace(PersistentClient=fail))
    with pytest.raises(KeyError, match="native state collision"):
        vector_store.clear_persisted_collection(str(tmp_path), "project_code")
    assert calls == [str(tmp_path)]


def test_unavailable_native_library_does_not_report_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(vector_store, "_chroma_available", False)
    with pytest.raises(RuntimeError, match="required"):
        vector_store.clear_persisted_collection(str(tmp_path), "project_code")


def test_close_failure_does_not_report_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class BadClose(Client):
        def close(self) -> None:
            raise OSError("close failed")

    client = BadClose(Collection(["one"]))
    install(monkeypatch, client, tmp_path)
    with pytest.raises(OSError, match="close failed"):
        vector_store.clear_persisted_collection(str(tmp_path), "project_code")
