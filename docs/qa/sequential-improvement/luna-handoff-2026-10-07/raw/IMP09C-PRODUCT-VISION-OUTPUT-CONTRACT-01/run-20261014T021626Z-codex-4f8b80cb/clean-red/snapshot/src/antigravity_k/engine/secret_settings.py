"""CR-05 — 서버 비밀 설정(API 키) allowlist·검증·원자적 저장 유틸.

설정 API가 비밀값을 다루는 규칙을 한 곳에 모은다.

- **allowlist**: `.env`에 쓸 수 있는 키를 고정한다. 임의의 `*_API_KEY` 키를
  만들거나, 다른 비밀 변수를 설정 화면으로 덮어쓰지 못하게 한다.
- **검증**: 키·값에 개행/제어문자를 허용하지 않는다. 개행이 들어가면
  `KEY=value\nOTHER=1` 형태로 `.env`에 임의 변수를 주입할 수 있다.
- **원자적 저장**: 같은 디렉터리 tempfile(0600) → flush/fsync → `os.replace` →
  디렉터리 fsync. 실패해도 기존 `.env` 내용이 잘리지 않는다.
- **상태 조회**: 응답에는 키 원문/부분값 대신 `configured` 여부만 싣는다.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

#: 설정 화면에서 다룰 수 있는 비밀 키(정확한 이름만 허용 — 와일드카드는 없다).
#:
#: `AGK_SEARCH_ENGINE_TOKEN` 은 원격 검색 백엔드의 bearer 다(task 10 의 `tools/search_auth.py`).
#: provider 키와 성질이 같다: 값이 결과·로그·화면 어디에도 남지 않아야 하고, 존재 여부만 상태로
#: 노출한다 → secret 목록에 넣는 것이 곧 "입력은 password, 응답은 불리언" 규칙을 적용한다는 뜻이다.
SECRET_ENV_KEYS: Final[tuple[str, ...]] = (
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "ZAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AGK_SEARCH_ENGINE_TOKEN",
)

#: 비밀이 아닌 설정 키.
#:
#: `search.ssak.*` (task 13) 는 설정 화면이 켜고/끄고/경로를 지정하는 **결정**이다 — 비밀이 아니다.
#: 이 키들은 환경변수 > yaml 우선순위를 이미 갖고 있어(`AGK_SEARCH_SSAK_*`), 화면이 `.env`에 쓰면
#: 다음 로드부터 곧바로 반영된다. 경로는 비밀값이 아니라 사용자가 스스로 입력해 스스로 보는 값이다.
PLAIN_ENV_KEYS: Final[tuple[str, ...]] = (
    "AGK_DAILY_BUDGET_USD",
    "AGK_HOURLY_ACTION_LIMIT",
    "AGK_SEARCH_SSAK_ENABLED",
    "AGK_SEARCH_SSAK_MODE",
    "AGK_SEARCH_SSAK_FALLBACK",
    "AGK_SEARCH_SSAK_ARTIFACT_PATH",
)

ALLOWED_ENV_KEYS: Final[tuple[str, ...]] = SECRET_ENV_KEYS + PLAIN_ENV_KEYS

#: 응답에서 지우는 config.yaml 경로(비밀이 들어갈 수 있는 곳).
SCRUBBED_CONFIG_PATHS: Final[tuple[tuple[str, ...], ...]] = (
    ("api_keys",),
    ("security", "access_pin"),
)

_ENV_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_DOTENV_ASSIGN_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_MAX_VALUE_LENGTH: Final[int] = 4096


class EnvSettingError(ValueError):
    """허용되지 않는 키/값(호출자가 400으로 변환한다)."""


def is_secret_env_key(key: str) -> bool:
    """provider 비밀 키인가(정확한 allowlist 이름만)."""
    return key in SECRET_ENV_KEYS


def validate_env_assignment(key: str, value: str) -> tuple[str, str]:
    """`.env`에 쓸 키·값을 검증하고 정규화된 쌍을 반환한다.

    Raises:
        EnvSettingError: allowlist 밖 키, 형식 위반, 제어문자/과길이 값.
    """
    if not _ENV_KEY_RE.match(key):
        raise EnvSettingError(f"invalid env key: {key!r}")
    if key not in ALLOWED_ENV_KEYS:
        raise EnvSettingError(f"env key is not allowed: {key!r}")
    if len(value) > _MAX_VALUE_LENGTH:
        raise EnvSettingError(f"env value too long for {key!r}")
    if any(ch in value for ch in ("\n", "\r", "\0")):
        raise EnvSettingError(f"env value contains control characters: {key!r}")
    return key, value.strip().strip('"').strip("'")


def validate_env_key(key: str) -> str:
    """삭제 대상 키 검증."""
    if not _ENV_KEY_RE.match(key) or key not in ALLOWED_ENV_KEYS:
        raise EnvSettingError(f"env key is not allowed: {key!r}")
    return key


def read_env_file_value(env_path: str | os.PathLike[str], key: str) -> str:
    """`.env` 파일에서 키 값을 읽는다(없으면 빈 문자열)."""
    try:
        for line in read_env_lines(env_path):
            match = _DOTENV_ASSIGN_RE.match(line)
            if match is None or match.group(1) != key:
                continue
            _, _, value = line.partition("=")
            return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def configured_secret_status(
    read: Callable[[str], str | None] | None = None,
    env_path: str | os.PathLike[str] | None = None,
) -> dict[str, bool]:
    """provider별 '설정됨' 여부만 반환한다(원문·부분값 없음).

    실행 중 프로세스 환경변수 **또는** 지속 저장된 ``.env`` 중 하나라도 값을
    가지면 설정됨이다. `.env`만 확인하면 설정 화면이 방금 저장한 키를 '미설정'으로
    되돌려 보여주고(설정 API의 쓰기 결과와 불일치), 프로세스 env만 확인하면
    저장 직후 상태가 바뀌지 않는다.
    """
    lookup: Callable[[str], str | None] = read or os.environ.get
    status: dict[str, bool] = {}
    for key in SECRET_ENV_KEYS:
        raw = lookup(key)
        configured = bool(raw and raw.strip())
        if not configured and env_path is not None:
            configured = bool(read_env_file_value(env_path, key))
        status[key] = configured
    return status


def scrub_config_secrets(payload: Mapping[str, object]) -> dict[str, object]:
    """설정 응답에서 비밀 경로를 제거한 얕은 복사본을 만든다.

    ``api_keys``는 통째로 지우고(provider 상태는 별도 필드로만 노출),
    ``security.access_pin`` 같은 중첩 비밀은 키만 제거한다.
    """
    scrubbed: dict[str, object] = dict(payload)
    for path in SCRUBBED_CONFIG_PATHS:
        if len(path) == 1:
            scrubbed.pop(path[0], None)
            continue
        parent = scrubbed.get(path[0])
        if isinstance(parent, Mapping):
            nested = dict(parent)
            nested.pop(path[1], None)
            scrubbed[path[0]] = nested
    return scrubbed


def _line_key(line: str) -> str | None:
    match = _DOTENV_ASSIGN_RE.match(line)
    return match.group(1) if match else None


def render_env_file(
    existing_lines: Sequence[str],
    updates: Mapping[str, str],
    deletions: Iterable[str],
) -> list[str]:
    """기존 라인 순서/주석을 보존하며 업데이트·삭제를 적용한 라인을 만든다."""
    removed = set(deletions)
    lines: list[str] = []
    seen: set[str] = set()
    for raw in existing_lines:
        key = _line_key(raw)
        if key is not None and key in removed:
            continue
        if key is not None and key in updates:
            lines.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
        lines.append(raw)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    return lines


def resolve_env_file_path(default_root: str | os.PathLike[str]) -> Path:
    """설정을 쓸 `.env` 경로 — `config._load_dotenv_once`와 같은 규칙.

    ``AGK_ENV_FILE``이 있으면 그 파일을 쓴다(테스트·격리 배포에서 실제 사용자
    `.env`를 건드리지 않기 위한 공식 경로이기도 하다).
    """
    override = os.environ.get("AGK_ENV_FILE")
    return Path(override) if override else Path(default_root) / ".env"


def write_env_file_atomic(env_path: str | os.PathLike[str], lines: Sequence[str]) -> None:
    """`.env`를 원자적으로 교체하고 소유자 전용 권한(0600)을 적용한다."""
    path = Path(env_path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines) + "\n"
    fd, temp_path = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(directory))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            _ = handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_path)
        raise
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    with contextlib.suppress(OSError):
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def read_env_lines(env_path: str | os.PathLike[str]) -> list[str]:
    """기존 `.env` 라인(개행 제외). 없으면 빈 목록."""
    path = Path(env_path)
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


def apply_env_settings(
    env_path: str | os.PathLike[str],
    *,
    updates: Mapping[str, str],
    deletions: Iterable[str] = (),
) -> tuple[int, int]:
    """검증된 업데이트/삭제를 `.env`에 적용하고 (갱신 수, 삭제 수)를 반환한다.

    빈 값은 '전송하지 않음'으로 간주해 아무것도 하지 않는다(기존 키 유지).
    """
    validated: dict[str, str] = {}
    for key, value in updates.items():
        if not value:
            continue
        validated_key, validated_value = validate_env_assignment(key, value)
        validated[validated_key] = validated_value
    delete_keys = sorted({validate_env_key(key) for key in deletions})

    existing_lines = read_env_lines(env_path)
    present = {key for key in (_line_key(line) for line in existing_lines) if key}
    effective_deletions = [key for key in delete_keys if key in present]
    if not validated and not effective_deletions:
        return 0, 0

    rendered = render_env_file(existing_lines, validated, delete_keys)
    write_env_file_atomic(env_path, rendered)
    return len(validated), len(effective_deletions)


__all__ = [
    "ALLOWED_ENV_KEYS",
    "PLAIN_ENV_KEYS",
    "SECRET_ENV_KEYS",
    "EnvSettingError",
    "apply_env_settings",
    "configured_secret_status",
    "is_secret_env_key",
    "read_env_file_value",
    "read_env_lines",
    "render_env_file",
    "resolve_env_file_path",
    "scrub_config_secrets",
    "validate_env_assignment",
    "validate_env_key",
    "write_env_file_atomic",
]
