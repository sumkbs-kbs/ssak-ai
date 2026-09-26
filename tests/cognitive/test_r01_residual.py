"""R01 residuals: seatbelt deny order + non-macOS fail-closed + digest binding."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from antigravity_k.engine.cognitive.protected_targets import CONSTITUTION_DOC
from antigravity_k.engine.sandbox import SandboxRunner
from antigravity_k.tools.permission_gate import PermissionGate, protection_action_digest
from antigravity_k.tools.tool_contracts import Permission
from tests.cognitive.test_protection import approval_for


def test_r01_seatbelt_deny_follows_broad_allow(tmp_path: Path) -> None:
    cons = tmp_path / CONSTITUTION_DOC
    cons.parent.mkdir(parents=True)
    cons.write_bytes(b"CONST\n")
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, network="none", require_sandbox=True)
    profile = runner.build_seatbelt_profile()
    root = os.path.realpath(tmp_path)
    cons_real = os.path.realpath(cons)
    allow_root = f'(allow file-write* (subpath "{root}"))'
    deny_cons = f'(deny file-write* (subpath "{cons_real}"))'
    assert allow_root in profile
    assert deny_cons in profile
    assert profile.index(allow_root) < profile.index(deny_cons)
    folders = '(allow file-write* (subpath "/private/var/folders"))'
    if folders in profile:
        assert profile.index(folders) < profile.index(deny_cons)


def test_r01_non_darwin_without_docker_is_fail_closed(tmp_path: Path) -> None:
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, network="none", require_sandbox=True)
    with (
        patch.object(runner, "_platform", "Linux"),
        patch.object(SandboxRunner, "_is_docker_available", return_value=False),
    ):
        result = runner.execute("echo hi", timeout=5)
    assert not result.success
    err = (result.error or "").lower()
    assert "unavailable" in err or "disabled" in err or "refused" in err


def test_r01_docker_cmd_includes_readonly_protected_mounts(tmp_path: Path) -> None:
    cons = tmp_path / CONSTITUTION_DOC
    cons.parent.mkdir(parents=True)
    cons.write_bytes(b"CONST\n")
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, network="none", require_sandbox=True)
    with patch.object(runner, "_run_limited_process", return_value=(0, "", "", False)) as mocked:
        with patch.object(SandboxRunner, "_is_docker_available", return_value=True):
            with patch.object(runner, "_platform", "Linux"):
                result = runner.execute("echo hi", timeout=5)
    assert result.sandboxed is True
    cmd = mocked.call_args.args[0]
    assert isinstance(cmd, list)
    joined = " ".join(cmd)
    assert ":ro" in joined
    assert "ssak-ai-core" in joined


def test_r01_protection_action_digest_binds_approval(tmp_path: Path) -> None:
    (tmp_path / "docs/ssak-ai-core").mkdir(parents=True)
    (tmp_path / CONSTITUTION_DOC).write_text("c\n")
    gate = PermissionGate(str(tmp_path))
    args = {"file_path": CONSTITUTION_DOC, "content": "approved"}
    digest = protection_action_digest("write_file", args)
    gate.set_protection_approvals((approval_for(".", action_digest=digest),))
    assert gate.check("write_file", args) is Permission.ALLOW
    assert gate.check("write_file", {**args, "content": "other"}) is Permission.DENY
