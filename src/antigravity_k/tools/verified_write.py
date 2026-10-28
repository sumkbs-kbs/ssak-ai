"""Project-bound text writes through directory handles, without following aliases."""

from __future__ import annotations

import errno
import os
import secrets
import stat
import sys


class VerifiedWriteError(OSError):
    pass


def _parts(path: str, root: str) -> list[str]:
    absolute, base = os.path.abspath(path), os.path.abspath(root)
    if os.path.commonpath([absolute, base]) != base:
        raise VerifiedWriteError("write target is outside the project")
    parts = os.path.relpath(absolute, base).split(os.sep)
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise VerifiedWriteError("invalid write target")
    return parts


def _target_mode(parent: int, name: str, *, overwrite: bool) -> int:
    try:
        target = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return 0o666
    if not stat.S_ISREG(target.st_mode) or target.st_nlink != 1:
        raise VerifiedWriteError("write target must be a single-link regular file")
    if not overwrite:
        raise FileExistsError(errno.EEXIST, "file already exists", name)
    return stat.S_IMODE(target.st_mode)


def write_text_under(path: str, root: str, content: str, *, overwrite: bool = True) -> None:
    """Write under a pinned root; a missing parent is created relative to its handle.

    Every parent is opened without following links. Existing targets must be
    regular single-link files. Installation replaces a name, never an aliased
    inode; exclusive creation uses link() so a raced-in file cannot be overwritten.
    """
    required = (os.open, os.mkdir, os.stat, os.unlink, os.link, os.rename)
    if not hasattr(os, "O_NOFOLLOW") or not all(fn in os.supports_dir_fd for fn in required):
        raise VerifiedWriteError("verified write unsupported on this platform")
    parts = _parts(path, root)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    parent = -1
    temporary: str | None = None
    try:
        parent = os.open(os.path.abspath(root), flags)
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=parent)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o755, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child

        name = parts[-1]
        mode = _target_mode(parent, name, overwrite=overwrite)
        candidate = ".ssak-write-" + secrets.token_hex(12)
        fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        temporary = candidate
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Recheck the path state after preparing content. A raced-in link is
        # refused; the final operation itself also never follows its target.
        _target_mode(parent, name, overwrite=overwrite)
        if overwrite:
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent)
        temporary = None
        os.fsync(parent)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise VerifiedWriteError("write path contains a link or non-directory") from error
        raise
    finally:
        pending_error = sys.exception()
        try:
            if temporary is not None and parent >= 0:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
                except OSError:
                    if pending_error is None:
                        raise
                    pending_error.add_note("temporary write cleanup also failed")
        finally:
            if parent >= 0:
                os.close(parent)
