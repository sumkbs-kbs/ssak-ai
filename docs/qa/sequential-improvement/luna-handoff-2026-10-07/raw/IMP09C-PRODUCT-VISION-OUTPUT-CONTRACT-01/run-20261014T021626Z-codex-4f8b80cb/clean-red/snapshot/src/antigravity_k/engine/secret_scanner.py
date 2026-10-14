"""SecretScanner & Redactor — 에이전트 출력/메모리에서 시크릿 자동 감지 & 마스킹.

==========================================================================
NemoClaw의 secret-scanner.ts + redact.ts + credential-filter.ts 패턴을 이식.

3단계 마스킹:
  - redact()      : 부분 마스킹 (첫 4자 유지) — CLI 출력용
  - redact_full() : 전체 대체 (<REDACTED>) — 디버그 덤프용
  - redact_url()  : URL 파라미터 마스킹 — 로그용

시크릿 감지:
  - scan_for_secrets(text) → [SecretMatch, ...]
  - is_credential_field(key) → bool
  - strip_credentials(obj) → dict (민감 필드 제거)

메모리 보호:
  - is_memory_path(path) → bool (보호 경로 감지)

사용법:
    from antigravity_k.engine.secret_scanner import scan_for_secrets, redact

    text = "API key: sk-proj-abc123xyz789..."
    matches = scan_for_secrets(text)
    safe_text = redact(text)
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from typing import TypeGuard, TypeVar, cast, overload

from pydantic import JsonValue, TypeAdapter, ValidationError

from antigravity_k.engine.secret_scanner_patterns import (
    CREDENTIAL_FIELD_PATTERN,
    CREDENTIAL_FIELDS,
    CREDENTIAL_SENSITIVE_BASENAMES,
    MEMORY_PATH_SEGMENTS,
    SecretMatch,
    SecretPattern,
)
from antigravity_k.engine.secret_scanner_patterns import (
    CREDENTIAL_PLACEHOLDER as _CREDENTIAL_PLACEHOLDER,
)

logger = logging.getLogger("antigravity_k.engine.secret_scanner")

type _NonStringScalar = None | bool | int | float
type SecretValue = JsonValue | tuple[JsonValue, ...]
_ValueT = TypeVar("_ValueT")
_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
CREDENTIAL_PLACEHOLDER = _CREDENTIAL_PLACEHOLDER


# ── 시크릿 패턴 정의 ──


# 토큰 접두어 기반 패턴 (독립 매칭 — 컨텍스트 불필요)
TOKEN_PREFIX_PATTERNS: list[SecretPattern] = [
    # NVIDIA
    SecretPattern("NVIDIA API key", re.compile(r"\bnvapi-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("NVIDIA Cloud key", re.compile(r"\bnvcf-[A-Za-z0-9_-]{10,}\b")),
    # OpenAI (sk-proj- 우선, sk-ant- 제외)
    SecretPattern("OpenAI project key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("OpenAI API key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b")),
    # Anthropic
    SecretPattern("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    # GitHub
    SecretPattern("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b")),
    SecretPattern("GitHub PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    # AWS
    SecretPattern("AWS access key", re.compile(r"\bA[KS]IA[A-Z0-9]{16}\b")),
    # HuggingFace
    SecretPattern("HuggingFace token", re.compile(r"\bhf_[A-Za-z0-9]{10,}\b")),
    # GitLab
    SecretPattern("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{10,}\b")),
    # Groq
    SecretPattern("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{10,}\b")),
    # Slack
    SecretPattern("Slack token", re.compile(r"\b(?:xox[bpas]|xapp)-[A-Za-z0-9-]{10,}\b")),
    # Google
    SecretPattern("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # npm
    SecretPattern("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36,}\b")),
    # PyPI
    SecretPattern("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_-]{10,}\b")),
    # Telegram bot token (봇 ID + 시크릿)
    SecretPattern("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    # Discord bot token — 컨텍스트 패턴으로 이동 (lookbehind 제약)
    # Private keys (PEM)
    SecretPattern(
        "Private key",
        re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----"),
    ),
]

# 컨텍스트 기반 패턴 (KEY=, Bearer 등 접두어 필요)
# Python re는 가변 폭 lookbehind를 지원하지 않으므로, 전체 매치 후 그룹 추출 방식 사용
CONTEXT_PATTERNS: list[SecretPattern] = [
    SecretPattern("Bearer token", re.compile(r"Bearer\s+([A-Za-z0-9_.+/=-]{10,})", re.IGNORECASE)),
    SecretPattern(
        "Environment credential",
        re.compile(
            r'(?:_KEY|API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[=: ][\'"]?([A-Za-z0-9_.+/=-]{10,})',
            re.IGNORECASE,
        ),
    ),
    SecretPattern(
        "Discord bot token",
        re.compile(
            r"(?:discord|bot|DISCORD_TOKEN|BOT_TOKEN|token)\s*[=:]\s*[\"']?"
            + r"([A-Za-z0-9]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})",
        ),
    ),
]

ALL_PATTERNS: list[SecretPattern] = TOKEN_PREFIX_PATTERNS + CONTEXT_PATTERNS


# ── 핵심 API ──


def scan_for_secrets(content: str | _NonStringScalar) -> list[SecretMatch]:
    """텍스트에서 시크릿 패턴을 스캔합니다.

    Returns:
        감지된 시크릿 목록 (패턴 이름 + 마스킹된 값).

    """
    if not isinstance(content, str) or not content:
        return []

    matches: list[SecretMatch] = []
    seen: set[str] = set()

    for pattern in ALL_PATTERNS:
        for match in pattern.regex.finditer(content):
            # 컨텍스트 패턴은 그룹(1)이 실제 시크릿
            value = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
            key = f"{pattern.name}:{value}"
            if key in seen:
                continue
            seen.add(key)

            if len(value) > 8:
                redacted = f"{value[:4]}..{value[-4:]}"
            else:
                redacted = "****"

            matches.append(
                SecretMatch(
                    pattern=pattern.name,
                    redacted=redacted,
                    original_length=len(value),
                ),
            )

    return matches


@overload
def redact(text: str) -> str: ...


@overload
def redact(text: _NonStringScalar) -> _NonStringScalar: ...


def redact(text: str | _NonStringScalar) -> str | _NonStringScalar:
    """부분 마스킹 — 첫 4자를 유지합니다 (CLI 출력용).

    Example:
        "sk-proj-abc123xyz" → "sk-p****************"

    """
    if not isinstance(text, str):
        return text

    # URL 파라미터 먼저 처리
    result = re.sub(r"https?://[^\s'\"]+", _redact_url_partial, text)

    # 시크릿 패턴 처리
    for pattern in ALL_PATTERNS:
        result = pattern.regex.sub(_redact_match_partial, result)

    return result


@overload
def redact_full(text: str) -> str: ...


@overload
def redact_full(text: _NonStringScalar) -> _NonStringScalar: ...


def redact_full(text: str | _NonStringScalar) -> str | _NonStringScalar:
    """전체 마스킹 — 값 전체를 <REDACTED>로 대체합니다 (디버그 덤프용)."""
    if not isinstance(text, str):
        return text

    result = text

    # 환경변수 형식: KEY=value
    result = re.sub(
        r"((?:NVIDIA_API_KEY|API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|_KEY)=)\S+",
        r"\1<REDACTED>",
        result,
        flags=re.IGNORECASE,
    )
    # Bearer 토큰
    result = re.sub(r"(Bearer\s)\S+", r"\1<REDACTED>", result, flags=re.IGNORECASE)

    # 토큰 접두어 패턴
    for pattern in TOKEN_PREFIX_PATTERNS:
        result = pattern.regex.sub("<REDACTED>", result)

    return result


def redact_url(url: str | _NonStringScalar) -> str | None:
    """URL에서 인증 정보를 제거합니다."""
    if not isinstance(url, str) or not url:
        return None
    try:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)

        # 사용자:비밀번호 제거
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"

        # 민감 쿼리 파라미터 마스킹
        params = parse_qs(parsed.query, keep_blank_values=True)
        sensitive_keys = {
            "signature",
            "sig",
            "token",
            "auth",
            "access_token",
            "api_key",
        }
        for key in list(params.keys()):
            if key.lower() in sensitive_keys:
                params[key] = ["<REDACTED>"]

        clean_query = urlencode(params, doseq=True)

        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                clean_query,
                "",  # fragment 제거
            ),
        )
    except (ValueError, UnicodeError):
        logger.exception("Unhandled exception")
        return redact(url)[:240] if url else None


def is_credential_field(key: str) -> bool:
    """필드 이름이 민감 필드인지 확인합니다."""
    return key in CREDENTIAL_FIELDS or bool(CREDENTIAL_FIELD_PATTERN.search(key))


def _is_json_value(value: _ValueT, _hint: _ValueT | None = None) -> TypeGuard[JsonValue]:
    try:
        _ = _JSON_VALUE_ADAPTER.validate_python(value)
    except ValidationError:
        return False
    return True


def _scrub_json_value(value: JsonValue) -> None:
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            _scrub_json_value(item)
        return
    for key, item in value.items():
        if is_credential_field(key):
            value[key] = CREDENTIAL_PLACEHOLDER
        else:
            _scrub_json_value(item)


def strip_credentials(obj: _ValueT) -> _ValueT:
    """딕셔너리에서 민감 필드 값을 재귀적으로 마스킹합니다.

    Returns:
        민감 값이 CREDENTIAL_PLACEHOLDER로 대체된 새 딕셔너리.

    """
    if not _is_json_value(obj):
        return obj
    scrubbed = deepcopy(obj)
    if _is_json_value(scrubbed):
        _scrub_json_value(scrubbed)
    return cast(_ValueT, scrubbed)


def is_sensitive_file(filename: str) -> bool:
    """파일이 전체 제외 대상인지 확인합니다."""
    return filename.lower() in CREDENTIAL_SENSITIVE_BASENAMES


def is_memory_path(file_path: str) -> bool:
    """파일 경로가 보호 대상 메모리 위치인지 확인합니다."""
    return any(segment in file_path for segment in MEMORY_PATH_SEGMENTS)


# ── 내부 헬퍼 ──


def _redact_match_partial(match: re.Match[str]) -> str:
    """매치된 시크릿을 부분 마스킹합니다."""
    value = match.group(0)
    if len(value) <= 4:
        return "****"
    return value[:4] + "*" * min(len(value) - 4, 20)


def _redact_url_partial(match: re.Match[str]) -> str:
    """URL에서 인증 정보를 부분 마스킹합니다."""
    url = match.group(0)
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = "****:****@" + (parsed.hostname or "")
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(
                (
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                ),
            )
    except (ValueError, UnicodeError):
        logger.exception("Unhandled exception")
    return url
