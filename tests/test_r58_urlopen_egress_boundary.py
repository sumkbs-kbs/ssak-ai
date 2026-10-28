"""Real urllib retry/redirect flow with only the final HTTP transport replaced.

No socket is constructed. Reserved .example names and a documentation-only DNS
marker are used. The fake DNS seam supplies allow/deny verdicts; this does not
test native DNS resolution or classify the documentation address as public.
"""

from __future__ import annotations

import io
import urllib.request
from email.message import Message
from typing import Literal
from urllib.response import addinfourl

import pytest

from antigravity_k.tools import egress_policy

Scenario = Literal["retry-dns-revoked", "redirect-loopback", "retry-public", "redirect-public"]
START = "http://r58-origin.example/start"
PUBLIC_END = "http://r58-destination.example/final"
LOOPBACK_END = "http://127.0.0.1/r58-synthetic-only"
DNS_MARKER = "192.0.2.41"
BODY = b"R58-SYNTHETIC-MEMORY-RESPONSE"


class MemoryReply(addinfourl):
    msg = "R58 synthetic response"


@pytest.mark.parametrize("scenario", ["retry-dns-revoked", "redirect-loopback", "retry-public", "redirect-public"])
def test_safe_urlopen_rechecks_each_retry_and_redirect_before_transport(
    monkeypatch: pytest.MonkeyPatch, scenario: Scenario,
) -> None:
    transport_urls: list[str] = []
    dns_verdicts: list[tuple[str, bool]] = []
    sleeps: list[float] = []
    state = {"dns_revoked": False}
    monkeypatch.delenv("AGK_EGRESS_LOCAL_ONLY", raising=False)
    # Real urlopen/build_opener/error/redirect processing remain in place. The
    # next opener is test-local, and no environment/system proxy is consulted.
    monkeypatch.setattr(urllib.request, "_opener", None)
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})

    def fake_dns_verdict(url: str) -> tuple[str, tuple[str, ...]] | None:
        assert url in (START, PUBLIC_END)
        allowed = not state["dns_revoked"]
        dns_verdicts.append((url, allowed))
        return (url, (DNS_MARKER,)) if allowed else None

    def memory_transport(
        _handler: object, _connection_class: object, request: urllib.request.Request, **_connection_options: object,
    ) -> MemoryReply:
        url = request.full_url
        assert url in (START, PUBLIC_END, LOOPBACK_END)
        transport_urls.append(url)
        headers = Message()
        status = 200
        if scenario.startswith("retry-") and len(transport_urls) == 1:
            assert url == START
            status = 503
            headers["Retry-After"] = "0"
            if scenario == "retry-dns-revoked":
                state["dns_revoked"] = True
        elif scenario.startswith("redirect-") and url == START:
            status = 302
            headers["Location"] = LOOPBACK_END if scenario == "redirect-loopback" else PUBLIC_END
        return MemoryReply(io.BytesIO(BODY), headers, url, status)

    monkeypatch.setattr(egress_policy, "resolve_public_http_url_sync", fake_dns_verdict)
    monkeypatch.setattr(egress_policy, "_retry_sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", memory_transport)
    outcome = "completed"
    try:
        with egress_policy.safe_urlopen(START, allow_local=False, timeout=1, max_retries=1) as response:
            assert response.read() == BODY
    except egress_policy.EgressPolicyError:
        outcome = "blocked"

    if scenario in ("retry-dns-revoked", "redirect-loopback"):
        assert {"outcome": outcome, "transport_urls": transport_urls} == {"outcome": "blocked", "transport_urls": [START]}
        if scenario == "retry-dns-revoked":
            assert (START, False) in dns_verdicts
    else:
        expected_urls = [START, START] if scenario == "retry-public" else [START, PUBLIC_END]
        assert {"outcome": outcome, "transport_urls": transport_urls} == {"outcome": "completed", "transport_urls": expected_urls}
    assert dns_verdicts and dns_verdicts[0] == (START, True)
    assert sleeps == ([0.0] if scenario.startswith("retry-") else [])
