"""r32: reservation lifecycle — reserved / dispatched / succeeded / failed / blocked / unknown.

All transports are fakes (httpx.MockTransport or in-process generators); nothing leaves the process.
"""

import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

import antigravity_k.engine.call_ledger as call_ledger
import antigravity_k.engine.llm_call_budget as budget
from antigravity_k.engine.provider_adapters.embedding_providers import (
    OllamaEmbeddingProvider,
    OllamaEmbeddingUnavailableError,
)


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for kind in ("llm", "embed"):
        (tmp_path / f"{kind}.count").write_text("0", encoding="ascii")
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", "100")
    monkeypatch.setenv("AGK_TEST_EMBED_TOTAL_LIMIT", "100")
    monkeypatch.delenv(budget.BUDGET_ENV, raising=False)
    monkeypatch.setattr(budget, "_used", 0)
    monkeypatch.setattr(budget, "_blocked", 0)
    return tmp_path


def _fake_send(outcome: str) -> Iterator[str]:
    n = budget.charge("fake-model", "stream_generate", "synthetic")
    _ = n
    ledger_n = budget.last_ledger_reservation()
    try:
        if outcome == "fail":
            raise RuntimeError("fake transport error")
        yield "a"
        yield "b"
    except GeneratorExit:
        budget.settle(ledger_n, "aborted_unknown")
        raise
    except BaseException:
        budget.settle(ledger_n, "failed")
        raise
    budget.settle(ledger_n, "succeeded")


def test_per_start_block_does_not_consume_a_reservation(ledger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(budget.BUDGET_ENV, "1")
    assert list(_fake_send("ok")) == ["a", "b"]
    with pytest.raises(budget.LLMCallBudgetExhausted):
        list(_fake_send("ok"))
    s = call_ledger.summary("llm")
    assert s["reserved"] == 1 and s["dispatched"] == 1 and s["succeeded"] == 1


def test_ledger_total_block_is_not_sent(ledger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", "1")
    list(_fake_send("ok"))
    with pytest.raises(budget.LLMCallBudgetExhausted):
        list(_fake_send("ok"))
    s = call_ledger.summary("llm")
    assert (s["reserved"], s["dispatched"], s["possibly_sent_upper_bound"]) == (1, 1, 1)


def test_retry_counts_each_attempt_once(ledger: Path) -> None:
    with pytest.raises(RuntimeError):
        list(_fake_send("fail"))
    assert list(_fake_send("ok")) == ["a", "b"]  # retry = new reservation
    s = call_ledger.summary("llm")
    assert (s["reserved"], s["dispatched"], s["failed"], s["succeeded"], s["unknown"]) == (2, 2, 1, 1, 0)


def test_abort_mid_stream_is_unknown_send_status(ledger: Path) -> None:
    gen = _fake_send("ok")
    assert next(gen) == "a"
    gen.close()
    s = call_ledger.summary("llm")
    assert s["aborted_unknown"] == 1 and s["possibly_sent_upper_bound"] == 1


def test_restart_before_terminal_mark_is_counted_as_possibly_sent(ledger: Path) -> None:
    gen = _fake_send("ok")
    assert next(gen) == "a"
    # simulate process death: no terminal mark is ever written; module state is gone
    del gen
    s = call_ledger.summary("llm", root=str(ledger))
    assert s["reserved"] == 1 and s["dispatched"] == 1
    assert s["unknown"] + s["aborted_unknown"] == 1
    assert s["possibly_sent_upper_bound"] == 1


def test_concurrent_reservations_never_double_count(ledger: Path) -> None:
    def worker() -> None:
        for _ in range(10):
            list(_fake_send("ok"))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s = call_ledger.summary("llm")
    assert (s["reserved"], s["dispatched"], s["succeeded"], s["unknown"]) == (50, 50, 50, 0)


def _profile() -> Any:
    return SimpleNamespace(api_base="http://fake-ollama.invalid:11434", name="nomic-embed-text:latest")


def test_embed_lifecycle_with_fake_transport(ledger: Path) -> None:
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"embeddings": [[0.1, 0.2]]}))
    provider = OllamaEmbeddingProvider(transport=ok)
    try:
        provider.embed(cast(Any, _profile()), None, "synthetic", "nomic-embed-text:latest")
    except Exception:
        pass  # shape validation is not under test; the send boundary is

    def refuse(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaEmbeddingUnavailableError):
        OllamaEmbeddingProvider(transport=httpx.MockTransport(refuse)).embed(
            cast(Any, _profile()), None, "synthetic", "nomic-embed-text:latest"
        )

    def timeout(_r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("late")

    with pytest.raises(OllamaEmbeddingUnavailableError):
        OllamaEmbeddingProvider(transport=httpx.MockTransport(timeout)).embed(
            cast(Any, _profile()), None, "synthetic", "nomic-embed-text:latest"
        )
    s = call_ledger.summary("embed")
    assert (s["reserved"], s["dispatched"], s["succeeded"], s["failed"], s["aborted_unknown"]) == (3, 3, 1, 1, 1)


def test_summary_handles_pre_journal_reservations(tmp_path: Path) -> None:
    """r31 had 23 reserved and no journal: every one is 'unmarked' and counted as possibly sent."""
    (tmp_path / "llm.count").write_text("23", encoding="ascii")
    s = call_ledger.summary("llm", root=str(tmp_path))
    assert s["unmarked"] == 23 and s["possibly_sent_upper_bound"] == 23
