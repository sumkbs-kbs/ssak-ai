"""r30 P0: tool read boundary with synthetic projects A/B and a protected outside file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from antigravity_k.engine.file_summarizer import FileSummarizer
from antigravity_k.tools.file_tools import GlobSearchTool, GrepSearchTool
from antigravity_k.tools.system_tools import ListDirectoryTool, ReadFileTool
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_path import is_sensitive_path
from antigravity_k.tools.tool_registry import ToolRegistry

MARK_A = "SYNTH_A_MARKER_7f3"
MARK_B = "SYNTH_B_MARKER_2c9"
MARK_P = "SYNTH_PROTECTED_MARKER_91d"
MARK_ENV = "SYNTH_ENV_VALUE_55e"


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    a = tmp_path / "projA"
    b = tmp_path / "projB"
    (a / "src").mkdir(parents=True)
    (b / "src").mkdir(parents=True)
    (a / "src" / "main.py").write_text(f"# {MARK_A}\nprint('a')\n")
    (b / "src" / "other.py").write_text(f"# {MARK_B}\n")
    protected = tmp_path / "protected.txt"
    protected.write_text(MARK_P)
    (a / ".env").write_text(f"TOKEN={MARK_ENV}\n")
    (a / ".env.example").write_text("TOKEN=placeholder\n")
    os.symlink(protected, a / "link_to_protected.txt")
    os.symlink(b / "src", a / "linked_b_dir")
    return {"a": a, "b": b, "protected": protected}


def _registry(root: Path) -> ToolRegistry:
    reg = ToolRegistry(project_root=str(root))
    for tool in (ReadFileTool(), GlobSearchTool(), GrepSearchTool(), ListDirectoryTool()):
        _ = reg.install(tool)
    return reg


def test_read_allowed_in_project(world: dict[str, Path]) -> None:
    perm, out = _registry(world["a"]).execute_with_permission("read_file", {"file_path": "src/main.py"})
    assert perm is Permission.ALLOW
    assert MARK_A in out


@pytest.mark.parametrize(
    "raw",
    ["../protected.txt", "../projB/src/other.py", "link_to_protected.txt", "linked_b_dir/other.py"],
)
def test_read_relative_symlink_and_project_confusion_denied(world: dict[str, Path], raw: str) -> None:
    perm, out = _registry(world["a"]).execute_with_permission("read_file", {"file_path": raw})
    assert perm is not Permission.ALLOW
    assert MARK_P not in out and MARK_B not in out


@pytest.mark.parametrize("key", ["protected", "b"])
def test_read_absolute_outside_denied(world: dict[str, Path], key: str) -> None:
    target = world[key] if key == "protected" else world["b"] / "src" / "other.py"
    perm, out = _registry(world["a"]).execute_with_permission("read_file", {"file_path": str(target)})
    assert perm is not Permission.ALLOW
    assert MARK_P not in out and MARK_B not in out


def test_sensitive_in_project_read_requires_approval(world: dict[str, Path]) -> None:
    perm, out = _registry(world["a"]).execute_with_permission("read_file", {"file_path": ".env"})
    assert perm is Permission.PROMPT
    assert MARK_ENV not in out
    perm2, _ = _registry(world["a"]).execute_with_permission("read_file", {"file_path": ".env.example"})
    assert perm2 is Permission.ALLOW


def test_glob_root_escape_denied_and_matches_contained(world: dict[str, Path]) -> None:
    reg = _registry(world["a"])
    perm, out = reg.execute_with_permission("glob_search", {"pattern": "*.py", "root": str(world["b"])})
    assert perm is not Permission.ALLOW or "other.py" not in out
    perm, out = reg.execute_with_permission("glob_search", {"pattern": "**/*", "root": "."})
    assert perm is Permission.ALLOW
    assert "main.py" in out
    assert "other.py" not in out  # via symlinked dir
    assert ".env\n" not in out and not out.rstrip().endswith(".env")


def test_grep_does_not_traverse_outside_or_sensitive(world: dict[str, Path]) -> None:
    reg = _registry(world["a"])
    perm, out = reg.execute_with_permission("grep_search", {"query": "SYNTH_", "path": "."})
    assert perm is Permission.ALLOW
    assert MARK_A in out
    for forbidden in (MARK_B, MARK_P, MARK_ENV):
        assert forbidden not in out
    perm, out = reg.execute_with_permission("grep_search", {"query": "SYNTH_", "path": ".", "include": "../**/*"})
    for forbidden in (MARK_B, MARK_P):
        assert forbidden not in out


def test_list_directory_does_not_enter_outside_symlink(world: dict[str, Path]) -> None:
    perm, out = _registry(world["a"]).execute_with_permission(
        "list_directory", {"path": ".", "recursive": True, "max_depth": 3}
    )
    assert perm is Permission.ALLOW
    assert "main.py" in out
    assert "other.py" not in out
    perm, _ = _registry(world["a"]).execute_with_permission("list_directory", {"path": str(world["b"])})
    assert perm is not Permission.ALLOW


def test_file_summarizer_excludes_outside_and_sensitive(world: dict[str, Path]) -> None:
    text = FileSummarizer().summarize_files(
        [
            {"file": "src/main.py"},
            {"file": str(world["protected"])},
            {"file": "../projB/src/other.py"},
            {"file": ".env"},
        ],
        str(world["a"]),
    )
    assert MARK_P not in text and MARK_B not in text and MARK_ENV not in text
    assert text.count("범위 밖 또는 민감 파일") == 3


@pytest.mark.parametrize(
    ("path", "sensitive"),
    [
        (".env", True),
        ("x/.env.local", True),
        (".env.example", False),
        ("home/.ssh/config", True),
        ("certs/server.pem", True),
        ("id_ed25519", True),
        ("src/environment.py", False),
        ("docs/keys.md", False),
    ],
)
def test_is_sensitive_path(path: str, sensitive: bool) -> None:
    assert is_sensitive_path(path) is sensitive
