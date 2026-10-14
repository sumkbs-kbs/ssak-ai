"""Ssak-Ai: 에이전트 트레이싱 시스템 (Agent Tracing).

=======================================================
에이전트의 추론 경로, 도구 호출, 성능 메트릭을 구조화된 트레이스로 기록합니다.

OpenTelemetry 호환 패턴을 따르며, 외부 옵저버빌리티 도구
(Arize Phoenix, Langfuse 등) 연동을 위한 기반을 제공합니다.

아키텍처:
    - Span: 개별 작업 단위 (도구 호출, LLM 추론, 검증 등)
    - Trace: Span들의 트리 구조 (하나의 요청 처리 전체)
    - AgentTracer: 트레이스 수집/저장/조회 관리자
    - @traced: 함수에 자동 트레이싱을 부여하는 데코레이터

사용법:
    tracer = AgentTracer()

    # 데코레이터 방식
    @traced(tracer, span_type="tool_call")
    def my_tool(query):
        ...

    # 컨텍스트 매니저 방식
    with tracer.span("llm_inference", {"model": "qwen3"}) as span:
        result = call_llm(prompt)
        span.set_output(result)
"""

import inspect
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import TypeAlias, cast

logger = logging.getLogger("antigravity_k.engine.tracing")
JsonMap: TypeAlias = dict[str, object]


# ─── Span (개별 작업 단위) ──────────────────────────────────────


@dataclass
class Span:
    """트레이스 내의 개별 작업 단위.

    OpenTelemetry Span 모델을 단순화한 구조입니다.
    """

    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trace_id: str = ""
    parent_span_id: str | None = None
    name: str = ""
    span_type: str = "generic"  # tool_call, llm_inference, validation, planning, search

    # 타이밍
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0

    # 입출력
    input_data: JsonMap = field(default_factory=dict)
    output_data: JsonMap = field(default_factory=dict)

    # 메타데이터
    attributes: JsonMap = field(default_factory=dict)
    status: str = "ok"  # ok, error
    error_message: str = ""

    # 메트릭
    token_count: int = 0

    def set_output(self, output: object) -> None:
        """출력 데이터를 설정합니다."""
        if isinstance(output, str):
            self.output_data["text"] = output[:500]  # 트레이스 크기 제한
        elif isinstance(output, dict):
            values = cast(dict[str, object], output)
            self.output_data = {key: str(value)[:200] for key, value in values.items()}
        else:
            self.output_data["value"] = str(output)[:500]

    def set_error(self, error: Exception) -> None:
        """에러 정보를 기록합니다."""
        self.status = "error"
        self.error_message = f"{type(error).__name__}: {error}"

    def finish(self) -> None:
        """Span을 종료하고 duration을 계산합니다."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 1)

    def to_dict(self) -> JsonMap:
        """JSON 직렬화 가능한 딕셔너리로 변환합니다."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "type": self.span_type,
            "start_time": (datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else ""),
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error_message,
            "input": self.input_data,
            "output": self.output_data,
            "attributes": self.attributes,
            "token_count": self.token_count,
        }


# ─── Trace (요청 전체) ──────────────────────────────────────────


@dataclass
class Trace:
    """하나의 요청 처리 전체를 나타내는 트레이스."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    root_span_id: str | None = None
    spans: list[Span] = field(default_factory=list)

    # 메타
    query: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    total_duration_ms: float = 0.0

    # 집계 메트릭
    total_tokens: int = 0
    tool_calls: int = 0
    errors: int = 0

    def add_span(self, span: Span) -> None:
        """Span을 트레이스에 추가합니다."""
        span.trace_id = self.trace_id
        self.spans.append(span)

        # 집계 업데이트
        self.total_tokens += span.token_count
        if span.span_type == "tool_call":
            self.tool_calls += 1
        if span.status == "error":
            self.errors += 1

    def finish(self) -> None:
        """트레이스를 종료하고 집계 메트릭을 계산합니다."""
        self.ended_at = time.time()
        if self.started_at:
            self.total_duration_ms = round((self.ended_at - self.started_at) * 1000, 1)

    def to_dict(self) -> JsonMap:
        """To Dict.

        Returns:
            dict[str, object]: The trace dictionary result.

        """
        return {
            "trace_id": self.trace_id,
            "query": self.query[:200],
            "started_at": (datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else ""),
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "spans": [s.to_dict() for s in self.spans],
        }

    def summary(self) -> str:
        """사람이 읽을 수 있는 트레이스 요약."""
        lines = [
            f"📊 Trace {self.trace_id[:8]}... | {self.total_duration_ms:.0f}ms",
            f"   Query: {self.query[:80]}",
            f"   Spans: {len(self.spans)} | Tools: {self.tool_calls} | Errors: {self.errors}",
        ]
        for s in self.spans:
            icon = "❌" if s.status == "error" else "✅"
            lines.append(f"   {icon} [{s.span_type}] {s.name} — {s.duration_ms:.0f}ms")
        return "\n".join(lines)


# ─── AgentTracer (트레이서 관리자) ────────────────────────────────


class AgentTracer:
    """에이전트 트레이싱 시스템.

    트레이스를 수집, 저장, 조회하는 중앙 관리자입니다.
    대시보드 연동 및 외부 옵저버빌리티 도구 내보내기를 지원합니다.
    """

    def __init__(self, persist_dir: str | None = None, max_traces: int = 100):
        """Initialize the AgentTracer.

        Args:
            persist_dir (str): str persist dir.
            max_traces (int): int max traces.

        """
        self._traces: list[Trace] = []
        self._active_trace: Trace | None = None
        self._span_stack: list[Span] = []
        self._max_traces: int = max_traces
        self._persist_dir: str | None = persist_dir

        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)

    # ─── Trace 라이프사이클 ──────────────────────────────────

    def start_trace(self, query: str = "") -> Trace:
        """새 트레이스를 시작합니다."""
        trace = Trace(query=query, started_at=time.time())
        self._active_trace = trace
        return trace

    def end_trace(self) -> Trace | None:
        """현재 트레이스를 종료하고 저장합니다."""
        if not self._active_trace:
            return None

        self._active_trace.finish()
        self._traces.append(self._active_trace)

        # 용량 제한
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces :]

        # 디스크 저장
        if self._persist_dir:
            self._persist_trace(self._active_trace)

        trace = self._active_trace
        self._active_trace = None
        self._span_stack.clear()

        logger.debug("[Tracer] Trace 완료: %s", trace.summary())
        return trace

    # ─── Span 컨텍스트 매니저 ────────────────────────────────

    @contextmanager
    def span(self, name: str, attributes: JsonMap | None = None, span_type: str = "generic"):
        """Span을 컨텍스트 매니저로 생성합니다.

        Usage:
            with tracer.span("search_jina", {"query": q}, span_type="tool_call") as s:
                result = jina_search(q)
                s.set_output(result)
        """
        s = Span(
            name=name,
            span_type=span_type,
            start_time=time.time(),
            attributes=attributes or {},
            parent_span_id=self._span_stack[-1].span_id if self._span_stack else None,
        )
        self._span_stack.append(s)

        try:
            yield s
        except Exception as e:
            s.set_error(e)
            raise
        finally:
            s.finish()
            _ = self._span_stack.pop()
            if self._active_trace:
                self._active_trace.add_span(s)

    # ─── Span 수동 시작/종료 ────────────────────────────

    def start_span(self, name: str, attributes: JsonMap | None = None, span_type: str = "generic") -> Span:
        """Create and start a span manually."""
        s = Span(
            name=name,
            span_type=span_type,
            start_time=time.time(),
            attributes=attributes or {},
            parent_span_id=self._span_stack[-1].span_id if self._span_stack else None,
        )
        self._span_stack.append(s)
        return s

    def end_span(self, span: Span) -> None:
        """Finish a manually started span."""
        span.finish()
        if span in self._span_stack:
            self._span_stack.remove(span)
        if self._active_trace:
            self._active_trace.add_span(span)

    # ─── 조회 ────────────────────────────────────────────────

    def get_recent_traces(self, n: int = 10) -> list[JsonMap]:
        """최근 N개 트레이스를 반환합니다."""
        return [t.to_dict() for t in self._traces[-n:]]

    def get_performance_stats(self) -> JsonMap:
        """성능 통계를 반환합니다."""
        if not self._traces:
            return {"message": "트레이스 없음"}

        durations = [t.total_duration_ms for t in self._traces if t.total_duration_ms > 0]
        error_traces = [t for t in self._traces if t.errors > 0]

        return {
            "total_traces": len(self._traces),
            "avg_duration_ms": round(sum(durations) / max(len(durations), 1), 1),
            "p95_duration_ms": round(
                sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
                1,
            ),
            "error_rate": f"{len(error_traces) / len(self._traces) * 100:.1f}%",
            "avg_tool_calls": round(sum(t.tool_calls for t in self._traces) / len(self._traces), 1),
            "total_tokens": sum(t.total_tokens for t in self._traces),
        }

    # ─── 내보내기 ────────────────────────────────────────────

    def export_jsonl(self, filepath: str) -> None:
        """트레이스를 JSONL 형식으로 내보냅니다 (Arize Phoenix, Langfuse 호환)."""
        with open(filepath, "w", encoding="utf-8") as f:
            for trace in self._traces:
                _ = f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
        logger.info("[Tracer] %s개 트레이스 내보내기: %s", len(self._traces), filepath)

    def _persist_trace(self, trace: Trace) -> None:
        """트레이스를 디스크에 저장합니다."""
        if not self._persist_dir:
            return
        try:
            filepath = os.path.join(self._persist_dir, f"trace_{trace.trace_id}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("[Tracer] 트레이스 저장 실패")


# ─── @traced 데코레이터 ──────────────────────────────────────────


def traced(tracer: AgentTracer, span_type: str = "generic", name: str | None = None):
    """함수에 자동 트레이싱을 부여하는 데코레이터.

    Usage:
        @traced(tracer, span_type="tool_call")
        def search(query: str):
            ...

        @traced(tracer, span_type="llm_inference", name="main_inference")
        async def infer(prompt: str):
            ...
    """

    def decorator(func: Callable[..., object]) -> Callable[..., object]:
        span_name = name or func.__name__

        @wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            with tracer.span(span_name, {"args_count": len(args)}, span_type=span_type) as s:
                result = func(*args, **kwargs)
                s.set_output(result)
                return result

        @wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            with tracer.span(span_name, {"args_count": len(args)}, span_type=span_type) as s:
                result = await cast(Awaitable[object], func(*args, **kwargs))
                s.set_output(result)
                return result

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ─── 글로벌 트레이서 인스턴스 ─────────────────────────────────────

_global_tracer: AgentTracer | None = None


def get_tracer(persist_dir: str | None = None) -> AgentTracer:
    """글로벌 트레이서 인스턴스를 반환합니다."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = AgentTracer(persist_dir=persist_dir)
    return _global_tracer
