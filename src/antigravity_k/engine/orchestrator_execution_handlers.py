"""Agent execution handlers for the orchestrator state graph."""

import logging
from collections.abc import Generator
from typing import Protocol, cast

from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.state_graph import AgentState, StateContext

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")


class _WorkerResultLike(Protocol):
    model: str
    strategy: str
    output: str
    elapsed_sec: float
    error: str | None


class _MaxResultLike(Protocol):
    final_output: str
    selected_idx: int
    results: list[_WorkerResultLike]
    error: str | None


class _MaxEngineLike(Protocol):
    def run(self, task_spec: dict[str, object], orchestrator: object | None = None) -> _MaxResultLike: ...


class _RuntimeLike(Protocol):
    is_canonical_runtime: bool

    def run_max(self, task_spec: dict[str, object]) -> _MaxResultLike: ...


class _OrchestratorLike(Protocol):
    max_engine: _MaxEngineLike | None
    agent_runtime: _RuntimeLike | None
    manager: object
    tool_registry: object


def _analysis_value(ctx: StateContext, key: str, default: object) -> object:
    return ctx.analysis.get(key, default)


def _pipeline_steps(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[object] = cast(list[object], value)
    return [cast(dict[str, object], item) for item in items if isinstance(item, dict)]


def _preserve_execution_request(ctx: StateContext) -> str:
    original_request = ctx.user_message or ctx.custom_messages[-1]["content"]
    auxiliary: list[str] = []
    if ctx.refined_prompt and ctx.refined_prompt != original_request:
        auxiliary.append("[Automatic task analysis — auxiliary context]\n" + ctx.refined_prompt)
    if ctx.rag_context:
        auxiliary.append("[Retrieved material — auxiliary context]\n" + ctx.rag_context)
    prompt = original_request
    if auxiliary:
        prompt = "\n\n".join(
            [
                "Follow the original user request if auxiliary context conflicts with it.",
                *auxiliary,
                "[Original user request — authoritative instruction]\n" + original_request,
            ]
        )
    if ctx.retry_count > 0:
        return prompt + "\n\n[Current retry feedback]\n" + ctx.custom_messages[-1]["content"]
    if auxiliary:
        ctx.custom_messages[-1] = {**ctx.custom_messages[-1], "content": prompt}
    return prompt


def max_execute_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """MAX 모드: 여러 워커를 병렬로 실행하고 Selector가 최적 선정.

    Codebuff MAX Mode 방식:
    1. N개 워커를 서로 다른 모델/전략으로 동시 실행
    2. Selector 엔진이 모든 결과 검토
    3. 최적 결과 선정 또는 합성
    """
    ctx.execution_origin = AgentState.MAX_EXECUTE
    execution_request = _preserve_execution_request(ctx)

    yield ProgressChunk("⚡ **[MAX Mode]** 다중 워커 병렬 실행 중...\n")

    try:
        max_engine = orch.max_engine
        if max_engine is None:
            # 폴백: 싱글 에이전트
            yield ProgressChunk("ℹ️ MAX Engine not available, falling back to single agent.\n")
            from antigravity_k.engine.tool_loop import ToolLoopEngine

            tool_loop = ToolLoopEngine(orch)
            yield from tool_loop.run_loop(
                ctx.custom_messages,
                ctx.delegate_to,
                ctx.task_type,
                ctx.max_steps,
                ctx.target_model,
            )
            ctx.agent_output = tool_loop.last_output
            if tool_loop.approval_required:
                ctx.approval_required = True
                ctx.transition_to(AgentState.COMPLETE)
            return

        # MAX 모드 태스크 명세 구성
        task_spec: dict[str, object] = {
            "prompt": execution_request,
            "messages": ctx.custom_messages,
            "task_type": ctx.task_type,
            "delegate_to": ctx.delegate_to,
            "max_steps": ctx.max_steps,
            "target_model": ctx.target_model,
        }

        runtime = orch.agent_runtime
        result: _MaxResultLike = (
            runtime.run_max(task_spec)
            if runtime is not None and runtime.is_canonical_runtime is True
            else max_engine.run(task_spec, orchestrator=orch)
        )

        if result.final_output:
            # 결과가 이미 trace를 포함하므로 바로 yield
            if result.selected_idx >= 0 and result.results:
                selected = result.results[result.selected_idx]
                ctx.agent_output = selected.output

                # 결과 프레임 출력
                worker_summary = (
                    f"\n\n🏆 **[MAX Selector]** Worker {result.selected_idx + 1} 선정 "
                    f"({selected.model}, {selected.strategy}, {selected.elapsed_sec}s)\n"
                )
                yield ProgressChunk(worker_summary)
            else:
                ctx.agent_output = result.final_output
        else:
            error_msg = result.error or "All workers failed"
            yield f"\n\n❌ **[MAX Error]** {error_msg}\n"
            ctx.agent_output = f"[MAX Error] {error_msg}"

        # 워커 상세 정보 표시 (성공한 워커만)
        if result.results:
            for i, r in enumerate(result.results):
                status = "✅" if r.error is None and r.output.strip() else "❌"
                yield ProgressChunk(f"{status} Worker {i + 1}: {r.model} [{r.strategy}] — {r.elapsed_sec}s\n")

    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - fallback boundary
        logger.exception("[MAX] Max execute handler failed")
        yield f"\n\n❌ **[MAX Error]** 병렬 실행 실패: {e}\n"
        # 폴백: 싱글 에이전트
        yield ProgressChunk("🔄 싱글 에이전트로 폴백합니다...\n\n")
        from antigravity_k.engine.tool_loop import ToolLoopEngine

        tool_loop = ToolLoopEngine(orch)
        yield from tool_loop.run_loop(
            ctx.custom_messages,
            ctx.delegate_to,
            ctx.task_type,
            ctx.max_steps,
            ctx.target_model,
        )
        ctx.agent_output = tool_loop.last_output
        if tool_loop.approval_required:
            ctx.approval_required = True
            ctx.transition_to(AgentState.COMPLETE)


# ─── AGENT_EXECUTE 핸들러 ────────────────────────────────────────


def agent_execute_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """단일 에이전트 실행 (기존 _run_single_agent 위임)."""
    ctx.execution_origin = AgentState.AGENT_EXECUTE
    _preserve_execution_request(ctx)

    from antigravity_k.engine.tool_loop import ToolLoopEngine

    tool_loop = ToolLoopEngine(orch)
    yield from tool_loop.run_loop(
        ctx.custom_messages,
        ctx.delegate_to,
        ctx.task_type,
        ctx.max_steps,
        ctx.target_model,
        evaluation_user_task=ctx.user_message,
    )
    ctx.agent_output = tool_loop.last_output
    if tool_loop.approval_required:
        ctx.approval_required = True
        ctx.transition_to(AgentState.COMPLETE)


# ─── PIPELINE_EXECUTE 핸들러 ─────────────────────────────────────


def pipeline_execute_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """멀티 스텝 파이프라인 실행."""
    ctx.execution_origin = AgentState.PIPELINE_EXECUTE
    pipeline = _pipeline_steps(_analysis_value(ctx, "pipeline", []))
    yield ProgressChunk("\n\n🚀 **멀티 스텝 파이프라인 시작**\n")

    current_messages = list(ctx.custom_messages)
    last_output = ""
    for step_info in pipeline:
        raw_step_num = step_info.get("step", 0)
        step_num = raw_step_num if isinstance(raw_step_num, int) else 0
        raw_agent_role = step_info.get("agent", "WORKER")
        agent_role = raw_agent_role if isinstance(raw_agent_role, str) else "WORKER"
        raw_task_desc = step_info.get("task", "")
        task_desc = raw_task_desc if isinstance(raw_task_desc, str) else ""

        yield ProgressChunk(f"\n\n---\n**[Step {step_num}] {agent_role}**: {task_desc}\n\n")

        # 각 단계의 작업 설명을 해당 단계 실행에 실제로 주입한다 —
        # 주입하지 않으면 전체 원 요청을 단계 수만큼 max_steps로 반복 실행하는
        # 것과 같아진다 (비용 N배, 분해 무의미).
        step_messages = [dict(message) for message in current_messages]
        if task_desc:
            step_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"[Pipeline Step {step_num} — role: {agent_role}]\n"
                        f"Execute ONLY this step now: {task_desc}\n"
                        "Do not repeat previous steps. Produce this step's output only."
                    ),
                }
            )

        from antigravity_k.engine.tool_loop import ToolLoopEngine

        tool_loop = ToolLoopEngine(orch)
        yield from tool_loop.run_loop(step_messages, agent_role, "complex_step", ctx.max_steps)
        last_output = tool_loop.last_output
        if tool_loop.approval_required:
            ctx.approval_required = True
            ctx.agent_output = last_output
            ctx.transition_to(AgentState.COMPLETE)
            return

        if tool_loop.last_output:
            current_messages.append(
                {
                    "role": "assistant",
                    "content": f"[{agent_role} 완료]: " + tool_loop.last_output,
                }
            )

    yield ProgressChunk("\n\n✅ **파이프라인 완료**\n")
    ctx.agent_output = last_output


# ─── DEBATE_EXECUTE 핸들러 ───────────────────────────────────────


def debate_execute_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """토론 파이프라인 실행."""
    ctx.execution_origin = AgentState.DEBATE_EXECUTE
    raw_debate_topic = _analysis_value(ctx, "debate_topic", ctx.user_message)
    debate_topic = raw_debate_topic if isinstance(raw_debate_topic, str) else ctx.user_message
    yield ProgressChunk(f"\n\n⚖️ **토론 시작**: {debate_topic}\n")

    current_messages = list(ctx.custom_messages)
    current_messages.append({"role": "user", "content": f"Debate Topic: {debate_topic}"})

    yield ProgressChunk("\n\n💡 **[PROPOSER의 제안]**\n\n")
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    tool_loop = ToolLoopEngine(orch)
    for chunk in tool_loop.run_loop(current_messages, "PROPOSER", "debate_propose", ctx.max_steps):
        yield chunk

    proposer_output = tool_loop.last_output
    if tool_loop.approval_required:
        ctx.approval_required = True
        ctx.agent_output = proposer_output
        ctx.transition_to(AgentState.COMPLETE)
        return
    current_messages.append({"role": "assistant", "content": f"PROPOSER 제안: {proposer_output}"})

    yield ProgressChunk("\n\n⚖️ **[CRITIC의 비판 및 검증]**\n\n")
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    tool_loop = ToolLoopEngine(orch)
    for chunk in tool_loop.run_loop(current_messages, "CRITIC", "debate_critic", ctx.max_steps):
        yield chunk

    critic_output = tool_loop.last_output
    if tool_loop.approval_required:
        ctx.approval_required = True
        ctx.agent_output = critic_output
        ctx.transition_to(AgentState.COMPLETE)
        return
    current_messages.append({"role": "assistant", "content": f"CRITIC 비판: {critic_output}"})

    # ARBITER 종합 — 비판으로 토론을 끝내면 사용자가 받는 것은 제안에 대한
    # 반박문이지 해결된 답이 아니다. 제안과 비판을 통합한 최종 답을 만든다.
    yield ProgressChunk("\n\n🧑‍⚖️ **[ARBITER의 종합]**\n\n")
    current_messages.append(
        {
            "role": "user",
            "content": (
                "Synthesize the PROPOSER's proposal and the CRITIC's critique into one final, "
                "resolved answer. Address each critique point directly: accept valid criticisms "
                "with corrections, and reject invalid ones with reasons."
            ),
        },
    )
    tool_loop = ToolLoopEngine(orch)
    for chunk in tool_loop.run_loop(current_messages, "QA", "debate_arbiter", ctx.max_steps):
        yield chunk

    ctx.agent_output = tool_loop.last_output
    if tool_loop.approval_required:
        ctx.approval_required = True
        ctx.transition_to(AgentState.COMPLETE)


# ─── AGI_CORE 핸들러 ─────────────────────────────────────────────


def agi_core_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """AGI 코어 / 하드웨어 리포트 작업."""
    if ctx.task_type == "agi_core":  # noqa: E501  # noqa: IF_VARIANT_OK - open task vocabulary
        raw_sub_type = _analysis_value(ctx, "sub_type", "scout")
        sub_type = raw_sub_type if isinstance(raw_sub_type, str) else "scout"
        from antigravity_k.engine.model_manager import ModelManager
        from antigravity_k.tools.tool_registry import ToolRegistry

        model_manager = cast(ModelManager, orch.manager)
        tool_registry = cast(ToolRegistry, orch.tool_registry)
        if "scout" in sub_type.lower():
            from antigravity_k.agents.scout_agent import ScoutAgent

            scout = ScoutAgent(model_manager, tool_registry)
            yield scout.propose_model_scout(ctx.user_message)
        else:
            from antigravity_k.agents.trainer_agent import TrainerAgent

            trainer = TrainerAgent(model_manager, tool_registry)
            yield trainer.propose_training(ctx.user_message)
    elif ctx.task_type == "hardware_report":
        from antigravity_k.agents.hardware_analyst import HardwareAnalystAgent
        from antigravity_k.engine.model_manager import ModelManager

        analyst = HardwareAnalystAgent(cast(ModelManager, orch.manager))
        yield analyst.propose_upgrade("AGI-Target-400B", 200.0)
