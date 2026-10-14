"""SubAgent Spawner Engine (OpenClaw Pattern).

===========================================

독립적인 서브 세션을 생성하고 병렬로 실행하여 결과를 취합하는 엔진 모듈입니다.
OpenClaw의 'sessions_spawn' 로직을 내재화하여 메인 컨텍스트 오염을 방지하고
작업을 효율적으로 병렬 분배합니다.
"""

import asyncio
import logging
import time
from collections.abc import Iterator, Mapping, Sequence
from importlib import import_module
from typing import Callable, Protocol, cast

from pydantic import ValidationError

from antigravity_k.engine.agent_definition import (
    AgentContractViolation,
    AgentSpawnContract,
    AgentSpawnRequest,
    AgentToolRegistry,
    default_agent_spawn_contract,
)
from antigravity_k.engine.subagent_execution import start_subagent_stream
from antigravity_k.engine.task_runner import get_task_runner
from antigravity_k.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class _OrchestratorPort(Protocol):
    def _get_model_for_role(self, role: str) -> str: ...

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Iterator[str]: ...


def OrchestratorAgent(*args: object, **kwargs: object) -> _OrchestratorPort:  # noqa: N802
    module = import_module("antigravity_k.engine.orchestrator")
    implementation = cast(Callable[..., _OrchestratorPort], module.__dict__["OrchestratorAgent"])
    return implementation(*args, **kwargs)


class SubagentSpawner:
    """Spawns isolated sub-agent processes for parallel task execution."""

    def __init__(
        self,
        model_manager: object,
        tool_registry: object,
        contract: AgentSpawnContract | None = None,
    ):
        """Initialize the SubagentSpawner.

        Args:
            model_manager: model manager.
            tool_registry: tool registry.

        """
        self.model_manager: object = model_manager
        self.tool_registry: object = tool_registry
        self.contract: AgentSpawnContract = contract or default_agent_spawn_contract()
        dependencies = import_module("antigravity_k.api.dependencies")
        get_vault_engine = cast(Callable[[], object], dependencies.__dict__["get_vault_engine"])
        self.vault_engine: object = get_vault_engine()

    async def spawn_parallel(
        self,
        tasks: Sequence[Mapping[str, object]],
        max_tokens: int = 4096,
    ) -> list[str]:
        """여러 서브 태스크를 병렬로 스폰하여 결과를 반환합니다."""
        _ = max_tokens
        logger.info("Spawning %s sub-agents in parallel.", len(tasks))

        async def _run_subagent(task_data: Mapping[str, object], index: int) -> str:
            try:
                request = AgentSpawnRequest.model_validate(task_data)
                resolved = self.contract.resolve(request.agent, request.tools)
            except ValidationError as error:
                return f"[Sub-Agent #{index} Error] Invalid spawn request: {error.errors(include_url=False)}"
            except AgentContractViolation as error:
                return f"[Sub-Agent #{index} Error] [DENIED] {error}"

            start_time = time.time()
            try:
                # 독립된 Orchestrator 인스턴스 생성 (부모 툴 레지스트리 공유)
                sub_orch = OrchestratorAgent(
                    model_manager=self.model_manager,
                    vault_engine=self.vault_engine,
                    tool_registry=AgentToolRegistry(
                        cast(ToolRegistry, self.tool_registry),
                        resolved.definition,
                        resolved.allowed_tools,
                    ),
                )

                get_model_for_role = cast(Callable[[str], str], getattr(sub_orch, "_get_model_for_role"))
                target_model = get_model_for_role(resolved.definition.role)
                system_prompt = resolved.definition.system_prompt

                messages = [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Task: {request.task}\nAllowed tools: {list(resolved.allowed_tools)}",
                    },
                ]

                # run_stream is synchronous generator, we need to run it in a thread to not block async
                def run_sync_stream() -> str:
                    tracked_stream = start_subagent_stream(
                        sub_orch,
                        task_runner=get_task_runner(),
                        messages=messages,
                        target_model=target_model,
                        subagent_kind="parallel_spawn",
                    )
                    output_parts = list(tracked_stream.chunks)
                    return "".join(output_parts)

                result = await asyncio.to_thread(run_sync_stream)
                elapsed = time.time() - start_time
                return f"[Sub-Agent #{index} Result] (in {elapsed:.1f}s)\n{result}"

            except Exception as e:
                logger.exception("Subagent #%s failed", index)
                return f"[Sub-Agent #{index} Error] {e}"

        coroutines = [_run_subagent(task, i) for i, task in enumerate(tasks)]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Format results
        formatted_results: list[str] = []
        for res in results:
            if isinstance(res, BaseException):
                formatted_results.append(f"Exception: {res}")
            else:
                formatted_results.append(str(res))

        return formatted_results

    def spawn(self, task: str, tools: list[str], max_tokens: int = 4096) -> str:
        """단일 서브 태스크를 스폰하는 동기 진입점 (기존 AgentSpawnTool 하위호환)."""
        tasks = [{"task": task, "tools": tools}]
        try:
            _ = asyncio.get_running_loop()
        except RuntimeError:
            results = asyncio.run(self.spawn_parallel(tasks, max_tokens))
            return results[0]

        raise RuntimeError(
            "SubagentSpawner.spawn cannot run inside an active event loop; await spawn_parallel instead.",
        )
