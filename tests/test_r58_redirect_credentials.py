"""Credential boundaries through the real urllib redirect handler chain.

Only the final HTTP transport and DNS verdict are synthetic. No socket, proxy
lookup, real key, or model is used. Production safe_urlopen callers inspected
here supply Authorization; no custom API-key header is assumed. Other credential
headers below exercise the common Request boundary with synthetic values only.
"""

from __future__ import annotations

import io
import urllib.request
from email.message import Message
from urllib.response import addinfourl

import pytest

from antigravity_k.tools import egress_policy

START = "https://r58-credential.example/start"
OTHER_HOST = "https://r58-other-credential.example/continued"
BODY = b"R58-SYNTHETIC-REDIRECT-RESPONSE"
CREDENTIALS = {
    "Authorization": "Bearer r58-synthetic-only",
    "Proxy-Authorization": "Basic r58-synthetic-only",
    "Cookie": "r58_session=synthetic-only",
    "Cookie2": "r58_legacy=synthetic-only",
}
ORDINARY_HEADERS = {"Accept": "application/json", "X-R58-Trace": "synthetic-trace"}


class MemoryReply(addinfourl):
    msg = "R58 synthetic credential response"


@pytest.mark.parametrize(
    ("destination", "with_credentials", "preserve_credentials", "method"),
    [
        ("https://r58-credential.example:443/continued", True, True, "GET"),
        (OTHER_HOST, True, False, "POST"),
        ("https://r58-credential.example:444/continued", True, False, "GET"),
        ("http://r58-credential.example/continued", True, False, "GET"),
        (OTHER_HOST, False, False, "GET"),
    ],
    ids=["same-origin-default-port", "cross-host-post", "cross-port", "cross-scheme", "unauthenticated-cross-host"],
)
def test_redirect_credentials_follow_origin_without_mutating_caller_request(
    monkeypatch: pytest.MonkeyPatch, destination: str, with_credentials: bool, preserve_credentials: bool, method: str,
) -> None:
    wire: list[dict[str, object]] = []
    dns_checks: list[str] = []
    dns_destination = destination.replace(":443/", "/")
    monkeypatch.delenv("AGK_EGRESS_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})

    def fake_dns_verdict(url: str) -> tuple[str, tuple[str, ...]]:
        assert url in (START, dns_destination)
        dns_checks.append(url)
        # This is a synthetic verdict marker, not native DNS/public-IP proof.
        return url, ("192.0.2.62",)

    def memory_transport(
        _handler: object, _connection_class: object, request: urllib.request.Request, **_options: object,
    ) -> MemoryReply:
        assert request.full_url in (START, destination)
        wire.append(
            {
                "url": request.full_url,
                "headers": {key.casefold(): value for key, value in request.header_items()},
                "method": request.get_method(),
                "data": request.data,
                "timeout": request.timeout,
            }
        )
        headers = Message()
        status = 200
        if request.full_url == START:
            status = 302
            headers["Location"] = destination
        return MemoryReply(io.BytesIO(BODY), headers, request.full_url, status)

    monkeypatch.setattr(egress_policy, "resolve_public_http_url_sync", fake_dns_verdict)
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", memory_transport)
    headers = {**ORDINARY_HEADERS, **(CREDENTIALS if with_credentials else {})}
    payload = b"r58=synthetic-payload" if method == "POST" else None
    original = urllib.request.Request(START, data=payload, headers=headers, method=method)
    original_headers = dict(original.headers)

    with egress_policy.safe_urlopen(original, allow_local=False, timeout=3, max_retries=0) as response:
        assert response.read() == BODY

    assert [entry["url"] for entry in wire] == [START, destination]
    assert dns_checks == [START, dns_destination]
    assert original.full_url == START
    assert original.headers == original_headers
    assert original.data == payload and original.get_method() == method
    initial_headers = wire[0]["headers"]
    final_headers = wire[1]["headers"]
    assert isinstance(initial_headers, dict) and isinstance(final_headers, dict)
    for name, value in CREDENTIALS.items():
        assert initial_headers.get(name.casefold()) == (value if with_credentials else None)
        assert final_headers.get(name.casefold()) == (value if preserve_credentials else None)
    for name, value in ORDINARY_HEADERS.items():
        assert initial_headers[name.casefold()] == value
        assert final_headers[name.casefold()] == value
    assert [entry["timeout"] for entry in wire] == [3, 3]
    assert wire[1]["method"] == "GET" and wire[1]["data"] is None
