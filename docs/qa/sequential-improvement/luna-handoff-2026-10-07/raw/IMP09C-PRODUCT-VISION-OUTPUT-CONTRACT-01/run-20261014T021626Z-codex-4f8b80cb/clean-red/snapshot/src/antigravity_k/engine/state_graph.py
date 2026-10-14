"""Ssak-Ai: 에이전트 상태 그래프 엔진 (AgentStateGraph).

==========================================================
오케스트레이터의 암묵적 분기 로직을 명시적 상태 전이 그래프로 구조화합니다.

아키텍처:
    - AgentState: 에이전트가 거치는 상태 (enum)
    - StateContext: 그래프 실행 중 공유되는 컨텍스트 데이터
    - AgentStateGraph: 상태 노드 + 전이 엣지 + 체크포인트 엔진

상태 전이 흐름:
    INIT → CONTEXT_ENRICH → CEO_ANALYZE → PRE_ROUTE → ROUTE
         ↓ simple/coding/reasoning
    → AGENT_EXECUTE → QUALITY_CHECK → REFLECT → MEMORY_SAVE → COMPLETE
         ↓ complex
    → PIPELINE_EXECUTE → MEMORY_SAVE → COMPLETE
         ↓ debate
    → DEBATE_EXECUTE → MEMORY_SAVE → COMPLETE

사용법:
    graph = AgentStateGraph()
    graph.add_node(AgentState.INIT, init_handler)
    graph.add_edge(AgentState.INIT, AgentState.CONTEXT_ENRICH)
    graph.add_conditional_edge(AgentState.ROUTE, route_decision_fn)

    ctx = StateContext(messages=messages)
    async for chunk in graph.execute(ctx):
        yield chunk
"""

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.task_state_store import TaskExecutionContext

logger = logging.getLogger("antigravity_k.engine.state_graph")

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


# ─── 에이전트 상태 정의 ──────────────────────────────────────────


class AgentState(Enum):
    """에이전트 실행 흐름의 각 상태."""

    INIT = "init"
    CONTEXT_ENRICH = "context_enrich"  # RAG, KI, 에피소딕 메모리 주입
    AUTO_LEARN = "auto_learn"  # 자율 학습 파이프라인
    SKILL_MATCH = "skill_match"  # 스킬 자동 매칭
    CEO_ANALYZE = "ceo_analyze"  # CEO 태스크 분석
    PRE_ROUTE = "pre_route"  # 불확실성 + 사용자 모델
    ROUTE = "route"  # 태스크 유형 라우팅
    AGENT_EXECUTE = "agent_execute"  # 단일 에이전트 실행
    CODE_REVIEW = "code_review"  # Freebuff-Style 코드 자동 리뷰
    COV_VERIFY = "cov_verify"  # Chain-of-Verification 자기검증
    PIPELINE_EXECUTE = "pipeline_execute"  # 멀티 스텝 파이프라인
    MAX_EXECUTE = "max_execute"  # MAX 모드 병렬 실행
    DEBATE_EXECUTE = "debate_execute"  # 토론 파이프라인
    AGI_CORE = "agi_core"  # AGI 코어 작업
    QUALITY_CHECK = "quality_check"  # 품질 게이트
    REFLECT = "reflect"  # 인지 성찰
    MEMORY_SAVE = "memory_save"  # 메모리 + 토큰 저장
    COMPLETE = "complete"  # 완료
    ERROR = "error"  # 에러


# ─── 상태 컨텍스트 (그래프 실행 중 공유 데이터) ────────────────────


@dataclass
class StateContext:
    """그래프 실행 중 모든 노드가 공유하는 컨텍스트.

    각 핸들러가 데이터를 읽고 쓰면서 상태를 전달합니다.
    """

    # 입력
    messages: list[dict[str, str]] = field(default_factory=list)
    user_message: str = ""
    target_model: str = ""
    max_steps: int = 15
    ephemeral_message: str | None = None

    # CEO 분석 결과
    analysis: dict[str, object] = field(default_factory=dict)
    task_type: str = "simple_chat"
    delegate_to: str = "SELF"
    refined_prompt: str = ""

    # 컨텍스트 데이터
    rag_context: str = ""
    custom_messages: list[dict[str, str]] = field(default_factory=list)

    # 실행 결과
    agent_output: str = ""
    approval_required: bool = False

    # 상태 추적
    current_state: AgentState = AgentState.INIT
    state_history: list[dict[str, object]] = field(default_factory=list)
    checkpoints: list[dict[str, object]] = field(default_factory=list)
    _routing_log: list[dict[str, object]] = field(default_factory=list)

    # 에러 복구 루프 추적
    retry_count: int = 0
    max_retries: int = 3
    validation_passed: bool = True
    _loop_back: bool = False
    # 품질 재시도 시 되돌아갈 원 실행 노드 — 없으면(기본 AGENT_EXECUTE)
    # MAX/PIPELINE/DEBATE 실패 재시도가 전부 단일 에이전트로 강등된다.
    execution_origin: "AgentState" = AgentState.AGENT_EXECUTE

    # 메타
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    error: str | None = None

    def transition_to(self, new_state: AgentState):
        """상태를 전이하고 이력을 기록합니다."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_history.append(
            {
                "from": old_state.value,
                "to": new_state.value,
                "timestamp": time.time(),
            },
        )
        logger.debug("[StateGraph] %s → %s", old_state.value, new_state.value)

    def save_checkpoint(self, label: str = ""):
        """현재 상태의 체크포인트를 저장합니다 (실패 시 복원용)."""
        checkpoint: dict[str, object] = {
            "label": label or self.current_state.value,
            "state": self.current_state.value,
            "task_type": self.task_type,
            "delegate_to": self.delegate_to,
            "messages_count": len(self.custom_messages),
            "timestamp": time.time(),
        }
        self.checkpoints.append(checkpoint)
        logger.debug("[StateGraph] Checkpoint saved: %s", checkpoint["label"])

    def get_duration_ms(self) -> float:
        """실행 시작부터 현재까지 경과 시간 (ms)."""
        return round((time.time() - self.started_at) * 1000, 1)


# ─── 상태 전이 엣지 ──────────────────────────────────────────────


@dataclass
class StateEdge:
    """두 상태 사이의 전이 엣지."""

    from_state: AgentState
    to_state: AgentState
    condition: str = ""  # 전이 조건 설명 (디버깅용)


# ─── 노드 핸들러 타입 ─────────────────────────────────────────────

# 핸들러 시그니처: (ctx: StateContext, orchestrator) -> Generator[str, None, Optional[str]]
# 반환값의 Generator는 스트리밍 청크를 yield
# Optional[str] return은 다음 상태 결정용 키 (조건부 전이에 사용)
NodeHandler = Callable[..., Generator[str, None, None] | None]


# ─── 에이전트 상태 그래프 엔진 ─────────────────────────────────────


class AgentStateGraph:
    """에이전트 실행 흐름을 관리하는 상태 그래프 엔진.

    기능:
    - 노드 등록 (상태별 핸들러)
    - 고정 엣지 (무조건 전이)
    - 조건부 엣지 (핸들러 반환값에 따라 분기)
    - 체크포인트 (실패 시 복원)
    - 실행 궤적 기록
    """

    def __init__(self) -> None:
        """Initialize the AgentStateGraph."""
        self._nodes: dict[AgentState, NodeHandler] = {}
        self._edges: dict[AgentState, AgentState] = {}  # 고정 전이
        self._conditional_edges: dict[AgentState, Callable[[StateContext], AgentState]] = {}  # 조건부 전이
        self._entry_state: AgentState = AgentState.INIT

    # ─── 그래프 정의 API ─────────────────────────────────────

    def add_node(self, state: AgentState, handler: NodeHandler):
        """상태에 핸들러를 등록합니다."""
        self._nodes[state] = handler
        return self

    def add_edge(self, from_state: AgentState, to_state: AgentState):
        """고정 전이 엣지를 추가합니다."""
        self._edges[from_state] = to_state
        return self

    def add_conditional_edge(
        self,
        from_state: AgentState,
        decision_fn: Callable[[StateContext], AgentState],
    ):
        """조건부 전이 엣지를 추가합니다.

        decision_fn은 StateContext를 받아 다음 AgentState를 반환합니다.
        """
        self._conditional_edges[from_state] = decision_fn
        return self

    def set_entry(self, state: AgentState):
        """진입 상태를 설정합니다."""
        self._entry_state = state
        return self

    @staticmethod
    def _task_execution_context(orchestrator: object) -> TaskExecutionContext | None:
        execution_context = getattr(orchestrator, "task_execution_context", None)
        if isinstance(execution_context, TaskExecutionContext):
            return execution_context
        return None

    def _record_execution_event(
        self,
        ctx: StateContext,
        orchestrator: object,
        event_type: str,
        from_state: str | None = None,
        to_state: str | None = None,
    ) -> None:
        execution_context = self._task_execution_context(orchestrator)
        if execution_context is None:
            return

        payload: dict[str, JsonValue] = {
            "trace_id": ctx.trace_id,
            "state": ctx.current_state.value,
            "task_type": ctx.task_type,
            "delegate_to": ctx.delegate_to,
            "retry_count": ctx.retry_count,
            "error": ctx.error,
        }
        if from_state is not None:
            payload["from_state"] = from_state
        if to_state is not None:
            payload["to_state"] = to_state

        try:
            _ = execution_context.state_store.append_execution_event(
                execution_context.task_id,
                event_type,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
        except sqlite3.Error as exc:
            logger.warning("[StateGraph] Failed to persist task event: %s", exc)

    def _transition_to(self, ctx: StateContext, orchestrator: object, new_state: AgentState) -> None:
        previous_state = ctx.current_state.value
        ctx.transition_to(new_state)
        self._record_execution_event(
            ctx,
            orchestrator,
            "state_transition",
            from_state=previous_state,
            to_state=new_state.value,
        )

    # ─── 그래프 실행 ─────────────────────────────────────────

    def execute(self, ctx: StateContext, orchestrator: object | None = None) -> Generator[str, None, None]:
        """상태 그래프를 실행합니다.

        각 노드의 핸들러를 순서대로 실행하고,
        핸들러의 yield를 스트리밍 청크로 전달합니다.

        Args:
            ctx: 공유 상태 컨텍스트
            orchestrator: OrchestratorAgent 인스턴스 (핸들러에서 사용)

        Yields:
            스트리밍 텍스트 청크

        """
        self._transition_to(ctx, orchestrator, self._entry_state)
        max_transitions = 50  # 무한 루프 방지

        for _ in range(max_transitions):
            current = ctx.current_state

            # 종료 상태 확인
            if current in (AgentState.COMPLETE, AgentState.ERROR):
                break

            # 핸들러 실행
            handler = self._nodes.get(current)
            if not handler:
                logger.warning("[StateGraph] No handler for state: %s", current.value)
                ctx.error = f"No handler registered for state: {current.value}"
                self._transition_to(ctx, orchestrator, AgentState.ERROR)
                break

            try:
                ctx.save_checkpoint()
                self._record_execution_event(ctx, orchestrator, "state_checkpoint")

                # 핸들러 실행 (Generator → yield 전파)
                gen = handler(ctx, orchestrator)
                if gen is not None:
                    for chunk in gen:
                        if current in (
                            AgentState.AGENT_EXECUTE,
                            AgentState.PIPELINE_EXECUTE,
                            AgentState.MAX_EXECUTE,
                            AgentState.DEBATE_EXECUTE,
                            AgentState.AGI_CORE,
                        ):
                            yield chunk
                        else:
                            yield ProgressChunk(chunk)

            except StopIteration:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
            except Exception as e:
                logger.exception("[StateGraph] Error in %s", current.value)
                ctx.error = str(e)
                self._transition_to(ctx, orchestrator, AgentState.ERROR)
                yield f"\n\n❌ **[State Graph Error]** {current.value} 단계에서 오류 발생: {e}\n"
                break

            # 핸들러가 스스로 종료 상태로 전이했다면 이를 존중한다.
            # (예: INIT에서 빈 메시지 감지 → COMPLETE 조기 반환.
            # 없으면 엣지 해상이 이를 덮어써 파이프라인이 계속 진행된다.)
            if ctx.current_state in (AgentState.COMPLETE, AgentState.ERROR):
                break

            # 다음 상태 결정
            next_state = self._resolve_next_state(current, ctx)
            if next_state is None:
                # 전이 정의 없음 → 완료
                self._transition_to(ctx, orchestrator, AgentState.COMPLETE)
                break

            self._transition_to(ctx, orchestrator, next_state)
        else:
            logger.error("[StateGraph] Max transitions (%s) reached!", max_transitions)
            ctx.error = "Maximum state transitions exceeded"
            self._transition_to(ctx, orchestrator, AgentState.ERROR)
            yield "\n\n⚠️ **[State Graph]** 최대 상태 전이 횟수 초과로 종료합니다.\n"

    def _resolve_next_state(self, current: AgentState, ctx: StateContext) -> AgentState | None:
        """현재 상태에서 다음 상태를 결정합니다."""
        # 1. 조건부 엣지 우선
        if current in self._conditional_edges:
            decision_fn = self._conditional_edges[current]
            try:
                return decision_fn(ctx)
            except Exception:
                logger.exception("[StateGraph] Decision function error at %s", current.value)
                return AgentState.ERROR

        # 2. 고정 엣지
        if current in self._edges:
            return self._edges[current]

        # 3. 전이 없음
        return None

    # ─── 디버깅/관찰성 ───────────────────────────────────────

    def get_graph_definition(self) -> dict[str, JsonValue]:
        """그래프 정의를 JSON 직렬화 가능한 형태로 반환합니다."""
        return {
            "nodes": [s.value for s in self._nodes],
            "edges": {s.value: t.value for s, t in self._edges.items()},
            "conditional_edges": [s.value for s in self._conditional_edges],
            "entry": self._entry_state.value,
        }

    def visualize(self) -> str:
        """그래프를 텍스트로 시각화합니다."""
        lines = ["[Agent State Graph]"]
        for state, handler in self._nodes.items():
            handler_name = getattr(handler, "__name__", str(handler))
            next_info = ""
            if state in self._edges:
                next_info = f" → {self._edges[state].value}"
            elif state in self._conditional_edges:
                next_info = " → (conditional)"
            lines.append(f"  [{state.value}] {handler_name}{next_info}")
        return "\n".join(lines)


# ─── 기본 그래프 빌더 ─────────────────────────────────────────────


def build_default_graph() -> AgentStateGraph:
    """Ssak-Ai의 기본 에이전트 상태 그래프를 구성합니다.

    핸들러는 orchestrator_handlers.py에서 제공됩니다.
    이 함수는 그래프 구조(노드+엣지)만 정의합니다.
    """
    graph = AgentStateGraph()
    _ = graph.set_entry(AgentState.INIT)

    # 고정 전이
    # ── 직렬 프리룰 단축 ──
    # CEO 분석을 가장 앞으로 옮긴다 — CEO는 user_message만 필요하다.
    # simple_chat으로 분류되면 컨텍스트 풍부화(RAG/코드트리)·자율학습·
    # 스킬매칭·불확실성 추정을 건너뛰고 바로 ROUTE로 간다 (조건부 엣지는
    # orchestrator_handler_graph에서 ceo_gate_decision으로 등록).
    _ = graph.add_edge(AgentState.INIT, AgentState.CEO_ANALYZE)
    _ = graph.add_edge(AgentState.CEO_ANALYZE, AgentState.CONTEXT_ENRICH)
    _ = graph.add_edge(AgentState.CONTEXT_ENRICH, AgentState.AUTO_LEARN)
    _ = graph.add_edge(AgentState.AUTO_LEARN, AgentState.SKILL_MATCH)
    _ = graph.add_edge(AgentState.SKILL_MATCH, AgentState.PRE_ROUTE)
    _ = graph.add_edge(AgentState.PRE_ROUTE, AgentState.ROUTE)

    # ROUTE → 조건부 전이 (핸들러에서 등록)
    # AGENT_EXECUTE, PIPELINE_EXECUTE, DEBATE_EXECUTE, MAX_EXECUTE → MEMORY_SAVE
    _ = graph.add_edge(AgentState.AGENT_EXECUTE, AgentState.COV_VERIFY)
    _ = graph.add_edge(AgentState.COV_VERIFY, AgentState.CODE_REVIEW)

    # Phase 5: COV_VERIFY 이후 바로 메모리 저장하지 않고 QUALITY_CHECK로 진행
    _ = graph.add_edge(AgentState.CODE_REVIEW, AgentState.QUALITY_CHECK)

    # QUALITY_CHECK 이후 조건부 전이(실패시 AGENT_EXECUTE 루프백, 성공시 MEMORY_SAVE)를
    # 핸들러 레벨(build_orchestrator_graph)에서 add_conditional_edge로 등록함

    _ = graph.add_edge(AgentState.MAX_EXECUTE, AgentState.COV_VERIFY)
    # 검증 없이 저장되던 위험 분기 — 가장 긴 실행(파이프라인/토론)이
    # 오히려 COV/품질 검증을 통과하지 않았다. AGENT/MAX와 동일하게 검증한다.
    _ = graph.add_edge(AgentState.PIPELINE_EXECUTE, AgentState.COV_VERIFY)
    _ = graph.add_edge(AgentState.DEBATE_EXECUTE, AgentState.COV_VERIFY)
    _ = graph.add_edge(AgentState.AGI_CORE, AgentState.COMPLETE)
    _ = graph.add_edge(AgentState.MEMORY_SAVE, AgentState.COMPLETE)

    return graph
