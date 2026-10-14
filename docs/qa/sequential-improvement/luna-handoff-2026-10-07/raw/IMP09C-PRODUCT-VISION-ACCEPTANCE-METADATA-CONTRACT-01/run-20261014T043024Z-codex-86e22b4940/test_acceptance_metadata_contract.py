from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
from pathlib import Path
from typing import Final, Never

import pytest

h = importlib.import_module("run_harness")
RUN: Final = Path(__file__).resolve().parent
ROOT: Final = h.resolve_repository_root()
PARENT: Final = Path(json.loads((RUN / "baseline.json").read_bytes())["parent_root"])


def test_supervisor_freezes_exact_schema_before_reservation_and_mock_wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked: list[str] = []

    def deny_socket(*args: str, **kwargs: str) -> Never:
        blocked.append("socket")
        raise AssertionError("acceptance writer fixture attempted a socket")

    for method in ("connect", "connect_ex", "bind", "listen"):
        monkeypatch.setattr(socket.socket, method, deny_socket)
    monkeypatch.setattr(socket, "create_connection", deny_socket)
    run = tmp_path / "owned-writer-fixture"
    run.mkdir()
    for name in (
        *h.IMPLEMENTATION_SOURCE_NAMES,
        "endpoint-contract.json",
        "runtime-bridge-contract.json",
        "budgets.json",
        "profile-contract.json",
        "response-schema.json",
        "planned-acceptance.json",
        "test_structured_product_payload_contract.py",
    ):
        source = RUN / name if name == "run_harness.py" else PARENT / name
        shutil.copyfile(source, run / name)
    shutil.copytree(PARENT / "fixture", run / "fixture")
    h.prepare_owned_request(ROOT, run, run / "offline-state")
    binding_before = (run / "execution-binding.json").read_bytes()
    parent_acceptance_before = (PARENT / "acceptance.json").read_bytes()
    adapter = h.OfflineAdapter(response='{"red_circles":2,"blue_squares":1}')
    metadata = dict(adapter.metadata({}))
    metadata["source"] = "OFFLINE_MOCK"
    monkeypatch.setattr(adapter, "metadata", lambda context: metadata)
    monkeypatch.setattr(
        adapter,
        "bootstrap",
        lambda context: {
            "worker_owned": True,
            "auth_state_owned": True,
            "source": "OFFLINE_MOCK",
        },
    )
    monkeypatch.setattr(
        adapter,
        "readiness",
        lambda context: {
            "unauthenticated_status": 401,
            "bearer_status": 200,
            "ready": True,
            "source": "OFFLINE_MOCK",
        },
    )
    journal = h.OneShotJournal(run / "fixture-journal.jsonl")
    reserve_original, wire_original = journal.reserve, journal.enter_wire
    ordering: list[str] = []
    frozen_reads: list[bytes] = []

    def reserve(slot: str, logical_id: str, request_bytes: bytes) -> bool:
        frozen_reads.append((run / "acceptance.json").read_bytes())
        ordering.append("reserve:" + slot)
        return reserve_original(slot, logical_id, request_bytes)

    def wire(slot: str, logical_id: str, request_bytes: bytes) -> bool:
        frozen_reads.append((run / "acceptance.json").read_bytes())
        ordering.append("mock_wire:" + slot)
        return wire_original(slot, logical_id, request_bytes)

    monkeypatch.setattr(journal, "reserve", reserve)
    monkeypatch.setattr(journal, "enter_wire", wire)
    state = h.SupervisorState()
    result = h.supervise_once(
        run=run,
        root=ROOT,
        adapter=adapter,
        journal=journal,
        state=state,
        authorization={"status": "OFFLINE_ADAPTER_FIXTURE_ONLY", "scope": h.TASK_ID},
    )
    saved = (run / "acceptance.json").read_bytes()
    actual = json.loads(saved)
    expected = {
        "type": "object",
        "properties": {"red_circles": {"type": "integer"}, "blue_squares": {"type": "integer"}},
        "required": ["red_circles", "blue_squares"],
        "additionalProperties": False,
    }
    capture = Path(os.environ["ACCEPTANCE_CAPTURE_ROOT"])
    capture.mkdir(parents=True)
    (capture / "acceptance.json").write_bytes(saved)
    (capture / "observations.json").write_text(
        json.dumps(
            {
                "ordering": ordering,
                "all_pre_wire_reads_match_saved": all(raw == saved for raw in frozen_reads),
                "mock_product_calls": adapter.product_calls,
                "mock_provider_calls": adapter.provider_calls,
                "socket_attempts": len(blocked),
                "supervisor_verdict": result["verdict"],
                "state_phases": [event["phase"] for event in state.events],
                "fixture_only": True,
            },
            indent=2,
        )
    )
    assert actual["format"] == expected
    assert json.loads((run / "request.json").read_bytes())["response_format"]["json_schema"]["schema"] == expected
    assert json.loads((run / "profile-contract.json").read_bytes())["expected_payload"]["format"] == expected
    assert json.loads((run / "planned-acceptance.json").read_bytes())["expected_schema"] == expected
    assert json.loads((run / "response-schema.json").read_bytes()) == expected
    assert len(frozen_reads) == 4 and all(raw == saved for raw in frozen_reads)
    phases = [event["phase"] for event in state.events]
    assert phases.index("frozen") < phases.index("reserved") < phases.index("dispatched")
    assert adapter.product_calls == adapter.provider_calls == 1
    assert not blocked
    assert (run / "execution-binding.json").read_bytes() == binding_before
    with pytest.raises(FileExistsError):
        h.write_once(run / "acceptance.json", b"changed")
    assert (run / "acceptance.json").read_bytes() == saved
    assert (PARENT / "acceptance.json").read_bytes() == parent_acceptance_before
