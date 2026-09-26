"""R01: protected targets must stay immutable at the real OS sandbox boundary."""

from __future__ import annotations

import hashlib
import os
import textwrap
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.protected_targets import CONSTITUTION_DOC
from antigravity_k.engine.sandbox import SandboxRunner
from antigravity_k.tools.permission_gate import PermissionGate, protection_action_digest
from antigravity_k.tools.tool_contracts import Permission
from tests.cognitive.test_protection import approval_for

pytestmark = pytest.mark.skipif(
    os.uname().sysname != "Darwin",
    reason="R01 OS boundary scenarios require macOS seatbelt in this checkout",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    cons = tmp_path / CONSTITUTION_DOC
    cons.parent.mkdir(parents=True)
    cons.write_bytes(b"CONST v1\n")
    sibling = cons.parent / "NOTES.md"
    sibling.write_text("notes\n")
    return cons, sibling, tmp_path / "ok.txt"


def _run_script(runner: SandboxRunner, root: Path, name: str, body: str):
    script = root / name
    script.write_text(textwrap.dedent(body))
    return runner.execute(f"python3 {script}", timeout=15)


def test_r01_a1_write_bytes_os_replace_parent_rename_symlink_immutable(tmp_path: Path) -> None:
    cons, _sibling, _ok = _fixture(tmp_path)
    before = _sha(cons)
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, network="none", require_sandbox=True)

    r = _run_script(
        runner,
        tmp_path,
        "_w.py",
        f"from pathlib import Path\nPath({str(cons)!r}).write_bytes(b'HACKED')\n",
    )
    assert not r.success
    assert _sha(cons) == before

    r = _run_script(
        runner,
        tmp_path,
        "_r.py",
        f"import os\nfrom pathlib import Path\nt=Path({str(tmp_path)!r})/'_t'; t.write_bytes(b'R'); os.replace(t, Path({str(cons)!r}))\n",
    )
    assert not r.success
    assert _sha(cons) == before

    r = _run_script(
        runner,
        tmp_path,
        "_mv.py",
        f"import os\nos.rename({str(cons.parent)!r}, {str(tmp_path / 'moved_core')!r})\n",
    )
    assert not r.success
    assert cons.exists()
    assert _sha(cons) == before

    r = _run_script(
        runner,
        tmp_path,
        "_sym.py",
        f"import os\nfrom pathlib import Path\nlink=Path({str(tmp_path)!r})/'l'; os.symlink({str(cons)!r}, link); link.write_bytes(b'X')\n",
    )
    assert not r.success
    assert _sha(cons) == before


def test_r01_a2_ordinary_and_sibling_writes_succeed(tmp_path: Path) -> None:
    cons, sibling, ok = _fixture(tmp_path)
    before = _sha(cons)
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, network="none", require_sandbox=True)

    r = _run_script(runner, tmp_path, "_ok.py", f"from pathlib import Path\nPath({str(ok)!r}).write_text('yes')\n")
    assert r.success
    assert ok.read_text() == "yes"

    r = _run_script(
        runner,
        tmp_path,
        "_sib.py",
        f"from pathlib import Path\nPath({str(sibling)!r}).write_text('side')\n",
    )
    assert r.success
    assert sibling.read_text() == "side"
    assert _sha(cons) == before


def test_r01_a3_approval_does_not_reuse_across_args(tmp_path: Path) -> None:
    _fixture(tmp_path)
    gate = PermissionGate(str(tmp_path))
    args = {"file_path": CONSTITUTION_DOC, "content": "approved"}
    digest = protection_action_digest("write_file", args)
    gate.set_protection_approvals((approval_for(".", action_digest=digest),))
    assert gate.check("write_file", args) is Permission.ALLOW
    assert gate.check("write_file", {**args, "content": "other"}) is Permission.DENY


def test_r01_a4_unavailable_or_disabled_sandbox_is_fail_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    runner = SandboxRunner(project_root=str(tmp_path), enabled=False, require_sandbox=True)
    result = runner.execute("echo hi", timeout=5)
    assert not result.success
    assert "refused" in (result.error or "").lower()


def test_r01_gate_blocks_interpreter_write_bytes_without_token_list(tmp_path: Path) -> None:
    _fixture(tmp_path)
    gate = PermissionGate(str(tmp_path))
    cmd = f"python3 -c \"from pathlib import Path; Path('{CONSTITUTION_DOC}').write_bytes(b'x')\""
    assert gate.check("run_bash_command", {"command": cmd}) is Permission.DENY
    assert (
        gate.check(
            "run_bash_command",
            {"command": "python3 -c \"import os; os.rename('docs/ssak-ai-core','moved')\""},
        )
        is Permission.DENY
    )
