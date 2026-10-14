from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class SecretPattern:
    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class SecretMatch:
    pattern: str
    redacted: str
    original_length: int = 0


TOKEN_PREFIX_PATTERNS: Final[list[SecretPattern]] = [
    SecretPattern("NVIDIA API key", re.compile(r"\bnvapi-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("NVIDIA Cloud key", re.compile(r"\bnvcf-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("OpenAI project key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("OpenAI API key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b")),
    SecretPattern("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    SecretPattern("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b")),
    SecretPattern("GitHub PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    SecretPattern("AWS access key", re.compile(r"\bA[KS]IA[A-Z0-9]{16}\b")),
    SecretPattern("HuggingFace token", re.compile(r"\bhf_[A-Za-z0-9]{10,}\b")),
    SecretPattern("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{10,}\b")),
    SecretPattern("Slack token", re.compile(r"\b(?:xox[bpas]|xapp)-[A-Za-z0-9-]{10,}\b")),
    SecretPattern("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    SecretPattern("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36,}\b")),
    SecretPattern("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_-]{10,}\b")),
    SecretPattern("Telegram bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    SecretPattern(
        "Private key",
        re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----"),
    ),
]

CONTEXT_PATTERNS: Final[list[SecretPattern]] = [
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

ALL_PATTERNS: Final[list[SecretPattern]] = TOKEN_PREFIX_PATTERNS + CONTEXT_PATTERNS

CREDENTIAL_FIELDS: Final[set[str]] = {
    "apiKey",
    "api_key",
    "token",
    "secret",
    "password",
    "resolvedKey",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "signing_key",
}

CREDENTIAL_FIELD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:access|refresh|client|bearer|auth|api|private|public|signing|session)" + r"(?:Token|Key|Secret|Password)$",
)
CREDENTIAL_PLACEHOLDER: Final[str] = "[STRIPPED_BY_SCANNER]"
CREDENTIAL_SENSITIVE_BASENAMES: Final[set[str]] = {
    "auth-profiles.json",
    ".env.local",
    ".env.production",
}
MEMORY_PATH_SEGMENTS: Final[list[str]] = [
    "/vault_data/",
    "/working_memory/",
    "/session_data/",
    "/credentials/",
    "/.env",
    "/secrets/",
    "/api_keys/",
]
