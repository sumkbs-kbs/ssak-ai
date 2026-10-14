"""NX-05 — PIN hash + auth epoch 을 하나의 원자적 문서로 저장한다.

계약 (docs/18_RELIABILITY_AND_CONNECTOME_DEVELOPMENT_PLAN.md NX-05):

* PIN hash 와 **auth epoch**(세션 세대)은 **같은 파일에 함께**, 원자 교체로만 바뀐다.
  두 파일로 나누면 hash 만 바뀌고 epoch 이 남는 중간 상태가 노출된다.
* epoch 은 PIN 변경마다 증가한다. 토큰/티켓은 발급 시점 epoch 을 claim 으로 갖고,
  검증은 매번 **현재 epoch 과 비교**한다(프로세스별 캐시 금지 — 다른 프로세스가
  PIN 을 바꾼 뒤에도 이 프로세스가 이전 토큰을 계속 받으면 결함이 남는다).
* 구버전 파일(PIN hash 한 줄)은 계속 읽는다 — epoch 은 :data:`LEGACY_EPOCH`(0)로
  간주한다. 구버전 토큰에는 epoch claim 이 없으므로 제품 경로에서 거부되고,
  사용자는 재로그인하게 된다(카드 요구: migration 뒤 재로그인).
* 저장 형식 ``agk.auth.v1``::

      {"schema": "agk.auth.v1", "pin_hash": "pbkdf2_sha256$...", "epoch": 2,
       "updated_at": 1789515305.73}

FastAPI/Starlette 에 의존하지 않는다 — startup 검사, 정책, 인증 라우트가 모두 쓴다.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger("antigravity_k.security.auth_state")

AUTH_STATE_SCHEMA: Final[str] = "agk.auth.v1"
HASH_MARKER: Final[str] = "pbkdf2_sha256$"

# 구버전(한 줄 hash) 파일에서 읽은 상태의 epoch. 실사용 토큰은 epoch claim 을
# 갖지 않으므로 제품 검증 경로에서 거부된다(요구: migration 후 재로그인).
LEGACY_EPOCH: Final[int] = 0

_FILE_MODE: Final[int] = 0o600


@dataclass(frozen=True)
class AuthState:
    """저장된 인증 상태 — PIN hash 와 세대(epoch)."""

    pin_hash: str | None
    epoch: int
    schema: str = AUTH_STATE_SCHEMA
    updated_at: float = 0.0
    legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pin_hash": self.pin_hash,
            "epoch": int(self.epoch),
            "updated_at": float(self.updated_at),
        }


def _parse_hash_line(text: str) -> str | None:
    """한 줄 hash 텍스트에서 hash 만 추출한다(형식이 아니면 None)."""
    stored = text.strip()
    if not stored or not stored.startswith(HASH_MARKER):
        return None
    return stored


def read_auth_state(path: str | Path) -> AuthState | None:
    """저장된 인증 상태를 읽는다 (JSON 우선, 구버전 한 줄 hash 폴백).

    파일이 없거나 읽을 수 없으면 ``None`` (fail-closed: 호출자는 credential 부재로
    취급한다). JSON 이지만 구조가 깨진 경우도 ``None`` — 손상된 내용을 유효한
    credential 로 승격하지 않는다.
    """
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    text = raw.strip()
    if not text:
        return None

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Auth state file is not valid JSON: %s", file_path)
            return None
        if not isinstance(data, dict) or data.get("schema") != AUTH_STATE_SCHEMA:
            logger.warning("Auth state file has an unknown schema: %s", file_path)
            return None
        pin_hash = data.get("pin_hash")
        epoch_raw = data.get("epoch")
        if pin_hash is not None and not isinstance(pin_hash, str):
            return None
        if isinstance(epoch_raw, bool) or not isinstance(epoch_raw, (int, str)):
            return None
        try:
            epoch = int(epoch_raw)
        except ValueError:
            return None
        if epoch < LEGACY_EPOCH:
            return None
        return AuthState(
            pin_hash=(pin_hash or None),
            epoch=epoch,
            updated_at=float(data.get("updated_at") or 0.0),
        )

    # 구버전: PIN hash 한 줄.
    pin_hash = _parse_hash_line(text)
    if pin_hash is None:
        return None
    return AuthState(pin_hash=pin_hash, epoch=LEGACY_EPOCH, legacy=True)


def read_pin_hash(path: str | Path) -> str | None:
    """현재 PIN hash (구버전/신버전 공통)."""
    state = read_auth_state(path)
    return None if state is None else state.pin_hash


def current_epoch(path: str | Path) -> int:
    """현재 epoch — 매 호출 파일에서 다시 읽는다(캐시 금지).

    상태 파일이 없거나 읽을 수 없으면 :data:`LEGACY_EPOCH` 를 돌려준다. 이 값은
    "credential 없음" 상태이며, 그때 발급된 epoch 0 토큰은 PIN 이 구성되는 순간
    (epoch ≥ 1) 자동으로 무효가 된다.
    """
    state = read_auth_state(path)
    return LEGACY_EPOCH if state is None else state.epoch


def write_auth_state_atomic(
    path: str | Path,
    *,
    pin_hash: str | None,
    epoch: int,
    updated_at: float | None = None,
    fsync: bool = True,
) -> AuthState:
    """PIN hash + epoch 을 하나의 문서로 원자 교체 저장한다.

    ``os.replace`` 이전까지는 기존 파일이 그대로 남으므로, 읽는 쪽은 항상
    (이전 hash, 이전 epoch) 또는 (새 hash, 새 epoch) 중 하나만 본다.
    """
    if int(epoch) < LEGACY_EPOCH:
        raise ValueError("auth epoch must be >= 0")
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    state = AuthState(
        pin_hash=pin_hash,
        epoch=int(epoch),
        updated_at=float(updated_at if updated_at is not None else time.time()),
    )
    payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{file_path.name}.",
        suffix=".tmp",
        dir=str(file_path.parent),
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        os.fchmod(handle.fileno(), _FILE_MODE)
        with handle:
            _ = handle.write(payload)
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())
        os.replace(temp_path, file_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    try:
        os.chmod(file_path, _FILE_MODE)
    except OSError:  # pragma: no cover - 일부 파일시스템/플랫폼 제약
        logger.warning("Could not restrict auth state permissions on %s", file_path)
    return state


def next_epoch(state: AuthState | None) -> int:
    """다음 세대 값 — 상태가 없으면 1 (첫 구성)."""
    return (state.epoch if state is not None else LEGACY_EPOCH) + 1


@contextmanager
def _state_process_lock(path: Path) -> Iterator[None]:
    """auth 상태 파일의 프로세스 간 배타 잠금 (macOS/Linux).

    잠금 파일은 원본과 다른 이름(``.<name>.lock``)을 쓴다 — 잠금 파일 자체가
    credential 로 오인되지 않게 한다. ``fcntl`` 이 없는 플랫폼은 잠금 없이
    진행한다(지원 OS는 macOS/Linux이며, 그 경우에도 세대는 단조 증가한다).
    """
    try:
        import fcntl
    except ImportError:  # pragma: no cover - 지원 범위 밖(Windows)
        yield
        return
    lock_path = path.parent / f".{path.name}.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, _FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def bump_epoch_atomic(path: str | Path, *, pin_hash: str | None) -> AuthState:
    """현재 세대를 읽고 **+1** 해서 (hash, epoch) 을 원자 교체한다.

    NX-05: 읽기-수정-쓰기를 파일 잠금으로 직렬화한다. 잠금이 없으면 동시에 들어온
    두 번의 PIN 변경이 같은 다음 세대를 계산해 **성공 2건이 세대 1증가**로 보고될
    수 있다(폐기 자체는 유지되지만 "성공 1건 = 새 세대 1개" 가 깨진다).
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with _state_process_lock(file_path):
        return write_auth_state_atomic(
            file_path,
            pin_hash=pin_hash,
            epoch=next_epoch(read_auth_state(file_path)),
        )


__all__ = [
    "AUTH_STATE_SCHEMA",
    "HASH_MARKER",
    "LEGACY_EPOCH",
    "AuthState",
    "bump_epoch_atomic",
    "current_epoch",
    "next_epoch",
    "read_auth_state",
    "read_pin_hash",
    "write_auth_state_atomic",
]
