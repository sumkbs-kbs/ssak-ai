"""r30 P0: Brain 'default' resolution and the shared pre-send budget for direct HTTP sends."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_k.engine import llm_call_budget
from antigravity_k.engine.direct_model_call import guard_direct_model_call
from antigravity_k.engine.llm_call_budget import LLMCallBudgetExhausted
from antigravity_k.engine.model_manager import ModelManager, ModelNotReadyError


class _Router:
    def __init__(self, combos: set[str]) -> None:
        self.combos = combos

    def get_combo(self, name: str) -> object | None:
        return object() if name in self.combos else None


class _Registry:
    def __init__(self, models: set[str], raw: dict[str, object], default: str | None = None) -> None:
        self.models = models
        self._raw = raw
        self._default = default

    def model_exists(self, name: str) -> bool:
        return name in self.models

    def get_default(self, role: str) -> object | None:
        return SimpleNamespace(name=self._default) if self._default and role == "default" else None


def _mgr(models: set[str], combos: set[str], raw: dict[str, object], default: str | None = None) -> object:
    return SimpleNamespace(router=_Router(combos), _registry=_Registry(models, raw, default))


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("AGK_LLM_CALL_BUDGET", "AGK_TEST_CALL_LEDGER_DIR", "AGK_TEST_LLM_TOTAL_LIMIT"):
        monkeypatch.delenv(env, raising=False)
    llm_call_budget.reset_for_tests()


def test_default_alias_resolves_to_configured_combo() -> None:
    m = _mgr({"qwen3.8:latest"}, {"orchestrator-swarm"}, {"agent_models": {"default": "orchestrator-swarm"}})
    assert ModelManager.resolve_target(m, "default") == "orchestrator-swarm"  # type: ignore[arg-type]
    assert ModelManager.resolve_target(m, "") == "orchestrator-swarm"  # type: ignore[arg-type]


def test_explicit_registered_model_unchanged() -> None:
    m = _mgr({"qwen3.8:latest"}, set(), {"agent_models": {"default": "qwen3.8:latest"}})
    assert ModelManager.resolve_target(m, "qwen3.8:latest") == "qwen3.8:latest"  # type: ignore[arg-type]


def test_missing_default_is_not_ready_without_substitution() -> None:
    m = _mgr({"some-latest-model", "cloud-model"}, set(), {})
    with pytest.raises(ModelNotReadyError):
        ModelManager.resolve_target(m, "default")  # type: ignore[arg-type]
    snap = llm_call_budget.snapshot()
    assert snap["resolution_failed"] == 1 and snap["used"] == 0


def test_default_points_to_unregistered_model_is_not_ready() -> None:
    m = _mgr({"other-provider-model"}, set(), {"agent_models": {"default": "removed-model"}})
    with pytest.raises(ModelNotReadyError, match="removed-model"):
        ModelManager.resolve_target(m, "auto")  # type: ignore[arg-type]


def test_provider_change_follows_config_only() -> None:
    m = _mgr({"qwen3.8:latest", "local-b"}, set(), {"agent_models": {"default": "local-b"}})
    assert ModelManager.resolve_target(m, "default") == "local-b"  # type: ignore[arg-type]


def test_registry_default_used_when_agent_models_missing() -> None:
    m = _mgr({"qwen3.8:latest"}, set(), {}, default="qwen3.8:latest")
    assert ModelManager.resolve_target(m, "default") == "qwen3.8:latest"  # type: ignore[arg-type]


def test_direct_guard_charges_and_caps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGK_LLM_CALL_BUDGET", "2")
    assert guard_direct_model_call("qwen3.8:latest", "t", "x", timeout=300) == 120.0
    assert guard_direct_model_call("qwen3.8:latest", "t", "x", timeout=30) == 30.0
    with pytest.raises(LLMCallBudgetExhausted):
        guard_direct_model_call("qwen3.8:latest", "t", "x", timeout=30)
    snap = llm_call_budget.snapshot()
    assert snap["used"] == 2 and snap["blocked"] == 1


def _ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: int, start: str | None = "0") -> Path:
    monkeypatch.setenv("AGK_TEST_CALL_LEDGER_DIR", str(tmp_path))
    monkeypatch.setenv("AGK_TEST_LLM_TOTAL_LIMIT", str(limit))
    path = tmp_path / "llm.count"
    if start is not None:
        path.write_text(start)
    return path


def test_ledger_shared_across_parallel_and_restart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _ledger(monkeypatch, tmp_path, 5)
    ok: list[int] = []
    blocked: list[int] = []

    def worker() -> None:
        try:
            guard_direct_model_call("m", "p", "", timeout=1)
            ok.append(1)
        except LLMCallBudgetExhausted:
            blocked.append(1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 5 and len(blocked) == 3
    llm_call_budget.reset_for_tests()  # simulated server restart: process counter resets, ledger does not
    with pytest.raises(LLMCallBudgetExhausted):
        guard_direct_model_call("m", "p", "", timeout=1)
    assert path.read_text() == "5"


@pytest.mark.parametrize("start", [None, "garbage"])
def test_ledger_missing_or_corrupt_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, start: str | None
) -> None:
    _ledger(monkeypatch, tmp_path, 5, start)
    with pytest.raises(LLMCallBudgetExhausted):
        guard_direct_model_call("m", "p", "", timeout=1)
    assert llm_call_budget.snapshot()["used"] == 0
