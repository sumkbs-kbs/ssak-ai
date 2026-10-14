"""Ssak-Ai: Secure Key Provider.

====================================

API 키를 안전하게 관리합니다.

적용 우선순위 (4단계):
  1. 환경변수 (AGK_ANTHROPIC_KEY, AGK_OPENAI_KEY, AGK_OPENROUTER_KEY)
  2. .env 파일 (프로젝트 루트)
  3. config.yaml api_keys 섹션 (fallback, placeholders)
  4. Vault 암호화 저장소 (런타임 저장 키)

사용법:
    from antigravity_k.engine.secure_key import get_api_key, store_api_key

    # 키 조회 (env → .env → config → vault 순서)
    key = get_api_key("anthropic")

    # 키 저장 (vault 암호화)
    store_api_key("anthropic", "sk-ant-xxxx")
"""

from __future__ import annotations

import base64
import json
import logging
import os
import stat
from pathlib import Path
from typing import TypedDict, cast

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("antigravity_k.secure_key")

# ─── 상수 ──────────────────────────────────────────────────────────

_ENV_VAR_MAP = {
    "anthropic": "AGK_ANTHROPIC_KEY",
    "openai": "AGK_OPENAI_KEY",
    "openrouter": "AGK_OPENROUTER_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "zai": "ZAI_API_KEY",
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DOTENV_PATH = _PROJECT_ROOT / ".env"

# AGK_VAULT_DIR 환경변수로 vault 디렉토리를 오버라이드할 수 있습니다.
# (CI, 테스트, 다중 인스턴스에서 사용)
_VAULT_KEY_DIR = Path(
    os.environ.get("AGK_VAULT_DIR") or str(_PROJECT_ROOT / ".agk_vault"),
)
_MASTER_KEY_FILE = _VAULT_KEY_DIR / "master.key"
_VAULT_DB = _VAULT_KEY_DIR / "keys.enc"

_PLACEHOLDER_KEYWORDS = {
    "your-key-here",
    "your-openrouter-api-key",
    "sk-ant-your-key-here",
    "sk-proj-your-key-here",
}


# ─── 마스터 키 관리 ────────────────────────────────────────────────

_KEYCHAIN_SERVICE = "antigravity-k"
_KEYCHAIN_ACCOUNT = "machine-seed"

# Fernet 키 = base64 44자
_FERNET_KEY_LEN = 44

# ─── KDF 파라미터 버전 관리 ──────────────────────────────────────
# 새 버전을 추가할 때마다 _CURRENT_KDF_VERSION만 증가시키고
# _KDF_VERSIONS에 새 항목을 추가합니다.
# 기존 vault 데이터는 rotate_master_key(force=True)로 마이그레이션합니다.

_CURRENT_KDF_VERSION = 3


class _KdfParams(TypedDict):
    salt: bytes
    iterations: int
    label: str


class _RotationResult(TypedDict):
    success: bool
    rotated: bool
    services_count: int
    error: str | None


_KDF_VERSIONS: dict[int, _KdfParams] = {
    1: {
        "salt": b"antigravity-k-v1-salt",
        "iterations": 600_000,
        "label": "v1 (SHA256, 600K PBKDF2 rounds)",
    },
    2: {
        "salt": b"antigravity-k-v2-salt",
        "iterations": 1_000_000,
        "label": "v2 (SHA256, 1M PBKDF2 rounds)",
    },
    3: {
        "salt": b"antigravity-k-v3-salt",
        "iterations": 2_000_000,
        "label": "v3 (AES-256-GCM ready, 2M PBKDF2 rounds)",
    },
}


def _get_keychain_seed() -> str | None:
    """MacOS 키체인에서 머신 시드를 조회합니다.

    macOS에서만 동작하며, 키체인 접근 권한이 없으면

    조용히 None을 반환합니다.
    """
    import platform

    if platform.system() != "Darwin":
        return None
    try:
        import subprocess

        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            seed = result.stdout.strip()
            if seed and len(seed) >= 8:
                logger.debug("Machine seed: Keychain")
                return seed
    except Exception:
        logger.exception("Unhandled exception")
    return None


def _set_keychain_seed(seed: str) -> bool:
    """머신 시드를 macOS 키체인에 저장합니다.

    이미 존재하면 업데이트합니다(-U 플래그).
    """
    import platform

    if platform.system() != "Darwin":
        return False
    try:
        import subprocess

        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-w",
                seed,
                "-U",
            ],  # -U: 항목이 이미 있으면 업데이트
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            logger.info("Machine seed stored in macOS Keychain")
            return True
        logger.warning("Failed to store machine seed in Keychain: %s", result.stderr.strip())
    except Exception as e:
        logger.exception("Unhandled exception")
        logger.debug("Could not store seed in Keychain: %s", e)
    return False


def _get_machine_seed() -> str:
    """시스템 고유 식별자를 안정적인 우선순위로 조회합니다.

    우선순위:

      0. macOS 키체인 — 가장 안전하고 OS에 귀속됨 (로그인 키체인)
      1. IOPlatformUUID (macOS ioreg) — 하드웨어 UUID, OS 재설치 후에도 유지
      2. /etc/machine-id (Linux systemd) — Linux 표준 머신 ID
      3. uuid.getnode() (MAC 주소) — 기존 호환성 유지
      4. 하드코딩 기본값 (절대 폴백)
    """
    # 0단계: macOS 키체인 (최우선, 사용자가 직접 관리)
    keychain_seed = _get_keychain_seed()
    if keychain_seed:
        return keychain_seed

    # 1단계: IOPlatformUUID (macOS 하드웨어 UUID)
    try:
        import subprocess

        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if '"IOPlatformUUID"' in line:
                # "IOPlatformUUID" = "XXXX-XXXX"
                uuid_val = line.split("=", 1)[-1].strip().strip('"')
                if uuid_val and len(uuid_val) >= 10:
                    logger.debug("Machine seed: IOPlatformUUID")
                    return uuid_val
    except Exception:
        logger.exception("Unhandled exception")

    # 2단계: /etc/machine-id (Linux systemd)
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            val = Path(path).read_text(encoding="utf-8").strip()
            if val and len(val) >= 8:
                logger.debug("Machine seed: %s", path)
                return val
        except Exception:
            logger.exception("Unhandled exception")
            continue

    # 3단계: MAC 주소 (기존 호환성)
    try:
        import uuid

        mac = uuid.getnode()
        # 유효한 MAC은 48비트 양의 정수; 0xFF...는 유효하지 않음
        if mac > 0 and mac < (1 << 48):
            logger.debug("Machine seed: MAC address")
            return mac.__str__()
    except Exception:
        logger.exception("Unhandled exception")

    # 4단계: 절대 폴백
    logger.warning("No stable machine identifier found; using fallback seed")
    return "antigravity-k-default-salt"


def _derive_key_from_seed(seed: str, version: int | None = None) -> bytes:
    """머신 시드로부터 PBKDF2 + Fernet 키를 파생합니다.

    Args:
        seed: 머신 시드 문자열
        version: KDF 파라미터 버전 (None=최신 버전)

    """
    if version is None:
        version = _CURRENT_KDF_VERSION
    params = _KDF_VERSIONS.get(version)
    if params is None:
        raise ValueError(f"Unknown KDF version: {version}. Available: {list(_KDF_VERSIONS)}")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=params["salt"],
        iterations=params["iterations"],
    )
    return base64.urlsafe_b64encode(kdf.derive(seed.encode("utf-8")))


# ─── Master Key 파일 I/O (version-aware) ──────────────────────────
# 파일 형식:
#   - 구형 (v1 호환): 44바이트 raw Fernet 키
#   - 신형 (v2+):     b"V{version}:{44바이트 키}"
#
# 예: b"V1:abc123...44bytes...xyz"

_MASTER_KEY_PREFIX = b"V"


def _read_master_key() -> tuple[int, bytes] | None:
    """master.key 파일을 읽고 (version, key_bytes)를 반환합니다.

    Returns:
        (version, key_bytes) 또는 None (파일 없음/손상)

    """
    if not _MASTER_KEY_FILE.exists():
        return None
    try:
        raw = _MASTER_KEY_FILE.read_bytes()

        # 신형 포맷: V{version}:{44바이트 키}
        if raw.startswith(_MASTER_KEY_PREFIX) and b":" in raw[:8]:
            # b"V1:...", b"V2:..."
            sep_idx = raw.index(b":")
            version_str = raw[1:sep_idx].decode("utf-8")
            if version_str.isdigit():
                version = int(version_str)
                key = raw[sep_idx + 1 :]
                if len(key) == _FERNET_KEY_LEN and version in _KDF_VERSIONS:
                    return (version, key)

        # 구형 포맷: raw 44바이트 (v1 호환)
        if len(raw) == _FERNET_KEY_LEN:
            return (1, raw)  # 1 = v1 (기본)

    except Exception:
        logger.exception("Unhandled exception")
    return None


def _save_master_key_file(key: bytes, version: int = _CURRENT_KDF_VERSION) -> None:
    """마스터 키를 파일에 저장합니다 (소유자만 읽기 가능, version 정보 포함).

    Args:
        key: Fernet 키 (44바이트)
        version: KDF 버전 번호

    """
    _VAULT_KEY_DIR.mkdir(parents=True, exist_ok=True)
    # 형식: V{version}:{44바이트 키}
    data = f"V{version}:".encode() + key
    _ = _MASTER_KEY_FILE.write_bytes(data)
    try:
        os.chmod(_MASTER_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        logger.exception("Unhandled exception")


def _get_or_create_master_key() -> bytes:
    """시스템별 마스터 키를 조회하거나 생성합니다.

    master.key 파일을 version-aware 방식으로 읽고,

    없으면 최신 KDF 버전으로 새로 생성합니다.

    Returns:
        Fernet 키 (44바이트 bytes)

    """
    # version-aware 읽기
    result = _read_master_key()
    if result is not None:
        version, key = result
        # 현재 버전보다 낮으면 업그레이드 로그 (조용히 기록)
        if version < _CURRENT_KDF_VERSION:
            logger.info(
                "Master key is KDF v%d (current: v%d); run 'agk key rotate' to upgrade KDF parameters.",
                version,
                _CURRENT_KDF_VERSION,
            )
        return key

    # 새 마스터 키 생성 (최신 KDF 버전)
    machine_seed = _get_machine_seed()
    _ = _set_keychain_seed(machine_seed)

    key = _derive_key_from_seed(machine_seed, version=_CURRENT_KDF_VERSION)
    _save_master_key_file(key, version=_CURRENT_KDF_VERSION)
    logger.info(
        "New master key created at %s (KDF v%d)",
        _MASTER_KEY_FILE,
        _CURRENT_KDF_VERSION,
    )
    return key


def _get_cipher() -> Fernet:
    """암호화/복호화에 사용할 Fernet 암호를 반환합니다."""
    return Fernet(_get_or_create_master_key())


# ─── .env 파일 로드 ────────────────────────────────────────────────


def _load_dotenv() -> dict[str, str]:
    """간단한 .env 파서 (python-dotenv 의존성 없이)."""
    env_vars: dict[str, str] = {}
    if not _DOTENV_PATH.exists():
        return env_vars

    try:
        for line in _DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value:
                env_vars[key] = value
    except Exception:
        logger.exception("Failed to load .env file")
    return env_vars


# ─── config.yaml에서 키 로드 ────────────────────────────────────────


def _load_config_keys() -> dict[str, str]:
    """config.yaml의 api_keys 섹션을 로드합니다."""
    config_path = _PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml

        raw: object = cast(object, yaml.safe_load(config_path.read_text(encoding="utf-8")))
        if not raw:
            raw = {}
        if not isinstance(raw, dict):
            return {}
        raw_mapping = cast(dict[object, object], raw)
        keys = raw_mapping.get("api_keys", {})
        if isinstance(keys, dict):
            # 자리표시자 키는 무시
            mapping = cast(dict[object, object], keys)
            return {
                k: v for k, v in mapping.items() if isinstance(k, str) and isinstance(v, str) and not _is_placeholder(v)
            }
    except Exception:
        logger.exception("Failed to load config keys")
    return {}


def _is_placeholder(value: str) -> bool:
    """값이 자리표시자인지 확인합니다."""
    return any(kw in value.lower() for kw in _PLACEHOLDER_KEYWORDS)


# ─── Vault 암호화 저장소 ──────────────────────────────────────────


def _load_vault_keys() -> dict[str, str]:
    """암호화된 vault 저장소에서 키를 로드합니다."""
    if not _VAULT_DB.exists():
        return {}
    try:
        cipher = _get_cipher()
        encrypted = _VAULT_DB.read_bytes()
        decrypted = cipher.decrypt(encrypted)
        value: object = cast(object, json.loads(decrypted.decode("utf-8")))
        if not isinstance(value, dict):
            return {}
        mapping = cast(dict[object, object], value)
        return {key: item for key, item in mapping.items() if isinstance(key, str) and isinstance(item, str)}
    except Exception:
        logger.exception("Failed to load vault keys (may need re-init)")
        return {}


def _save_vault_keys(keys: dict[str, str]) -> None:
    """키를 암호화하여 vault 저장소에 저장합니다."""
    _VAULT_KEY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        cipher = _get_cipher()
        data = json.dumps(keys, ensure_ascii=False).encode("utf-8")
        encrypted = cipher.encrypt(data)
        _ = _VAULT_DB.write_bytes(encrypted)
        try:
            os.chmod(_VAULT_DB, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            logger.exception("Unhandled exception")
        logger.info("Vault keys saved (%d entries)", len(keys))
    except Exception:
        logger.exception("Failed to save vault keys")


# ─── 공개 API ──────────────────────────────────────────────────────


def get_api_key(service: str) -> str | None:
    """Retrieve an API key.

    Priority: env vars > .env > config.yaml > vault encrypted storage

    Args:
        service: Service name ("anthropic", "openai", "openrouter")

    Returns:
        API key string, or None (not found in any source)

    """
    service = service.lower().strip()

    # 1단계: 환경변수
    env_var = _ENV_VAR_MAP.get(service)
    if env_var:
        value = os.environ.get(env_var)
        if value and not _is_placeholder(value):
            logger.debug("Loaded %s from env var %s", service, env_var)
            return value

    # 2단계: .env 파일
    dotenv: dict[str, str] = _load_dotenv()
    if env_var and env_var in dotenv:
        value = dotenv[env_var]
        if value and not _is_placeholder(value):
            logger.debug("Loaded %s from .env file", service)
            return value

    # 3단계: config.yaml
    config_keys = _load_config_keys()
    if service in config_keys:
        value = config_keys[service]
        if value and not _is_placeholder(value):
            logger.debug("Loaded %s from config.yaml", service)
            return value

    # 4단계: Vault 암호화 저장소
    vault_keys = _load_vault_keys()
    if service in vault_keys:
        value = vault_keys[service]
        if value and not _is_placeholder(value):
            logger.debug("Loaded %s from vault storage", service)
            return value

    return None


def store_api_key(service: str, key: str) -> bool:
    """Encrypt and store an API key in the vault storage.

    Args:
        service: Service name ("anthropic", "openai", "openrouter")
        key: API key to store

    Returns:
        True if successful

    """
    service = service.lower().strip()
    if not key or _is_placeholder(key):
        logger.warning("Refusing to store placeholder key for %s", service)
        return False

    vault_keys = _load_vault_keys()
    vault_keys[service] = key
    _save_vault_keys(vault_keys)
    logger.info("Stored API key for %s (encrypted vault)", service)
    return True


def has_api_key(service: str) -> bool:
    """Check whether an API key is configured."""
    return get_api_key(service) is not None


def list_configured_services() -> list[str]:
    """설정된 API 키가 있는 서비스 목록을 반환합니다."""
    return [s for s in _ENV_VAR_MAP if get_api_key(s) is not None]


def clear_vault_keys() -> None:
    """Vault 저장소의 모든 키를 삭제합니다."""
    if _VAULT_DB.exists():
        _VAULT_DB.unlink()
        logger.info("Vault keys cleared")


# ─── config.AppConfig 통합 헬퍼 ────────────────────────────────────


def get_raw_config_api_keys() -> dict[str, str | None]:
    """config.yaml의 api_keys 섹션을 반환합니다 (호환성용).

    config.py의 AppConfig에서 config.raw_config['api_keys']를

    대체하기 위해 사용됩니다.
    """
    return {s: get_api_key(s) for s in _ENV_VAR_MAP if get_api_key(s) is not None}


def remove_api_key(service: str) -> bool:
    """Vault 저장소에서 특정 서비스의 API 키를 삭제합니다.

    환경변수나 .env 파일에 설정된 키는 삭제되지 않으며,

    vault 암호화 저장소에 저장된 키만 제거합니다.

    Args:
        service: 서비스 이름 ("anthropic", "openai", "openrouter")

    Returns:
        키가 실제로 삭제되었으면 True, 없었으면 False

    """
    service = service.lower().strip()
    vault_keys = _load_vault_keys()
    if service not in vault_keys:
        return False
    del vault_keys[service]
    _save_vault_keys(vault_keys)
    logger.info("Removed API key for %s from vault", service)
    return True


def get_key_source(service: str) -> str:
    """Return which source has the API key configured.

    Returns: "env", "dotenv", "config", "vault", or "none"
    """
    service = service.lower().strip()
    env_var = _ENV_VAR_MAP.get(service)

    # 1단계: 환경변수
    if env_var:
        value = os.environ.get(env_var)
        if value and not _is_placeholder(value):
            return "env"

    # 2단계: .env 파일
    dotenv = _load_dotenv()
    if env_var and env_var in dotenv:
        value = dotenv[env_var]
        if value and not _is_placeholder(value):
            return "dotenv"

    # 3단계: config.yaml
    config_keys = _load_config_keys()
    if service in config_keys:
        value = config_keys[service]
        if value and not _is_placeholder(value):
            return "config"

    # 4단계: Vault 암호화 저장소
    vault_keys = _load_vault_keys()
    if service in vault_keys:
        value = vault_keys[service]
        if value and not _is_placeholder(value):
            return "vault"

    return "none"


def rotate_master_key(
    new_seed: str | None = None,
    force: bool = False,
) -> _RotationResult:
    """마스터 키를 순환(rotation)하고 모든 vault 데이터를 재암호화합니다.

    기존 vault DB(keys.enc)를 읽고 새 마스터 키로 다시 암호화합니다.

    새 시드를 지정하지 않으면 현재 머신 시드가 사용됩니다
    (키체인/IOPlatformUUID가 동일하면 동일한 키가 생성되므로
    새 시드를 전달해야 실제 순환이 이루어집니다).

    Args:
        new_seed: 새 머신 시드 (None이면 현재 시드 재사용)
        force: True면 키가 동일해도 강제로 재암호화합니다.

    Returns:
        {
            "success": bool,
            "rotated": bool,  # 실제로 새 키가 생성되었는지 여부
            "services_count": int,  # 재암호화된 서비스 수
            "error": str | None,
        }

    Example:
        >>> rotate_master_key()
        {"success": True, "rotated": False, "services_count": 2, "error": None}

        >>> rotate_master_key("new-custom-seed-42")
        {"success": True, "rotated": True, "services_count": 2, "error": None}

    """
    # 1. 기존 vault 데이터 읽기
    old_keys = _load_vault_keys()

    # 2. 새 시드 결정
    if new_seed is not None:
        seed = new_seed
    else:
        seed = _get_machine_seed()

    # 3. 새 마스터 키 생성
    new_key = _derive_key_from_seed(seed)

    # 4. 현재 키와 같은지 확인 (force가 아니고 같으면 rotation 불필요)
    if not force:
        result = _read_master_key()
        if result is not None:
            _, current_key = result
            if current_key == new_key:
                return {
                    "success": True,
                    "rotated": False,
                    "services_count": len(old_keys),
                    "error": None,
                }

    # 5. 새 마스터 키 저장 (최신 KDF 버전)
    _save_master_key_file(new_key, version=_CURRENT_KDF_VERSION)
    _ = _set_keychain_seed(seed)
    logger.info(
        "Master key rotated (force=%s, KDF v%d, new seed: %s...)",
        force,
        _CURRENT_KDF_VERSION,
        seed[:12] if len(seed) > 12 else seed,
    )

    # 6. 기존 vault 데이터 재암호화
    if old_keys:
        try:
            # 새 키로 vault DB 다시 쓰기
            cipher = Fernet(new_key)
            data = json.dumps(old_keys, ensure_ascii=False).encode("utf-8")
            encrypted = cipher.encrypt(data)
            _ = _VAULT_DB.write_bytes(encrypted)
            try:
                os.chmod(_VAULT_DB, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                logger.exception("Unhandled exception")
            logger.info("Re-encrypted %d service keys with new master key", len(old_keys))
        except Exception as e:
            logger.exception("Failed to re-encrypt vault data")
            return {
                "success": False,
                "rotated": True,
                "services_count": 0,
                "error": f"Re-encryption failed: {e}",
            }

    return {
        "success": True,
        "rotated": True,
        "services_count": len(old_keys),
        "error": None,
    }


# 유효한 서비스 목록 (CLI, 외부 모듈에서 사용)
VALID_SERVICES = list(_ENV_VAR_MAP.keys())
