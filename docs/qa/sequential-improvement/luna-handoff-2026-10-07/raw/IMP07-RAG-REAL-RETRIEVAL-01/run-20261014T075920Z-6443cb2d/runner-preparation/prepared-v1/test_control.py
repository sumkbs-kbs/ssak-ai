from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import httpx
import pytest

from control import (
    BASE,
    MODEL,
    Budget,
    WireTransport,
    score,
    validate_oracles,
    verify_manifest,
)

FIXTURE = Path(__file__).resolve().parent.parent


def embed_request(text: str = "search_query: a question") -> httpx.Request:
    return httpx.Request(
        "POST",
        BASE + "/api/embed",
        json={"model": MODEL, "input": [text], "truncate": False},
    )


def test_frozen_oracles_are_complete_before_execution():
    queries, oracles = validate_oracles(FIXTURE)
    assert {row["id"] for row in queries} == set(oracles)
    assert len(verify_manifest(FIXTURE, "fixture-manifest.sha256")) == 38


@pytest.mark.parametrize(
    ("paths", "expected_rank", "expected_rr", "expected_ndcg"),
    [
        (["target", "other"], 1, 1, 1),
        (["other", "target", "target"], 2, 0.5, 1 / math.log2(3)),
        (["a", "b", "c", "d", "target"], 5, 0.2, 1 / math.log2(6)),
        (["a", "b", "c", "d", "e", "target"], None, 0, 0),
        ([], None, 0, 0),
    ],
)
def test_ranking_uses_first_raw_rank_with_top_five_cutoff(
    paths, expected_rank, expected_rr, expected_ndcg
):
    result = score(paths, "target")
    assert result == {
        "rank": expected_rank,
        "recall_at_5": int(expected_rank is not None),
        "mrr_at_5": expected_rr,
        "ndcg_at_5": expected_ndcg,
    }


def test_manifest_detects_source_preimage_change(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("original")
    (tmp_path / "manifest").write_text(
        hashlib.sha256(source.read_bytes()).hexdigest() + "  source.md\n"
    )
    source.write_text("changed")
    with pytest.raises(ValueError, match="preimage changed"):
        verify_manifest(tmp_path, "manifest")


def test_query_phase_cannot_exceed_twenty_calls():
    budget = Budget()
    budget.phase = "queries-a"
    for _ in range(20):
        budget.reserve(embed_request())
    with pytest.raises(ValueError, match="Phase inference budget"):
        budget.reserve(embed_request())
    assert budget.counts == {"queries-a": 20}


def test_remaining_deadline_limits_request_and_blocks_expired_call():
    now = [100.0]
    budget = Budget(clock=lambda: now[0])
    budget.phase = "queries-a"
    now[0] = 279.5
    assert budget.reserve(embed_request()) == 0.5
    now[0] = 280
    with pytest.raises(TimeoutError):
        budget.reserve(embed_request())
    assert sum(budget.counts.values()) == 1


@pytest.mark.parametrize(
    "text",
    [
        "plain question",
        "search_query: search_query: repeated",
        "search_document: wrong kind",
    ],
)
def test_bad_prefix_is_rejected_before_budget_consumption(text):
    budget = Budget()
    budget.phase = "queries-a"
    with pytest.raises(ValueError, match="prefix"):
        budget.reserve(embed_request(text))
    assert not budget.counts


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", BASE + "/api/pull"),
        ("POST", BASE + "/api/chat"),
        ("GET", "http://example.test/api/tags"),
        ("GET", BASE + "/api/tags?x=1"),
    ],
)
def test_unauthorized_http_is_rejected_before_transport(method, url):
    budget = Budget()
    with pytest.raises(ValueError):
        budget.reserve(httpx.Request(method, url))
    assert not budget.counts and budget.metadata == 0


def test_metadata_counts_are_separate_and_bounded():
    budget = Budget()
    for endpoint in ("/api/tags", "/api/tags", "/api/ps"):
        budget.reserve(httpx.Request("GET", BASE + endpoint))
    with pytest.raises(ValueError, match="Metadata budget"):
        budget.reserve(httpx.Request("GET", BASE + "/api/ps"))
    assert budget.metadata == 3 and not budget.counts


def test_each_provider_client_gets_fresh_transport_and_preserves_response_headers(
    tmp_path,
):
    created = []

    class RecordingTransport(httpx.MockTransport):
        def __init__(self):
            super().__init__(
                lambda request: httpx.Response(
                    200,
                    json={"embeddings": [[0.1, 0.2, 0.3]], "model": MODEL},
                    headers={"x-fixture": "preserved"},
                )
            )
            self.closed = False
            created.append(self)

        def handle_request(self, request):
            assert not self.closed
            return super().handle_request(request)

        def close(self):
            self.closed = True
            super().close()

    budget = Budget()
    budget.phase = "queries-a"
    wire = WireTransport(tmp_path, budget, RecordingTransport)
    responses = []
    for _ in range(2):
        with httpx.Client(transport=wire) as client:
            responses.append(client.send(embed_request()))
    assert len(created) == 2 and all(item.closed for item in created)
    assert all(
        response.headers["x-fixture"] == "preserved"
        and response.json()["model"] == MODEL
        for response in responses
    )
    assert wire.client_close_calls == 2 and budget.counts == {"queries-a": 2}
    for number in ("001", "002"):
        receipt = json.loads((tmp_path / f"{number}.receipt.json").read_text())
        assert receipt["status"] == 200 and receipt["input_sha256"]
        assert json.loads((tmp_path / f"{number}.response.bin").read_bytes())[
            "embeddings"
        ] == [[0.1, 0.2, 0.3]]


def test_failed_wire_attempt_is_recorded_once_without_retry(tmp_path):
    attempts = []

    def fail(request):
        attempts.append(request)
        raise httpx.ConnectError("offline fixture failure", request=request)

    budget = Budget()
    budget.phase = "queries-a"
    wire = WireTransport(tmp_path, budget, lambda: httpx.MockTransport(fail))
    with pytest.raises(httpx.ConnectError):
        wire.handle_request(embed_request())
    receipt = json.loads((tmp_path / "001.receipt.json").read_text())
    assert len(attempts) == 1 and sum(budget.counts.values()) == 1
    assert receipt["status"] is None and "ConnectError" in receipt["error"]


@pytest.mark.parametrize(
    ("operation", "address"),
    [
        ("connect", ("203.0.113.10", 443)),
        ("connect", ("127.0.0.1", 80)),
        ("bind", ("127.0.0.1", 0)),
    ],
)
def test_socket_guard_blocks_unapproved_physical_operation_without_connecting(
    tmp_path, monkeypatch, operation, address
):
    import socket
    from control import install_socket_guard

    monkeypatch.setattr(socket, "socket", socket.socket)
    counts = install_socket_guard(tmp_path / "network.jsonl")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(PermissionError, match="denied"):
            getattr(connection, operation)(address)
    assert counts == {"denied": 1}
    assert json.loads((tmp_path / "network.jsonl").read_text())["allowed"] is False


@pytest.mark.parametrize(
    "replacement",
    [
        {"authorization": "PENDING_ROOT_GO"},
        {"source_root": 12},
        {"sources": {"/tmp/not-read": "invalid-sha"}},
    ],
)
def test_source_freeze_rejects_unapproved_or_malformed_governing_fields(replacement):
    from pydantic import ValidationError
    from control import SourceFreeze

    payload = {
        "authorization": "ROOT_GO",
        "retrieval_mode": "semantic",
        "source_root": "/unused",
        "sources": {},
    }
    payload.update(replacement)
    with pytest.raises(ValidationError):
        SourceFreeze.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "replacement", [{"model": "wrong-model"}, {"truncate": True}, {"input": [123]}]
)
def test_embedding_wire_parser_rejects_wrong_model_truncation_or_nontext(replacement):
    budget = Budget()
    budget.phase = "queries-a"
    payload = {"model": MODEL, "input": ["search_query: question"], "truncate": False}
    payload.update(replacement)
    with pytest.raises(ValueError):
        budget.reserve(httpx.Request("POST", BASE + "/api/embed", json=payload))
    assert not budget.counts
