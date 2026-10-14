"""테스트: Git API 엔드포인트 통합 계약.
==================================
실제 git 리포지토리(tmp_path)를 대상으로 status/log/diff/stage/commit/
branch/graph/file-content/stash 흐름과 헬퍼 엣지를 검증한다.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from antigravity_k.api.routes import git_api
from antigravity_k.api.server import app
from antigravity_k.config import config

JsonObject = dict[str, object]


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> object: ...


def _json(response: ResponseLike) -> JsonObject:
    value = response.json()
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object, got {type(value).__name__}")
    return cast(JsonObject, value)


def _as_object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError(f"expected object, got {type(value).__name__}")
    return cast(JsonObject, value)


def _git_raw(args: list[str], cwd: str) -> None:
    _ = subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _parse_status_line(line: str) -> JsonObject | None:
    parser = cast(Callable[[str], JsonObject | None], getattr(git_api, "_parse_status_line"))
    return parser(line)


def _status_char(value: str) -> str:
    parser = cast(Callable[[str], str], getattr(git_api, "_status_char"))
    return parser(value)


def _git(args: list[str], cwd: str, timeout: float | None = None) -> str:
    command = cast(Callable[..., str], getattr(git_api, "_git"))
    return command(args, cwd=cwd, timeout=timeout)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    unique = tmp_path.name
    """프로젝트 루트=tmp_path, 커밋 1개 있는 git 리포지토리."""
    project_root = tmp_path
    repo_dir = project_root / f"repo-{unique}"
    repo_dir.mkdir()

    _git_raw(["init", "-b", "main"], str(repo_dir))
    _git_raw(["config", "user.name", "tester"], str(repo_dir))
    _git_raw(["config", "user.email", "tester@example.com"], str(repo_dir))
    _ = (repo_dir / "hello.txt").write_text("line1\n", encoding="utf-8")
    _git_raw(["add", "."], str(repo_dir))
    _git_raw(["commit", "-m", "init"], str(repo_dir))

    monkeypatch.setattr(config.paths, "project_root", project_root)
    yield repo_dir  # .name이 캐시 키 분리용 고유 cwd 이름을 제공한다


@pytest.fixture
def no_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """행복경로 테스트용: 권한 게이트를 통과시킨다(차단 계약은 별도 스위트 담당)."""

    def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(git_api, "_require_allowed", allow)


@pytest.fixture
def client() -> Iterator[TestClient]:
    headers = {"X-Access-Pin": config.security.access_pin}
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update(headers)
        yield test_client


# ─── /api/git/status ─────────────────────────────────────────────


class TestStatus:
    def test_clean_repo_reports_zero_counts(self, client: TestClient, repo: Path) -> None:
        response = client.get("/api/git/status", params={"path": repo.name})
        body = _json(response)

        assert body["ok"] is True
        assert body["branch"] == "main"
        assert body["upstream"] is None
        counts = _as_object(body["counts"])
        assert counts["total"] == 0

    def test_mixed_changes_are_counted(self, client: TestClient, repo: Path) -> None:
        _ = (repo / "hello.txt").write_text("line1\nline2\n", encoding="utf-8")
        _ = (repo / "new.txt").write_text("new\n", encoding="utf-8")

        body = _json(client.get("/api/git/status", params={"path": repo.name}))

        counts = _as_object(body["counts"])
        assert cast(int, counts["unstaged"]) >= 1
        assert counts["untracked"] == 1
        files = cast(list[JsonObject], body["files"])
        names = {cast(str, entry["file_path"]) for entry in files}
        assert "new.txt" in names


class TestStrictGitInputs:
    def test_log_rejects_non_object_payload(self, client: TestClient) -> None:
        response = client.post("/api/git/log", json=[])

        assert response.status_code == 400

    def test_log_rejects_non_integer_count(self, client: TestClient) -> None:
        response = client.post("/api/git/log", json={"count": "5"})

        assert response.status_code == 400

    def test_diff_rejects_non_boolean_staged(self, client: TestClient) -> None:
        response = client.post("/api/git/diff", json={"staged": 1})

        assert response.status_code == 400

    def test_add_rejects_non_string_files(self, client: TestClient) -> None:
        response = client.post("/api/git/add", json={"files": [123]})

        assert response.status_code == 400

    def test_commit_rejects_non_string_message(self, client: TestClient) -> None:
        response = client.post("/api/git/commit", json={"message": 123})

        assert response.status_code == 400

    def test_branch_create_rejects_non_string_name(self, client: TestClient) -> None:
        response = client.post("/api/git/branch/create", json={"name": 123})

        assert response.status_code == 400

    def test_branch_delete_rejects_non_boolean_force(self, client: TestClient) -> None:
        response = client.post("/api/git/branch/delete", json={"name": "feature", "force": 1})

        assert response.status_code == 400


# ─── /api/git/log · graph ────────────────────────────────────────


class TestLogAndGraph:
    def test_log_returns_structured_commits(self, client: TestClient, repo: Path) -> None:
        body = _json(client.post("/api/git/log", json={"path": repo.name, "count": 5}))

        assert body["ok"] is True
        assert body["count"] == 1
        commits = cast(list[JsonObject], body["commits"])
        commit = commits[0]
        assert commit["message"] == "init"
        assert commit["author_name"] == "tester"
        assert len(cast(str, commit["hash"])) == 40

    def test_graph_nodes_carry_graph_prefix(self, client: TestClient, repo: Path) -> None:
        body = _json(client.get("/api/git/graph", params={"path": repo.name}))

        assert body["ok"] is True
        assert cast(int, body["count"]) >= 1
        nodes = cast(list[JsonObject], body["nodes"])
        assert cast(str, nodes[0]["graph"]).startswith("*")


# ─── diff · add · unstage · commit ───────────────────────────────


class TestChangeFlow:
    def test_diff_unstaged_then_staged(self, client: TestClient, repo: Path) -> None:
        _ = (repo / "hello.txt").write_text("line1\nline2\n", encoding="utf-8")

        unstaged = _json(client.post("/api/git/diff", json={"path": repo.name}))
        assert "+line2" in cast(str, unstaged["diff"])
        assert unstaged["staged"] is False

        _git_raw(["add", "hello.txt"], str(repo))
        staged = _json(client.post("/api/git/diff", json={"path": repo.name, "staged": True}))
        assert "+line2" in cast(str, staged["diff"])

    def test_add_specific_files(self, client: TestClient, repo: Path, no_gate: None) -> None:
        _ = (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _ = (repo / "c.txt").write_text("c\n", encoding="utf-8")

        body = _json(client.post("/api/git/add", json={"path": repo.name, "files": ["b.txt", "c.txt"]}))

        assert body["ok"] is True
        status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, text=True).stdout
        assert "A  b.txt" in status
        assert "A  c.txt" in status
        del no_gate

    def test_add_without_files_reports_error(self, client: TestClient, repo: Path) -> None:
        body = _json(client.post("/api/git/add", json={"path": repo.name, "files": []}))
        assert body["ok"] is False

    def test_unstage_all(self, client: TestClient, repo: Path, no_gate: None) -> None:
        _ = (repo / "hello.txt").write_text("changed\n", encoding="utf-8")
        _git_raw(["add", "."], str(repo))

        body = _json(client.post("/api/git/unstage", json={"path": repo.name, "files": []}))

        assert body["ok"] is True
        status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, text=True).stdout
        staged_lines = [line for line in status.splitlines() if line.startswith("M ")]
        assert staged_lines == []
        assert any(line.startswith(" M") for line in status.splitlines())
        del no_gate

    def test_commit_requires_message(self, client: TestClient, repo: Path) -> None:
        body = _json(client.post("/api/git/commit", json={"path": repo.name, "message": "  "}))
        assert body["ok"] is False

    def test_commit_creates_revision(self, client: TestClient, repo: Path, no_gate: None) -> None:
        _ = (repo / "hello.txt").write_text("v2\n", encoding="utf-8")

        body = _json(
            client.post(
                "/api/git/commit",
                json={"path": repo.name, "message": "update hello", "stage_all": True},
            )
        )

        assert body["ok"] is True
        log = _json(client.post("/api/git/log", json={"path": repo.name}))
        commits = cast(list[JsonObject], log["commits"])
        assert _as_object(commits[0])["message"] == "update hello"
        del no_gate


# ─── branches ────────────────────────────────────────────────────


class TestBranches:
    def test_branch_lifecycle_roundtrip(self, client: TestClient, repo: Path, no_gate: None) -> None:
        created = _json(client.post("/api/git/branch/create", json={"path": repo.name, "name": "feature/x"}))
        assert created["ok"] is True

        listing = _json(client.get("/api/git/branches", params={"path": repo.name}))
        branches = cast(list[JsonObject], listing["branches"])
        by_name = {cast(str, branch["name"]): branch for branch in branches}
        assert by_name["feature/x"]["is_current"] is True
        assert listing["current"] == "feature/x"

        switched = _json(client.post("/api/git/checkout", json={"path": repo.name, "name": "main"}))
        assert switched["ok"] is True

        deleted = _json(client.post("/api/git/branch/delete", json={"path": repo.name, "name": "feature/x"}))
        assert deleted["ok"] is True
        del no_gate

    def test_create_requires_name(self, client: TestClient, repo: Path) -> None:
        body = _json(client.post("/api/git/branch/create", json={"path": repo.name, "name": " "}))
        assert body["ok"] is False

    def test_checkout_requires_name(self, client: TestClient, repo: Path) -> None:
        body = _json(client.post("/api/git/checkout", json={"path": repo.name, "name": ""}))
        assert body["ok"] is False


# ─── file-content · stash ────────────────────────────────────────


class TestContentAndStash:
    def test_file_content_at_head(self, client: TestClient, repo: Path) -> None:
        body = _json(client.get("/api/git/file-content", params={"path": repo.name, "file": "hello.txt"}))

        assert body["ok"] is True
        assert body["content"] == "line1\n"
        assert body["ref"] == "HEAD"

    def test_stash_list_empty_is_ok(self, client: TestClient, repo: Path) -> None:
        body = _json(client.get("/api/git/stash/list", params={"path": repo.name}))

        assert body == {"ok": True, "stashes": []}


# ─── 헬퍼 엣지 ────────────────────────────────────────────────────


class TestHelpers:
    def test_parse_status_line_variants(self) -> None:
        renamed = _parse_status_line("R  old.txt -> new.txt")
        assert renamed is not None
        assert renamed["is_renamed"] is True
        assert renamed["old_path"] == "old.txt"
        assert renamed["file_path"] == "new.txt"

        normal = _parse_status_line(" M src/main.py")
        assert normal is not None
        assert normal["is_renamed"] is False
        assert normal["staged_status"] == "unchanged"
        assert normal["unstaged_status"] == "modified"

        assert _parse_status_line("") is None
        assert _parse_status_line("# branch info") is None

    def test_status_char_unknown_fallback(self) -> None:
        assert _status_char("X") == "unknown"

    def test_git_missing_directory_is_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config.paths, "project_root", tmp_path)

        with pytest.raises(HTTPException) as error:
            _ = _git(["status"], cwd="ghost-dir")

        assert error.value.status_code == 400

    def test_git_command_failure_maps_to_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config.paths, "project_root", tmp_path)

        with pytest.raises(HTTPException) as error:
            _ = _git(["show", "HEAD"], cwd=".")  # 커밋 없는 저장소

        assert error.value.status_code == 400

    def test_git_timeout_maps_to_408(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config.paths, "project_root", tmp_path)

        with pytest.raises(HTTPException) as error:
            _ = _git(["status"], cwd=".", timeout=0)

        assert error.value.status_code == 408

    def test_git_binary_absent_maps_to_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config.paths, "project_root", tmp_path)

        def raise_file_not_found(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("git")

        monkeypatch.setattr(subprocess, "run", raise_file_not_found)

        with pytest.raises(HTTPException) as error:
            _ = _git(["status"], cwd=".")

        assert error.value.status_code == 400
