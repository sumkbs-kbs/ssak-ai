"""화면이 지정한 합성 프로젝트의 실제 파일 경로와 캐시 분리를 확인한다.

인증·프로젝트 등록부·파일 라우트·권한 검사·캐시는 제품 코드를 사용한다.
프로젝트 소유권 정책이나 실제 모델 동작을 검증하는 시험은 아니다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from httpx import Response

from tests.test_r45_authenticated_task_ownership import OwnerCase
from tests.test_r45_authenticated_task_ownership import owner_case as owner_case

RELATIVE_FILE = "notes/shared-note.txt"
CONTENTS = {"alpha": "R57 identity ALPHA-7391", "beta": "R57 identity BETA-8624"}


@dataclass
class FilesystemCase:
    ownership: OwnerCase
    roots: dict[str, Path]

    def headers(self, project_id: str) -> dict[str, str]:
        return {
            **self.ownership.headers["user"],
            "X-AGK-Session-Id": "r57-filesystem-session",
            "X-AGK-Project-Id": project_id,
        }

    def get(self, endpoint: str, project_id: str, params: dict[str, str]) -> Response:
        return self.ownership.client.get(
            endpoint,
            params={**params, "project_id": project_id},
            headers=self.headers(project_id),
        )

    def mutate(self, method: str, endpoint: str, project_id: str, body: dict[str, object]) -> Response:
        return self.ownership.client.request(
            method,
            endpoint,
            json={**body, "project_id": project_id},
            headers=self.headers(project_id),
        )

    def read(self, project: str) -> Response:
        return self.get("/api/fs/read", self.ownership.project_ids[project], {"file": RELATIVE_FILE})


@pytest.fixture
def filesystem_case(owner_case: OwnerCase, monkeypatch: pytest.MonkeyPatch) -> Iterator[FilesystemCase]:
    import antigravity_k.engine.api_cache as cache_module
    from antigravity_k.api.routes import filesystem
    from antigravity_k.engine.project_registry import ProjectRegistry

    registry = cast(ProjectRegistry, owner_case.state["registry"])
    roots: dict[str, Path] = {}
    for name in ("alpha", "beta"):
        record = registry.get_project(owner_case.project_ids[name])
        assert record is not None
        roots[name] = Path(record.path).resolve()
        target = roots[name] / RELATIVE_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(CONTENTS[name], encoding="utf-8")
        (roots[name] / f"{name}-only.txt").write_text(f"{name} list marker", encoding="utf-8")

    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", str(roots["alpha"]))
    cache = cache_module.ApiCache()
    # 데코레이터의 전역 조회와 쓰기 라우트의 무효화가 같은 실제 캐시를 사용한다.
    monkeypatch.setattr(cache_module, "api_cache", cache)
    monkeypatch.setattr(filesystem, "api_cache", cache)
    yield FilesystemCase(owner_case, roots)
    assert owner_case.providers == {}, "파일 화면 시험은 모델 실행 환경을 만들면 안 됩니다"


def _assert_read(response: Response, expected: str) -> None:
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "content": expected}


def test_explicit_beta_read_uses_registered_beta_root(filesystem_case: FilesystemCase) -> None:
    case = filesystem_case
    _assert_read(case.read("beta"), CONTENTS["beta"])
    assert (case.roots["alpha"] / RELATIVE_FILE).read_text(encoding="utf-8") == CONTENTS["alpha"]


def test_explicit_beta_write_changes_only_beta_file(filesystem_case: FilesystemCase) -> None:
    case = filesystem_case
    written = "R57 beta edited through the file route"
    response = case.mutate(
        "POST", "/api/fs/write", case.ownership.project_ids["beta"], {"path": RELATIVE_FILE, "content": written}
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert (case.roots["beta"] / RELATIVE_FILE).read_text(encoding="utf-8") == written
    assert (case.roots["alpha"] / RELATIVE_FILE).read_text(encoding="utf-8") == CONTENTS["alpha"]


def test_same_relative_path_read_cache_is_separate_for_each_project(filesystem_case: FilesystemCase) -> None:
    case = filesystem_case
    for project in ("alpha", "beta", "alpha", "beta"):
        _assert_read(case.read(project), CONTENTS[project])


def test_beta_write_invalidates_cached_read_without_changing_alpha(filesystem_case: FilesystemCase) -> None:
    case = filesystem_case
    _assert_read(case.read("alpha"), CONTENTS["alpha"])
    _assert_read(case.read("beta"), CONTENTS["beta"])
    written = "R57 beta content after cache invalidation"
    response = case.mutate(
        "POST", "/api/fs/write", case.ownership.project_ids["beta"], {"path": RELATIVE_FILE, "content": written}
    )
    assert response.status_code == 200, response.text
    _assert_read(case.read("beta"), written)
    _assert_read(case.read("alpha"), CONTENTS["alpha"])


@pytest.mark.parametrize("project_id", ["r57-unregistered-project", "../../alpha"])
@pytest.mark.parametrize("operation", ["read", "write"])
def test_explicit_unknown_project_never_falls_back_to_workspace(
    filesystem_case: FilesystemCase, project_id: str, operation: str
) -> None:
    case = filesystem_case
    _assert_read(case.read("alpha"), CONTENTS["alpha"])
    if operation == "read":
        response = case.get("/api/fs/read", project_id, {"file": RELATIVE_FILE})
    else:
        response = case.mutate(
            "POST", "/api/fs/write", project_id, {"path": RELATIVE_FILE, "content": "must not be written"}
        )
    assert response.status_code == 404, response.text
    for project in ("alpha", "beta"):
        assert (case.roots[project] / RELATIVE_FILE).read_text(encoding="utf-8") == CONTENTS[project]


@pytest.mark.parametrize("operation", ["read", "write"])
def test_beta_identity_cannot_target_absolute_alpha_path(filesystem_case: FilesystemCase, operation: str) -> None:
    case = filesystem_case
    project_id = case.ownership.project_ids["beta"]
    alpha_path = str(case.roots["alpha"] / RELATIVE_FILE)
    if operation == "read":
        response = case.get("/api/fs/read", project_id, {"file": alpha_path})
    else:
        response = case.mutate(
            "POST", "/api/fs/write", project_id, {"path": alpha_path, "content": "must not escape beta"}
        )
    assert response.status_code == 403, response.text
    for project in ("alpha", "beta"):
        assert (case.roots[project] / RELATIVE_FILE).read_text(encoding="utf-8") == CONTENTS[project]


def test_beta_file_tree_and_search_workflow_preserves_alpha(filesystem_case: FilesystemCase) -> None:
    case = filesystem_case
    project_id = case.ownership.project_ids["beta"]
    alpha_directory = case.roots["alpha"] / "workflow"
    alpha_directory.mkdir()
    for name in ("new-note.txt", "renamed-note.txt"):
        (alpha_directory / name).write_text("alpha file must survive", encoding="utf-8")

    listing = case.get("/api/fs/list", project_id, {"dir": "."})
    assert listing.status_code == 200, listing.text
    paths = {item["path"] for item in listing.json()["items"]}
    assert "beta-only.txt" in paths
    assert "alpha-only.txt" not in paths

    search = case.mutate("POST", "/api/fs/search", project_id, {"query": "R57 identity"})
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert len(results) == 1
    assert results[0]["file_path"] == RELATIVE_FILE
    assert [match["content"] for match in results[0]["matches"]] == [CONTENTS["beta"]]

    created = case.mutate("POST", "/api/fs/mkdir", project_id, {"path": "workflow"})
    assert created.status_code == 200 and created.json()["ok"] is True, created.text
    assert (case.roots["beta"] / "workflow").is_dir()
    written = case.mutate(
        "POST", "/api/fs/write", project_id, {"path": "workflow/new-note.txt", "content": "beta workflow"}
    )
    assert written.status_code == 200 and written.json()["ok"] is True, written.text
    renamed = case.mutate(
        "POST", "/api/fs/rename", project_id, {"path": "workflow/new-note.txt", "new_name": "renamed-note.txt"}
    )
    assert renamed.status_code == 200 and renamed.json()["ok"] is True, renamed.text
    assert renamed.json()["path"] == "workflow/renamed-note.txt"
    assert not (case.roots["beta"] / "workflow/new-note.txt").exists()
    assert (case.roots["beta"] / "workflow/renamed-note.txt").read_text(encoding="utf-8") == "beta workflow"

    removed = case.mutate("DELETE", "/api/fs/delete", project_id, {"path": "workflow/renamed-note.txt"})
    assert removed.status_code == 200 and removed.json()["ok"] is True, removed.text
    assert not (case.roots["beta"] / "workflow/renamed-note.txt").exists()
    for name in ("new-note.txt", "renamed-note.txt"):
        assert (alpha_directory / name).read_text(encoding="utf-8") == "alpha file must survive"
    assert (case.roots["alpha"] / RELATIVE_FILE).read_text(encoding="utf-8") == CONTENTS["alpha"]
