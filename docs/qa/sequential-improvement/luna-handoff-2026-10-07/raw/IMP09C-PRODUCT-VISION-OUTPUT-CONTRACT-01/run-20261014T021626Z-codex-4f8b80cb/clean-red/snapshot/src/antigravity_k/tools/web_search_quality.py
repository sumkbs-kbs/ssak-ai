"""검색 결과 정규화, 품질 점수, 비신뢰 웹 콘텐츠 경계."""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import re
import socket
from collections.abc import Sequence
from dataclasses import replace
from functools import partial
from typing import Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .web_search_models import SearchResult

_TRACKING_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"})
_BLOCKED_MARKUP = re.compile(r"</?(?:tool_call|action_call|system|assistant|developer)\b[^>]*>", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_VERSION_PATTERN = re.compile(
    r"\b(?=[a-z0-9.]*\d)(?:[a-z][a-z0-9]*\.)+[a-z0-9]+\b|\b\d+(?:\.\d+)+\b",
    re.IGNORECASE,
)
_AUTHORITATIVE_INTENT_PATTERN = re.compile(r"\b(?:official|docs?|documentation|rfc|standard)\b", re.IGNORECASE)
_QUERY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "citation": ("reference", "evidence", "source"),
    "compaction": ("compress", "compression", "compact"),
    "freshness": ("updated", "latest", "current"),
    "latency": ("delay", "response", "speed"),
    "provenance": ("citation", "evidence", "source"),
    "recall": ("retrieve", "retrieval"),
    "runtime": ("server", "inference", "execution"),
}


def canonicalize_url(url: str) -> str:
    """Return a stable public URL representation for identity and caching."""
    try:
        parsed = urlsplit(url.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        return ""

    scheme = parsed.scheme.lower()
    host = hostname.lower().rstrip(".")
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    # IPv6 literals must keep brackets in netloc (urlunsplit / urlsplit contract).
    host_netloc = f"[{host}]" if ":" in host else host
    netloc = host_netloc if port is None or default_port else f"{host_netloc}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
        ),
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def source_id_for_url(url: str) -> str:
    """Return a short stable citation id derived from a canonical URL."""
    canonical = canonicalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12] if canonical else ""


def authority_score(url: str) -> float:
    """Estimate source authority from domain class without claiming factual truth."""
    canonical = canonicalize_url(url)
    host = (urlsplit(canonical).hostname or "").removeprefix("www.")
    if host.endswith((".gov", ".gov.uk", ".go.kr", ".gc.ca", ".edu", ".ac.kr")):
        return 0.95
    if host in {
        "datatracker.ietf.org",
        "docs.python.org",
        "docs.ollama.com",
        "developer.mozilla.org",
        "fastapi.tiangolo.com",
        "github.com",
        "kubernetes.io",
        "ollama.com",
        "python.org",
        "qwen.ai",
        "rfc-editor.org",
        "qwenlm.ai",
    }:
        return 0.9
    if host == "unsloth.ai":
        return 0.8
    if host.endswith("wikipedia.org"):
        return 0.7
    if host.endswith((".com", ".org", ".net")):
        return 0.55
    return 0.4


def requires_authoritative_sources(query: str) -> bool:
    return bool(_AUTHORITATIVE_INTENT_PATTERN.search(query))


def is_authoritative_source(url: str, authority_threshold: float = 0.9) -> bool:
    canonical = canonicalize_url(url)
    host = (urlsplit(canonical).hostname or "").removeprefix("www.")
    return host != "github.com" and authority_score(canonical) >= authority_threshold


def official_source_hints(query: str) -> list[SearchResult]:
    if "qwen3.6" not in query.casefold():
        return []
    return [
        SearchResult(
            title="Qwen3.6 official repository",
            url="https://github.com/QwenLM/Qwen3.6",
            snippet="Official Qwen3.6 source. Retrieve page content before making model-specific claims.",
            source="Official source registry",
            relevance_score=1.0,
        ),
        SearchResult(
            title="Qwen3.6 model library - Ollama",
            url="https://ollama.com/library/qwen3.6",
            snippet="Official Ollama Qwen3.6 model page. Retrieve page content before making model-specific claims.",
            source="Official source registry",
            relevance_score=1.0,
        ),
    ]


def rank_search_results(
    results: list[SearchResult],
    max_results: int,
    max_per_domain: int = 2,
    query: str = "",
) -> list[SearchResult]:
    """Normalize, deduplicate, score, and diversify search results."""
    best_by_url: dict[str, SearchResult] = {}
    for result in results:
        canonical = canonicalize_url(result.url)
        if not canonical:
            continue
        authority = authority_score(canonical)
        query_score = _query_relevance(query, result)
        authority_bonus = 0.1 if requires_authoritative_sources(query) and is_authoritative_source(canonical) else 0.0
        enriched = replace(
            result,
            url=canonical,
            canonical_url=canonical,
            source_id=source_id_for_url(canonical),
            domain=urlsplit(canonical).hostname or "",
            authority_score=authority,
            ranking_score=(max(0.0, min(1.0, result.relevance_score)) * 0.45)
            + (authority * 0.30)
            + (query_score * 0.25)
            + authority_bonus,
        )
        current = best_by_url.get(canonical)
        if current is None or enriched.ranking_score > current.ranking_score:
            best_by_url[canonical] = enriched

    ordered = sorted(best_by_url.values(), key=lambda item: item.ranking_score, reverse=True)
    selected: list[SearchResult] = []
    domain_counts: dict[str, int] = {}
    for result in ordered:
        count = domain_counts.get(result.domain, 0)
        if count >= max_per_domain:
            continue
        selected.append(result)
        domain_counts[result.domain] = count + 1
        if len(selected) >= max_results:
            break
    return selected


def _query_relevance(query: str, result: SearchResult) -> float:
    query_tokens: set[str] = set(_TOKEN_PATTERN.findall(query.casefold()))
    if not query_tokens:
        return 0.0
    title_tokens: set[str] = set(_TOKEN_PATTERN.findall(result.title.casefold()))
    result_tokens: set[str] = title_tokens | set(_TOKEN_PATTERN.findall(result.snippet.casefold()))
    alias_tokens = {alias for token in query_tokens for alias in _QUERY_ALIASES.get(token, ())}
    coverage = (len(query_tokens & result_tokens) + (0.5 * len(alias_tokens & result_tokens))) / len(query_tokens)
    title_coverage = (len(query_tokens & title_tokens) + (0.5 * len(alias_tokens & title_tokens))) / len(query_tokens)
    score = min(1.0, (coverage * 0.7) + (title_coverage * 0.3))
    specific_terms: list[str] = _VERSION_PATTERN.findall(query.casefold())
    if specific_terms:
        compact_result = re.sub(r"[\W_]+", "", f"{result.title} {result.snippet}".casefold())
        exact_matches = sum(1 for term in specific_terms if re.sub(r"[\W_]+", "", term) in compact_result)
        score *= exact_matches / len(specific_terms)
    return score


def has_query_relevant_result(
    query: str,
    results: Sequence[SearchResult],
    threshold: float = 0.45,
) -> bool:
    return any(_query_relevance(query, result) >= threshold for result in results)


def has_authoritative_query_result(
    query: str,
    results: Sequence[SearchResult],
    relevance_threshold: float = 0.45,
    authority_threshold: float = 0.9,
) -> bool:
    return any(
        is_authoritative_source(result.url, authority_threshold)
        and _query_relevance(query, result) >= relevance_threshold
        for result in results
    )


def sanitize_untrusted_text(text: str, max_chars: int = 1200, *, wrap: bool = True) -> str:
    """Wrap web text as data and neutralize markup that resembles agent control syntax."""
    clean = _CONTROL_CHARS.sub("", text).strip()[:max_chars]
    clean = _BLOCKED_MARKUP.sub("[blocked_tool_markup]", clean)
    if not wrap:
        return html.escape(clean, quote=False)
    return f"[untrusted_web_content]\n{html.escape(clean, quote=False)}\n[/untrusted_web_content]"


_NUMERIC_HOST_RE = re.compile(
    r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$",
    re.IGNORECASE,
)


def _looks_like_numeric_host(hostname: str) -> bool:
    """True for decimal/short/hex/octal IPv4 spellings (not DNS names)."""
    return bool(_NUMERIC_HOST_RE.fullmatch(hostname))


def _coerce_ip_hostname(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a hostname as an IP, including ambiguous IPv4 encodings.

    ``ipaddress`` rejects decimal (``2130706433``), short (``127.1``), hex
    (``0x7f.0.0.1``), and octal-leading (``0177.0.0.1``) forms, but
    ``socket.inet_aton`` / some HTTP stacks accept them — often as loopback.
    Prefer the strict parser; fall back to ``inet_aton`` for numeric hosts.
    """
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass
    if not hostname or ":" in hostname or not _looks_like_numeric_host(hostname):
        return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except OSError:
        return None


def is_public_http_url(url: str) -> bool:
    """Reject non-HTTP, credential-bearing, local, and private-network URLs."""
    canonical = canonicalize_url(url)
    if not canonical:
        return False
    parsed = urlsplit(canonical)
    hostname = parsed.hostname or ""
    if not hostname:
        return False
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal", ".localhost")):
        return False
    address = _coerce_ip_hostname(hostname)
    if address is not None:
        return _is_public_address(address)
    # Ambiguous numeric hosts that no parser accepted are not "public DNS names".
    if _looks_like_numeric_host(hostname):
        return False
    return True


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def is_resolved_public_http_url(url: str) -> bool:
    return await resolve_public_http_url(url) is not None


async def resolve_public_http_url(url: str) -> tuple[str, tuple[str, ...]] | None:
    resolver = partial(resolve_public_http_url_sync, url)
    return await asyncio.to_thread(resolver)


def resolve_public_http_url_sync(url: str) -> tuple[str, tuple[str, ...]] | None:
    canonical = canonicalize_url(url)
    if not is_public_http_url(canonical):
        return None
    parsed = urlsplit(canonical)
    hostname = parsed.hostname or ""
    literal = _coerce_ip_hostname(hostname)
    if literal is None:
        resolver = partial(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        try:
            records = resolver()
        except (OSError, UnicodeError):
            return None
        addresses = {str(record[4][0]) for record in records if record[4]}
        if not addresses:
            return None
        try:
            if not all(_is_public_address(ipaddress.ip_address(address)) for address in addresses):
                return None
        except ValueError:
            return None
        return canonical, tuple(sorted(addresses))
    if not _is_public_address(literal):
        return None
    return canonical, (str(literal),)
