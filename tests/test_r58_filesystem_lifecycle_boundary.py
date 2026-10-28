"""합성 폴더 교체와 기존 보호 목적지 계약을 실제 파일 라우트로 검사한다.

실제 인증·등록부·권한 검사는 유지한다. 교체 장치는 권한 검사 통과 뒤에만
소유 임시 폴더를 바꾸며, 운영 자료나 실제 모델을 사용하지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import pytest
from fastapi import HTTPException
from httpx import Response

from tests.test_r45_authenticated_task_ownership import OwnerCase
from tests.test_r45_authenticated_task_ownership import owner_case as owner_case

Operation = Literal["mkdir", "delete", "rename", "list"]
TreeSnapshot = dict[str, tuple[str, bytes]]
OUTSIDE_MARKER = "r58-outside-only-marker.txt"
INSIDE_CONTENT = b"R58 synthetic checked file"
OUTSIDE_CONTENT = b"R58 synthetic outside canary"


def _snapshot(root: Path) -> TreeSnapshot:
    snapshot: TreeSnapshot = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("link", os.readlink(path).encode("utf-8"))
        elif path.is_dir():
            snapshot[relative] = ("directory", b"")
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


@dataclass(frozen=True, slots=True)
class LifecycleCase:
    root: Path
    outside: Path
    project_id: str
    owner: OwnerCase = field(repr=False)

    def request(self, operation: Operation, path: str, *, new_name: str = "") -> Response:
        headers = {
            **self.owner.headers["user"],
            "X-AGK-Session-Id": "r58-lifecycle-session",
            "X-AGK-Project-Id": self.project_id,
        }
        if operation == "list":
            return self.owner.client.get(
                "/api/fs/list", params={"dir": path, "project_id": self.project_id}, headers=headers
            )
        body = {"path": path, "project_id": self.project_id}
        if operation == "rename":
            body["new_name"] = new_name
        return self.owner.client.request(
            "DELETE" if operation == "delete" else "POST", "/api/fs/" + operation, json=body, headers=headers
        )


@pytest.fixture
def lifecycle_case(
    owner_case: OwnerCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[LifecycleCase]:
    from antigravity_k.api.routes import filesystem
    from antigravity_k.engine.project_registry import ProjectRegistry

    registry = cast(ProjectRegistry, owner_case.state["registry"])
    selected = registry.get_project(owner_case.project_ids["beta"])
    fallback = registry.get_project(owner_case.project_ids["alpha"])
    assert selected is not None and fallback is not None
    root = Path(selected.path).resolve()
    outside = (tmp_path / "r58-lifecycle-outside").resolve()
    outside.mkdir()
    assert not outside.is_relative_to(root)
    (outside / OUTSIDE_MARKER).write_bytes(OUTSIDE_CONTENT)
    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", fallback.path)
    yield LifecycleCase(root, outside, selected.id, owner_case)
    assert owner_case.providers == {}, "파일 작업이 모델 실행 환경을 만들면 안 됩니다"


def test_normal_lifecycle_keeps_real_operations_working(lifecycle_case: LifecycleCase) -> None:
    case = lifecycle_case
    outside_before = _snapshot(case.outside)
    created = case.request("mkdir", "normal")
    assert created.status_code == 200 and created.json()["ok"] is True, created.text
    folder = case.root / "normal"
    assert folder.is_dir()
    (folder / "before.txt").write_bytes(INSIDE_CONTENT)

    listed = case.request("list", "normal")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [{"name": "before.txt", "path": "normal/before.txt", "is_dir": False}]
    renamed = case.request("rename", "normal/before.txt", new_name="after.txt")
    assert renamed.status_code == 200 and renamed.json()["ok"] is True, renamed.text
    assert not (folder / "before.txt").exists()
    assert (folder / "after.txt").read_bytes() == INSIDE_CONTENT
    deleted = case.request("delete", "normal/after.txt")
    assert deleted.status_code == 200 and deleted.json()["ok"] is True, deleted.text
    assert not (folder / "after.txt").exists()
    assert _snapshot(case.outside) == outside_before


@pytest.mark.parametrize("operation", ["mkdir", "delete", "rename", "list"])
def test_parent_swap_after_real_permission_cannot_escape_project(
    lifecycle_case: LifecycleCase, monkeypatch: pytest.MonkeyPatch, operation: Operation
) -> None:
    from antigravity_k.api.routes import filesystem

    case = lifecycle_case
    visible = case.root / "visible"
    visible.mkdir()
    if operation == "mkdir":
        relative = "visible/new-directory"
    elif operation == "list":
        (visible / "listing").mkdir()
        (visible / "listing/inside-only.txt").write_bytes(INSIDE_CONTENT)
        (case.outside / "listing").mkdir()
        (case.outside / "listing" / OUTSIDE_MARKER).write_bytes(OUTSIDE_CONTENT)
        relative = "visible/listing"
    else:
        (visible / "before.txt").write_bytes(INSIDE_CONTENT)
        (case.outside / "before.txt").write_bytes(OUTSIDE_CONTENT)
        relative = "visible/before.txt"

    inside_before = _snapshot(visible)
    outside_before = _snapshot(case.outside)
    parked = case.root / "checked-visible-before-swap"
    original = cast(Callable[..., None], filesystem._require_allowed)
    swaps: list[str] = []

    def swap_after_real_permission(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)
        assert args[0] == "fs_" + operation
        assert not swaps
        visible.rename(parked)
        visible.symlink_to(case.outside, target_is_directory=True)
        swaps.append(operation)

    monkeypatch.setattr(filesystem, "_require_allowed", swap_after_real_permission)
    response = case.request(operation, relative, new_name="after.txt")
    observed = {
        "status": response.status_code,
        "outside_unchanged": _snapshot(case.outside) == outside_before,
        "outside_marker_returned": OUTSIDE_MARKER in response.text,
        "checked_original_unchanged": _snapshot(parked) == inside_before,
        "swaps": swaps,
    }
    assert observed == {
        "status": 403,
        "outside_unchanged": True,
        "outside_marker_returned": False,
        "checked_original_unchanged": True,
        "swaps": [operation],
    }


def test_rename_respects_destination_protection_already_enforced_by_real_gate(lifecycle_case: LifecycleCase) -> None:
    from antigravity_k.api.routes import filesystem
    from antigravity_k.engine.cognitive.protected_targets import CONSTITUTION_DOC

    case = lifecycle_case
    source = case.root / "ordinary-note.txt"
    source.write_bytes(INSIDE_CONTENT)
    destination = case.root / CONSTITUTION_DOC
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert not destination.exists()
    outside_before = _snapshot(case.outside)

    # 먼저 기존 제품 보호 장치가 이 합성 목적지를 막는다는 계약을 독립 확인한다.
    with pytest.raises(HTTPException) as blocked:
        filesystem._require_allowed("fs_rename", {"path": str(destination)}, "medium", root=str(case.root))
    assert blocked.value.status_code == 403
    assert not destination.exists()

    response = case.request("rename", source.name, new_name=CONSTITUTION_DOC)
    observed = {
        "status": response.status_code,
        "source_content": source.read_bytes() if source.exists() else None,
        "protected_destination_exists": destination.exists(),
        "outside_unchanged": _snapshot(case.outside) == outside_before,
    }
    assert observed == {
        "status": 403,
        "source_content": INSIDE_CONTENT,
        "protected_destination_exists": False,
        "outside_unchanged": True,
    }
