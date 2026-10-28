"""r34: secret-file contract at the real execution boundary (synthetic files only).

outside project = DENY; in-project secret-named = PROMPT for read_file, read_hash_file and
grep_search; approval is one-shot and bound to the inode seen at PROMPT time; reads go through
a verified handle (component-wise O_NOFOLLOW from the root fd).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from antigravity_k.tools import verified_read
from antigravity_k.tools.file_tools import GrepSearchTool
from antigravity_k.tools.hashline_tools import ReadHashFileTool
from antigravity_k.tools.system_tools import ReadFileTool
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

MARK_ENV = "SYNTH_ENV_VALUE_r34a"
MARK_SWAP = "SYNTH_SWAPPED_r34b"
MARK_OUT = "SYNTH_OUTSIDE_r34c"
MARK_OK = "SYNTH_PLAIN_r34d"


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    a = tmp_path / "proj"
    (a / "cfg").mkdir(parents=True)
    (a / ".env").write_text(f"TOKEN={MARK_ENV}\n")
    (a / "cfg" / ".env").write_text(f"TOKEN={MARK_ENV}\n")
    (a / "main.py").write_text(f"# {MARK_OK}\n")
    (a / "server.pem").write_text(f"KEY {MARK_ENV}\n")
    out = tmp_path / "outside.txt"
    out.write_text(MARK_OUT)
    return {"a": a, "out": out, "tmp": tmp_path}


def _reg(root: Path) -> ToolRegistry:
    reg = ToolRegistry(project_root=str(root))
    for tool in (ReadFileTool(), GrepSearchTool(), ReadHashFileTool()):
        _ = reg.install(tool)
    return reg


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("read_file", {"file_path": ".env"}),
        ("read_hash_file", {"file_path": ".env"}),
        ("grep_search", {"query": "TOKEN", "path": ".env"}),
        ("grep_search", {"query": "TOKEN", "path": "cfg/.env"}),
    ],
)
def test_every_content_reader_prompts_and_cache_does_not_bypass(world, tool, args) -> None:
    reg = _reg(world["a"])
    reg.permission_gate.record_approval(tool, reg.get(tool).risk_level.value)  # tool-level cache
    perm, out = reg.execute_with_permission(tool, args)
    assert perm is Permission.PROMPT and MARK_ENV not in out


def test_outside_is_deny_for_readers(world) -> None:
    reg = _reg(world["a"])
    for tool, args in (
        ("read_file", {"file_path": str(world["out"])}),
        ("grep_search", {"query": "S", "path": "../outside.txt"}),
    ):
        perm, out = reg.execute_with_permission(tool, args)
        assert perm is Permission.DENY and MARK_OUT not in out


def test_directory_grep_never_reads_secret_and_says_so(world) -> None:
    perm, out = _reg(world["a"]).execute_with_permission("grep_search", {"query": MARK_ENV, "path": "."})
    assert perm is Permission.ALLOW and MARK_ENV not in out.split("\n", 1)[-1].replace(f"'{MARK_ENV}'", "")
    assert "secret-named file(s) not searched" in out


def test_approved_read_is_one_shot_and_exact(world) -> None:
    reg = _reg(world["a"])
    perm, _ = reg.execute_with_permission("read_file", {"file_path": ".env"})
    assert perm is Permission.PROMPT
    assert MARK_ENV in reg.execute_approved("read_file", {"file_path": ".env"})
    perm, out = reg.execute_with_permission("read_file", {"file_path": ".env"})
    assert perm is Permission.PROMPT and MARK_ENV not in out  # grant consumed
    # approval for .env never covers cfg/.env
    assert MARK_ENV not in reg.execute_approved("read_file", {"file_path": "cfg/.env"})


def test_approval_without_prior_prompt_is_refused(world) -> None:
    assert MARK_ENV not in _reg(world["a"]).execute_approved("read_file", {"file_path": ".env"})


def test_replace_between_prompt_and_execution_is_refused(world) -> None:
    reg = _reg(world["a"])
    perm, _ = reg.execute_with_permission("read_file", {"file_path": ".env"})
    assert perm is Permission.PROMPT
    swap = world["a"] / ".env.new"
    swap.write_text(f"TOKEN={MARK_SWAP}\n")
    os.replace(swap, world["a"] / ".env")  # different inode under the approved name
    out = reg.execute_approved("read_file", {"file_path": ".env"})
    assert MARK_SWAP not in out and MARK_ENV not in out


def test_symlink_swap_to_outside_after_prompt_is_denied(world) -> None:
    reg = _reg(world["a"])
    perm, _ = reg.execute_with_permission("read_file", {"file_path": ".env"})
    assert perm is Permission.PROMPT
    os.unlink(world["a"] / ".env")
    os.symlink(world["out"], world["a"] / ".env")
    out = reg.execute_approved("read_file", {"file_path": ".env"})
    assert MARK_OUT not in out


def test_parent_dir_symlink_swap_is_refused_by_verified_open(world) -> None:
    a = world["a"]
    evil = world["tmp"] / "evil"
    evil.mkdir()
    (evil / ".env").write_text(f"TOKEN={MARK_SWAP}\n")
    os.rename(a / "cfg", a / "cfg_old")
    os.symlink(evil, a / "cfg")
    with pytest.raises(verified_read.VerifiedReadError):
        verified_read.open_verified(str(a / "cfg" / ".env"), str(a))
    # inside-project parent symlink is also refused at open time (no follow)
    os.unlink(a / "cfg")
    os.symlink(a / "cfg_old", a / "cfg")
    with pytest.raises(verified_read.VerifiedReadError):
        verified_read.open_verified(str(a / "cfg" / ".env"), str(a))


def test_direct_tool_call_without_grant_cannot_read_secret(world) -> None:
    out = ReadFileTool().execute(file_path=str(world["a"] / ".env"))
    assert MARK_ENV not in out and "per-file approval" in out
    out = GrepSearchTool().execute(query="TOKEN", path=str(world["a"] / ".env"))
    assert MARK_ENV not in out


def test_normal_reads_still_work(world) -> None:
    perm, out = _reg(world["a"]).execute_with_permission("read_file", {"file_path": "main.py"})
    assert perm is Permission.ALLOW and MARK_OK in out
    assert verified_read.supported()
