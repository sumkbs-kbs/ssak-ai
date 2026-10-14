"""Memory persistence handler for the orchestrator state graph."""

import logging
from collections.abc import Generator, Iterable
from typing import Callable, Protocol, cast

from antigravity_k.engine.state_graph import StateContext

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")


class _MemoryRecorderLike(Protocol):
    def record(
        self,
        *,
        user_message: str,
        agent_output: str,
        task_type: str,
        preferred_model: str | None,
    ) -> Iterable[str]: ...


class _ModeLike(Protocol):
    value: str


class _ModeManagerLike(Protocol):
    current_mode: _ModeLike


class _QualityGradeLike(Protocol):
    value: str


class _QualityScoreLike(Protocol):
    grade: _QualityGradeLike
    score: float
    issues: list[str]


class _QualityGateLike(Protocol):
    def evaluate(
        self,
        *,
        task_type: str,
        user_request: str,
        agent_output: str,
        execution_mode: str | None,
    ) -> _QualityScoreLike: ...


class _ToolExecutorLike(Protocol):
    tool_call_history: Iterable[dict[str, object]]


class _OrchestratorContextLike(Protocol):
    quality_gate: _QualityGateLike
    tool_executor: object | None


class _EvolutionResultLike(Protocol):
    success: bool
    summary: str
    rolled_back: bool
    error_message: str


class _EvolutionCoordinatorLike(Protocol):
    def auto_evolve(self, snapshot: object) -> _EvolutionResultLike: ...


class _OrchestratorLike(Protocol):
    _memory_recorder: _MemoryRecorderLike
    _evolution_coordinator: _EvolutionCoordinatorLike | None
    config: object
    ctx: _OrchestratorContextLike
    mode_manager: _ModeManagerLike | None


def memory_save_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """메모리 저장 + 토큰 사용량 추적 + Hermes Self-Evolution."""
    from antigravity_k.engine.tokenizer import TokenEstimator

    # 메모리 저장
    memory_recorder = cast(_MemoryRecorderLike, getattr(orch, "_memory_recorder"))
    yield from memory_recorder.record(
        user_message=ctx.user_message,
        agent_output=ctx.agent_output,
        task_type=ctx.task_type,
        preferred_model=ctx.target_model or None,
    )

    # 토큰 사용량
    tokens_in = TokenEstimator.estimate_text(ctx.user_message + ctx.rag_context)
    tokens_out = TokenEstimator.estimate_text(ctx.agent_output)
    yield f"\n\n📊 **[Token Usage]** In: {tokens_in} tokens | Out: {tokens_out} tokens\n"

    # ─── Hermes Self-Evolution (QualityGate C/F 등급 시 자동 진화) ───
    # P2: config에서 self_evolution.auto_modify가 true일 때만 동작 (기본 false)
    # 질문 응답 중 스킬 파일이 자동 수정되어 diff가 응답에 섞이는 것을 방지
    try:
        _raw_cfg: object = orch.config or {}
        # amplification.self_evolution.enabled가 명시되면 우선, 아니면 기존 self_evolution.auto_modify 사용
        import antigravity_k.engine.orchestrator_handler_config as config_module

        amplification_section = cast(
            Callable[[_OrchestratorLike, str], dict[str, object]],
            getattr(config_module, "_amplification_section"),
        )
        _amp_se = amplification_section(orch, "self_evolution").get("enabled")
        config = cast(dict[str, object], _raw_cfg) if isinstance(_raw_cfg, dict) else {}
        raw_self_evolution = config.get("self_evolution")
        self_evolution = cast(dict[str, object], raw_self_evolution) if isinstance(raw_self_evolution, dict) else {}
        _sec_enabled = bool(self_evolution.get("auto_modify", False))
        if _amp_se is not None:
            _sec_enabled = bool(_amp_se)
        sec = cast(_EvolutionCoordinatorLike | None, getattr(orch, "_evolution_coordinator", None))
        if sec is not None and _sec_enabled and ctx.agent_output and len(ctx.agent_output.strip()) > 50:
            # QualityGate 평가 수행 (execution_mode 전달 — Phase 1 D5)
            exec_mode = orch.mode_manager.current_mode.value if orch.mode_manager is not None else None
            quality = orch.ctx.quality_gate.evaluate(
                task_type=ctx.task_type,
                user_request=ctx.user_message,
                agent_output=ctx.agent_output,
                execution_mode=exec_mode,
            )

            # C/F 등급일 때만 SEC 동작
            if quality.grade.value in ("retry", "fail"):
                logger.info(
                    "[SEC] 품질 기준 미달 감지 (grade=%s, score=%s) — Hermes Self-Evolution 시작",
                    quality.grade.value,
                    quality.score,
                )

                # 도구 호출 기록 수집
                tool_calls: list[dict[str, object]] = []
                if orch.ctx.tool_executor is not None:
                    try:
                        executor = cast(_ToolExecutorLike, orch.ctx.tool_executor)
                        tool_calls = list(executor.tool_call_history)
                    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - trace boundary
                        logger.warning("[SEC] tool_call_history 조회 실패 (non-critical)", exc_info=True)

                from antigravity_k.engine.self_evolution_coordinator import (
                    PerformanceSnapshot,
                )

                snapshot = PerformanceSnapshot(
                    user_message=ctx.user_message,
                    agent_output=ctx.agent_output[:500],
                    task_type=ctx.task_type,
                    quality_grade=quality.grade.value,
                    quality_score=quality.score,
                    quality_issues=quality.issues,
                    tool_calls=tool_calls,
                )

                evolution_result = sec.auto_evolve(snapshot)

                if evolution_result.success:
                    yield f"\n\n🧬 **[Self-Evolution]** {evolution_result.summary}\n"
                elif evolution_result.rolled_back:
                    logger.info("[SEC] Evolution rolled back: %s", evolution_result.error_message)
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - evolution boundary
        # SEC 실패가 메인 플로우를 막지 않도록 최소 로깅
        logger.warning("[SEC] Self-Evolution 실행 실패 (non-critical): %s", e, exc_info=True)
