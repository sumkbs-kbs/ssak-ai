from functools import partial
from typing import Literal, assert_never

import httpx
import pytest

from antigravity_k.tools import egress_policy
from antigravity_k.tools.web_search_engine import WebSearchEngine
from antigravity_k.tools.web_search_html import parse_duckduckgo_results
from antigravity_k.tools.web_search_tool import WebSearchTool

Adapter = Literal["sync", "html", "lite"]
SearchTuple = tuple[str, str, str]


async def _search(adapter: Adapter, page: str, monkeypatch: pytest.MonkeyPatch) -> list[SearchTuple]:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text=page)

    transport = httpx.MockTransport(respond)

    def resolve_provider(url: str) -> tuple[str, tuple[str, ...]]:
        return url, ("93.184.216.34",)

    monkeypatch.setattr(egress_policy, "resolve_public_http_url_sync", resolve_provider)
    match adapter:
        case "sync":
            monkeypatch.setattr(httpx, "Client", partial(httpx.Client, transport=transport))
            return WebSearchTool()._sync_search_duckduckgo("parser test")
        case "html" | "lite":
            async with httpx.AsyncClient(transport=transport) as client:
                engine = WebSearchEngine()
                engine._client = client
                match adapter:
                    case "html":
                        results = await engine._search_duckduckgo("parser test")
                    case "lite":
                        results = await engine._search_duckduckgo_lite("parser test")
                    case unreachable:
                        assert_never(unreachable)
                return [(result.title, result.url, result.snippet) for result in results]
        case unreachable:
            assert_never(unreachable)


def _classes(adapter: Adapter) -> tuple[str, str]:
    match adapter:
        case "lite":
            return "result-link", "result-snippet"
        case "html" | "sync":
            return "result__a", "result__snippet"
        case unreachable:
            assert_never(unreachable)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
async def test_retains_snippet_owner_when_first_result_has_no_snippet(
    adapter: Adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: two HTML result containers (Lite uses successive table rows).
    title_class, snippet_class = _classes(adapter)
    page = (
        f'<div class="result results_links"><a class="{title_class}" '
        'href="https://example.com/first">First</a></div>'
        f'<div class="result results_links"><a class="{title_class}" '
        'href="https://example.com/second">Second</a>'
        f'<a class="{snippet_class}">Second result facts</a></div>'
    )
    match adapter:
        case "lite":
            page = (
                '<table><tr><td>1.</td><td><a class="result-link" '
                'href="https://example.com/first">First</a></td></tr>'
                '<tr><td>2.</td><td><a class="result-link" '
                'href="https://example.com/second">Second</a></td></tr>'
                '<tr><td></td><td class="result-snippet">Second result facts</td></tr></table>'
            )
        case "sync" | "html":
            pass
        case unreachable:
            assert_never(unreachable)

    # When: the real adapter reads the HTTP response.
    results = await _search(adapter, page, monkeypatch)

    # Then: absence does not shift the next result's facts.
    assert results == [
        ("First", "https://example.com/first", ""),
        ("Second", "https://example.com/second", "Second result facts"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
async def test_parses_markup_drift_and_escaped_text_when_attributes_are_reordered(
    adapter: Adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: single quotes, whitespace around '=', multiple classes, nested text.
    title_class, snippet_class = _classes(adapter)
    page = (
        "<div class='result'><a href = '//duckduckgo.com/l/?uddg="
        "https%3A%2F%2Fexample.com%2Fpage%3Fa%3D1%26b%3D2&amp;rut=token' "
        f"class = 'extra {title_class} selected'>Fish &amp; <b>chips</b></a>"
        f"<td class = 'extra {snippet_class}'>Fresh &lt;facts&gt; &#39;today&#39;</td></div>"
    )

    # When: markup is parsed through each deployed adapter.
    results = await _search(adapter, page, monkeypatch)

    # Then: entities become text and the DDG redirect yields its target.
    assert results == [("Fish & chips", "https://example.com/page?a=1&b=2", "Fresh <facts> 'today'")]


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
async def test_keeps_ordinary_results_when_articles_discuss_captcha(
    adapter: Adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an ordinary result that describes bot challenge systems.
    title_class, snippet_class = _classes(adapter)
    page = (
        f'<a class="{title_class}" href="https://example.com/captcha">CAPTCHA research</a>'
        f'<td class="{snippet_class}">Please complete the following challenge is a common CAPTCHA phrase.</td>'
    )

    # When: the result page is processed.
    results = await _search(adapter, page, monkeypatch)

    # Then: discussion is retained as a search result.
    assert len(results) == 1
    assert results[0][0] == "CAPTCHA research"


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
@pytest.mark.parametrize("challenge", ["<div class='anomaly-modal'>", "<form id='challenge-form'>"])
async def test_returns_no_results_when_structural_challenge_wraps_result_links(
    adapter: Adapter, challenge: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: challenge markup contains links that imitate results.
    title_class, _ = _classes(adapter)
    page = f'{challenge}<a class="{title_class}" href="https://example.com/fake">Fake</a></form></div>'

    # When: the provider returns the challenge page.
    results = await _search(adapter, page, monkeypatch)

    # Then: no challenge content enters the result pool.
    assert results == []


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
@pytest.mark.parametrize("target", ["http://127.0.0.1/private", "https://example.com:bad/path", "http://[broken"])
async def test_excludes_invalid_targets_when_provider_returns_untrusted_links(
    adapter: Adapter, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a provider result carries a private or malformed target.
    title_class, _ = _classes(adapter)
    page = f'<a class="{title_class}" href="{target}">Invalid target</a>'

    # When: the result reaches the shared parsing boundary.
    results = await _search(adapter, page, monkeypatch)

    # Then: invalid targets are absent from all adapter return shapes.
    assert results == []


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["sync", "html", "lite"])
async def test_preserves_external_query_when_uddg_parameter_is_not_a_ddg_redirect(
    adapter: Adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an external page has an unrelated uddg parameter.
    title_class, _ = _classes(adapter)
    target = "https://example.com/article?uddg=https%3A%2F%2Fother.example%2Ftarget"
    page = f'<a class="{title_class}" href="{target}">External article</a>'

    # When: the provider link is parsed.
    results = await _search(adapter, page, monkeypatch)

    # Then: its own public URL survives without arbitrary redirect routing.
    assert results == [("External article", target, "")]


@pytest.mark.parametrize(
    "href",
    [
        "https://duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fprivate",
        "https://user:secret@duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget",
        "https://duckduckgo.com:bad/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget",
    ],
)
def test_excludes_redirect_when_wrapper_or_target_is_invalid(href: str) -> None:
    # Given: DDG redirect markup carries an invalid wrapper or private target.
    page = f'<a class="result__a" href="{href}">Redirect</a>'

    # When: the shared parser processes the response.
    results = parse_duckduckgo_results(page)

    # Then: no invalid link crosses the boundary.
    assert results == []


def test_uses_container_when_snippet_precedes_title_and_detached_snippet_follows() -> None:
    # Given: a snippet precedes its title, with unrelated snippet markup outside.
    page = (
        '<div class="result"><div class="result__snippet">Owned facts</div>'
        '<a class="result__a" href="https://example.com/first">First</a></div>'
        '<div class="result__snippet">Detached facts</div>'
        '<div class="result"><a class="result__a" href="https://example.com/second">Second</a></div>'
    )

    # When: the shared parser applies container ownership.
    results = parse_duckduckgo_results(page)

    # Then: only the snippet belonging to the same result is associated.
    assert [(result.title, result.snippet) for result in results] == [("First", "Owned facts"), ("Second", "")]


def test_preserves_isolated_fixture_when_links_have_no_container() -> None:
    # Given: legacy fixtures contain only adjacent title and snippet nodes.
    page = (
        '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Ffirst">First</a>'
        '<a class="result__snippet">First facts</a>'
        '<a class="result__a" href="https://example.com/second">Second</a>'
        '<a class="result__snippet">Second facts</a>'
    )

    # When: the shared parser processes isolated nodes.
    results = parse_duckduckgo_results(page)

    # Then: order supplies ownership and a relative DDG redirect is decoded.
    assert [(result.url, result.snippet) for result in results] == [
        ("https://example.com/first", "First facts"),
        ("https://example.com/second", "Second facts"),
    ]
