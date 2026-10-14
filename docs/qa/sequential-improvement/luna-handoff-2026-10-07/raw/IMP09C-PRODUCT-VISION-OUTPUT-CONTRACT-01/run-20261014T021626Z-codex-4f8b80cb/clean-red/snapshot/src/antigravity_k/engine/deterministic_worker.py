"""Ssak-Ai: Deterministic Worker (결정론적 실행 엔진).

=========================================================
LLM은 "무엇을 할지 판단"만 하고, 실제 실행은 Python이 담당.

핵심 개념:
  - LLM의 불확실성은 "판단" 단계에만 한정
  - 도구 호출, 파일 I/O, API 요청 등은 사전 정의된 Worker 레시피가 수행
  - 레시피는 입력/출력 스키마가 명확하여 100% 재현 가능

연구 근거:
  - DeterministicWorker Pattern (2025): LLM-as-Judge, Code-as-Executor
  - Structured Outputs + Constrained Decoding으로 판단 자체도 결정론적

사용법:
    worker = DeterministicWorker(model_manager)
    worker.register_recipe(StockLookupRecipe())
    result = await worker.execute("삼성전자 오늘 종가 알려줘")
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeAlias, cast, override

logger = logging.getLogger("antigravity_k.deterministic_worker")
JsonMap: TypeAlias = dict[str, object]


class ModelManagerLike(Protocol):
    def generate(self, **kwargs: object) -> object: ...


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_float(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _as_map(value: object) -> JsonMap:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[str, object], value)
    return dict(mapping)


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


# ─── 작업 유형 ───────────────────────────────────────────────────────


class TaskIntent(Enum):
    """Deterministic Worker가 처리할 수 있는 작업 유형."""

    STOCK_LOOKUP = "stock_lookup"  # 주가 조회
    WEATHER_CHECK = "weather_check"  # 날씨 조회
    WEB_SEARCH = "web_search"  # 웹 검색 + 요약
    FILE_OPERATION = "file_operation"  # 파일 읽기/쓰기
    CODE_GENERATION = "code_generation"  # 코드 생성
    DATA_ANALYSIS = "data_analysis"  # 데이터 분석
    UNKNOWN = "unknown"  # 분류 불가 → LLM 자유 생성


# ─── 데이터 구조 ─────────────────────────────────────────────────────


@dataclass
class WorkerDecision:
    """LLM이 내리는 판단 결과 (구조화된 JSON으로 강제)."""

    intent: TaskIntent
    parameters: JsonMap = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class WorkerResult:
    """레시피 실행 결과."""

    success: bool
    data: Any = None  # pyright: ignore[reportExplicitAny]
    formatted_output: str = ""
    execution_time_ms: float = 0.0
    recipe_name: str = ""
    error: str = ""


# ─── 레시피 인터페이스 ───────────────────────────────────────────────


class WorkerRecipe(ABC):
    """Deterministic Worker 레시피 기본 인터페이스.

    각 레시피는:
    1. 자신이 처리할 수 있는 intent를 선언
    2. 파라미터를 검증
    3. 결정론적으로 실행
    4. 결과를 구조화된 마크다운으로 포맷
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """레시피 이름."""

    @property
    @abstractmethod
    def intent(self) -> TaskIntent:
        """처리할 작업 유형."""

    @property
    @abstractmethod
    def parameter_schema(self) -> JsonMap:
        """JSON Schema 형태의 파라미터 정의."""

    @abstractmethod
    def validate(self, params: JsonMap) -> bool:
        """파라미터 유효성 검증."""

    @abstractmethod
    def execute(self, params: JsonMap) -> WorkerResult:
        """결정론적 실행."""

    def format_output(self, result: WorkerResult) -> str:
        """결과를 사용자 친화적 마크다운으로 포맷 (오버라이드 가능)."""
        if result.error:
            return f"> [!WARNING]\n> 실행 중 오류: {result.error}"
        return result.formatted_output or str(cast(object, result.data))


# ─── 내장 레시피: 웹 검색 ────────────────────────────────────────────


class WebSearchRecipe(WorkerRecipe):
    """웹 검색 + 결과 요약 레시피."""

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "web_search"

    @property
    @override
    def intent(self) -> TaskIntent:
        """Intent.

        Returns:
            TaskIntent: The taskintent result.

        """
        return TaskIntent.WEB_SEARCH

    @property
    @override
    def parameter_schema(self) -> JsonMap:
        """Parameter Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 쿼리"},
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    @override
    def validate(self, params: JsonMap) -> bool:
        """Validate.

        Args:
            params (dict[str, Any]): dict[str, Any] params.

        Returns:
            bool: The bool result.

        """
        return bool(_as_str(params.get("query")).strip())

    @override
    def execute(self, params: JsonMap) -> WorkerResult:
        """Execute.

        Args:
            params (dict[str, Any]): dict[str, Any] params.

        Returns:
            WorkerResult: The workerresult result.

        """
        start = time.time()
        try:
            from antigravity_k.tools.web_search import WebSearchTool

            tool = WebSearchTool()
            raw = tool.execute(query=_as_str(params.get("query")))
            elapsed = (time.time() - start) * 1000

            return WorkerResult(
                success=True,
                data=raw,
                formatted_output=raw,
                execution_time_ms=elapsed,
                recipe_name=self.name,
            )
        except Exception as e:
            logger.exception("Unhandled exception")
            elapsed = (time.time() - start) * 1000
            return WorkerResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
                recipe_name=self.name,
            )


class FileReadRecipe(WorkerRecipe):
    """파일 읽기 레시피."""

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "file_read"

    @property
    @override
    def intent(self) -> TaskIntent:
        """Intent.

        Returns:
            TaskIntent: The taskintent result.

        """
        return TaskIntent.FILE_OPERATION

    @property
    @override
    def parameter_schema(self) -> JsonMap:
        """Parameter Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "읽을 파일 경로"},
                "start_line": {"type": "integer", "default": 1},
                "end_line": {"type": "integer", "default": -1},
            },
            "required": ["path"],
        }

    @override
    def validate(self, params: JsonMap) -> bool:
        """Validate.

        Args:
            params (dict[str, Any]): dict[str, Any] params.

        Returns:
            bool: The bool result.

        """
        import os

        path = _as_str(params.get("path"))
        return bool(path) and os.path.exists(path)

    @override
    def execute(self, params: JsonMap) -> WorkerResult:
        """Execute.

        Args:
            params (dict[str, Any]): dict[str, Any] params.

        Returns:
            WorkerResult: The workerresult result.

        """
        start = time.time()
        try:
            path = _as_str(params.get("path"))
            start_line = _as_int(params.get("start_line"), 1)
            end_line = _as_int(params.get("end_line"), -1)

            with open(path, encoding="utf-8") as f:
                lines = f.readlines()

            if end_line == -1:
                end_line = len(lines)
            selected = lines[max(0, start_line - 1) : end_line]
            content = "".join(selected)

            elapsed = (time.time() - start) * 1000
            return WorkerResult(
                success=True,
                data={"path": path, "lines": len(selected), "content": content},
                formatted_output=f"```\n{content}\n```",
                execution_time_ms=elapsed,
                recipe_name=self.name,
            )
        except Exception as e:
            logger.exception("Unhandled exception")
            elapsed = (time.time() - start) * 1000
            return WorkerResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
                recipe_name=self.name,
            )


# ─── 메인 Deterministic Worker ───────────────────────────────────────


# LLM 판단용 JSON Schema (Ollama structured output으로 강제)
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [t.value for t in TaskIntent],
        },
        "parameters": {
            "type": "object",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "reasoning": {
            "type": "string",
        },
    },
    "required": ["intent", "parameters", "confidence"],
}


class DeterministicWorker:
    """LLM은 판단만, Python이 실행하는 결정론적 워커.

    파이프라인:
    1. 사용자 입력 → LLM에게 JSON Schema 강제 출력으로 판단 요청
    2. 판단 결과(intent + params) → 등록된 레시피에서 매칭
    3. 레시피가 결정론적으로 실행
    4. 실행 결과 → LLM이 사용자 친화적 답변으로 포맷

    이점:
    - 도구 호출 파싱 실패 0% (JSON Schema 강제)
    - 실행 결과 100% 재현 가능 (결정론적 레시피)
    - LLM은 가벼운 판단만 → 빠르고 저렴
    """

    def __init__(
        self,
        model_manager: object | None = None,
        judge_model: str = "",
        formatter_model: str = "",
    ):
        """Initialize the DeterministicWorker.

        Args:
            model_manager: model manager.
            judge_model (str): str judge model.
            formatter_model (str): str formatter model.

        """
        self._manager: ModelManagerLike | None = (
            cast(ModelManagerLike, model_manager) if model_manager is not None else None
        )
        self._judge_model: str = judge_model
        self._formatter_model: str = formatter_model
        self._recipes: dict[TaskIntent, WorkerRecipe] = {}

        # 내장 레시피 자동 등록
        self.register_recipe(WebSearchRecipe())
        self.register_recipe(FileReadRecipe())

    def register_recipe(self, recipe: WorkerRecipe) -> None:
        """레시피를 등록합니다."""
        self._recipes[recipe.intent] = recipe
        logger.info("[DeterministicWorker] 레시피 등록: %s (%s)", recipe.name, recipe.intent.value)

    def unregister_recipe(self, intent: TaskIntent) -> bool:
        """레시피를 해제합니다."""
        if intent in self._recipes:
            del self._recipes[intent]
            return True
        return False

    def list_recipes(self) -> list[JsonMap]:
        """등록된 레시피 목록을 반환합니다."""
        return [
            {
                "name": r.name,
                "intent": r.intent.value,
                "schema": r.parameter_schema,
            }
            for r in self._recipes.values()
        ]

    def judge(self, user_input: str) -> WorkerDecision:
        """LLM에게 사용자 의도를 판단하게 합니다 (JSON Schema 강제).

        Args:
            user_input: 사용자의 자연어 입력

        Returns:
            WorkerDecision: 구조화된 판단 결과

        """
        if not self._manager:
            return WorkerDecision(intent=TaskIntent.UNKNOWN, confidence=0.0)

        available_intents = [r.intent.value for r in self._recipes.values()]
        judge_prompt = (
            "[ROLE]\n당신은 사용자 의도 분류기입니다.\n\n"
            "[TASK]\n사용자의 입력을 분석하여 가장 적합한 작업 유형을 판단하세요.\n\n"
            f"사용 가능한 작업 유형: {', '.join(available_intents)}, unknown\n\n"
            "각 레시피의 파라미터:\n"
        )
        for recipe in self._recipes.values():
            props = recipe.parameter_schema.get("properties")
            prop_map = _as_mapping(props)
            param_parts: list[str] = []
            for key, value in prop_map.items():
                value_map = _as_mapping(value)
                description = value_map.get("description", value_map.get("type", ""))
                param_parts.append(f"{key}: {_as_str(description)}")
            param_desc = ", ".join(param_parts)
            judge_prompt += f"- {recipe.intent.value}: {param_desc}\n"

        judge_prompt += (
            f"\n사용자 입력: {user_input}\n\n위 입력에 가장 적합한 intent를 선택하고, 필요한 parameters를 추출하세요."
        )

        try:
            raw = self._manager.generate(
                prompt=judge_prompt,
                target=self._judge_model or None,
                task_type="SEARCH",  # 낮은 temperature로 정확한 판단
                response_format=DECISION_SCHEMA,
                max_tokens=300,
            )

            # JSON 파싱
            parsed_value: object = cast(object, json.loads(_as_str(raw).strip()))
            parsed = _as_map(parsed_value)
            intent_str = _as_str(parsed.get("intent"), "unknown")
            try:
                intent = TaskIntent(intent_str)
            except ValueError:
                intent = TaskIntent.UNKNOWN

            return WorkerDecision(
                intent=intent,
                parameters=_as_map(parsed.get("parameters")),
                confidence=_as_float(parsed.get("confidence"), 0.5),
                reasoning=_as_str(parsed.get("reasoning")),
            )
        except Exception:
            logger.exception("[DeterministicWorker] 판단 실패")
            return WorkerDecision(intent=TaskIntent.UNKNOWN, confidence=0.0)

    def execute(self, decision: WorkerDecision) -> WorkerResult:
        """판단 결과에 따라 결정론적으로 실행합니다."""
        recipe = self._recipes.get(decision.intent)
        if not recipe:
            return WorkerResult(
                success=False,
                error=f"레시피 없음: {decision.intent.value}",
                recipe_name="none",
            )

        if not recipe.validate(decision.parameters):
            return WorkerResult(
                success=False,
                error=f"파라미터 검증 실패: {decision.parameters}",
                recipe_name=recipe.name,
            )

        logger.info("[DeterministicWorker] 실행: %s (params: %s)", recipe.name, decision.parameters)
        return recipe.execute(decision.parameters)

    def format_response(
        self,
        user_input: str,
        result: WorkerResult,
    ) -> str:
        """실행 결과를 사용자 친화적 답변으로 포맷합니다.

        LLM을 사용하여 구조화된 데이터를 자연스러운 한국어 답변으로 변환합니다.
        """
        if not result.success:
            return f"> [!WARNING]\n> 작업 실행 중 오류가 발생했습니다: {result.error}"

        if not self._manager:
            return result.formatted_output

        from antigravity_k.engine.prompt_builder import PromptBuilder

        pb = PromptBuilder()
        format_prompt = pb.structured_prompt(
            role="정보 정리 전문가",
            task=(
                f"아래의 원시 데이터를 사용자의 질문에 맞게 "
                f"간결하고 정확한 한국어 답변으로 정리하세요.\n\n"
                f"사용자 질문: {user_input}\n\n"
                f"원시 데이터:\n{result.formatted_output[:2000]}"
            ),
            constraints=[
                "반드시 한국어로 답변하세요.",
                "핵심 수치와 데이터를 마크다운 테이블로 정리하세요.",
                "출처를 명시하세요.",
                "불필요한 서론 없이 핵심부터 시작하세요.",
            ],
            output_format="마크다운 테이블 + 핵심 요약",
            few_shot=pb.get_task_few_shots("SEARCH"),
        )

        try:
            formatted = self._manager.generate(
                prompt=format_prompt,
                target=self._formatter_model or None,
                task_type="SEARCH",
                max_tokens=2048,
            )
            return _as_str(formatted, result.formatted_output)
        except Exception:
            logger.exception("[DeterministicWorker] 포맷 실패")
            return result.formatted_output

    def run(self, user_input: str) -> WorkerResult:
        """전체 파이프라인을 동기 실행합니다.

        1. Judge: LLM이 의도 분류
        2. Execute: 레시피가 결정론적 실행
        3. Format: LLM이 결과를 포맷

        Args:
            user_input: 사용자의 자연어 입력

        Returns:
            WorkerResult with formatted_output 포함

        """
        # 1) 판단
        decision = self.judge(user_input)
        logger.info(
            "[DeterministicWorker] 판단 완료: %s (신뢰도: %s)",
            decision.intent.value,
            decision.confidence,
        )

        if decision.intent == TaskIntent.UNKNOWN or decision.confidence < 0.4:
            return WorkerResult(
                success=False,
                error="deterministic_worker_bypass",
                recipe_name="unknown",
            )

        # 2) 실행
        result = self.execute(decision)

        # 3) 포맷
        if result.success:
            result.formatted_output = self.format_response(user_input, result)

        return result

    def status(self) -> JsonMap:
        """워커 상태를 반환합니다."""
        return {
            "registered_recipes": len(self._recipes),
            "recipes": self.list_recipes(),
            "judge_model": self._judge_model,
            "formatter_model": self._formatter_model,
        }


"""
Ssak-Ai Deterministic Worker — LLM judges, Python executes.
"""
