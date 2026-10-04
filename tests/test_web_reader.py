from __future__ import annotations

import gzip
from collections.abc import Iterator
from typing import override

import httpx
import pytest

from antigravity_k.tools import web_search_engine as engine_module
from antigravity_k.tools.crawler_policy import RobotsRateLimitPolicy
from antigravity_k.tools.web_search_engine import PageScraper, WebSearchEngine

CHALLENGE = (
    "Title: Just a moment...\nWarning: This page is requiring CAPTCHA.\n"
    "Markdown Content: Please verify you are human before continuing."
)


class LargeStream(httpx.SyncByteStream):
    def __init__(self) -> None:
        self.chunks = 0
        self.closed = False

    @override
    def __iter__(self) -> Iterator[bytes]:
        for _ in range(6):
            self.chunks += 1
            yield b"x" * (2 * 1024 * 1024)

    @override
    def close(self) -> None:
        self.closed = True


def allow_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "resolve_public_http_url_sync", lambda url: (url, ("93.184.216.34",)))


@pytest.mark.parametrize(
    "mime,body",
    [
        ("text/markdown", CHALLENGE),
        ("text/html", "<title>Attention Required!</title><p>Cloudflare Ray ID: 12345</p>"),
        (
            "text/html",
            "<title>Just a moment...</title>" + " " * 4200 + '<script src="/cdn-cgi/challenge-platform/run"></script>',
        ),
        ("application/pdf", "%PDF-1.7 " + "private binary content " * 10),
    ],
    ids=["jina-challenge", "cloudflare", "late-cloudflare-marker", "binary"],
)
def test_jina_rejects_challenge_and_binary(
    monkeypatch: pytest.MonkeyPatch,
    mime: str,
    body: str,
) -> None:
    allow_public(monkeypatch)

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": mime}, text=body, request=request)

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(engine_module.httpx, "Client", lambda **kwargs: client)
    assert WebSearchEngine().extract_content_jina("https://example.com/article") == ""
    assert client.is_closed


def test_jina_keeps_real_article_about_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_public(monkeypatch)
    article = "Title: CAPTCHA accessibility research\nMarkdown Content: " + "Study results are available. " * 6

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=article, request=request)

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(engine_module.httpx, "Client", lambda **kwargs: client)
    assert WebSearchEngine().extract_content_jina("https://example.com/article", max_chars=90) == article[:90]


def test_jina_stops_large_stream_and_closes_response(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_public(monkeypatch)
    stream = LargeStream()

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "1"}, stream=stream, request=request)

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(engine_module.httpx, "Client", lambda **kwargs: client)
    assert WebSearchEngine().extract_content_jina("https://example.com/article") == ""
    assert stream.closed
    assert stream.chunks == 3


@pytest.mark.parametrize(
    "mime,body",
    [
        ("text/html", '<title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/run"></script>'),
        ("image/png", "binary content"),
        ("text/html", "x" * (5 * 1024 * 1024 + 1)),
    ],
    ids=["cloudflare", "binary", "oversize"],
)
@pytest.mark.asyncio
async def test_scraper_rejects_unusable_bodies(
    monkeypatch: pytest.MonkeyPatch,
    mime: str,
    body: str,
) -> None:
    async def resolve(url: str) -> tuple[str, tuple[str, ...]]:
        return url, ("93.184.216.34",)

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(200, headers={"content-type": mime}, text=body, request=request)

    monkeypatch.setattr(engine_module, "resolve_public_http_url", resolve)
    scraper = PageScraper()
    client = httpx.AsyncClient(transport=httpx.MockTransport(serve))
    setattr(scraper, "_client", client)
    setattr(scraper, "_crawl_policy", RobotsRateLimitPolicy(min_interval=0))
    try:
        assert "차단됨" in await scraper.extract_text("https://example.com/article")
    finally:
        await scraper.close()
    assert client.is_closed


def test_jina_limits_decompressed_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_public(monkeypatch)
    compressed = gzip.compress(b"x" * (5 * 1024 * 1024 + 1))

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-type": "text/plain"},
            stream=httpx.ByteStream(compressed),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(engine_module.httpx, "Client", lambda **kwargs: client)
    assert WebSearchEngine().extract_content_jina("https://example.com/article") == ""


def test_jina_handles_unknown_declared_charset(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_public(monkeypatch)
    article = "한글 문서 본문 " * 20

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=unknown-test-codec"},
            stream=httpx.ByteStream(article.encode()),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(engine_module.httpx, "Client", lambda **kwargs: client)
    assert WebSearchEngine().extract_content_jina("https://example.com/article") == article.strip()


@pytest.mark.parametrize("mime", ["text/plain", "text/markdown"])
@pytest.mark.asyncio
async def test_scraper_preserves_literal_html_in_plain_text(
    monkeypatch: pytest.MonkeyPatch,
    mime: str,
) -> None:
    article = "Version 2: KEEP THE SAFETY WARNING.\n\nUse <main>Sample content</main> and <article>facts</article>."

    async def resolve(url: str) -> tuple[str, tuple[str, ...]]:
        return url, ("93.184.216.34",)

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, request=request)
        return httpx.Response(200, headers={"content-type": mime}, text=article, request=request)

    monkeypatch.setattr(engine_module, "resolve_public_http_url", resolve)
    scraper = PageScraper()
    setattr(scraper, "_client", httpx.AsyncClient(transport=httpx.MockTransport(serve)))
    setattr(scraper, "_crawl_policy", RobotsRateLimitPolicy(min_interval=0))
    try:
        assert await scraper.extract_text("https://example.com/readme.txt") == article
        assert await scraper.extract_text("https://example.com/readme.txt", max_chars=8) == article[:8]
    finally:
        await scraper.close()
