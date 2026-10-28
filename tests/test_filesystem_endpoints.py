"""테스트: Filesystem API — 워크스페이스 파일 CRUD·검색 통합 계약.
============================================
워크스페이스 루트 경계 보호(403), CRUD 흐름, 이름 변경, 내용 검색을 검증한다.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest
from fastapi.testclient import TestClient

from antigravity_k.api.routes import filesystem
from antigravity_k.api.server import app

JsonObject = dict[str, object]


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> object: ...


def _json(response: ResponseLike) -> JsonObject:
    value = response.json()
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object, got {type(value).__name__}")
    return cast(JsonObject, value)


def _clear_filesystem_cache() -> None:
    from antigravity_k.engine.api_cache import api_cache

    tag_index = cast(dict[str, set[str]], getattr(api_cache, "_tag_index"))
    entries = cast(dict[str, object], getattr(api_cache, "_entries"))
    keys = tag_index.pop("filesystem", set())
    for key in keys:
        _ = entries.pop(key, None)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", str(ws))
    return ws


@pytest.fixture
def client() -> Iterator[TestClient]:
    from antigravity_k.config import config

    headers = {"X-Access-Pin": config.security.access_pin}
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update(headers)
        _clear_filesystem_cache()
        yield test_client
        _clear_filesystem_cache()


# ─── browse / list ───────────────────────────────────────────────


class TestBrowseAndList:
    def test_browse_lists_dirs_and_hides_dotfiles(self, client: TestClient, workspace: Path) -> None:
        (workspace / "subdir").mkdir()
        (workspace / ".secret").mkdir()

        body = _json(client.get("/api/fs/browse", params={"dir": "."}))

        items = cast(list[JsonObject], body["items"])
        names = [cast(str, e["name"]) for e in items]
        assert "subdir" in names
        assert ".secret" not in names
        # r29: workspace root is the browse root; its parent lies outside allowed roots -> not offered.
        assert body["parent"] is None

    def test_list_returns_relative_paths_sorted_dirs_first(self, client: TestClient, workspace: Path) -> None:
        (workspace / "zdir").mkdir()
        _ = (workspace / "afile.txt").write_text("x", encoding="utf-8")

        body = _json(client.get("/api/fs/list", params={"dir": "."}))

        assert body["ok"] is True
        items = cast(list[JsonObject], body["items"])
        paths = [cast(str, e["path"]) for e in items]
        assert paths == ["zdir", "afile.txt"]
        assert items[0]["is_dir"] is True

    def test_traversal_outside_workspace_is_403(self, client: TestClient) -> None:
        response = client.get("/api/fs/list", params={"dir": "../../etc"})

        assert response.status_code == 403

    def test_browse_missing_dir_is_404(self, client: TestClient) -> None:
        response = client.get("/api/fs/browse", params={"dir": "no-such-dir"})
        assert response.status_code == 404


# ─── mkdir / delete ──────────────────────────────────────────────


class TestMkdirDelete:
    def test_mkdir_creates_and_duplicate_reports_false(self, client: TestClient, workspace: Path) -> None:
        ok = _json(client.post("/api/fs/mkdir", json={"path": "newdir"}))
        dup = _json(client.post("/api/fs/mkdir", json={"path": "newdir"}))

        assert ok["ok"] is True
        assert (workspace / "newdir").is_dir()
        assert dup["ok"] is False

    def test_mkdir_root_path_is_400(self, client: TestClient) -> None:
        for bad in (".", ""):
            assert client.post("/api/fs/mkdir", json={"path": bad}).status_code == 400

    def test_delete_file_and_directory(self, client: TestClient, workspace: Path) -> None:
        f = workspace / "doomed.txt"
        _ = f.write_text("bye", encoding="utf-8")
        d = workspace / "doomed-dir"
        d.mkdir()

        assert _json(client.request("DELETE", "/api/fs/delete", json={"path": "doomed.txt"}))["ok"] is True
        assert _json(client.request("DELETE", "/api/fs/delete", json={"path": "doomed-dir"}))["ok"] is True
        assert not f.exists() and not d.exists()

    def test_delete_root_is_400_and_missing_is_ok_false(self, client: TestClient) -> None:
        root_resp = client.request("DELETE", "/api/fs/delete", json={"path": "."})
        assert root_resp.status_code == 400

        missing = _json(client.request("DELETE", "/api/fs/delete", json={"path": "ghost"}))
        assert missing == {"ok": False, "detail": "Path does not exist"}


# ─── write / read / rename ───────────────────────────────────────


class TestWriteReadRename:
    def test_write_creates_parent_dirs_then_read_roundtrip(self, client: TestClient, workspace: Path) -> None:
        _ = workspace
        write_body = _json(
            client.post(
                "/api/fs/write",
                json={"path": "deep/nested/file.txt", "content": "본문 내용"},
            )
        )

        assert write_body["ok"] is True
        read_body = _json(client.get("/api/fs/read", params={"file": "deep/nested/file.txt"}))
        assert read_body == {"ok": True, "content": "본문 내용"}

    def test_read_missing_file_is_404(self, client: TestClient) -> None:
        assert client.get("/api/fs/read", params={"file": "ghost.txt"}).status_code == 404

    def test_rename_moves_file(self, client: TestClient, workspace: Path) -> None:
        _ = (workspace / "before.txt").write_text("v", encoding="utf-8")

        body = _json(client.post("/api/fs/rename", json={"path": "before.txt", "new_name": "after.txt"}))

        assert body["ok"] is True
        assert (workspace / "after.txt").exists()
        assert not (workspace / "before.txt").exists()

    def test_rename_to_existing_name_reports_conflict(self, client: TestClient, workspace: Path) -> None:
        _ = (workspace / "src.txt").write_text("a", encoding="utf-8")
        _ = (workspace / "dst.txt").write_text("b", encoding="utf-8")

        body = _json(client.post("/api/fs/rename", json={"path": "src.txt", "new_name": "dst.txt"}))

        assert body["ok"] is False

    def test_rename_missing_source_is_404(self, client: TestClient) -> None:
        response = client.post("/api/fs/rename", json={"path": "ghost.txt", "new_name": "x.txt"})
        assert response.status_code == 404


# ─── content search ──────────────────────────────────────────────


class TestContentSearch:
    def test_short_query_is_400(self, client: TestClient) -> None:
        response = client.post("/api/fs/search", json={"query": "a"})
        assert response.status_code == 400

    def test_finds_matches_with_counts(self, client: TestClient, workspace: Path) -> None:
        _ = (workspace / "hit.md").write_text("고유단어 가 포함된 문서", encoding="utf-8")
        _ = (workspace / "miss.md").write_text("관련 없음", encoding="utf-8")

        body = _json(client.post("/api/fs/search", json={"query": "고유단어"}))

        assert body["total_files"] == 1
        results = cast(list[JsonObject], body["results"])
        assert cast(int, results[0]["match_count"]) >= 1
