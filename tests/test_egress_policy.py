from urllib.request import Request

import httpx
import pytest

from antigravity_k.tools.egress_policy import (
    EgressPolicyError,
    safe_urlopen,
    validate_egress_url,
    validate_httpx_request_async,
    validate_public_httpx_request,
)


def test_validate_egress_url_allows_local_ollama():
    assert validate_egress_url("http://localhost:11434/api/tags") == "http://localhost:11434/api/tags"
    assert validate_egress_url("http://127.0.0.1:11434/api/tags") == "http://127.0.0.1:11434/api/tags"


def test_validate_egress_url_rejects_private_and_non_http_targets():
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("http://192.168.1.20:11434/api/tags")
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("file:///etc/passwd")
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("http://localhost:11434/api/tags", allow_local=False)


def test_public_httpx_hook_rejects_local_destination():
    request = httpx.Request("POST", "http://127.0.0.1:8080/webhook")

    with pytest.raises(EgressPolicyError):
        validate_public_httpx_request(request)


def test_validate_egress_url_rejects_public_hostname_with_private_dns(
    monkeypatch: pytest.MonkeyPatch,
):
    def reject_private_dns(url: str) -> None:
        _ = url
        return None

    monkeypatch.setattr(
        "antigravity_k.tools.egress_policy.resolve_public_http_url_sync",
        reject_private_dns,
    )
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("https://provider.example/v1/chat/completions")


def test_safe_urlopen_validates_request_before_open(monkeypatch: pytest.MonkeyPatch):
    request = Request("http://127.0.0.1:11434/api/tags")
    opened: list[str] = []

    def fake_urlopen(_opener: object, target: str | Request, *_args: object, **_kwargs: object) -> str:
        opened.append(target.full_url if isinstance(target, Request) else target)
        return "response"

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fake_urlopen)
    assert safe_urlopen(request, timeout=2) == "response"
    assert opened == [request.full_url]


@pytest.mark.asyncio
async def test_async_httpx_hook_is_awaitable_and_validates_request():
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [validate_httpx_request_async]},
    ) as client:
        response = await client.get("http://localhost:11434/api/tags")

    assert response.status_code == 200
    assert seen == ["http://localhost:11434/api/tags"]


class TestSafeUrlopenRetry:
    """일시적 HTTP 오류(429/5xx) 재시도 + Retry-After 백오프 검증."""

    @pytest.fixture(autouse=True)
    def _synthetic_public_dns(self, monkeypatch):
        def resolve(url: str) -> tuple[str, tuple[str, ...]] | None:
            if url == "https://openrouter.ai/api/v1/x":
                return url, ("192.0.2.53",)
            return None

        monkeypatch.setattr("antigravity_k.tools.egress_policy.resolve_public_http_url_sync", resolve)

    def test_retries_on_429_then_succeeds(self, monkeypatch):
        import urllib.error

        from antigravity_k.tools import egress_policy

        calls = {"n": 0}
        sleeps: list[float] = []

        def fake_urlopen(_opener, target, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(str(target), 429, "Too Many Requests", hdrs=None, fp=None)
            return object()

        monkeypatch.setattr(egress_policy.urllib.request.OpenerDirector, "open", fake_urlopen)
        monkeypatch.setattr(egress_policy, "_retry_sleep", lambda s: sleeps.append(s))
        # 공개 호스트 URL 사용
        req = egress_policy.urllib.request.Request("https://openrouter.ai/api/v1/x")

        egress_policy.safe_urlopen(req, timeout=30)
        assert calls["n"] == 2
        assert len(sleeps) == 1 and sleeps[0] > 0

    def test_honors_retry_after_header(self, monkeypatch):
        import urllib.error

        from antigravity_k.tools import egress_policy

        sleeps: list[float] = []

        def fake_urlopen(_opener, target, timeout=None):
            raise urllib.error.HTTPError(
                str(target),
                503,
                "Service Unavailable",
                hdrs={"Retry-After": "7"},
                fp=None,
            )

        monkeypatch.setattr(egress_policy.urllib.request.OpenerDirector, "open", fake_urlopen)
        monkeypatch.setattr(egress_policy, "_retry_sleep", lambda s: sleeps.append(s))
        req = egress_policy.urllib.request.Request("https://openrouter.ai/api/v1/x")

        with pytest.raises(urllib.error.HTTPError):
            egress_policy.safe_urlopen(req, timeout=30)
        # 최초 시도 1회 + 재시도 2회 = 총 3회 시도, 2회 슬립
        assert sleeps == [7.0, 7.0]

    def test_non_retryable_status_raises_immediately(self, monkeypatch):
        import urllib.error

        from antigravity_k.tools import egress_policy

        calls = {"n": 0}

        def fake_urlopen(_opener, target, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError(str(target), 404, "Not Found", hdrs=None, fp=None)

        monkeypatch.setattr(egress_policy.urllib.request.OpenerDirector, "open", fake_urlopen)
        monkeypatch.setattr(egress_policy, "_retry_sleep", lambda s: None)
        req = egress_policy.urllib.request.Request("https://openrouter.ai/api/v1/x")

        with pytest.raises(urllib.error.HTTPError):
            egress_policy.safe_urlopen(req, timeout=30)
        assert calls["n"] == 1  # 재시도 없음
