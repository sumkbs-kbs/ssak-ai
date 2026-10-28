"""Synthetic direct-file HTTP boundaries; no model, server or shell execution.

Real PIN authentication, project registration/session binding and PermissionGate
remain installed. Only the deterministic race hook runs after the real permission
check. Both direct agent-tools and editor filesystem routes read/write real owned
temporary files; no normal user data is used.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

import pytest
from httpx import Response

from tests.test_r45_authenticated_task_ownership import OwnerCase
from tests.test_r45_authenticated_task_ownership import owner_case as owner_case

Endpoint = Literal["agent-tools", "editor-filesystem"]
Operation = Literal["read", "write"]
Attack = Literal["hardlink", "final-link-after-permission", "parent-link-after-permission"]
OUTSIDE_CONTENT = "R57-SYNTHETIC-OUTSIDE-CONTENT-6791"
INSIDE_CONTENT = "R57-SYNTHETIC-INSIDE-CONTENT-2318"
REPLACEMENT = "R57-SYNTHETIC-REPLACEMENT-5402"


@dataclass(frozen=True, slots=True)
class DirectFileCase:
    endpoint: Endpoint
    module: ModuleType
    root: Path
    outside: Path
    project_id: str
    headers: dict[str, str] = field(repr=False)
    owner: OwnerCase = field(repr=False)

    def request(self, operation: Operation, target: Path, *, content: str = REPLACEMENT) -> Response:
        if self.endpoint == "agent-tools":
            payload: dict[str, object] = {"path": str(target), "project_id": self.project_id}
            if operation == "write":
                payload.update(content=content, overwrite=True)
            return self.owner.client.post("/api/agent/tools/fs/" + operation, json=payload, headers=self.headers)
        if operation == "read":
            return self.owner.client.get(
                "/api/fs/read", params={"file": str(target), "project_id": self.project_id}, headers=self.headers,
            )
        return self.owner.client.post(
            "/api/fs/write", json={"path": str(target), "content": content, "project_id": self.project_id}, headers=self.headers,
        )


@pytest.fixture(params=["agent-tools", "editor-filesystem"])
def direct_file_case(
    owner_case: OwnerCase, request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[DirectFileCase]:
    from antigravity_k.api import project_binding
    from antigravity_k.api.routes import agent_tools, filesystem
    from antigravity_k.config import config
    from antigravity_k.engine import access_mode
    from antigravity_k.engine.project_registry import ProjectRegistry

    endpoint = cast(Endpoint, request.param)
    assert endpoint in ("agent-tools", "editor-filesystem")
    registry = cast(ProjectRegistry, owner_case.state["registry"])
    project_id = owner_case.project_ids["alpha"]
    project = registry.get_project(project_id)
    assert project is not None
    root = Path(project.path).resolve()
    outside = tmp_path / "r57-synthetic-outside"
    outside.mkdir()
    assert not outside.is_relative_to(root)
    monkeypatch.setattr(config.paths, "project_root", root)
    monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", str(root))
    monkeypatch.delenv(access_mode.EXECUTION_POLICY_ENV, raising=False)
    prior_mode, prior_policy = access_mode.get_access_mode(), access_mode.get_execution_policy()
    access_mode.set_access_mode(access_mode.AccessMode.FULL_ACCESS)
    access_mode.set_execution_policy(access_mode.ExecutionPolicy.AUTO_PILOT)
    session = "r57-synthetic-direct-file-session"
    project_binding.bind_session_active_project(session, project_id)
    headers = {**owner_case.headers["user"], project_binding.SESSION_ID_HEADER: session}
    # The inherited app already has the real filesystem router; add the real
    # direct agent-tools router without replacing authentication or permission.
    owner_case.app.include_router(agent_tools.router)
    module = agent_tools if endpoint == "agent-tools" else filesystem
    try:
        yield DirectFileCase(endpoint, module, root, outside, project_id, headers, owner_case)
    finally:
        access_mode.set_access_mode(prior_mode)
        access_mode.set_execution_policy(prior_policy)


def test_single_link_file_keeps_real_read_and_write_working(direct_file_case: DirectFileCase) -> None:
    case = direct_file_case
    target = case.root / "r57-positive-control.txt"
    written = case.request("write", target, content=INSIDE_CONTENT)
    read = case.request("read", target)
    assert written.status_code == read.status_code == 200
    assert target.read_text(encoding="utf-8") == INSIDE_CONTENT
    assert target.stat().st_nlink == 1
    assert read.json() == {"ok": True, "content": INSIDE_CONTENT}


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("attack", ["hardlink", "final-link-after-permission", "parent-link-after-permission"])
def test_direct_file_access_refuses_alias_or_post_permission_swap(
    direct_file_case: DirectFileCase, monkeypatch: pytest.MonkeyPatch, operation: Operation, attack: Attack,
) -> None:
    case = direct_file_case
    victim = case.outside / "synthetic-credentials.env"
    victim.write_text(OUTSIDE_CONTENT, encoding="utf-8")
    before = victim.read_bytes()
    folder = case.root / "r57-visible-folder"
    folder.mkdir()
    target = folder / "ordinary-note.txt"
    swapped: list[str] = []
    if attack == "hardlink":
        os.link(victim, target)
        assert target.stat().st_nlink == victim.stat().st_nlink == 2
    else:
        target.write_text(INSIDE_CONTENT, encoding="utf-8")
        original = cast(Callable[..., None], getattr(case.module, "_require_allowed"))

        def after_real_permission(*args: object, **kwargs: object) -> None:
            original(*args, **kwargs)
            if swapped:
                return
            swapped.append(attack)
            if attack == "final-link-after-permission":
                target.unlink()
                target.symlink_to(victim)
            else:
                # The destination basename is the innocent name used in the
                # inspected path; its parent becomes the outside-directory link.
                victim.rename(case.outside / target.name)
                folder.rename(case.root / "r57-original-checked-folder")
                folder.symlink_to(case.outside, target_is_directory=True)

        monkeypatch.setattr(case.module, "_require_allowed", after_real_permission)
    response = case.request(operation, target)
    actual_victim = case.outside / target.name if attack == "parent-link-after-permission" else victim
    observed = {
        "status": response.status_code,
        "outside_unchanged": actual_victim.read_bytes() == before,
        "outside_content_in_response": OUTSIDE_CONTENT in response.text,
    }
    assert observed == {"status": 403, "outside_unchanged": True, "outside_content_in_response": False}
    if attack != "hardlink":
        assert swapped == [attack]
