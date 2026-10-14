"""Orchestrator streaming execution logic.

run_stream / run_sync 의 실제 구현을 제공합니다.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Generator, Iterable, Iterator, Mapping
from typing import Callable, Protocol, cast, runtime_checkable

from antigravity_k.engine.chat_stream_events import FinalChunk, ProgressChunk, chat_stream_events_enabled
from antigravity_k.engine.state_graph import AgentState, StateContext
from antigravity_k.engine.task_context_snapshot import (
    ContextSnapshotStoreError,
    save_task_context_snapshot,
)
from antigravity_k.engine.task_execution_context import TaskExecutionContext

logger = logging.getLogger("antigravity_k.orchestrator.stream")


class _AuthoritativeFactLike(Protocol):
    key: str
    source: str
    scope: str
    value: str


class _MemoryManagerLike(Protocol):
    def authoritative_project_fact_for_query(self, user_text: str) -> _AuthoritativeFactLike | None: ...

    def prefetch_all(self, user_text: str) -> str: ...

    def sync_all(self, user_text: str, output: str, metadata: dict[str, object] | None = None) -> object: ...


class _ContextLike(Protocol):
    memory_manager: _MemoryManagerLike
    user_model: object | None


class _CompressionResultLike(Protocol):
    compressed_messages: list[dict[str, str]]
    user_message: str | None


class _CompressorLike(Protocol):
    def should_compress(self, messages: list[dict[str, str]]) -> bool: ...

    def compress(self, messages: list[dict[str, str]]) -> _CompressionResultLike: ...

    def needs_compression(self, messages: list[dict[str, str]]) -> bool: ...

    def usage_percent(self, messages: list[dict[str, str]]) -> float: ...

    def adaptive_compress(self, messages: list[dict[str, str]], task_type: str) -> list[dict[str, str]]: ...


class _StateGraphLike(Protocol):
    def execute(self, ctx: StateContext, orchestrator: _OrchestratorLike | None = None) -> Iterator[str]: ...


class _OrchestratorLike(Protocol):
    manager: object
    ctx: _ContextLike
    task_execution_context: TaskExecutionContext | None

    def trajectory_compressor_for(self, target_model: str) -> _CompressorLike | None: ...

    def context_compressor_for(self, target_model: str) -> _CompressorLike | None: ...


@runtime_checkable
class _StreamingModelManager(Protocol):
    def stream_generate(self, prompt: str, target: str, **kwargs: object) -> Iterator[str]: ...


def _latest_user_text(orch: _OrchestratorLike, messages: list[dict[str, str]]) -> str:
    resolver = cast(Callable[[list[dict[str, str]]], str], getattr(orch, "_latest_user_text"))
    return resolver(messages)


def _set_last_agent_output(orch: _OrchestratorLike, output: str) -> None:
    setattr(orch, "_last_agent_output", output)


def _state_graph(orch: _OrchestratorLike) -> _StateGraphLike | None:
    return cast(_StateGraphLike | None, getattr(orch, "_state_graph", None))


def _render_self_capability_response(orch: _OrchestratorLike) -> str:
    renderer = cast(Callable[[], str], getattr(orch, "_render_self_capability_response"))
    return renderer()


def _benchmark_context(orch: _OrchestratorLike) -> dict[str, object] | None:
    execution_context = orch.task_execution_context
    if execution_context is None:
        return None
    try:
        checkpoint = execution_context.state_store.get_last_checkpoint(execution_context.task_id)
        if checkpoint is None:
            return None
        context_json = checkpoint["context_json"]
        payload = cast(object, json.loads(context_json))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _is_direct_benchmark(context: dict[str, object] | None) -> bool:
    if context is None or context.get("benchmark_read_only") is not True:
        return False
    return not _has_expected_tools(context)


def _has_expected_tools(context: dict[str, object] | None) -> bool:
    if context is None:
        return False
    expected_tools = context.get("expected_tools", ())
    if isinstance(expected_tools, str):
        return bool(expected_tools.strip())
    if not isinstance(expected_tools, (list, tuple, set)):
        return False
    return any(str(tool).strip() for tool in cast(Iterable[object], expected_tools))


def _is_direct_response(context: dict[str, object] | None) -> bool:
    return context is not None and context.get("direct_response") is True


def _direct_response_task_type(user_text: str) -> str:
    return (
        "code"
        if re.search(r"(코드|함수|구현|python|javascript|typescript|function|implement|code)", user_text, re.I)
        else "chat"
    )


def _expected_tool_task_type(context: dict[str, object] | None, user_text: str) -> str:
    if context is None:
        return _direct_response_task_type(user_text)
    expected_tools = context.get("expected_tools", ())
    if isinstance(expected_tools, str):
        return "search" if expected_tools == "web_search" else _direct_response_task_type(user_text)
    if isinstance(expected_tools, (list, tuple, set)) and "web_search" in cast(Iterable[object], expected_tools):
        return "search"
    return _direct_response_task_type(user_text)


def _stream_direct_benchmark(
    orch: _OrchestratorLike,
    user_text: str,
    target_model: str,
) -> Generator[str, None, None]:
    prompt = (
        "[LOCAL BENCHMARK MODE]\n"
        "Return a complete final answer to the user request. Use no tools and do not modify files.\n"
        "Do not output hidden reasoning, <think> blocks, plans, or agent status messages.\n\n"
        f"User request:\n{user_text}\n\n"
        "Final answer:\n"
    )
    output = ""
    manager = orch.manager
    chunks: Iterable[str]
    if isinstance(manager, _StreamingModelManager):
        chunks = manager.stream_generate(
            prompt=prompt,
            target=target_model,
            task_type="benchmark",
            max_tokens=4096,
        )
    else:
        stream_generate = cast(Callable[..., Iterable[str]] | None, getattr(manager, "stream_generate", None))
        if not callable(stream_generate):
            raise RuntimeError("benchmark stream requires a model manager")
        chunks = stream_generate(
            prompt=prompt,
            target=target_model,
            task_type="benchmark",
            max_tokens=4096,
        )
    for chunk in chunks:
        text = str(chunk)
        output += text
        yield text
    _set_last_agent_output(orch, output)
    if output and chat_stream_events_enabled():
        yield FinalChunk(output)


def _count_map(value: object) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {key: item for key, item in raw.items() if isinstance(key, str) and isinstance(item, int)}


def _extract_learned_preferences(orch: _OrchestratorLike) -> dict[str, object] | None:
    """UserIntentModeler 프로파일에서 학습된 선호도를 추출합니다 (작업 5).

    GlobalMemoryProvider.sync_turn()이 이 metadata를 받아
    preferences/patterns로 영속화합니다.
    """
    try:
        user_model = orch.ctx.user_model
        if user_model is None:
            return None
        profile = cast(Mapping[str, object], getattr(user_model, "_profile", {}))
        stats = profile.get("stats")
        if not isinstance(stats, Mapping):
            return None
        stats_map = cast(Mapping[str, object], stats)

        prefs: dict[str, str] = {}

        # 언어 선호
        lang_counts = _count_map(stats_map.get("language_pref", {}))
        if lang_counts:
            top_lang = max(lang_counts, key=lambda key: lang_counts[key])
            if lang_counts[top_lang] >= 3:
                lang_map = {"korean": "ko", "english": "en", "mixed": "mixed"}
                prefs["response_language"] = lang_map.get(top_lang, "mixed")

        # 도메인
        domain_counts = _count_map(stats_map.get("domain", {}))
        if domain_counts:
            top_domain = max(domain_counts, key=lambda key: domain_counts[key])
            if domain_counts[top_domain] >= 3:
                prefs["task_domain"] = top_domain

        # 스킬 수준
        skill_counts = _count_map(stats_map.get("skill_level", {}))
        if skill_counts:
            top_skill = max(skill_counts, key=lambda key: skill_counts[key])
            if skill_counts[top_skill] >= 3:
                skill_map = {
                    "beginner": "beginner",
                    "intermediate": "intermediate",
                    "expert": "advanced",
                    "advanced": "advanced",
                }
                prefs["explanation_level"] = skill_map.get(top_skill, "intermediate")

        style_counts = _count_map(stats_map.get("comm_style", {}))
        if style_counts:
            top_style = max(style_counts, key=lambda key: style_counts[key])
            if style_counts[top_style] >= 3 and top_style in {"concise", "detailed"}:
                prefs["response_detail"] = top_style

        if prefs:
            return {"learned_preference_facts": prefs}
        return None
    except Exception:
        logger.debug("선호도 추출 실패 (non-critical)", exc_info=True)
        return None


def _persist_stream_compress_event(orch: object, record: object) -> None:
    """Best-effort persist of stream-pre compress telemetry (CTX-03)."""
    from antigravity_k.engine.context_compress_observability import CompressTelemetryRecord
    from antigravity_k.engine.task_execution_context import TaskExecutionContext

    if not isinstance(record, CompressTelemetryRecord):
        return
    execution_context = getattr(orch, "task_execution_context", None)
    if not isinstance(execution_context, TaskExecutionContext):
        return
    try:
        _ = execution_context.state_store.append_execution_event(
            execution_context.task_id,
            record.event_type(),
            record.payload_json(),
        )
    except Exception:  # noqa: BLE001
        logger.warning("stream compress telemetry persist failed", exc_info=True)


def run_stream(
    orch: object,
    messages: list[dict[str, str]],
    target_model: str,
    max_steps: int = 15,
    ephemeral_message: str | None = None,
) -> Generator[str, None, None]:
    """State Graph 기반 멀티 에이전트 스트리밍 실행.

    Args:
        orch: OrchestratorAgent 인스턴스
        messages: 대화 메시지 목록
        target_model: 대상 모델
        max_steps: 최대 단계 수
        ephemeral_message: 임시 메시지

    Yields:
        str: 스트리밍 응답 청크
    """
    orch = cast(_OrchestratorLike, orch)
    benchmark_context = _benchmark_context(orch)
    if _is_direct_benchmark(benchmark_context):
        yield from _stream_direct_benchmark(orch, _latest_user_text(orch, messages), target_model)
        return
    if _has_expected_tools(benchmark_context):
        from antigravity_k.engine.tool_loop import ToolLoopEngine

        user_text = _latest_user_text(orch, messages)
        tool_loop = ToolLoopEngine(orch)
        yield from tool_loop.run_loop(
            messages,
            "SELF",
            _expected_tool_task_type(benchmark_context, user_text),
            max_steps=max_steps,
            target_model=target_model,
            direct_response=False,
        )
        if tool_loop.last_output and chat_stream_events_enabled():
            yield FinalChunk(tool_loop.last_output)
        return
    if _is_direct_response(benchmark_context):
        from antigravity_k.engine.tool_loop import ToolLoopEngine

        user_text = _latest_user_text(orch, messages)
        tool_loop = ToolLoopEngine(orch)
        yield from tool_loop.run_loop(
            messages,
            "SELF",
            _direct_response_task_type(user_text),
            max_steps=2,
            target_model=target_model,
            direct_response=True,
        )
        if tool_loop.last_output and chat_stream_events_enabled():
            yield FinalChunk(tool_loop.last_output)
        return

    # ─── Self-Capability Fast Path ───
    try:
        from antigravity_k.engine.self_capability import (
            is_self_capability_request,
        )

        if is_self_capability_request(_latest_user_text(orch, messages)):
            response = _render_self_capability_response(orch)
            _set_last_agent_output(orch, response)
            yield response
            if chat_stream_events_enabled():
                yield FinalChunk(response)
            return
    except ImportError:
        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
    except (AttributeError, TypeError) as e:
        logger.warning("Self-capability fast path skipped: %s", e)

    user_text = _latest_user_text(orch, messages)
    authoritative_fact = orch.ctx.memory_manager.authoritative_project_fact_for_query(user_text)
    if authoritative_fact is not None:
        from antigravity_k.engine.tool_loop import ToolLoopEngine

        recalled = (
            "[Recalled Memory]\n"
            f"[resolved:{authoritative_fact.key} source={authoritative_fact.source} "
            f"scope={authoritative_fact.scope}] {authoritative_fact.value}"
        )
        direct_messages = [{"role": "system", "content": recalled}, *messages]
        tool_loop = ToolLoopEngine(orch)
        yield from tool_loop.run_loop(
            direct_messages,
            "SELF",
            "chat",
            max_steps=2,
            target_model=target_model,
            direct_response=True,
        )
        if tool_loop.last_output and chat_stream_events_enabled():
            yield FinalChunk(tool_loop.last_output)
        return

    # ─── State Graph Fallback ───
    state_graph = _state_graph(orch)
    if state_graph is None:
        from antigravity_k.engine.orchestrator_handlers import (
            build_orchestrator_graph,
        )

        state_graph = build_orchestrator_graph()
        setattr(orch, "_state_graph", state_graph)

    # ─── Memory Prefetch: 대화 시작 전 관련 기억 주입 ───
    try:
        user_text = _latest_user_text(orch, messages)

        # --- Hermes Synergy: Preflight Validator ---
        from antigravity_k.engine.engine_profile import EngineProfile
        from antigravity_k.engine.preflight_validator import PreflightValidator

        validator = PreflightValidator(orch.manager)
        is_valid, reject_reason, profile = validator.validate(user_text)
        if not is_valid:
            yield f"✈️ [Preflight 거부]\n{reject_reason}"
            return

        # P1: 모드 메시지는 코딩/복잡한 작업에만 간략하게 표시 (simple_chat에는 생략)
        # 단순 질문(인사, 날씨, 정보 조회)에는 방해가 되므로 출력하지 않음
        user_text_lower = user_text.lower()
        _simple_patterns = ["안녕", "고마워", "누구", "뭐해", "hello", "hi ", "thanks"]
        _is_simple_chat = len(user_text) < 30 and any(p in user_text_lower for p in _simple_patterns)
        if not _is_simple_chat and profile == EngineProfile.FAST_PROTOTYPER:
            yield ProgressChunk("🚀 **[빠른 프로토타이핑 모드]**\n\n")
        elif not _is_simple_chat:
            yield ProgressChunk("🛡️ **[정밀 엔지니어링 모드]**\n\n")
        # -------------------------------------------

        recalled = orch.ctx.memory_manager.prefetch_all(user_text)
        if recalled:
            messages = list(messages)  # 원본 불변
            messages.insert(
                1 if len(messages) > 1 else 0,
                {"role": "system", "content": f"[Recalled Memory]\n{recalled}"},
            )
    except ImportError:
        logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
    except (AttributeError, RuntimeError, ValueError, TypeError) as e:
        logger.warning("Memory prefetch error (non-critical): %s", e, exc_info=True)

    # ─── Trajectory / Context compress (CTX-03: no silent fail-open) ───
    # Compress failures here mark limited degrade; ToolLoop final hard-limit gate
    # still halts provider/mutation when the serialized prompt remains over budget.
    from antigravity_k.engine.context_compress_observability import (
        ComponentTokenSnapshot,
        CompressFailureCode,
        CompressTelemetryRecord,
        ElapsedTimer,
        decide_post_compress_policy,
        ui_status_line,
    )

    context_compacted = False
    compress_degraded = False
    timer = ElapsedTimer()
    traj_strategy = "trajectory"
    try:
        trajectory_compressor = orch.trajectory_compressor_for(target_model)
        if trajectory_compressor and trajectory_compressor.should_compress(messages):
            result = trajectory_compressor.compress(messages)
            context_compacted = result.compressed_messages != messages
            messages = result.compressed_messages
            if result.user_message:
                yield ProgressChunk(f"\n{result.user_message}\n\n")
                logger.info("[Orchestrator] %s", result.user_message)
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        compress_degraded = True
        logger.warning(
            "Trajectory compression failed (limited degrade; hard-limit gated later): %s",
            e,
            exc_info=True,
        )
        outcome = decide_post_compress_policy(compress_failed=True, over_hard_limit=False)
        record = CompressTelemetryRecord(
            outcome=outcome,
            trigger="stream_pre",
            strategy=traj_strategy,
            digest=None,
            elapsed_ms=timer.elapsed_ms(),
            failure_code=CompressFailureCode.COMPRESS_EXCEPTION.value,
            message=str(e),
        )
        yield ProgressChunk(ui_status_line(record))
        _persist_stream_compress_event(orch, record)

    timer = ElapsedTimer()
    try:
        ctx_compressor = orch.context_compressor_for(target_model)
        if ctx_compressor and ctx_compressor.needs_compression(messages):
            strategy = None
            suggest = getattr(ctx_compressor, "suggest_strategy", None)
            if callable(suggest):
                try:
                    strategy = suggest(messages)
                except Exception:  # noqa: BLE001
                    strategy = None
            strategy = str(strategy) if strategy else "adaptive:GENERAL"
            before_tokens = float(ctx_compressor.usage_percent(messages))
            tokens_before = ComponentTokenSnapshot(
                messages=sum(len(str(m.get("content", ""))) // 4 for m in messages),
            )
            compressed_messages = ctx_compressor.adaptive_compress(messages, task_type="GENERAL")
            context_compacted = context_compacted or compressed_messages != messages
            messages = compressed_messages
            after_tokens = float(ctx_compressor.usage_percent(messages))
            outcome = decide_post_compress_policy(compress_failed=False, over_hard_limit=False)
            record = CompressTelemetryRecord(
                outcome=outcome,
                trigger="stream_pre",
                strategy=strategy,
                digest=None,
                elapsed_ms=timer.elapsed_ms(),
                usage_before_pct=before_tokens,
                usage_after_pct=after_tokens,
                tokens_before=tokens_before,
                tokens_after=ComponentTokenSnapshot(
                    messages=sum(len(str(m.get("content", ""))) // 4 for m in messages),
                ),
            )
            yield ProgressChunk(ui_status_line(record))
            _persist_stream_compress_event(orch, record)
            logger.info(
                "[Orchestrator] Context compressed: %.0f%% → %.0f%% strategy=%s",
                before_tokens,
                after_tokens,
                strategy,
            )
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        # Limited degrade for read/continue path; ToolLoop hard-limit still halt-closes.
        compress_degraded = True
        logger.warning(
            "Context compression failed (limited degrade; hard-limit gated later): %s",
            e,
            exc_info=True,
        )
        outcome = decide_post_compress_policy(compress_failed=True, over_hard_limit=False)
        record = CompressTelemetryRecord(
            outcome=outcome,
            trigger="stream_pre",
            strategy="adaptive:GENERAL",
            digest=None,
            elapsed_ms=timer.elapsed_ms(),
            failure_code=CompressFailureCode.ADAPTIVE_COMPRESS_ERROR.value,
            message=str(e),
        )
        yield ProgressChunk(ui_status_line(record))
        _persist_stream_compress_event(orch, record)

    _ = compress_degraded  # surfaced via events; tool_loop re-checks hard limit

    execution_context = orch.task_execution_context
    if context_compacted and isinstance(execution_context, TaskExecutionContext):
        try:
            _ = save_task_context_snapshot(
                execution_context.state_store,
                execution_context.task_id,
                messages,
                target_model,
            )
        except ContextSnapshotStoreError as error:
            logger.warning("Task context snapshot failed: %s", error, exc_info=True)

    # ─── State Context 생성 및 그래프 실행 ───
    ctx = StateContext(
        messages=messages,
        target_model=target_model,
        max_steps=max_steps,
        ephemeral_message=ephemeral_message,
    )

    logger.info("[Orchestrator] State Graph 실행 시작 (trace_id=%s)", ctx.trace_id)

    state_graph = _state_graph(orch)
    if state_graph is None:
        return
    yield from state_graph.execute(ctx, orchestrator=orch)

    # ─── 에이전트 출력 동기화 ───
    if ctx.agent_output:
        _set_last_agent_output(orch, ctx.agent_output)
    if ctx.agent_output and not ctx.approval_required:
        # Memory Sync: 턴 완료 후 모든 메모리 제공자에 동기화
        try:
            # 작업 5: 사용자 프로파일에서 학습된 선호도를 추출하여 metadata로 전달
            _sync_metadata = _extract_learned_preferences(orch)
            _ = orch.ctx.memory_manager.sync_all(
                _latest_user_text(orch, messages),
                ctx.agent_output,
                metadata=_sync_metadata,
            )
        except (RuntimeError, ConnectionError, ValueError) as e:
            logger.warning("Memory sync error (non-critical): %s", e, exc_info=True)

    logger.info(
        "[Orchestrator] State Graph 완료: %s, %s개 전이, %sms",
        ctx.current_state.value,
        len(ctx.state_history),
        ctx.get_duration_ms(),
    )
    if ctx.agent_output and ctx.current_state is AgentState.COMPLETE and ctx.error is None:
        if chat_stream_events_enabled():
            yield FinalChunk(ctx.agent_output)


def run_sync(
    orch: object,
    messages: list[dict[str, str]],
    target_model: str,
    max_steps: int = 15,
) -> str:
    """동기식 실행 (커맨드 팔레트 등에서 사용).

    Args:
        orch: OrchestratorAgent 인스턴스
        messages: 대화 메시지 목록
        target_model: 대상 모델
        max_steps: 최대 단계 수

    Returns:
        str: 전체 응답 텍스트
    """
    return "".join(run_stream(orch, messages, target_model, max_steps))
