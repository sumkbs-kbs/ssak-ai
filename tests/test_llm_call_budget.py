"""r27: one run-wide LLM request budget at the common provider boundary (fake provider only)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from antigravity_k.engine import llm_call_budget
from antigravity_k.engine.error_classifier import classify_api_error
from antigravity_k.engine.llm_call_budget import BUDGET_ENV, LLMCallBudgetExhausted
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.model_router import AllModelsUnavailableError
from antigravity_k.engine.tool_loop import _may_retry_transient  # pyright: ignore[reportPrivateUsage]


class FakeProvider:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self._lock = threading.Lock()

    def generate(self, loaded: object, prompt: str, **_kw: object) -> str:
        with self._lock:
            self.sent.append(prompt)
        return "ok"

    def stream_generate(self, loaded: object, prompt: str, **_kw: object):
        with self._lock:
            self.sent.append(prompt)
        yield "ok"


def _mm(provider: FakeProvider) -> SimpleNamespace:
    mm = SimpleNamespace(_uses_anthropic_direct=lambda _l: False, _get_provider=lambda _l: provider)
    mm._provider_kwargs = lambda _l, kw: kw
    return mm


LOADED = SimpleNamespace(profile=SimpleNamespace(name="qwen3.8"))


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_call_budget.reset_for_tests()
    monkeypatch.delenv(BUDGET_ENV, raising=False)


def test_unset_budget_is_unlimited_legacy() -> None:
    fake = FakeProvider()
    for _ in range(5):
        assert ModelManager._do_generate(_mm(fake), LOADED, "p") == "ok"  # type: ignore[arg-type]
    assert len(fake.sent) == 5 and llm_call_budget.snapshot()["limit"] is None


def test_all_internal_calls_share_one_budget_and_block_before_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUDGET_ENV, "3")
    fake = FakeProvider()
    mm = _mm(fake)
    _ = ModelManager._do_generate(mm, LOADED, "intent")  # type: ignore[arg-type]
    _ = list(ModelManager._do_stream_generate(mm, LOADED, "ceo analysis"))  # type: ignore[arg-type]
    _ = ModelManager._do_generate(mm, LOADED, "answer")  # type: ignore[arg-type]
    with pytest.raises(LLMCallBudgetExhausted):
        _ = list(ModelManager._do_stream_generate(mm, LOADED, "retry"))  # type: ignore[arg-type]
    assert fake.sent == ["intent", "ceo analysis", "answer"]  # 4th never reached the provider
    snap = llm_call_budget.snapshot()
    assert snap["used"] == 3 and snap["blocked"] == 1 and snap["state"] == "budget_exhausted"


def test_parallel_agents_cannot_jointly_exceed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUDGET_ENV, "5")
    fake = FakeProvider()
    mm = _mm(fake)
    errors: list[BaseException] = []

    def worker() -> None:
        for _ in range(4):
            try:
                _ = ModelManager._do_generate(mm, LOADED, "x")  # type: ignore[arg-type]
            except LLMCallBudgetExhausted as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(fake.sent) == 5 and len(errors) == 27


def test_transient_retry_at_most_once_and_charged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUDGET_ENV, "10")
    transient = classify_api_error(TimeoutError("read timed out"), provider="ollama", model="qwen3.8")
    assert transient.retryable
    assert _may_retry_transient(TimeoutError(), transient.retryable, 0) is True
    assert _may_retry_transient(TimeoutError(), transient.retryable, 1) is False
    fake = FakeProvider()
    for _ in range(2):  # original + one retry both go through the charged boundary
        _ = ModelManager._do_generate(_mm(fake), LOADED, "p")  # type: ignore[arg-type]
    assert llm_call_budget.snapshot()["used"] == 2


def test_unfixable_errors_end_immediately() -> None:
    for text in ("model 'qwen9:latest' not found, try pulling it first", "401 Unauthorized: invalid api key"):
        exc = RuntimeError(text)
        cls = classify_api_error(exc, provider="ollama", model="qwen9")
        assert _may_retry_transient(exc, cls.retryable, 0) is False
    assert _may_retry_transient(AllModelsUnavailableError("combo", ["qwen3.8"]), True, 0) is False
    assert _may_retry_transient(LLMCallBudgetExhausted(1, "m"), True, 0) is False


def test_invalid_budget_config_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUDGET_ENV, "abc")
    fake = FakeProvider()
    with pytest.raises(ValueError):
        _ = ModelManager._do_generate(_mm(fake), LOADED, "p")  # type: ignore[arg-type]
    assert fake.sent == [] and llm_call_budget.snapshot()["state"] == "invalid_config"


def test_budget_exhaustion_does_not_fall_back_to_another_combo_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(BUDGET_ENV, "1")
    llm_call_budget.charge("qwen3.8")
    mm = mock.MagicMock()
    mm.router.get_combo.return_value = SimpleNamespace(strategy=None, models=["qwen3.8", "other"])
    mm.router.route.return_value = SimpleNamespace(name="qwen3.8")
    mm._do_generate.side_effect = lambda *a, **k: llm_call_budget.charge("qwen3.8")
    with pytest.raises(LLMCallBudgetExhausted):
        _ = ModelManager.generate(mm, "p", "combo-x")
    assert mm.router.route.call_count == 1  # no recursive fallback to the next model
    mm._record_failed_call.assert_not_called()
