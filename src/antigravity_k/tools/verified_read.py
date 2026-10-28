"""r34: verified-handle reads for content-reading tools (read_file, read_hash_file, grep_search).

Guarantee (POSIX with dir_fd support — macOS/Linux):
  * The path is opened component-by-component from an fd of the canonical project root with
    O_NOFOLLOW on every directory and on the final file, so a symlink introduced anywhere in the
    chain (parent swap or final swap) after the policy check fails with ELOOP/ENOTDIR instead of
    being followed. The content is read from that same fd (no re-open by name).
  * fstat on the opened fd must be a regular file.
  * For a secret-named file the fd's (st_dev, st_ino) must equal the identity captured when the
    user was asked (PROMPT). A rename/replace between approval and execution => refused.
  * If dir_fd/O_NOFOLLOW is unavailable the guarantee cannot be proven and secret reads are
    refused (non-secret reads also fail closed with an explicit error).
  * r35 content binding: the approval identity is (st_dev, st_ino, sha256 of the bytes read from the
    fd at PROMPT time). At execution the bytes are read ONCE from the verified fd, hashed, compared,
    and exactly those bytes are decoded and returned (no check-then-reopen). Changed content on the
    same inode => SecretReadRefused; the one-shot grant is already consumed, so re-approval is needed.
  * r37: files with st_nlink > 1 are refused (hard-link alias to an outside/secret inode, found by the
    r37 adversarial run c04). Limits: secret detection is still name-based for single-link files.
"""

from __future__ import annotations

import contextvars
import hashlib
import os
import stat

from antigravity_k.tools.tool_path import is_sensitive_path

Identity = tuple[int, int, str]

READ_ROOT: contextvars.ContextVar[str | None] = contextvars.ContextVar("agk_read_root", default=None)
APPROVED_TARGET: contextvars.ContextVar[tuple[str, Identity] | None] = contextvars.ContextVar(
    "agk_approved_secret_target", default=None
)


class VerifiedReadError(OSError):
    pass


class SecretReadRefused(VerifiedReadError):
    pass


def supported() -> bool:
    return hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd


def _components(path: str, root: str) -> list[str]:
    absolute = os.path.abspath(path)
    base = None
    for cand in (os.path.abspath(root), os.path.realpath(root)):
        try:
            if os.path.commonpath([absolute, cand]) == cand:
                base = cand
                break
        except ValueError:
            continue
    if base is None:
        raise VerifiedReadError(f"outside root: {os.path.basename(path)}")
    rel = os.path.relpath(absolute, base)
    parts = [p for p in rel.split(os.sep) if p not in ("", ".")]
    if not parts or ".." in parts:
        raise VerifiedReadError("invalid relative path")
    return parts


def open_verified(path: str, root: str) -> tuple[int, Identity]:
    if not supported():
        raise VerifiedReadError("verified open unsupported on this platform; refusing")
    parts = _components(path, root)
    dir_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    cur = os.open(os.path.realpath(root), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        for comp in parts[:-1]:
            nxt = os.open(comp, dir_flags, dir_fd=cur)
            os.close(cur)
            cur = nxt
        fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=cur,
        )
    except OSError as exc:
        raise VerifiedReadError(f"verified open refused ({exc.strerror}): {os.path.basename(path)}") from exc
    finally:
        os.close(cur)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise VerifiedReadError(f"not a regular file: {os.path.basename(path)}")
    if st.st_nlink > 1:
        # r37: a hard link can alias an inode outside the project (or a secret) under an innocent
        # in-root name; realpath/O_NOFOLLOW cannot see that, so multi-link files are refused.
        os.close(fd)
        raise VerifiedReadError(f"hard-linked file refused (st_nlink={st.st_nlink}): {os.path.basename(path)}")
    return fd, (st.st_dev, st.st_ino)


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        b = os.read(fd, 1 << 20)
        if not b:
            return b"".join(chunks)
        chunks.append(b)


def identity(path: str, root: str) -> Identity:
    fd, ino = open_verified(path, root)
    try:
        data = _read_all(fd)
    finally:
        os.close(fd)
    return (ino[0], ino[1], hashlib.sha256(data).hexdigest())


def _root_for(path: str) -> str:
    return READ_ROOT.get() or os.path.dirname(os.path.abspath(path))


def read_text(path: str, *, errors: str = "strict") -> str:
    """Read through a verified handle; secret-named files need a matching approved identity."""
    path = os.path.abspath(path)
    fd, ino = open_verified(path, _root_for(path))
    try:
        data = _read_all(fd)
    finally:
        os.close(fd)
    if is_sensitive_path(path):
        grant = APPROVED_TARGET.get()
        if grant is None or grant[0] != path or grant[1][:2] != ino:
            raise SecretReadRefused(
                f"secret-named file requires a per-file approval bound to this exact file: {os.path.basename(path)}"
            )
        if grant[1][2] != hashlib.sha256(data).hexdigest():
            raise SecretReadRefused(
                f"secret file content changed after approval; re-approval required: {os.path.basename(path)}"
            )
    return data.decode("utf-8", errors=errors)


def read_text_under(path: str, root: str, *, errors: str = "strict") -> str:
    """Verified read with an explicit root (for non-registry callers such as FileSummarizer)."""
    token = READ_ROOT.set(root)
    try:
        return read_text(path, errors=errors)
    finally:
        READ_ROOT.reset(token)
