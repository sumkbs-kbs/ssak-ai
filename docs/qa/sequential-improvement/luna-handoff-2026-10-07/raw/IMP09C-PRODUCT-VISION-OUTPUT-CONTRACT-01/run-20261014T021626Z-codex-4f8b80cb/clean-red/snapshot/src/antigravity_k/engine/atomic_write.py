"""원자적 텍스트 저장의 **단일 계약** (NX-08-F01, NX-10 리팩터).

`vault.write_text_atomically` 를 이 leaf 모듈로 옮겼다. 이유는 구조다 —
`vault_privacy`(마스킹)가 같은 원자성 계약을 쓰는데, 그 함수가 `vault` 안에 있으면
`vault → vault_privacy`(마스킹 적용) 와 `vault_privacy → vault`(저장) 가 서로를
가리켜 **순환 임포트**가 된다. 이 모듈은 vault 를 임포트하지 않으므로 두 모듈이
모두 이 모듈만 향한다.

계약 순서(CR-02 세션 저장과 동일):

    1. 같은 디렉터리에 고유 임시 파일 생성(권한은 이전 파일 것을 보존)
    2. write → flush → fsync (여기서 죽어도 원본은 그대로다)
    3. ``os.replace`` 로 원자적 교체 (같은 파일시스템이므로 rename 이다)
    4. 디렉터리 fsync (미지원 파일시스템은 조용히 통과)

실패는 :class:`~antigravity_k.engine.vault_git.VaultCommitError` 로 올라간다 —
호출자들이 이미 이 예외로 실패를 구분하므로 저장 실패 타입은 하나로 유지한다.
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
import time
from contextlib import suppress
from pathlib import Path

from antigravity_k.engine.vault_git import VaultCommitError

logger = logging.getLogger(__name__)

# NX-08-F01: 원자적 저장의 실패 주입 지점 (테스트가 monkeypatch 하는 이름).
_TEMP_SUFFIX = ".tmp"
_ORPHAN_TEMP_MIN_AGE_S = 60.0


def _fsync_fd(fd: int) -> None:
    """파일/디렉터리 fsync (실패 주입 지점)."""
    os.fsync(fd)


def _replace_file(source: Path, destination: Path) -> None:
    """원자적 교체 (실패 주입 지점)."""
    os.replace(source, destination)


def _fsync_directory(path: Path) -> None:
    """디렉터리 엔트리 내구성 확보. 미지원 플랫폼/파일시스템에서는 조용히 통과한다."""
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        dir_fd = os.open(str(path), flags)
    except OSError:
        return
    try:
        _fsync_fd(dir_fd)
    except OSError:
        # rename 은 이미 끝났다(내용은 저장됨). 디렉터리 fsync 미지원은 내구성 대상이 아니다.
        logger.debug("Directory fsync unavailable for %s", path)
    finally:
        os.close(dir_fd)


def _orphan_temps(path: Path) -> list[Path]:
    """죽은 프로세스가 남긴 같은 대상의 임시 파일(생성 후 60초 이상 경과한 것만)."""
    prefix = f".{path.name}."
    orphans: list[Path] = []
    now = time.time()
    for candidate in path.parent.glob(f"{prefix}*{_TEMP_SUFFIX}"):
        pid_text = candidate.name[len(prefix) :].split(".", 1)[0]
        if not pid_text.isdigit():
            continue
        try:
            age = now - candidate.stat().st_mtime
        except OSError:
            continue
        if age < _ORPHAN_TEMP_MIN_AGE_S:
            continue
        try:
            os.kill(int(pid_text), 0)
        except ProcessLookupError:
            orphans.append(candidate)
        except (PermissionError, OSError):
            # 살아 있는지 확신할 수 없다 — 지우지 않는다.
            continue
    return orphans


def _cleanup_failed_write(tmp: Path, fd: int | None) -> None:
    """replace 이전에 실패한 저장의 잔여물만 치운다(원본 파일은 건드리지 않는다)."""
    if fd is not None:
        with suppress(OSError):
            os.close(fd)
    with suppress(OSError):
        tmp.unlink()


def write_text_atomically(path: Path, text: str) -> None:
    """NX-08-F01: 텍스트를 **자르고 쓰지 않고** 원자적으로 저장한다.

    replace 이전에 실패하면 원본 bytes 가 그대로 남고 임시 파일만 정리된다. 교체 이후
    디렉터리 fsync 가 실패해도 내용은 이미 저장됐으므로 되돌리지 않는다(로그만 남긴다).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    for orphan in _orphan_temps(path):
        with suppress(OSError):
            orphan.unlink()

    try:
        previous_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        previous_mode = None

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}{_TEMP_SUFFIX}")
    fd: int | None = None
    try:
        # O_CREAT|O_EXCL 로 열어 임시 파일 이름 충돌을 거부하고, 권한은 umask 기본값을 따른다.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        if previous_mode is not None:
            os.fchmod(fd, previous_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None  # fdopen 이 소유권을 가져갔다
            _ = handle.write(text)
            handle.flush()
            _fsync_fd(handle.fileno())
        _replace_file(tmp, path)
    except OSError as exc:
        _cleanup_failed_write(tmp, fd)
        raise VaultCommitError(f"Vault bytes could not be persisted: {path}") from exc
    except BaseException:
        _cleanup_failed_write(tmp, fd)
        raise
    _fsync_directory(path.parent)


__all__ = ["write_text_atomically"]
