"""r28: cross-restart test call ledger, ticket redaction in logs, RAG-segment audit split (fake values)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from antigravity_k.api.log_redaction import SecretQueryRedactionFilter, redact
from antigravity_k.engine import call_ledger
from antigravity_k.engine import llm_input_audit as audit


def test_ledger_persists_across_processes_and_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", "3")
    (tmp_path / "llm.count").write_text("2")  # e.g. two sends by a previous server start
    assert call_ledger.reserve("llm") == 3
    with pytest.raises(call_ledger.CallLedgerError):
        _ = call_ledger.reserve("llm")
    assert (tmp_path / "llm.count").read_text() == "3"


def test_ledger_fails_closed_on_missing_or_corrupt_counter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("AGK_TEST_EMBED_TOTAL_LIMIT", "8")
    with pytest.raises(call_ledger.CallLedgerError):
        _ = call_ledger.reserve("embed")
    (tmp_path / "embed.count").write_text("garbage")
    with pytest.raises(call_ledger.CallLedgerError):
        _ = call_ledger.reserve("embed")


def test_ledger_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(call_ledger.LEDGER_DIR_ENV, raising=False)
    assert call_ledger.reserve("llm") is None


def test_ticket_and_token_redacted_with_fake_values() -> None:
    fake = '127.0.0.1:1 - "WebSocket /v1/ws/events?ticket=FAKE.TICKET.VALUE&x=1" [accepted] token=FAKE-TOKEN'
    out = redact(fake)
    assert "FAKE.TICKET.VALUE" not in out and "FAKE-TOKEN" not in out and "ticket=[REDACTED]&x=1" in out
    rec = logging.LogRecord(
        "uvicorn.error", logging.INFO, "f", 1, '%s - "WebSocket %s"', ("c", "/ws?ticket=FAKE1"), None
    )
    assert SecretQueryRedactionFilter().filter(rec) and "FAKE1" not in rec.getMessage()


def test_wire_audit_splits_rag_segment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "a.jsonl"
    monkeypatch.setenv(audit.AUDIT_PATH_ENV, str(out))
    monkeypatch.setenv(audit.EXPECT_ENV, "FACT-A")
    monkeypatch.setenv(audit.FORBID_ENV, "FACT-B")
    msgs = [{"content": "system"}, {"content": "question without fact <relevant_code>doc FACT-A</relevant_code> tail"}]
    audit.audit_wire_messages(model="qwen3.8", provider="ollama", purpose="stream", messages=msgs)
    rec = json.loads(out.read_text())
    assert rec["rag_segment"] == {"expect_fact_contained": True, "forbid_fact_contained": False}
    assert rec["non_rag_segment"] == {"expect_fact_contained": False, "forbid_fact_contained": False}
    assert "doc FACT-A" not in out.read_text()
