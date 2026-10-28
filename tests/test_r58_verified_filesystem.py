"""Verified-handle helper contracts using only owned synthetic trees.

These do not repeat the HTTP permission-to-parent-swap regressions. The final
destination existence check and os.rename are still separate: concurrent
destination creation in that interval is not claimed to be protected here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from antigravity_k.tools import verified_filesystem as filesystem


def _tree(root: Path) -> dict[str, tuple[str, int, bytes]]:
    """Observe contents and identity without following fixture links."""
    observed: dict[str, tuple[str, int, bytes]] = {}
    for path in [root, *sorted(root.rglob("*"))]:
        name = "." if path == root else path.relative_to(root).as_posix()
        identity = path.stat(follow_symlinks=False).st_ino
        if path.is_symlink():
            observed[name] = ("link", identity, os.readlink(path).encode())
        elif path.is_dir():
            observed[name] = ("directory", identity, b"")
        else:
            observed[name] = ("file", identity, path.read_bytes())
    return observed


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "keep.txt").write_bytes(b"synthetic survivor")
    return root


def test_nested_creation_and_root_listing_keep_existing_entries(project: Path) -> None:
    target = project / "nested/branch/leaf"
    assert filesystem.make_directory_under(str(target), str(project)) is True
    assert target.is_dir()
    (target / "note.txt").write_bytes(b"nested synthetic note")
    before = _tree(project)
    assert filesystem.make_directory_under(str(target), str(project)) is False
    assert filesystem.make_directory_under(str(project), str(project)) is False
    assert filesystem.make_directory_under(str(project / "keep.txt"), str(project)) is False
    root_entries = filesystem.list_directory_under(str(project), str(project))
    assert root_entries is not None
    assert sorted((entry.name, entry.is_dir) for entry in root_entries) == [("keep.txt", False), ("nested", True)]
    leaf_entries = filesystem.list_directory_under(str(target), str(project))
    assert leaf_entries is not None
    assert [(entry.name, entry.is_dir) for entry in leaf_entries] == [("note.txt", False)]
    assert _tree(project) == before


def test_recursive_delete_removes_real_tree_without_following_internal_link(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-fixture"
    outside.mkdir()
    (outside / "canary.txt").write_bytes(b"synthetic outside canary")
    target = project / "remove-tree"
    (target / "nested/deeper").mkdir(parents=True)
    (target / "nested/deeper/data.txt").write_bytes(b"synthetic recursive delete target")
    (target / "linked-directory").symlink_to(outside, target_is_directory=True)
    outside_before = _tree(outside)
    survivor = (project / "keep.txt").stat().st_ino

    assert filesystem.delete_path_under(str(target), str(project)) is True

    assert not target.exists()
    assert _tree(outside) == outside_before
    assert (project / "keep.txt").read_bytes() == b"synthetic survivor"
    assert (project / "keep.txt").stat().st_ino == survivor
    assert filesystem.delete_path_under(str(target), str(project)) is False


def test_directory_rename_preserves_nested_contents_and_identity(project: Path) -> None:
    source = project / "origin/folder"
    destination = project / "other/renamed"
    (source / "nested/deeper").mkdir(parents=True)
    (source / "note.txt").write_bytes(b"synthetic directory note")
    (source / "nested/deeper/data.bin").write_bytes(b"\x00synthetic nested bytes\xff")
    destination.parent.mkdir()
    source_before = _tree(source)
    survivor = project / "keep.txt"
    survivor_before = (survivor.stat().st_ino, survivor.read_bytes())

    assert filesystem.rename_path_under(str(source), str(destination), str(project)) is True

    assert not source.exists()
    assert destination.is_dir()
    assert _tree(destination) == source_before
    assert (survivor.stat().st_ino, survivor.read_bytes()) == survivor_before


@pytest.mark.parametrize("operation", ["delete", "rename-source", "rename-destination"])
def test_project_root_mutation_is_refused_before_any_change(project: Path, operation: str) -> None:
    source, destination = project / "keep.txt", project / "renamed"
    before = _tree(project)

    with pytest.raises(filesystem.VerifiedFilesystemError, match="project root"):
        if operation == "delete":
            filesystem.delete_path_under(str(project), str(project))
        elif operation == "rename-source":
            filesystem.rename_path_under(str(project), str(destination), str(project))
        else:
            filesystem.rename_path_under(str(source), str(project), str(project))

    assert _tree(project) == before
    assert not destination.exists()


@pytest.mark.parametrize("operation", ["mkdir", "list", "delete", "rename-source", "rename-destination"])
def test_final_link_is_refused_and_both_synthetic_trees_are_preserved(
    project: Path, tmp_path: Path, operation: str,
) -> None:
    outside = tmp_path / "outside-fixture"
    outside.mkdir()
    (outside / "canary.txt").write_bytes(b"synthetic link target")
    link = project / "final-link"
    link.symlink_to(outside, target_is_directory=True)
    before, outside_before = _tree(project), _tree(outside)

    with pytest.raises(filesystem.VerifiedFilesystemError, match="link"):
        if operation == "mkdir":
            filesystem.make_directory_under(str(link), str(project))
        elif operation == "list":
            filesystem.list_directory_under(str(link), str(project))
        elif operation == "delete":
            filesystem.delete_path_under(str(link), str(project))
        elif operation == "rename-source":
            filesystem.rename_path_under(str(link), str(project / "moved"), str(project))
        else:
            filesystem.rename_path_under(str(project / "keep.txt"), str(link), str(project))

    assert _tree(project) == before
    assert _tree(outside) == outside_before


@pytest.mark.parametrize(
    ("operation", "missing_capability"),
    [("mkdir", "mkdir"), ("delete", "unlink"), ("rename", "rename"), ("mkdir", "open"), ("mkdir", "stat")],
    ids=["mkdir-dir-fd", "unlink-dir-fd", "rename-dir-fd", "open-dir-fd", "stat-dir-fd"],
)
def test_missing_dir_fd_support_is_rejected_before_mutation(
    project: Path, monkeypatch: pytest.MonkeyPatch, operation: str, missing_capability: str,
) -> None:
    target = project / "remove-tree"
    target.mkdir()
    (target / "nested.txt").write_bytes(b"synthetic target")
    before = _tree(project)
    missing = getattr(os, missing_capability)
    monkeypatch.setattr(os, "supports_dir_fd", set(os.supports_dir_fd) - {missing})

    with pytest.raises(filesystem.VerifiedFilesystemError, match="unsupported"):
        if operation == "mkdir":
            filesystem.make_directory_under(str(project / "new-parent/new-child"), str(project))
        elif operation == "delete":
            filesystem.delete_path_under(str(target), str(project))
        else:
            filesystem.rename_path_under(str(project / "keep.txt"), str(project / "moved.txt"), str(project))

    assert _tree(project) == before


@pytest.mark.parametrize("missing_capability", ["symlink-defense", "dir-fd-signature"])
def test_unsafe_recursive_delete_platform_is_refused_before_removal(
    project: Path, monkeypatch: pytest.MonkeyPatch, missing_capability: str,
) -> None:
    target = project / "remove-tree"
    (target / "nested").mkdir(parents=True)
    (target / "nested/data.txt").write_bytes(b"synthetic recursive target")
    before = _tree(project)
    calls: list[object] = []

    def unsafe_rmtree(path: object, *args: object, **kwargs: object) -> None:
        calls.append((path, args, kwargs))
        raise AssertionError("Unsupported recursive primitive must never be invoked")

    # For the signature case, expose the safety flag while deliberately omitting
    # the named dir_fd parameter. No recursive deletion implementation is run.
    setattr(unsafe_rmtree, "avoids_symlink_attacks", missing_capability != "symlink-defense")
    monkeypatch.setattr(shutil, "rmtree", unsafe_rmtree)

    with pytest.raises(filesystem.VerifiedFilesystemError, match="unsupported"):
        filesystem.delete_path_under(str(target), str(project))

    assert calls == []
    assert _tree(project) == before


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_rename_destination_is_a_conflict_without_overwriting(project: Path, kind: str) -> None:
    source, destination = project / "source", project / "destination"
    if kind == "file":
        source.write_bytes(b"synthetic source")
        destination.write_bytes(b"synthetic existing destination")
    else:
        source.mkdir()
        (source / "source-only.txt").write_bytes(b"synthetic directory source")
        destination.mkdir()
    before = _tree(project)

    assert filesystem.rename_path_under(str(source), str(destination), str(project)) is False

    assert _tree(project) == before
