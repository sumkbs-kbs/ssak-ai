"""HTTP contract for extracted financial numbers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antigravity_k.tools.web_search import WebSearchTool


def test_search_extract_repeats_canonical_tiny_fractional_scaled_value(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fixture_execute(_tool: WebSearchTool, *, query: str) -> str:
        assert query == "정밀 규모"
        return "1조 0.0000000000000000000000000001만"

    monkeypatch.setattr(WebSearchTool, "execute", fixture_execute)

    response = client.post("/api/search/extract", json={"query": "정밀 규모"})

    assert response.status_code == 200
    item = response.json()["extracted"]["numeric_data"][0]
    expected = "1000000000000.000000000000000000000001"
    assert item["value"] == expected
    assert item["normalized_value"] == expected


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create the real API only after isolating user-home state."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from antigravity_k.api.server import app
    from antigravity_k.config import config

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update({"X-Access-Pin": config.security.access_pin})
        yield test_client


def test_search_extract_returns_financial_numbers_from_search_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the actual route and an HTTP-level search-provider seam.
    def fake_execute(_tool: WebSearchTool, *, query: str) -> str:
        assert query == "분기 매출"
        return "분기 매출은 1조 2,345억 원이며, 마진은 3.5%p다."

    monkeypatch.setattr("antigravity_k.tools.web_search.WebSearchTool.execute", fake_execute)

    # When: a client calls the public extraction endpoint.
    response = client.post("/api/search/extract", json={"query": "분기 매출"})

    # Then: numeric values, units, currency, and source linkage are serialized.
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["extracted"]["numeric_data"] == [
        {
            "label": "1조 2,345억 원",
            "value": 1234500000000.0,
            "unit": "KRW",
            "currency": "KRW",
            "normalized_value": "1234500000000",
            "display_unit": "조 억 원",
            "source_index": 0,
            "raw_text": "1조 2,345억 원",
        },
        {
            "label": "3.5%p",
            "value": 3.5,
            "unit": "percentage_point",
            "currency": "",
            "normalized_value": "3.5",
            "display_unit": "%p",
            "source_index": 0,
            "raw_text": "3.5%p",
        },
    ]
    assert "📊 기타 데이터:" in body["extraction_log"]


def test_search_extract_rejects_empty_query_before_calling_search_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a search provider that would make any unexpected call visible.
    def fail_execute(_tool: WebSearchTool, *, query: str) -> str:
        raise AssertionError(f"unexpected search query: {query}")

    monkeypatch.setattr("antigravity_k.tools.web_search.WebSearchTool.execute", fail_execute)

    # When: a client omits the required query text.
    response = client.post("/api/search/extract", json={"query": "   "})

    # Then: the API returns its error contract without executing the provider.
    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "query is required"}


def test_search_extract_serializes_unsafe_integer_as_exact_text(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute(_tool: WebSearchTool, *, query: str) -> str:
        assert query == "자산"
        return "자산은 9,007,199,254,740,993원이다."

    monkeypatch.setattr("antigravity_k.tools.web_search.WebSearchTool.execute", fake_execute)

    response = client.post("/api/search/extract", json={"query": "자산"})

    assert response.status_code == 200
    numeric = response.json()["extracted"]["numeric_data"]
    assert numeric == [
        {
            "label": "9,007,199,254,740,993원",
            "value": "9007199254740993",
            "unit": "KRW",
            "currency": "KRW",
            "normalized_value": "9007199254740993",
            "display_unit": "원",
            "source_index": 0,
            "raw_text": "9,007,199,254,740,993원",
        },
    ]


def test_search_extract_serializes_long_scaled_amount_as_exact_text(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_value = "123456789012345678901234567890"
    expected = "123456789012345678901234567890000000000000"

    def fake_execute(_tool: WebSearchTool, *, query: str) -> str:
        assert query == "장기 규모"
        return f"추정 규모는 {raw_value}조원이다."

    monkeypatch.setattr("antigravity_k.tools.web_search.WebSearchTool.execute", fake_execute)

    response = client.post("/api/search/extract", json={"query": "장기 규모"})

    assert response.status_code == 200
    assert response.json()["extracted"]["numeric_data"] == [
        {
            "label": f"{raw_value}조원",
            "value": expected,
            "unit": "KRW",
            "currency": "KRW",
            "normalized_value": expected,
            "display_unit": "조 원",
            "source_index": 0,
            "raw_text": f"{raw_value}조원",
        },
    ]
