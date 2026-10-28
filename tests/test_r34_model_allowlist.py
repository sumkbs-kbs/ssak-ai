"""r34: approved-model boundary before every send (fake transport only; nothing real is sent).

r33 evidence: after qwen3.8 returned HTTP 500 the combo fallback actually SENT a request to the
unapproved qwen3.6:latest (Ollama 404 => not loaded, but sent). These tests pin that a refused
model gets zero transmissions and no substitute model is chosen.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from antigravity_k.engine import call_ledger, llm_call_budget, model_allowlist
from antigravity_k.engine.direct_model_call import guard_direct_model_call
from antigravity_k.engine.llm_call_budget import BUDGET_ENV, LLMLedgerLimitReached, LLMLedgerUnavailable
from antigravity_k.engine.model_allowlist import ModelNotAllowedError
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.model_policy import ModelRoutingPolicy
from antigravity_k.engine.model_router import AllModelsUnavailableError

CHAIN = ["qwen3.8", "qwen3.6:latest", "deepseek-r1:70b"]


class FakeTransport:
    """Records every request that would leave the process; per-model scripted outcomes."""

    def __init__(self, outcomes: dict[str, BaseException | None]) -> None:
        self.sent: list[str] = []
        self.outcomes = outcomes

    def _go(self, model: str) -> str:
        self.sent.append(model)
        exc = self.outcomes.get(model)
        if exc is not None:
            raise exc
        return f"ok:{model}"

    def generate(self, loaded: object, prompt: str, **_kw: object) -> str:
        return self._go(loaded.profile.name)  # type: ignore[attr-defined]

    def stream_generate(self, loaded: object, prompt: str, **_kw: object):
        yield self._go(loaded.profile.name)  # type: ignore[attr-defined]


def _profile(name: str, api_base: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        provider="ollama",
        api_base=api_base,
        is_local=True,
        effective_parameter_count_b=8.0,
        cost_per_1k_tokens_usd=0.0,
    )


class FakeRouter:
    """Fallback order + the REAL routing policy filter (allowlist lives in ModelRoutingPolicy.decide)."""

    def __init__(self, models: list[str], *, honor_policy: bool = True) -> None:
        self.models = models
        self.failed: set[str] = set()
        self.policy = ModelRoutingPolicy.from_mapping({"enabled": False})
        self.honor_policy = honor_policy
        self.route_calls = 0

    def get_combo(self, name: str):
        return SimpleNamespace(strategy=None, models=self.models) if name == "orchestrator-swarm" else None

    def route(self, _combo: str):
        self.route_calls += 1
        for m in self.models:
            if m in self.failed:
                continue
            if self.honor_policy and not self.policy.decide(_profile(m)).allowed:  # type: ignore[arg-type]
                continue
            return _profile(m)
        raise AllModelsUnavailableError("orchestrator-swarm", self.models)

    def route_single(self, name: str):
        if not self.policy.decide(_profile(name), explicit=True).allowed:  # type: ignore[arg-type]
            raise ValueError(f"모델 '{name}'이 라우팅 정책에 의해 제외되었습니다")
        return _profile(name)


def _manager(transport: FakeTransport, router: FakeRouter) -> mock.MagicMock:
    inner = SimpleNamespace(_uses_anthropic_direct=lambda _l: False, _get_provider=lambda _l: transport)
    inner._provider_kwargs = lambda _l, kw: kw
    mm = mock.MagicMock()
    mm.router = router
    mm.resolve_target.side_effect = lambda t: t
    mm._registry.model_exists.return_value = True
    mm.get.side_effect = lambda name: SimpleNamespace(profile=_profile(name), tokenizer=None)
    mm._do_generate.side_effect = lambda loaded, prompt, **k: ModelManager._do_generate(inner, loaded, prompt, **k)  # type: ignore[arg-type]
    mm._do_stream_generate.side_effect = lambda loaded, prompt, **k: ModelManager._do_stream_generate(
        inner, loaded, prompt, **k
    )  # type: ignore[arg-type]
    mm._strip_hidden_reasoning.side_effect = lambda t: t
    mm._maybe_cascade_escalate.return_value = None
    mm._record_failed_call.side_effect = lambda model, *a, **k: router.failed.add(model)
    mm.generate.side_effect = lambda *a, **k: ModelManager.generate(mm, *a, **k)
    mm.stream_generate.side_effect = lambda *a, **k: ModelManager.stream_generate(mm, *a, **k)
    return mm


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    llm_call_budget.reset_for_tests()
    model_allowlist.reset_for_tests()
    monkeypatch.setenv(BUDGET_ENV, "10")
    monkeypatch.setenv(model_allowlist.MODEL_ENV, "qwen3.8:latest")
    monkeypatch.delenv(model_allowlist.PROVIDER_ENV, raising=False)
    monkeypatch.delenv(model_allowlist.ENDPOINT_ENV, raising=False)
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", "10")
    (tmp_path / "llm.count").write_text("0")


@pytest.mark.parametrize("streaming", [False, True])
def test_r33_chain_qwen38_500_never_reaches_unapproved_models(streaming: bool, tmp_path) -> None:
    t = FakeTransport({"qwen3.8": RuntimeError("HTTP 500: tool call parsing failed EOF")})
    mm = _manager(t, FakeRouter(CHAIN))
    with pytest.raises(AllModelsUnavailableError):
        if streaming:
            _ = list(ModelManager.stream_generate(mm, "p", "orchestrator-swarm"))
        else:
            _ = ModelManager.generate(mm, "p", "orchestrator-swarm")
    assert t.sent == ["qwen3.8"]  # qwen3.6:latest and deepseek-r1:70b: zero transmissions
    assert (tmp_path / "llm.count").read_text() == "1"
    assert llm_call_budget.snapshot()["used"] == 1


def test_approved_alternative_is_used_and_unapproved_middle_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(model_allowlist.MODEL_ENV, "qwen3.8,deepseek-r1:70b")
    t = FakeTransport({"qwen3.8": TimeoutError("read timed out")})
    mm = _manager(t, FakeRouter(CHAIN))
    assert ModelManager.generate(mm, "p", "orchestrator-swarm") == "ok:deepseek-r1:70b"
    assert t.sent == ["qwen3.8", "deepseek-r1:70b"]


def test_router_bypass_is_still_refused_before_load_and_send(tmp_path) -> None:
    t = FakeTransport({})
    router = FakeRouter(["qwen3.6:latest", "qwen3.8"], honor_policy=False)
    mm = _manager(t, router)
    with pytest.raises(ModelNotAllowedError):
        _ = list(ModelManager.stream_generate(mm, "p", "orchestrator-swarm"))
    assert t.sent == [] and mm.get.call_count == 0 and router.route_calls == 1  # no swap to qwen3.8
    assert (tmp_path / "llm.count").read_text() == "0" and llm_call_budget.snapshot()["used"] == 0


def test_charge_refuses_before_budget_and_ledger(tmp_path) -> None:
    with pytest.raises(ModelNotAllowedError):
        llm_call_budget.charge("qwen3.6:latest", "stream_generate")
    assert (tmp_path / "llm.count").read_text() == "0" and model_allowlist.refused_count() == 1


def test_explicit_single_unapproved_target_is_an_explicit_model_error() -> None:
    t = FakeTransport({})
    mm = _manager(t, FakeRouter(CHAIN))
    mm.router.get_combo = lambda _n: None
    with pytest.raises(ValueError, match="라우팅 정책"):
        _ = ModelManager.generate(mm, "p", "qwen3.6:latest")
    assert t.sent == []


def test_uninstalled_approved_model_fails_once_without_substitute() -> None:
    t = FakeTransport({"qwen3.8": RuntimeError("model 'qwen3.8' not found, try pulling it first")})
    mm = _manager(t, FakeRouter(CHAIN))
    mm.router.get_combo = lambda _n: None
    with pytest.raises(RuntimeError, match="not found"):
        _ = ModelManager.generate(mm, "p", "qwen3.8")
    assert t.sent == ["qwen3.8"]


def test_direct_calls_and_endpoints_use_the_same_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ModelNotAllowedError):
        guard_direct_model_call("qwen3.6:latest", "qa", "x", timeout=5)
    monkeypatch.setenv(model_allowlist.ENDPOINT_ENV, "127.0.0.1:11434")
    with pytest.raises(ModelNotAllowedError, match="endpoint_not_allowlisted"):
        llm_call_budget.charge("qwen3.8", endpoint="http://10.9.8.7:11434")
    assert llm_call_budget.charge("qwen3.8", endpoint="http://127.0.0.1:11434") == 1
    monkeypatch.setenv(model_allowlist.PROVIDER_ENV, "ollama")
    with pytest.raises(ModelNotAllowedError, match="provider_not_allowlisted"):
        llm_call_budget.charge("qwen3.8", provider="openrouter")


def test_policy_refuses_even_when_routing_policy_disabled() -> None:
    pol = ModelRoutingPolicy.from_mapping({"enabled": False})
    assert pol.decide(_profile("qwen3.6:latest")).reason == "model_not_allowlisted"  # type: ignore[arg-type]
    assert pol.decide(_profile("qwen3.8")).allowed  # type: ignore[arg-type]


def test_unset_allowlist_is_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(model_allowlist.MODEL_ENV)
    assert model_allowlist.model_allowed("anything")


def test_ledger_missing_and_corrupt_differ_from_limit_reached(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    (tmp_path / "llm.count").unlink()
    with pytest.raises(LLMLedgerUnavailable, match="ledger_unavailable") as e1:
        llm_call_budget.charge("qwen3.8")
    assert e1.value.status == "ledger_unavailable" and not (tmp_path / "llm.count").exists()  # never reset to 0
    (tmp_path / "llm.count").write_text("x?")
    with pytest.raises(LLMLedgerUnavailable):
        llm_call_budget.charge("qwen3.8")
    assert (tmp_path / "llm.count").read_text() == "x?"
    (tmp_path / "llm.count").write_text("10")
    with pytest.raises(LLMLedgerLimitReached, match="budget_exhausted") as e2:
        llm_call_budget.charge("qwen3.8")
    assert e2.value.status == "budget_exhausted" and "LLM call budget 0" not in str(e2.value)


def test_embedding_wire_model_outside_allowlist_is_never_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from antigravity_k.engine.provider_adapters.embedding_providers import (
        OllamaEmbeddingProvider,
        OllamaEmbeddingUnavailableError,
    )

    hits: list[str] = []
    transport = httpx.MockTransport(
        lambda req: (hits.append(str(req.url)), httpx.Response(200, json={"embeddings": [[0.1]]}))[1]
    )
    monkeypatch.setenv(model_allowlist.EMBED_MODEL_ENV, "nomic-embed-text:latest")
    prof = SimpleNamespace(name="mxbai", api_base="http://127.0.0.1:11434", provider="ollama")
    with pytest.raises(OllamaEmbeddingUnavailableError, match="not allowlisted"):
        OllamaEmbeddingProvider(transport=transport).embed(prof, None, "x", "mxbai-embed-large")  # type: ignore[arg-type]
    assert hits == []
