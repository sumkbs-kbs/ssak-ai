"""Search diagnostic probes respect process-local-only policy before any sender.

Only a fake context-manager connection can run; its destination is replaced by a
reserved documentation address. No real socket or MCP child is constructed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from antigravity_k.tools import ssak_search_provider as provider

TARGET = ("192.0.2.82", 443)


@pytest.mark.parametrize(
    ("local_only", "offline", "expected", "expected_calls"),
    [("1", None, False, 0), ("0", "1", False, 0), ("0", None, True, 1)],
    ids=["local-only-before-probe", "existing-offline-before-probe", "explicit-probe-allowed"],
)
def test_search_network_probe_obeys_local_only_before_fake_connection(
    monkeypatch: pytest.MonkeyPatch, local_only: str, offline: str | None, expected: bool, expected_calls: int,
) -> None:
    calls: list[tuple[tuple[str, int], float]] = []
    monkeypatch.setenv("AGK_EGRESS_LOCAL_ONLY", local_only)
    if offline is None:
        monkeypatch.delenv(provider.OFFLINE_ENV, raising=False)
    else:
        monkeypatch.setenv(provider.OFFLINE_ENV, offline)
    monkeypatch.setattr(provider, "_network_probe_cache", None)
    monkeypatch.setattr(provider, "_NETWORK_PROBE_TARGET", TARGET)

    @contextmanager
    def fake_connection(target: tuple[str, int], *, timeout: float) -> Iterator[None]:
        calls.append((target, timeout))
        yield None

    monkeypatch.setattr(provider.socket, "create_connection", fake_connection)
    actual = provider.network_available(force_probe=True)
    assert {"available": actual, "connection_calls": len(calls)} == {"available": expected, "connection_calls": expected_calls}
    if calls:
        assert calls == [(TARGET, provider._NETWORK_PROBE_TIMEOUT_SECONDS)]
