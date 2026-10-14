from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import JsonValue, TypeAdapter

_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


@dataclass(frozen=True, slots=True)
class LegalTermsRecord:
    domain: str
    terms_url: str
    allowed_purposes: tuple[str, ...]
    attested_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LegalPolicyDecision:
    domain: str
    allowed: bool
    reason: str
    terms_url: str = ""


class LegalTermsPolicy:
    mode: str
    _now: Callable[[], datetime]

    def __init__(
        self,
        mode: str = "audit",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"audit", "enforce"}:
            raise ValueError("legal policy mode must be 'audit' or 'enforce'")
        self.mode = normalized_mode
        self._now = now or (lambda: datetime.now(UTC))
        self._records: dict[str, LegalTermsRecord] = {}

    @classmethod
    def from_env(cls, now: Callable[[], datetime] | None = None) -> LegalTermsPolicy:
        policy = cls(mode=os.environ.get("AGK_CRAWLER_LEGAL_POLICY_MODE", "audit"), now=now)
        path_value = os.environ.get("AGK_CRAWLER_LEGAL_POLICY_FILE", "").strip()
        if not path_value:
            return policy
        try:
            payload: JsonValue = _JSON_VALUE_ADAPTER.validate_json(
                Path(path_value).read_text(encoding="utf-8"),
            )
            records_value: JsonValue = payload.get("records", payload) if isinstance(payload, dict) else payload
            records = records_value
            if not isinstance(records, list):
                raise TypeError("legal policy file must contain a records list")
            for record in records:
                if not isinstance(record, dict):
                    raise TypeError("legal policy records must be objects")
                _ = policy.register(
                    domain=_required_string(record, "domain"),
                    terms_url=_required_string(record, "terms_url"),
                    allowed_purposes=_required_strings(record, "allowed_purposes"),
                    attested_at=_parse_datetime(record, "attested_at"),
                    expires_at=_parse_datetime(record, "expires_at"),
                )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return policy
        return policy

    def register(
        self,
        domain: str,
        terms_url: str,
        allowed_purposes: Sequence[str],
        attested_at: datetime,
        expires_at: datetime,
    ) -> LegalTermsRecord:
        normalized_domain = _normalize_domain(domain)
        terms = urlsplit(terms_url)
        purposes = tuple(dict.fromkeys(purpose.strip() for purpose in allowed_purposes if purpose.strip()))
        if terms.scheme != "https" or not terms.netloc:
            raise ValueError("terms_url must be an absolute HTTPS URL")
        if not purposes:
            raise ValueError("allowed_purposes must not be empty")
        if attested_at.tzinfo is None or expires_at.tzinfo is None:
            raise ValueError("legal policy timestamps must be timezone-aware")
        if expires_at <= attested_at:
            raise ValueError("expires_at must be after attested_at")
        record = LegalTermsRecord(
            domain=normalized_domain,
            terms_url=terms_url,
            allowed_purposes=purposes,
            attested_at=attested_at.astimezone(UTC),
            expires_at=expires_at.astimezone(UTC),
        )
        self._records[normalized_domain] = record
        return record

    def evaluate(self, url: str, purpose: str = "research") -> LegalPolicyDecision:
        domain = _normalize_domain(url)
        record = self._records.get(domain)
        if record is None:
            return LegalPolicyDecision(
                domain=domain,
                allowed=self.mode == "audit",
                reason="missing_policy_audit" if self.mode == "audit" else "missing_policy",
            )
        if purpose not in record.allowed_purposes:
            return LegalPolicyDecision(domain, False, "purpose_not_allowed", record.terms_url)
        if record.expires_at <= self._now().astimezone(UTC):
            return LegalPolicyDecision(domain, False, "policy_expired", record.terms_url)
        return LegalPolicyDecision(domain, True, "policy_attested", record.terms_url)


def _normalize_domain(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"https://{candidate}")
    domain = (parsed.hostname or "").rstrip(".").lower()
    if not domain or any(char.isspace() for char in domain):
        raise ValueError("legal policy domain must be a hostname")
    return domain


def _required_string(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"legal policy field {key!r} must be a non-empty string")
    return value


def _required_strings(payload: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"legal policy field {key!r} must be a list of strings")
    return tuple(item for item in value if isinstance(item, str))


def _parse_datetime(payload: Mapping[str, JsonValue], key: str) -> datetime:
    return datetime.fromisoformat(_required_string(payload, key))


class RobotsRateLimitPolicy:
    user_agent: str
    min_interval: float

    def __init__(self, user_agent: str = "Ssak-Ai/1.0", min_interval: float = 0.2) -> None:
        self.user_agent = user_agent
        self.min_interval = min_interval
        self._robots: dict[str, RobotFileParser | None] = {}
        self._delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    async def _wait(self, origin: str, delay: float | None = None) -> None:
        interval = max(self.min_interval, delay or 0.0)
        elapsed = time.monotonic() - self._last_request.get(origin, 0.0)
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        self._last_request[origin] = time.monotonic()

    async def _load_robots(self, origin: str, client: httpx.AsyncClient) -> RobotFileParser | None:
        if origin in self._robots:
            return self._robots[origin]

        await self._wait(origin)
        robots_url = f"{origin}/robots.txt"
        try:
            response = await client.get(robots_url, follow_redirects=False)
        except httpx.RequestError:
            self._robots[origin] = None
            return None

        if response.status_code == 404:
            parser = RobotFileParser(robots_url)
            parser.parse([])
            self._robots[origin] = parser
            return parser
        if response.status_code != 200:
            self._robots[origin] = None
            return None

        parser = RobotFileParser(robots_url)
        parser.parse(response.text.splitlines())
        self._robots[origin] = parser
        crawl_delay = parser.crawl_delay(self.user_agent) or parser.crawl_delay("*") or 0.0
        self._delays[origin] = float(crawl_delay) if isinstance(crawl_delay, (int, float)) else 0.0
        return parser

    async def authorize(self, url: str, client: httpx.AsyncClient) -> bool:
        origin = self._origin(url)
        parser = await self._load_robots(origin, client)
        if parser is None or not parser.can_fetch(self.user_agent, url):
            return False
        await self._wait(origin, self._delays.get(origin))
        return True


__all__ = [
    "LegalPolicyDecision",
    "LegalTermsPolicy",
    "LegalTermsRecord",
    "RobotsRateLimitPolicy",
]
