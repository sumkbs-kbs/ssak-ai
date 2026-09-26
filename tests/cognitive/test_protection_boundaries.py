from dataclasses import replace
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.protected_targets import (
    ProtectedClass,
    ProtectedRoot,
    ProtectedWriteGuard,
)
from antigravity_k.tools.permission_gate import PermissionGate, protection_action_digest
from antigravity_k.tools.tool_contracts import Permission
from tests.cognitive.test_protection import CONSTITUTION_RELATIVE, approval_for, request_for


def test_blank_request_digest_cannot_use_bound_approval(tmp_path: Path) -> None:
    guard = ProtectedWriteGuard(tmp_path)
    approval = approval_for(".", action_digest="sha256:original")
    assert not guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(approval,), digest="")).allowed


def test_gate_binds_approval_to_actual_arguments(tmp_path: Path) -> None:
    gate = PermissionGate(str(tmp_path))
    gate.set_protection_approvals((approval_for(".", action_digest="sha256:original"),))
    assert gate.check("write_file", {"file_path": CONSTITUTION_RELATIVE, "content": "changed"}) is Permission.DENY


def test_allow_override_cannot_open_protected_write(tmp_path: Path) -> None:
    gate = PermissionGate(str(tmp_path))
    gate.set_override("write_file", Permission.ALLOW)
    assert gate.check("write_file", {"file_path": CONSTITUTION_RELATIVE}) is Permission.DENY


@pytest.mark.parametrize("target", ["docs/ssak-ai-core", "docs", "."])
def test_ancestor_deletion_is_protected(tmp_path: Path, target: str) -> None:
    gate = PermissionGate(str(tmp_path))
    assert gate.check("run_bash_command", {"command": f"rm -r {target}"}) is Permission.DENY


def test_every_protected_class_requires_approval(tmp_path: Path) -> None:
    guard = ProtectedWriteGuard(tmp_path, store_roots=(tmp_path,))
    approval = approval_for(".", action_digest="sha256:action")
    request = replace(
        request_for(CONSTITUTION_RELATIVE, approvals=(approval,), digest="sha256:action"),
        targets=(CONSTITUTION_RELATIVE, "records/authority_profile/abc.md"),
    )
    assert not guard.evaluate(request).allowed


def test_injected_store_guard_is_preserved(tmp_path: Path) -> None:
    gate = PermissionGate(str(tmp_path))
    guard = ProtectedWriteGuard(
        tmp_path,
        protected_roots=(ProtectedRoot.of(tmp_path, "custom", ProtectedClass.HUMAN_AUTHORITY, "custom store"),),
    )
    gate.set_protection_guard(guard)
    assert gate.check("write_file", {"file_path": "custom/record.md"}) is Permission.DENY


@pytest.mark.parametrize("content, expected", [("approved", Permission.ALLOW), ("changed", Permission.DENY)])
def test_only_exact_approved_content_is_allowed(tmp_path: Path, content: str, expected: Permission) -> None:
    gate = PermissionGate(str(tmp_path))
    args = {"file_path": CONSTITUTION_RELATIVE, "content": "approved"}
    digest = protection_action_digest("write_file", args)
    gate.set_protection_approvals((approval_for(".", action_digest=digest),))
    assert gate.check("write_file", {**args, "content": content}) is expected


def test_ancestor_covering_two_classes_needs_both_approvals(tmp_path: Path) -> None:
    guard = ProtectedWriteGuard(tmp_path, store_roots=(tmp_path,))
    approval = approval_for(".", action_digest="sha256:action")
    assert not guard.evaluate(request_for(".", approvals=(approval,), digest="sha256:action")).allowed


def test_future_different_workspace_cannot_reuse_approval(tmp_path: Path) -> None:
    gate = PermissionGate(str(tmp_path))
    args = {"file_path": CONSTITUTION_RELATIVE}
    digest = protection_action_digest("write_file", args)
    gate.set_protection_approvals((approval_for(".", action_digest=digest),))
    (tmp_path / "other").mkdir()
    gate.project_root = str(tmp_path / "other")
    assert gate.check("write_file", args) is Permission.DENY
