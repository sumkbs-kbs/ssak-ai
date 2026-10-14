"""Analysis and routing handlers for the orchestrator state graph."""

import logging
from collections.abc import Generator, Mapping, Sequence
from typing import Protocol, cast

from antigravity_k.engine.state_graph import AgentState, StateContext

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")

__all__ = [
    "_synthesize_explicit_pipeline",
    "ceo_analyze_handler",
    "pre_route_handler",
    "route_decision",
    "route_handler",
]


class _KiEngineLike(Protocol):
    def load_kis(self) -> Sequence[object]: ...


class _ConfidenceLike(Protocol):
    value: str


class _UncertaintyResultLike(Protocol):
    confidence: _ConfidenceLike
    should_ask_user: bool
    clarification: str


class _UncertaintyEstimatorLike(Protocol):
    def estimate(
        self,
        user_message: str,
        analysis: Mapping[str, object],
        ki_count: int,
    ) -> _UncertaintyResultLike: ...

    def format_prompt_injection(self, result: _UncertaintyResultLike) -> str: ...


class _UserModelLike(Protocol):
    def observe(self, user_message: str, task_type: str) -> None: ...
    def build_context(self, preferences: Mapping[str, str]) -> str: ...


class _MemoryManagerLike(Protocol):
    def resolved_preferences(self, query: str) -> Mapping[str, str]: ...


class _AnalysisContextLike(Protocol):
    ki_engine: _KiEngineLike | None
    uncertainty_estimator: _UncertaintyEstimatorLike
    user_model: _UserModelLike
    memory_manager: _MemoryManagerLike


class _OrchestratorLike(Protocol):
    ctx: _AnalysisContextLike

    def _ceo_analyze(self, user_message: str, target_model: str) -> Generator[str | dict[str, object], None, None]: ...
    def _get_model_for_role(self, role: str) -> str: ...


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_pipeline(value: object) -> Sequence[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return ()


def ceo_analyze_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """CEO 태스크 분석."""
    yield "🏢 "  # CEO 분석 시작 시각 표시

    orchestrator = cast(_OrchestratorLike, orch)
    analysis: dict[str, object] = {}
    in_ceo_think = False
    buffer = ""

    for chunk in orchestrator._ceo_analyze(  # pyright: ignore[reportPrivateUsage]
        ctx.user_message,
        ctx.target_model,
    ):
        if isinstance(chunk, dict):  # noqa: E501  # noqa: IF_VARIANT_OK - open model stream
            analysis = chunk
            break
        else:
            buffer += chunk

            # <think> 감지
            if not in_ceo_think and "<think>" in buffer:
                in_ceo_think = True
                idx = buffer.find("<think>")
                yield buffer[:idx] + "\n\n<think>\n"
                buffer = buffer[idx + 7 :]

            # </think> 감지
            if in_ceo_think and "</think>" in buffer:
                in_ceo_think = False
                idx = buffer.find("</think>")
                yield buffer[:idx] + "\n</think>\n\n"
                buffer = buffer[idx + 8 :]
                continue

            # 스트리밍 출력
            if in_ceo_think and len(buffer) > 8:
                safe_chunk = buffer[:-8]
                yield safe_chunk
                buffer = buffer[-8:]

    # 루프 종료 후, 생각 블록이 열려있다면 닫아줍니다.
    if in_ceo_think:
        if buffer:
            yield buffer
        yield "\n</think>\n\n"

    ctx.analysis.clear()
    ctx.analysis.update(analysis)
    ctx.task_type = _as_text(analysis.get("task_type"), "simple_chat")
    ctx.delegate_to = _as_text(analysis.get("delegate_to"), "SELF")
    ctx.refined_prompt = _as_text(analysis.get("refined_prompt"), ctx.user_message)

    # 역할 자동 보정
    if ctx.task_type == "coding" and ctx.delegate_to == "SELF":
        ctx.delegate_to = "WORKER"
    elif ctx.task_type in ("reasoning", "complex") and ctx.delegate_to == "SELF":
        ctx.delegate_to = "ENG_MANAGER"


# ─── PRE_ROUTE 핸들러 ────────────────────────────────────────────


def ceo_gate_decision(ctx: StateContext) -> AgentState:
    """CEO 직후 조기 차단 — simple_chat은 풍부화 프리룰을 건너뛴다.

    RAG/코드트리 컨텍스트, 자율 학습, 스킬 매칭, 불확실성 추정은 실작업에만
    가치가 있다. 인사·단순 질문이 이 4노드를 순차로 통과하는 것은 순수 낭비다.
    """
    if ctx.task_type == "simple_chat":
        return AgentState.ROUTE
    return AgentState.CONTEXT_ENRICH


def pre_route_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """불확실성 인식 + 사용자 모델 학습."""
    orchestrator = cast(_OrchestratorLike, orch)
    # 불확실성 인식
    try:
        ki_count = len(orchestrator.ctx.ki_engine.load_kis()) if orchestrator.ctx.ki_engine else 0
        uncertainty = orchestrator.ctx.uncertainty_estimator.estimate(ctx.user_message, ctx.analysis, ki_count)
        if uncertainty.should_ask_user:
            yield f"\n❓ **[불확실성 감지]** {uncertainty.clarification}\n"
        elif uncertainty.confidence.value != "high":
            unc_context = orchestrator.ctx.uncertainty_estimator.format_prompt_injection(uncertainty)
            if unc_context:
                ctx.custom_messages[-1] = {
                    **ctx.custom_messages[-1],
                    "role": "user",
                    "content": ctx.custom_messages[-1]["content"] + unc_context,
                }
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - uncertainty boundary
        logger.exception("Unhandled exception")
        logger.debug("Uncertainty estimation error: %s", e)

    # 사용자 모델 학습
    try:
        orchestrator.ctx.user_model.observe(ctx.user_message, ctx.task_type)
        preferences = orchestrator.ctx.memory_manager.resolved_preferences(ctx.user_message)
        user_context = orchestrator.ctx.user_model.build_context(preferences)
        if user_context:
            ctx.custom_messages[-1] = {
                **ctx.custom_messages[-1],
                "role": "user",
                "content": ctx.custom_messages[-1]["content"] + user_context,
            }
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - user-model boundary
        logger.exception("Unhandled exception")
        logger.debug("User model error: %s", e)


# ─── RuleEngine 기반 결정론적 라우팅 ──────────────────────────────────
def route_decision(ctx: StateContext) -> AgentState:
    """태스크 유형에 따라 다음 상태를 결정합니다. (RuleEngine 기반 결정론적)"""
    from antigravity_k.engine.rule_engine import route_decision_deterministic

    return route_decision_deterministic(ctx)


# ─── 파이프라인 합성 헬퍼 (RuleEngine 조건용 분석 데이터 보강) ──────────────────
def _synthesize_explicit_pipeline(ctx: StateContext) -> bool:
    """사용자 프롬프트에 명시적 단계가 있으면 파이프라인을 합성합니다 (RuleEngine 조건 평가 전 호출)."""
    if ctx.analysis.get("pipeline"):
        return False
    from antigravity_k.engine.cognitive_loop import _split_explicit_steps  # pyright: ignore[reportPrivateUsage]

    steps = _split_explicit_steps(ctx.user_message or "")
    if len(steps) < 2:
        return False
    ctx.analysis["pipeline"] = [
        {"step": idx, "agent": ctx.delegate_to or "WORKER", "task": desc} for idx, desc in enumerate(steps, start=1)
    ]
    return True


# ─── ROUTE 핸들러 (라우팅 UI 표시) ──────────────────────────────────


def route_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """라우팅 UI 표시 (P4: simple_chat은 메시지 생략, 이모지 중복 제거)."""
    role_emoji = {
        "WORKER": "👨‍💻",
        "ENG_MANAGER": "🏗️",
        "QA": "🔍",
        "DESIGNER": "🎨",
        "SELF": "💬",
        "ARCHITECT": "🏗️",
        "PROPOSER": "💡",
        "CRITIC": "⚖️",
        "ARBITER": "🔨",
    }
    emoji = role_emoji.get(ctx.delegate_to, "🤖")

    # P4: simple_chat (SELF 위임)은 CEO 메시지 생략 — 단순 질문에 방해가 됨
    if ctx.delegate_to == "SELF" and ctx.task_type in ("simple_chat", "reasoning"):
        return

    if ctx.task_type == "agi_core":  # noqa: E501  # noqa: IF_VARIANT_OK - open task vocabulary
        sub_type = _as_text(ctx.analysis.get("sub_type"), "scout")
        yield f"**[CEO]** 🧬 **AGI Core ({sub_type})** 파이프라인 시작\n\n"
    elif ctx.task_type == "hardware_report":  # noqa: E501  # noqa: IF_VARIANT_OK - open task vocabulary
        yield "**[CEO]** 🖥️ **하드웨어 컨설턴트** 호출\n\n"
    elif ctx.task_type == "complex" or ctx.analysis.get("pipeline"):
        pipeline = _as_pipeline(ctx.analysis.get("pipeline"))
        if pipeline:
            yield f"**[CEO]** 🚀 **다단계 파이프라인({len(pipeline)}단계)** 시작\n\n"
        elif ctx.analysis.get("max_mode"):
            yield "**[CEO]** ⚡ **MAX 모드 병렬 편집** 시작\n\n"
        else:
            # complex라도 max_mode=False면 단일 에이전트로 실행된다 —
            # 공지가 실제 전략과 어긋나면 벤치마크/관측이 왜곡된다.
            yield f"**[CEO]** {emoji} **{ctx.delegate_to}** 위임 (복합 작업)\n\n"
    elif ctx.task_type == "max_execute":  # noqa: E501  # noqa: IF_VARIANT_OK - open task vocabulary
        yield "**[CEO]** ⚡ **MAX 모드** — 다중 워커 병렬 실행\n\n"
    elif ctx.task_type == "debate":
        yield "**[CEO]** ⚖️ **토론(Debate) 파이프라인** 시작\n\n"
    elif ctx.delegate_to != "SELF":
        delegate_model = cast(_OrchestratorLike, orch)._get_model_for_role(  # pyright: ignore[reportPrivateUsage]
            ctx.delegate_to,
        )
        yield f"**[CEO]** {emoji} **{ctx.delegate_to}** 위임 (`{delegate_model}`)\n\n"
