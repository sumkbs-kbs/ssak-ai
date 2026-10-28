"""r33: ledger reservations are linked (request/task/purpose/attempt) and unknown stays unknown.

Fake transports only; nothing leaves the process.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import antigravity_k.engine.call_ledger as call_ledger
import antigravity_k.engine.llm_call_budget as budget
from antigravity_k.engine.task_execution_context import TaskExecutionContext, bind_task_execution_context


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for kind in ("llm", "embed"):
        (tmp_path / f"{kind}.count").write_text("0", encoding="ascii")
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", "3")
    monkeypatch.setenv("AGK_TEST_EMBED_TOTAL_LIMIT", "3")
    monkeypatch.delenv(budget.BUDGET_ENV, raising=False)
    monkeypatch.setattr(budget, "_used", 0)
    monkeypatch.setattr(budget, "_blocked", 0)
    return tmp_path


def _journal(root: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (root / "llm.journal").read_text(encoding="ascii").splitlines() if line]


def test_dispatch_mark_links_request_task_and_attempt(ledger: Path) -> None:
    with bind_task_execution_context(TaskExecutionContext("task_r33_link", object())):  # type: ignore[arg-type]
        budget.charge("fake-model", "stream_generate", "synthetic input")
        n = budget.last_ledger_reservation()
    budget.settle(n, "succeeded")
    marks = _journal(ledger)
    dispatched = next(m for m in marks if m["state"] == "dispatched")
    assert dispatched["n"] == n == 1
    assert dispatched["task_id"] == "task_r33_link"
    assert dispatched["purpose"] == "stream_generate" and dispatched["attempt"] == 1
    assert isinstance(dispatched["request_id"], str) and len(dispatched["request_id"]) == 12
    assert all("ts" in m for m in marks)
    assert "synthetic input" not in (ledger / "llm.journal").read_text(encoding="ascii")


def test_post_send_loss_is_unknown_counted_and_not_resent(ledger: Path) -> None:
    budget.charge("fake-model", "stream_generate", "x")  # dispatched, then the process "dies"
    summary = call_ledger.summary("llm", str(ledger))
    assert summary["unknown"] == 1 and summary["succeeded"] == 0
    assert summary["possibly_sent_upper_bound"] == 1 and summary["reserved"] == 1
    # restart: the counter is not decremented and the unknown call is not replayed
    budget.reset_for_tests()
    budget.charge("fake-model", "stream_generate", "y")
    n2 = budget.last_ledger_reservation()
    budget.settle(n2, "succeeded")
    after = call_ledger.summary("llm", str(ledger))
    assert n2 == 2 and after["reserved"] == 2 and after["unknown"] == 1 and after["succeeded"] == 1


def test_abort_mid_stream_stays_possibly_sent(ledger: Path) -> None:
    budget.charge("fake-model", "stream_generate", "x")
    budget.settle(budget.last_ledger_reservation(), "aborted_unknown")
    summary = call_ledger.summary("llm", str(ledger))
    assert summary["aborted_unknown"] == 1 and summary["possibly_sent_upper_bound"] == 1
    assert summary["succeeded"] == 0 and summary["failed"] == 0


def test_ledger_limit_blocks_before_reserving(ledger: Path) -> None:
    for _ in range(3):
        budget.charge("fake-model", "generate", "x")
        budget.settle(budget.last_ledger_reservation(), "failed")  # pre-send/transport failure
    with pytest.raises(budget.LLMCallBudgetExhausted):
        budget.charge("fake-model", "generate", "x")
    summary = call_ledger.summary("llm", str(ledger))
    assert summary["reserved"] == 3 and summary["failed"] == 3 and summary["dispatched"] == 3


def test_r32_shaped_journal_keeps_unknown(tmp_path: Path) -> None:
    """r32 evidence: n=3 dispatched with no terminal mark -> unknown, not success or unsent."""
    (tmp_path / "llm.count").write_text("8", encoding="ascii")
    lines = []
    for n in range(1, 9):
        lines.append({"n": n, "state": "dispatched"})
        if n != 3:
            lines.append({"n": n, "state": "succeeded"})
    (tmp_path / "llm.journal").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="ascii")
    summary = call_ledger.summary("llm", str(tmp_path))
    assert summary["unknown"] == 1 and summary["succeeded"] == 7 and summary["possibly_sent_upper_bound"] == 8
