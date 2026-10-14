from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Literal, Never, assert_never, override

import httpx
import pytest
from pydantic import RootModel

from .control import (
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


def test_frozen_oracles_are_complete_before_execution() -> None:
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
    paths: list[str], expected_rank: int | None, expected_rr: float, expected_ndcg: float
) -> None:
    result = score(paths, "target")
    assert result == {
        "rank": expected_rank,
        "recall_at_5": int(expected_rank is not None),
        "mrr_at_5": expected_rr,
        "ndcg_at_5": expected_ndcg,
    }


def test_manifest_detects_source_preimage_change(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    _ = source.write_text("original")
    _ = (tmp_path / "manifest").write_text(hashlib.sha256(source.read_bytes()).hexdigest() + "  source.md\n")
    _ = source.write_text("changed")
    with pytest.raises(ValueError, match="preimage changed"):
        _ = verify_manifest(tmp_path, "manifest")


def test_query_phase_cannot_exceed_twenty_calls() -> None:
    budget = Budget()
    budget.phase = "queries-a"
    for _ in range(20):
        _ = budget.reserve(embed_request())
    with pytest.raises(ValueError, match="Phase inference budget"):
        _ = budget.reserve(embed_request())
    assert budget.counts == {"queries-a": 20}


def test_remaining_deadline_limits_request_and_blocks_expired_call() -> None:
    now = [100.0]
    budget = Budget(clock=lambda: now[0])
    budget.phase = "queries-a"
    now[0] = 279.5
    assert budget.reserve(embed_request()) == 0.5
    now[0] = 280
    with pytest.raises(TimeoutError):
        _ = budget.reserve(embed_request())
    assert sum(budget.counts.values()) == 1


@pytest.mark.parametrize(
    "text",
    [
        "plain question",
        "search_query: search_query: repeated",
        "search_document: wrong kind",
    ],
)
def test_bad_prefix_is_rejected_before_budget_consumption(text: str) -> None:
    budget = Budget()
    budget.phase = "queries-a"
    with pytest.raises(ValueError, match="prefix"):
        _ = budget.reserve(embed_request(text))
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
def test_unauthorized_http_is_rejected_before_transport(method: str, url: str) -> None:
    budget = Budget()
    with pytest.raises(ValueError):
        _ = budget.reserve(httpx.Request(method, url))
    assert not budget.counts and budget.metadata == 0


def test_metadata_counts_are_separate_and_bounded() -> None:
    budget = Budget()
    for endpoint in ("/api/tags", "/api/tags", "/api/ps"):
        _ = budget.reserve(httpx.Request("GET", BASE + endpoint))
    with pytest.raises(ValueError, match="Metadata budget"):
        _ = budget.reserve(httpx.Request("GET", BASE + "/api/ps"))
    assert budget.metadata == 3 and not budget.counts


def test_each_provider_client_gets_fresh_transport_and_preserves_response_headers(
    tmp_path: Path,
) -> None:
    created: list[RecordingTransport] = []

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"embeddings": [[0.1, 0.2, 0.3]], "model": MODEL}, headers={"x-fixture": "preserved"}
        )

    class RecordingTransport(httpx.MockTransport):
        def __init__(self):
            super().__init__(respond)
            self.closed: bool = False
            created.append(self)

        @override
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            assert not self.closed
            return super().handle_request(request)

        @override
        def close(self) -> None:
            self.closed = True
            super().close()

    budget = Budget()
    budget.phase = "queries-a"
    wire = WireTransport(tmp_path, budget, RecordingTransport)
    responses: list[httpx.Response] = []
    for _ in range(2):
        with httpx.Client(transport=wire) as client:
            responses.append(client.send(embed_request()))
    assert len(created) == 2 and all(item.closed for item in created)
    assert all(
        response.headers["x-fixture"] == "preserved"
        and RootModel[dict[str, object]].model_validate_json(response.content).root["model"] == MODEL
        for response in responses
    )
    assert wire.client_close_calls == 2 and budget.counts == {"queries-a": 2}
    for number in ("001", "002"):
        receipt = (
            RootModel[dict[str, object]].model_validate_json((tmp_path / f"{number}.receipt.json").read_bytes()).root
        )
        assert receipt["status"] == 200 and receipt["input_sha256"]
        assert RootModel[dict[str, object]].model_validate_json(
            (tmp_path / f"{number}.response.bin").read_bytes()
        ).root["embeddings"] == [[0.1, 0.2, 0.3]]


def test_failed_wire_attempt_is_recorded_once_without_retry(tmp_path: Path) -> None:
    attempts: list[httpx.Request] = []

    def fail(request: httpx.Request) -> Never:
        attempts.append(request)
        raise httpx.ConnectError("offline fixture failure", request=request)

    budget = Budget()
    budget.phase = "queries-a"
    wire = WireTransport(tmp_path, budget, lambda: httpx.MockTransport(fail))
    with pytest.raises(httpx.ConnectError):
        _ = wire.handle_request(embed_request())
    receipt = RootModel[dict[str, object]].model_validate_json((tmp_path / "001.receipt.json").read_bytes()).root
    assert len(attempts) == 1 and sum(budget.counts.values()) == 1
    error = receipt["error"]
    assert receipt["status"] is None and isinstance(error, str) and "ConnectError" in error


@pytest.mark.parametrize(
    ("operation", "address"),
    [
        ("connect", ("203.0.113.10", 443)),
        ("connect", ("127.0.0.1", 80)),
        ("bind", ("127.0.0.1", 0)),
    ],
)
def test_socket_guard_blocks_unapproved_physical_operation_without_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: Literal["connect", "bind"], address: tuple[str, int]
) -> None:
    import socket

    from .control import install_socket_guard

    monkeypatch.setattr(socket, "socket", socket.socket)
    counts = install_socket_guard(tmp_path / "network.jsonl")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(PermissionError, match="denied"):
            match operation:
                case "connect":
                    connection.connect(address)
                case "bind":
                    connection.bind(address)
                case unexpected:
                    assert_never(unexpected)
    assert counts == {"denied": 1}
    assert (
        RootModel[dict[str, object]].model_validate_json((tmp_path / "network.jsonl").read_bytes()).root["allowed"]
        is False
    )


@pytest.mark.parametrize(
    "replacement",
    [
        {"authorization": "PENDING_ROOT_GO"},
        {"source_root": 12},
        {"sources": {"/tmp/not-read": "invalid-sha"}},
    ],
)
def test_source_freeze_rejects_unapproved_or_malformed_governing_fields(replacement: dict[str, object]) -> None:
    from pydantic import ValidationError

    from .control import SourceFreeze

    payload: dict[str, object] = {
        "authorization": "ROOT_GO",
        "retrieval_mode": "semantic",
        "source_root": "/unused",
        "sources": {},
    }
    payload.update(replacement)
    with pytest.raises(ValidationError):
        _ = SourceFreeze.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("replacement", [{"model": "wrong-model"}, {"truncate": True}, {"input": [123]}])
def test_embedding_wire_parser_rejects_wrong_model_truncation_or_nontext(replacement: dict[str, object]) -> None:
    budget = Budget()
    budget.phase = "queries-a"
    payload: dict[str, object] = {"model": MODEL, "input": ["search_query: question"], "truncate": False}
    payload.update(replacement)
    with pytest.raises(ValueError):
        _ = budget.reserve(httpx.Request("POST", BASE + "/api/embed", json=payload))
    assert not budget.counts


def test_progressing_response_hits_whole_rpc_deadline_and_preserves_partial_bytes(tmp_path: Path) -> None:
    import time
    from collections.abc import Iterator

    from .control import RequestDeadlineExceeded

    attempts: list[httpx.Request] = []

    class SlowProgress(httpx.SyncByteStream):
        @override
        def __iter__(self) -> Iterator[bytes]:
            for _ in range(100):
                time.sleep(0.01)
                yield b"progress\n"

    def respond(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(
            200, headers={"content-type": "application/json", "x-progress": "yes"}, stream=SlowProgress()
        )

    budget = Budget()
    budget.phase = "queries-a"
    budget.deadline = time.monotonic() + 0.08
    wire = WireTransport(tmp_path, budget, lambda: httpx.MockTransport(respond))
    with pytest.raises(RequestDeadlineExceeded, match="whole-RPC"):
        _ = wire.handle_request(embed_request())
    partial = (tmp_path / "001.response.partial.bin").read_bytes()
    receipt = RootModel[dict[str, object]].model_validate_json((tmp_path / "001.receipt.json").read_bytes()).root
    headers = RootModel[dict[str, object]].model_validate_json((tmp_path / "001.headers.json").read_bytes()).root
    assert len(attempts) == 1 and sum(budget.counts.values()) == 1
    assert 2 <= partial.count(b"progress\n") < 100
    assert headers["status"] == 200 and receipt["received_bytes"] == len(partial)
    assert isinstance(receipt["elapsed_seconds"], float) and receipt["elapsed_seconds"] < 0.5
    assert (tmp_path / "001.start.json").is_file() and not (tmp_path / "001.response.bin").exists()
    assert "RequestDeadlineExceeded" in str(receipt["error"])


class FakeClock:
    def __init__(self) -> None:
        self.value: float = 100.0

    def __call__(self) -> float:
        return self.value


class FakeOwnedProcess:
    def __init__(self, clock: FakeClock, outcomes: list[Literal["timeout", "error", "ok"]]) -> None:
        self.pid: int = 4242
        self.clock: FakeClock = clock
        self.outcomes: list[Literal["timeout", "error", "ok"]] = outcomes
        self.wait_timeouts: list[float] = []

    def wait(self, timeout: float) -> int:
        import subprocess

        self.wait_timeouts.append(timeout)
        outcome = self.outcomes[len(self.wait_timeouts) - 1]
        self.clock.value += timeout if outcome == "timeout" else min(0.05, timeout)
        match outcome:
            case "timeout":
                raise subprocess.TimeoutExpired("owned-fake", timeout)
            case "error":
                raise OSError("injected reap failure")
            case "ok":
                return -9
            case unexpected:
                assert_never(unexpected)


def test_cleanup_inventory_failure_cannot_prevent_signals_or_reap() -> None:
    import signal

    from .supervisor import cleanup_owned

    clock = FakeClock()
    process = FakeOwnedProcess(clock, ["ok"])
    signals: list[tuple[int, int]] = []

    def inventory(_pid: int, _timeout: float) -> list[dict[str, str]]:
        raise OSError("ps unavailable")

    result = cleanup_owned(
        process,
        outer_deadline=clock() + 230,
        clock=clock,
        signal_group=lambda pid, sig: signals.append((pid, sig)),
        inventory=inventory,
    )
    assert signals == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
    assert result.reaped and result.remaining is None
    assert any("ps unavailable" in message for message in result.errors)


def test_cleanup_graceful_timeout_kills_and_reaps_with_remaining_budget() -> None:
    import signal

    from .supervisor import cleanup_owned

    clock = FakeClock()
    process = FakeOwnedProcess(clock, ["timeout", "ok"])
    signals: list[int] = []
    inventory_budgets: list[float] = []

    def inventory(_pid: int, timeout: float) -> list[dict[str, str]]:
        inventory_budgets.append(timeout)
        return []

    result = cleanup_owned(
        process,
        outer_deadline=clock() + 230,
        clock=clock,
        signal_group=lambda _pid, sig: signals.append(sig),
        inventory=inventory,
    )
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert process.wait_timeouts == [1.0, 9.0]
    assert result.reaped and result.exit_code == -9 and result.remaining == []
    assert result.graceful_wait_timed_out and not result.errors
    assert len(inventory_budgets) == 1 and 8.9 < inventory_budgets[0] < 9.0


def test_cleanup_reap_failure_is_reported_without_claiming_reaped() -> None:
    from .supervisor import cleanup_owned

    clock = FakeClock()
    process = FakeOwnedProcess(clock, ["error", "error"])
    signals: list[int] = []
    result = cleanup_owned(
        process,
        outer_deadline=clock() + 230,
        clock=clock,
        signal_group=lambda _pid, sig: signals.append(sig),
        inventory=lambda _pid, _timeout: [],
    )
    assert len(signals) == 2 and not result.reaped and result.exit_code is None
    assert len(result.errors) == 2 and all("reap failure" in message for message in result.errors)


@pytest.mark.parametrize("outer_seconds", [3.0, 230.0])
def test_cleanup_uses_one_shared_deadline_without_fresh_wait_budget(outer_seconds: float) -> None:
    from .supervisor import cleanup_owned

    clock = FakeClock()
    process = FakeOwnedProcess(clock, ["timeout", "timeout"])
    signals: list[int] = []
    inventory_calls: list[int] = []

    def inventory(pid: int, _timeout: float) -> list[dict[str, str]]:
        inventory_calls.append(pid)
        return []

    result = cleanup_owned(
        process,
        outer_deadline=clock() + outer_seconds,
        clock=clock,
        signal_group=lambda _pid, sig: signals.append(sig),
        inventory=inventory,
    )
    limit = min(10.0, outer_seconds)
    assert process.wait_timeouts == [1.0, limit - 1.0]
    assert result.elapsed_seconds == limit and not result.reaped
    assert not inventory_calls and len(signals) == 2
    assert any("Shared cleanup deadline" in message for message in result.errors)


@pytest.mark.parametrize("module", ["supervisor", "runner"])
def test_module_cli_refuses_pending_freeze_before_execution(tmp_path: Path, module: str) -> None:
    import os
    import subprocess
    import sys

    from .control import save

    freeze = tmp_path / "pending.json"
    save(
        freeze,
        {"authorization": "PENDING_ROOT_GO", "retrieval_mode": "semantic", "source_root": str(FIXTURE), "sources": {}},
    )
    before = sorted(path.name for path in FIXTURE.glob("execution-*"))
    argv = [sys.executable, "-B", "-m", "runner-preparation." + module, "--freeze", str(freeze)]
    argv += (
        ["--go", "ROOT_GO", "--python", sys.executable]
        if module == "supervisor"
        else ["--execution", str(FIXTURE / "execution-noexec-refusal")]
    )
    result = subprocess.run(
        argv,
        cwd=FIXTURE,
        env=dict(os.environ, PYTHONPATH=str(FIXTURE), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
        timeout=5,
    )
    save(
        tmp_path / "module-cli-receipt.json",
        {
            "argv": argv,
            "cwd": str(FIXTURE),
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    assert result.returncode != 0 and "ROOT_GO" in result.stderr and "ValidationError" in result.stderr
    assert "ImportError" not in result.stderr and "ModuleNotFoundError" not in result.stderr
    assert sorted(path.name for path in FIXTURE.glob("execution-*")) == before


def test_runner_argv_preserves_venv_symlink_without_resolving(tmp_path: Path) -> None:
    import sys

    from .supervisor import runner_argv

    python = tmp_path / "venv-python"
    python.symlink_to(sys.executable)
    argv = runner_argv(python, tmp_path / "execution-unused")
    assert argv[0] == str(python.absolute()) and argv[0] != str(python.resolve())
    assert argv[1:4] == ["-B", "-m", "runner-preparation.runner"]


def test_native_audit_parser_preserves_metadata_and_match_provenance() -> None:
    import numpy as np
    from pydantic import TypeAdapter

    from .runner import Match, NativeRows

    metadata = {"source": "fixture.md", "start_line": 2, "content_hash": "fixed"}
    rows = NativeRows.model_validate(
        {"ids": ["row"], "documents": ["text"], "metadatas": [metadata], "embeddings": np.array([[0.1, 0.2, 0.3]])}
    )
    matches = TypeAdapter(list[Match]).validate_python(
        [{"id": "row", "text": "text", "metadata": metadata, "distance": 0.1, "provenance": {"source_id": "fixture"}}]
    )
    assert rows.metadatas == [metadata] and rows.embeddings == [[0.1, 0.2, 0.3]]
    assert RootModel[dict[str, object]].model_validate(matches[0]).root["provenance"] == {"source_id": "fixture"}
