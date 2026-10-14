"""Ssak-Search client module — lightweight client for deployed search API."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from antigravity_k.tools.egress_policy import safe_urlopen
from antigravity_k.tools.search_auth import SEARCH_TOKEN_ENV, search_auth_headers

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://search-engine-api.pages.dev"


@dataclass(frozen=True, slots=True)
class SsakHit:
    """Represents a single search result from Ssak-Search."""

    title: str
    url: str
    content: str
    score: float
    domain: str


def search(
    query: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    max_results: int = 5,
    search_depth: str = "basic",
    timeout: float = 15.0,
) -> list[SsakHit]:
    """Execute search query against the Ssak-Search API."""
    body = json.dumps(
        {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")
    endpoint = f"{base_url.rstrip('/')}/api/search"
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SSAK-AI/1.0",
            # 인증 게이트가 기본 closed 다 — 헤더가 없으면 401 이고 결과는 조용히 빈다.
            **search_auth_headers(),
        },
        method="POST",
    )
    try:
        with safe_urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            logger.warning(
                "Ssak-Search 인증 실패(HTTP %s) — %s 를 설정하세요",
                error.code,
                SEARCH_TOKEN_ENV,
            )
        return []
    except Exception:
        return []
    hits: list[SsakHit] = []
    for item in payload.get("results", []):
        try:
            hits.append(
                SsakHit(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    content=str(item.get("content", "")),
                    score=float(item.get("score", 0.0)),
                    domain=str(item.get("domain", "")),
                )
            )
        except (TypeError, ValueError):
            continue
    return hits


def grounded_context(query: str, *, max_results: int = 5, base_url: str = DEFAULT_BASE_URL) -> str:
    """Retrieve search results and format as context lines."""
    hits = search(query, max_results=max_results, base_url=base_url)
    if not hits:
        return ""
    lines = [f"Web search results for: {query}"]
    for i, h in enumerate(hits, 1):
        lines.append(f"\n[{i}] {h.title}\n    {h.url}\n    {h.content[:300]}")
    return "\n".join(lines)


def _refine_query(question: str) -> str:
    """Strip question fillers to produce a concise search query."""
    q = question.strip().rstrip("?").strip()
    lowered = q.lower()
    prefixes = (
        "what is",
        "what are",
        "what was",
        "what were",
        "how to implement",
        "how to write",
        "how to create",
        "how to build",
        "how to",
        "tell me about",
        "tell me",
        "explain to me",
        "explain how to",
        "explain how",
        "explain",
        "can you explain",
        "can you tell me",
        "can you",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix + " "):
            q = q[len(prefix) + 1 :].strip()
            lowered = q.lower()
            break

    filler_words = {"the", "a", "an", "is", "are", "does", "do", "can"}
    words = [w for w in q.split() if w.lower() not in filler_words]
    return " ".join(words[:8]) if words else question


def grounded_answer(
    question: str,
    generate_fn: Callable[..., str],
    model: str,
    *,
    max_results: int = 5,
    base_url: str = DEFAULT_BASE_URL,
) -> tuple[str, list[SsakHit]]:
    """Search for relevant web facts and generate an evidence-grounded answer."""
    refined = _refine_query(question)
    hits = search(refined, max_results=max_results, base_url=base_url)
    if not hits:
        hits = search(question, max_results=max_results, base_url=base_url)
    context = "\n".join(f"[{i + 1}] {h.title}\n{h.url}\n{h.content[:400]}" for i, h in enumerate(hits))
    prompt = (
        f"Answer this question using the reference information below. "
        f"Be specific and cite which sources support your answer.\n\n"
        f"Reference:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )
    answer = generate_fn(prompt=prompt, target=model, max_tokens=600, temperature=0.0)
    return answer, hits
