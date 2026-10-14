from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, NoReturn, override

import pytest
from pydantic import JsonValue

if TYPE_CHECKING:
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.benchmark_harness import TaskOutcome
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
    from antigravity_k.engine.task_runner import BackgroundTaskRunner


@dataclass(frozen=True, slots=True)
class FixtureGenerationError(RuntimeError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ModelPort:
    fail: bool = False
    block: bool = False
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    requests: list[str] = field(default_factory=list)

    def is_loaded(self, name: str) -> bool:
        return name == "qa-local"

    def stream(self, prompt: str, target: str, **options: JsonValue) -> Iterator[str]:
        assert target == "qa-local"
        self.requests.append(prompt)
        if options.get("response_format") == "json":
            yield json.dumps({"task_type": "simple_chat", "delegate_to": "SELF", "refined_prompt": "13+29"})
            return
        self.entered.set()
        if self.block and not self.release.wait(timeout=10):
            raise FixtureGenerationError("QA model wait timed out")
        if self.fail:
            raise FixtureGenerationError("QA model unavailable")
        yield "42"

    def generate(self, prompt: str, target: str, **options: JsonValue) -> str:
        return "".join(self.stream(prompt, target, **options))


@dataclass(frozen=True, slots=True)
class ExecutionLane:
    runtime: AgentRuntime
    runner: BackgroundTaskRunner
    orchestrator: OrchestratorAgent
    model: ModelPort
    outcomes: list[TaskOutcome]
    root: Path


def _no_network(_socket: socket.socket, _address: tuple[str, int] | str) -> NoReturn:
    raise ConnectionRefusedError("QA model port substituted; all network disabled")


def make_lane(root: Path, monkeypatch: pytest.MonkeyPatch, *, fail: bool = False, block: bool = False) -> ExecutionLane:
    monkeypatch.chdir(root)
    monkeypatch.setattr(Path, "home", lambda: root)
    monkeypatch.setenv("AGK_CONFIG_FILE", str(root / "config.yaml"))
    _ = (root / "config.yaml").write_text(
        """model:
  main_model: qa-local
  complex_task_thinking: false
models:
  reasoning:
    - name: qa-local
      repo: qa-local
      provider: ollama
      context_length: 32768
defaults:
  reasoning: qa-local
  coding: qa-local
tool_loop:
  native_function_calling: false
persistent_agency:
  enabled: false
cognitive_core:
  mode: off
""",
        encoding="utf-8",
    )
    from antigravity_k.config import config
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.model_manager import ModelManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.orchestrator.agent import OrchestratorAgent
    from antigravity_k.engine.session_manager import SessionManager
    from antigravity_k.engine.task_runner import BackgroundTaskRunner
    from antigravity_k.engine.usage_tracker import UsageTracker
    from antigravity_k.tools.tool_registry import ToolRegistry

    monkeypatch.setattr(config.paths, "project_root", root)
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    model = ModelPort(fail=fail, block=block)
    manager = ModelManager(ModelRegistry(str(root / "config.yaml")), tracker=UsageTracker(str(root / "usage.json")))
    monkeypatch.setattr(manager, "stream_generate", model.stream)
    monkeypatch.setattr(manager, "generate", model.generate)
    monkeypatch.setattr(manager, "is_loaded", model.is_loaded)
    orchestrator = OrchestratorAgent(
        manager,
        project_root=str(root),
        tool_registry=ToolRegistry(project_root=str(root)),
        session_manager=SessionManager(base_dir=str(root / "sessions")),
    )
    outcomes: list[TaskOutcome] = []
    runner = BackgroundTaskRunner(db_path=str(root / "tasks.db"), outcome_recorder=outcomes.append)
    runtime = AgentRuntime(orchestrator, task_runner=runner)
    return ExecutionLane(runtime, runner, orchestrator, model, outcomes, root)
