"""Owned temporary-file effects at verified-write installation and failure boundaries."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from antigravity_k.tools import verified_write as writes


def test_nested_missing_parents_receive_exact_utf8_content(tmp_path: Path) -> None:
    # Given: a project root with no descendants at the requested target.
    target = tmp_path / "one" / "two" / "three" / "result.txt"
    content = "중첩 쓰기 🌈\nsecond line\n"
    # When: verified writing creates the parent chain and installs the file.
    writes.write_text_under(str(target), str(tmp_path), content)
    # Then: exact bytes exist at that target and no installation temporary remains.
    assert target.read_bytes() == content.encode("utf-8")
    assert set(target.parent.iterdir()) == {target}


def test_exclusive_existing_target_keeps_its_bytes_and_inode(tmp_path: Path) -> None:
    # Given: a single-link file already occupies an exclusive creation target.
    target = tmp_path / "existing.txt"
    target.write_bytes(b"original bytes\n")
    identity = target.stat().st_ino
    # When: overwrite=False requests a different value at that existing name.
    with pytest.raises(FileExistsError):
        writes.write_text_under(str(target), str(tmp_path), "replacement", overwrite=False)
    # Then: no existing inode/content is replaced and no temporary file survives.
    assert target.stat().st_ino == identity
    assert target.read_bytes() == b"original bytes\n"
    assert set(tmp_path.iterdir()) == {target}


def test_exclusive_install_race_preserves_the_raced_in_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a competitor creates a plain target immediately before atomic installation.
    target = tmp_path / "raced.txt"
    original_link = os.link
    raced = b"competitor's owned synthetic file\n"

    def racing_link(
        source: str, destination: str, *, src_dir_fd: int, dst_dir_fd: int, follow_symlinks: bool,
    ) -> None:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dst_dir_fd)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raced)
        original_link(source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
                      follow_symlinks=follow_symlinks)

    # Keep the wrapper's declared dirfd support so the intended race is reached.
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {racing_link})
    monkeypatch.setattr(os, "link", racing_link)
    # When: the exclusive install loses that last-moment creation race.
    with pytest.raises(FileExistsError):
        writes.write_text_under(str(target), str(tmp_path), "writer content", overwrite=False)
    # Then: the competitor remains intact and the writer's temporary is removed.
    assert target.read_bytes() == raced
    assert set(tmp_path.iterdir()) == {target}


def test_file_sync_failure_preserves_existing_target_and_cleans_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: disk persistence fails after writing the temporary and before installation.
    target = tmp_path / "retained.txt"
    target.write_bytes(b"old committed bytes\n")
    identity = target.stat().st_ino
    attempted: list[int] = []
    original_sync = os.fsync

    def disk_full(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            attempted.append(descriptor)
            raise OSError(errno.ENOSPC, "synthetic file persistence failure")
        original_sync(descriptor)

    monkeypatch.setattr(os, "fsync", disk_full)
    # When: the prepared content cannot be durably synced.
    with pytest.raises(OSError) as failure:
        writes.write_text_under(str(target), str(tmp_path), "new uncommitted bytes 🌿\n")
    # Then: the failure occurred before replacement; all owned temporaries are gone.
    assert failure.value.errno == errno.ENOSPC and attempted
    assert target.stat().st_ino == identity
    assert target.read_bytes() == b"old committed bytes\n"
    assert set(tmp_path.iterdir()) == {target}


def test_install_failure_preserves_existing_target_and_cleans_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: content is prepared successfully, but its atomic installation fails.
    target = tmp_path / "install-retained.txt"
    target.write_bytes(b"old installed bytes\n")
    identity = target.stat().st_ino
    attempted: list[str] = []

    def failed_replace(source: str, destination: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
        del source, src_dir_fd, dst_dir_fd
        attempted.append(destination)
        raise OSError(errno.EIO, "synthetic installation failure")

    monkeypatch.setattr(os, "replace", failed_replace)
    # When: installation fails before changing the target name.
    with pytest.raises(OSError) as failure:
        writes.write_text_under(str(target), str(tmp_path), "new prepared bytes")
    # Then: old content/inode survive, and the prepared temporary is removed.
    assert failure.value.errno == errno.EIO and attempted == [target.name]
    assert target.stat().st_ino == identity
    assert target.read_bytes() == b"old installed bytes\n"
    assert set(tmp_path.iterdir()) == {target}


def test_temporary_name_collision_never_deletes_the_existing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a different owned file already has the next temporary candidate name.
    suffix = "c" * 24
    candidate = tmp_path / (".ssak-write-" + suffix)
    candidate.write_bytes(b"pre-existing candidate must survive\n")
    target = tmp_path / "new.txt"
    monkeypatch.setattr(writes.secrets, "token_hex", lambda _count: suffix)
    # When: exclusive temporary creation collides before this invocation owns an fd.
    with pytest.raises(FileExistsError):
        writes.write_text_under(str(target), str(tmp_path), "new content")
    # Then: the old candidate is preserved and no target was installed.
    assert candidate.read_bytes() == b"pre-existing candidate must survive\n"
    assert set(tmp_path.iterdir()) == {candidate}


def test_unsupported_dirfd_platform_refuses_before_creating_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the platform cannot provide any of the required dirfd operations.
    monkeypatch.setattr(os, "supports_dir_fd", set())
    target = tmp_path / "missing" / "nested" / "new.txt"
    # When: verified writing cannot establish its path guarantees.
    with pytest.raises(writes.VerifiedWriteError):
        writes.write_text_under(str(target), str(tmp_path), "must not be written")
    # Then: even missing parents remain uncreated.
    assert tuple(tmp_path.iterdir()) == ()


def test_cleanup_failure_still_closes_the_pinned_parent_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a preinstall disk failure is followed by an unlink failure during cleanup.
    target = tmp_path / "old.txt"
    target.write_bytes(b"committed\n")
    parent_handles: list[tuple[int, int, int]] = []
    original_close = os.close
    original_sync = os.fsync

    def failed_sync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(errno.EIO, "synthetic disk error")
        original_sync(descriptor)

    def failed_unlink(_path: str, *, dir_fd: int) -> None:
        identity = os.fstat(dir_fd)
        parent_handles.append((dir_fd, identity.st_dev, identity.st_ino))
        raise OSError(errno.EACCES, "synthetic cleanup error")

    try:
        with monkeypatch.context() as faults:
            faults.setattr(os, "supports_dir_fd", os.supports_dir_fd | {failed_unlink})
            faults.setattr(os, "fsync", failed_sync)
            faults.setattr(os, "unlink", failed_unlink)
            # When: cleanup itself cannot unlink the owned temporary.
            with pytest.raises(OSError) as operation_failure:
                writes.write_text_under(str(target), str(tmp_path), "uncommitted")
        # Then: the original data survives and the pinned directory fd is closed.
        assert operation_failure.value.errno == errno.EIO
        assert parent_handles
        with pytest.raises(OSError) as failure:
            os.fstat(parent_handles[0][0])
        assert failure.value.errno == errno.EBADF
        assert target.read_bytes() == b"committed\n"
    finally:
        # Release only this fixture's leaked handle if the regression is reproduced.
        for descriptor, device, inode in parent_handles:
            try:
                current = os.fstat(descriptor)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise
            else:
                if (current.st_dev, current.st_ino) == (device, inode):
                    original_close(descriptor)
        for temporary in tmp_path.glob(".ssak-write-*"):
            temporary.unlink()
