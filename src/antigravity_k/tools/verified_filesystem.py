"""Project-bound filesystem operations through verified directory handles."""

from __future__ import annotations

import errno
import inspect
import os
import shutil
import stat
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass


class VerifiedFilesystemError(OSError):
    pass


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    name: str
    is_dir: bool


def _require_dir_fd(*functions: Callable[..., object]) -> None:
    if any(function not in os.supports_dir_fd for function in functions):
        raise VerifiedFilesystemError("directory-relative operation unsupported; refusing")


def _parts(path: str, root: str, *, allow_root: bool = False) -> tuple[str, ...]:
    absolute, base = os.path.abspath(path), os.path.abspath(root)
    try:
        inside = os.path.commonpath([absolute, base]) == base
    except ValueError:
        inside = False
    if not inside:
        raise VerifiedFilesystemError("target is outside the project")
    parts = tuple(part for part in os.path.relpath(absolute, base).split(os.sep) if part not in ("", "."))
    if ".." in parts or (not parts and not allow_root):
        raise VerifiedFilesystemError("operation on the project root is refused")
    return parts


def _open_directory(path: str, *, parent: int | None = None) -> int:
    before = os.stat(path, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISLNK(before.st_mode):
        raise VerifiedFilesystemError("directory path contains a link")
    if not stat.S_ISDIR(before.st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "not a directory", path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags, dir_fd=parent)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise VerifiedFilesystemError("directory changed during verified open") from error
        raise
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise VerifiedFilesystemError("directory identity changed during verified open")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _root_handle(root: str) -> Iterator[int]:
    _require_dir_fd(os.open, os.stat)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or os.stat not in os.supports_follow_symlinks:
        raise VerifiedFilesystemError("verified directory open unsupported; refusing")
    descriptor = _open_directory(os.path.abspath(root))
    try:
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _directory_handle(root: int, parts: Sequence[str], *, create: bool = False) -> Iterator[int]:
    current = os.dup(root)
    try:
        for part in parts:
            try:
                child = _open_directory(part, parent=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, dir_fd=current)
                except FileExistsError:
                    pass
                child = _open_directory(part, parent=current)
            previous, current = current, child
            os.close(previous)
        yield current
    finally:
        os.close(current)


def _entry(parent: int, name: str) -> os.stat_result | None:
    try:
        entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(entry.st_mode):
        raise VerifiedFilesystemError("final target is a link")
    return entry


def make_directory_under(path: str, root: str) -> bool:
    """Create missing directories under pinned parents; return false for an existing target."""
    _require_dir_fd(os.mkdir)
    parts = _parts(path, root, allow_root=True)
    with _root_handle(root) as root_descriptor:
        if not parts:
            return False
        with _directory_handle(root_descriptor, parts[:-1], create=True) as parent:
            if _entry(parent, parts[-1]) is not None:
                return False
            try:
                os.mkdir(parts[-1], dir_fd=parent)
            except FileExistsError:
                _entry(parent, parts[-1])
                return False
            return True


def list_directory_under(path: str, root: str) -> list[DirectoryEntry] | None:
    """List a verified directory, including the project root, without following entry links."""
    if os.scandir not in os.supports_fd:
        raise VerifiedFilesystemError("directory-handle listing unsupported; refusing")
    parts = _parts(path, root, allow_root=True)
    try:
        with _root_handle(root) as root_descriptor, _directory_handle(root_descriptor, parts) as directory:
            with os.scandir(directory) as entries:
                return [DirectoryEntry(entry.name, entry.is_dir(follow_symlinks=False)) for entry in entries]
    except (FileNotFoundError, NotADirectoryError):
        return None


def _require_safe_recursive_delete() -> None:
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise VerifiedFilesystemError("safe recursive deletion unsupported; refusing")
    try:
        supported = "dir_fd" in inspect.signature(shutil.rmtree).parameters
    except (TypeError, ValueError):
        supported = False
    if not supported:
        raise VerifiedFilesystemError("directory-relative recursive deletion unsupported; refusing")


def delete_path_under(path: str, root: str) -> bool:
    """Remove a child entry under a pinned parent; the project root is never a target."""
    _require_dir_fd(os.unlink)
    parts = _parts(path, root)
    try:
        with _root_handle(root) as root_descriptor, _directory_handle(root_descriptor, parts[:-1]) as parent:
            entry = _entry(parent, parts[-1])
            if entry is None:
                return False
            if stat.S_ISDIR(entry.st_mode):
                _require_safe_recursive_delete()
                try:
                    shutil.rmtree(parts[-1], dir_fd=parent)
                except OSError as error:
                    raise VerifiedFilesystemError(
                        "recursive target could not be removed through verified handles"
                    ) from error
            else:
                os.unlink(parts[-1], dir_fd=parent)
            return True
    except (FileNotFoundError, NotADirectoryError):
        return False


def rename_path_under(source: str, destination: str, root: str) -> bool:
    """Rename through parents anchored to the same root; an existing destination is a conflict."""
    _require_dir_fd(os.rename)
    source_parts, destination_parts = _parts(source, root), _parts(destination, root)
    with _root_handle(root) as root_descriptor:
        with _directory_handle(root_descriptor, source_parts[:-1]) as source_parent:
            if _entry(source_parent, source_parts[-1]) is None:
                raise FileNotFoundError(errno.ENOENT, "source not found", source_parts[-1])
            with _directory_handle(root_descriptor, destination_parts[:-1]) as destination_parent:
                if _entry(destination_parent, destination_parts[-1]) is not None:
                    return False
                os.rename(
                    source_parts[-1],
                    destination_parts[-1],
                    src_dir_fd=source_parent,
                    dst_dir_fd=destination_parent,
                )
                return True
