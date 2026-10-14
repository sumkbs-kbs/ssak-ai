"""Ssak-Ai: Rule Engine for Deterministic Routing.
=====================================================

StateGraph의 비결정론적 LLM 기반 라우팅을 규칙 엔진으로 대체합니다.

핵심 원칙:
1. 모든 라우팅 결정은 명시적 규칙(rules)으로만 수행
2. LLM 분석(analysis)은 규칙의 입력 데이터로만 사용, 결정 로직은 규칙에 위임
3. 규칙은 우선순위 기반 평가, 첫 번째 매칭 규칙이 승리
4. 규칙은 YAML/JSON으로 외부화 가능, 핫 리로드 지원
5. 디버깅용 결정 로그 필수
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sized
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import TypeAlias, cast, final

from antigravity_k.engine.state_graph import AgentState, StateContext

logger = logging.getLogger("antigravity_k.engine.rule_engine")

RuleValue: TypeAlias = str | int | float | bool | None | list["RuleValue"] | dict[str, "RuleValue"]
JsonObject: TypeAlias = dict[str, object]


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, dict) else {}


class RuleOperator(Enum):
    """규칙 조건 연산자."""

    EQUALS = "eq"
    NOT_EQUALS = "neq"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    REGEX_MATCH = "regex"
    REGEX_NOT_MATCH = "not_regex"
    IN_LIST = "in"
    NOT_IN_LIST = "not_in"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_EQUAL = "lte"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "not_empty"
    STARTS_WITH = "startswith"
    ENDS_WITH = "endswith"


@dataclass
class RuleCondition:
    """단일 규칙 조건."""

    field: str  # StateContext 필드 경로 (점 표기법 지원: "analysis.task_type")
    operator: RuleOperator
    value: RuleValue = None
    case_sensitive: bool = False

    def evaluate(self, ctx: StateContext) -> bool:
        """컨텍스트에 대해 조건을 평가합니다."""
        actual = self._get_field_value(ctx)
        return self._compare(actual, self.value)

    def _get_field_value(self, ctx: StateContext) -> object:
        """점 표기법으로 필드 값을 추출합니다."""
        parts = self.field.split(".")
        obj: object = ctx

        for part in parts:
            if obj is None:
                return None
            if isinstance(obj, dict):
                obj = cast(JsonObject, obj).get(part)
            elif hasattr(obj, part):
                obj = cast(object, object.__getattribute__(obj, part))
            else:
                return None
        return obj

    def _compare(self, actual: object, expected: object) -> bool:
        """연산자에 따라 비교를 수행합니다."""
        if actual is None and expected is None:
            return self.operator in (RuleOperator.EQUALS, RuleOperator.IS_EMPTY)

        if actual is None:
            return self.operator in (RuleOperator.NOT_EQUALS, RuleOperator.IS_EMPTY)

        op = self.operator

        if op == RuleOperator.EQUALS:
            return actual == expected
        elif op == RuleOperator.NOT_EQUALS:
            return actual != expected
        elif op == RuleOperator.CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected.lower() in actual.lower() if not self.case_sensitive else expected in actual
            if isinstance(actual, (list, tuple, set)):
                return expected in actual
            return False
        elif op == RuleOperator.NOT_CONTAINS:
            # NOT_CONTAINS: 직접 구현으로 재귀 방지
            if isinstance(actual, str) and isinstance(expected, str):
                return expected.lower() not in actual.lower() if not self.case_sensitive else expected not in actual
            if isinstance(actual, (list, tuple, set)):
                return expected not in actual
            return True
        elif op == RuleOperator.REGEX_MATCH:
            if isinstance(actual, str) and isinstance(expected, str):
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(expected, actual, flags))
            return False
        elif op == RuleOperator.REGEX_NOT_MATCH:
            return not self._compare(actual, expected) if self.operator == RuleOperator.REGEX_MATCH else True
        elif op == RuleOperator.IN_LIST:
            if isinstance(expected, (list, tuple, set)):
                return actual in expected
            return False
        elif op == RuleOperator.NOT_IN_LIST:
            if isinstance(expected, (list, tuple, set)):
                return actual not in expected
            return False
        elif op == RuleOperator.GREATER_THAN:
            return (
                float(actual) > float(expected)
                if isinstance(actual, (int, float)) and isinstance(expected, (int, float))
                else False
            )
        elif op == RuleOperator.GREATER_EQUAL:
            return (
                float(actual) >= float(expected)
                if isinstance(actual, (int, float)) and isinstance(expected, (int, float))
                else False
            )
        elif op == RuleOperator.LESS_THAN:
            return (
                float(actual) < float(expected)
                if isinstance(actual, (int, float)) and isinstance(expected, (int, float))
                else False
            )
        elif op == RuleOperator.LESS_EQUAL:
            return (
                float(actual) <= float(expected)
                if isinstance(actual, (int, float)) and isinstance(expected, (int, float))
                else False
            )
        elif op == RuleOperator.IS_TRUE:
            return bool(actual) is True
        elif op == RuleOperator.IS_FALSE:
            return bool(actual) is False
        elif op == RuleOperator.IS_EMPTY:
            if actual is None:
                return True
            if isinstance(actual, str):
                return len(actual) == 0
            if isinstance(actual, (list, dict, set, tuple)):
                return len(cast(Sized, cast(object, actual))) == 0
            return False
        elif op == RuleOperator.IS_NOT_EMPTY:
            # IS_NOT_EMPTY: 직접 구현으로 재귀 방지
            if actual is None:
                return False
            if isinstance(actual, str):
                return len(actual) > 0
            if isinstance(actual, (list, dict, set, tuple)):
                return len(cast(Sized, cast(object, actual))) > 0
            return True
        elif op == RuleOperator.STARTS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return (
                    actual.startswith(expected) if self.case_sensitive else actual.lower().startswith(expected.lower())
                )
            return False
        elif op == RuleOperator.ENDS_WITH:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.endswith(expected) if self.case_sensitive else actual.lower().endswith(expected.lower())
            return False

        return False


@dataclass
class Rule:
    """단일 라우팅 규칙.

    모든 조건이 만족되어야 규칙이 매칭됩니다 (AND 논리).
    """

    name: str
    description: str = ""
    conditions: list[RuleCondition] = field(default_factory=list)
    target_state: AgentState = AgentState.AGENT_EXECUTE
    priority: int = 100  # 낮을수록 우선순위 높음
    enabled: bool = True
    metadata: JsonObject = field(default_factory=dict)

    def matches(self, ctx: StateContext) -> bool:
        """모든 조건이 만족되는지 확인합니다."""
        if not self.enabled:
            return False
        if not self.conditions:
            return True  # 조건 없으면 항상 매칭 (기본 규칙용)
        return all(cond.evaluate(ctx) for cond in self.conditions)

    def to_dict(self) -> JsonObject:
        """규칙을 직렬화합니다."""
        return {
            "name": self.name,
            "description": self.description,
            "conditions": [
                {
                    "field": c.field,
                    "operator": c.operator.value,
                    "value": c.value,
                    "case_sensitive": c.case_sensitive,
                }
                for c in self.conditions
            ],
            "target_state": self.target_state.value,
            "priority": self.priority,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Rule":
        """딕셔너리에서 규칙을 생성합니다."""
        conditions: list[RuleCondition] = []
        raw_conditions = data.get("conditions", [])
        condition_items = cast(list[object], raw_conditions) if isinstance(raw_conditions, list) else []
        for raw_condition in condition_items:
            c = _as_mapping(raw_condition)
            conditions.append(
                RuleCondition(
                    field=str(c["field"]),
                    operator=RuleOperator(str(c["operator"])),
                    value=cast(RuleValue, c.get("value")),
                    case_sensitive=bool(c.get("case_sensitive", False)),
                )
            )
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            conditions=conditions,
            target_state=AgentState(str(data["target_state"])),
            priority=int(cast(str | int | float, data.get("priority", 100))),
            enabled=bool(data.get("enabled", True)),
            metadata=dict(_as_mapping(data.get("metadata", {}))),
        )


@final
class RuleEngine:
    """결정론적 라우팅 규칙 엔진.

    규칙들을 우선순위 순으로 평가하여 첫 번째 매칭 규칙의 target_state를 반환합니다.
    """

    def __init__(self, rules: list[Rule] | None = None, config_path: str | Path | None = None):
        self._rules: list[Rule] = rules or []
        self._config_path: Path | None = Path(config_path) if config_path else None
        self._decision_log: list[JsonObject] = []

        # 기본 규칙 로드
        if not self._rules:
            self._load_default_rules()

        # 설정 파일에서 로드
        if self._config_path and self._config_path.exists():
            self.load_from_file(self._config_path)

        # 우선순위 정렬 (낮은 숫자 = 높은 우선순위)
        self._rules.sort(key=lambda r: r.priority)

    def _load_default_rules(self) -> None:
        """기본 내장 규칙들을 로드합니다."""
        self._rules = [
            # 1. AGI Core / 하드웨어 리포트 (최우선)
            Rule(
                name="agi_core_hardware",
                description="AGI Core 또는 하드웨어 리포트 태스크",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.IN_LIST, ["agi_core", "hardware_report"]),
                ],
                target_state=AgentState.AGI_CORE,
                priority=10,
            ),
            # 2. 명시적 파이프라인 (사용자가 단계 나열)
            Rule(
                name="explicit_pipeline",
                description="사용자 프롬프트에 명시적 단계(번호/불릿)가 포함된 경우",
                conditions=[
                    RuleCondition("analysis.pipeline", RuleOperator.IS_NOT_EMPTY, None),
                ],
                target_state=AgentState.PIPELINE_EXECUTE,
                priority=20,
            ),
            # 3. MAX 모드 후보 (복잡/대규모/아키텍처/마이그레이션)
            Rule(
                name="max_mode_complex",
                description="complex 태스크이거나 CEO 분석에서 max_mode=True",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.EQUALS, "complex"),
                    RuleCondition("analysis.max_mode", RuleOperator.EQUALS, True),
                ],
                target_state=AgentState.MAX_EXECUTE,
                priority=30,
            ),
            Rule(
                name="max_mode_large_scale",
                description="대규모/아키텍처/마이그레이션/리팩토링 키워드 포함",
                conditions=[
                    RuleCondition(
                        "user_message",
                        RuleOperator.REGEX_MATCH,
                        r"(대규모|전면|아키텍처|마이그레이션|refactor|architecture|migrate|redesign|리팩토링|구조개선|전체\s*재작성|full\s*rewrite)",
                    ),
                ],
                target_state=AgentState.MAX_EXECUTE,
                priority=35,
            ),
            # 4. 코딩/리즈닝 중 MAX 모드 후보 (대규모 특성)
            Rule(
                name="max_mode_coding_large",
                description="코딩/리즈닝 태스크 중 대규모 특성 감지",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.IN_LIST, ["coding", "reasoning"]),
                    RuleCondition("analysis.max_mode", RuleOperator.EQUALS, True),
                ],
                target_state=AgentState.MAX_EXECUTE,
                priority=40,
            ),
            # 5. 토론 태스크
            Rule(
                name="debate_task",
                description="토론/논쟁 유형 태스크",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.EQUALS, "debate"),
                ],
                target_state=AgentState.DEBATE_EXECUTE,
                priority=45,
            ),
            # 6. 코딩 태스크 → AGENT_EXECUTE (단일 에이전트)
            Rule(
                name="coding_task",
                description="코딩 태스크",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.EQUALS, "coding"),
                ],
                target_state=AgentState.AGENT_EXECUTE,
                priority=50,
            ),
            # 7. 리즈닝 태스크 → AGENT_EXECUTE (단일 에이전트)
            Rule(
                name="reasoning_task",
                description="리즈닝/분석 태스크",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.EQUALS, "reasoning"),
                ],
                target_state=AgentState.AGENT_EXECUTE,
                priority=55,
            ),
            # 8. 단순 채팅 → AGENT_EXECUTE (SELF 위임)
            Rule(
                name="simple_chat",
                description="단순 대화/질문 응답",
                conditions=[
                    RuleCondition("analysis.task_type", RuleOperator.EQUALS, "simple_chat"),
                ],
                target_state=AgentState.AGENT_EXECUTE,
                priority=60,
            ),
            # 9. 기본값 (매칭되는 규칙 없음) - AGENT_EXECUTE
            Rule(
                name="default_fallback",
                description="기본 폴백: 단일 에이전트 실행",
                conditions=[],  # 조건 없음 = 항상 매칭
                target_state=AgentState.AGENT_EXECUTE,
                priority=1000,
            ),
        ]

    def load_from_file(self, path: str | Path) -> None:
        """YAML/JSON 파일에서 규칙을 로드합니다."""
        path = Path(path)
        if not path.exists():
            logger.warning("[RuleEngine] Config file not found: %s", path)
            return

        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix in (".yaml", ".yml"):
                import yaml

                data = cast(object, yaml.safe_load(content))
            else:
                data = cast(object, json.loads(content))

            if isinstance(data, dict) and "rules" in data:
                config = cast(JsonObject, data)
                raw_rules = config["rules"]
                rule_items = cast(list[object], raw_rules) if isinstance(raw_rules, list) else []
                for raw_rule in rule_items:
                    rule = Rule.from_dict(_as_mapping(raw_rule))
                    # 기존 규칙과 이름이 같으면 교체, 없으면 추가
                    existing_idx = next((i for i, r in enumerate(self._rules) if r.name == rule.name), None)
                    if existing_idx is not None:
                        self._rules[existing_idx] = rule
                    else:
                        self._rules.append(rule)
                logger.info("[RuleEngine] Loaded %s rules from %s", len(rule_items), path)
        except Exception as e:
            logger.exception("[RuleEngine] Failed to load rules from %s: %s", path, e)

    def save_to_file(self, path: str | Path) -> None:
        """현재 규칙을 파일로 저장합니다."""
        path = Path(path)
        data = {"rules": [r.to_dict() for r in self._rules]}

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix in (".yaml", ".yml"):
                import yaml

                _ = path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            else:
                _ = path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("[RuleEngine] Saved %s rules to %s", len(self._rules), path)
        except Exception as e:
            logger.exception("[RuleEngine] Failed to save rules to %s: %s", path, e)

    def add_rule(self, rule: Rule) -> None:
        """규칙을 추가하거나 기존 규칙을 교체합니다."""
        existing_idx = next((i for i, r in enumerate(self._rules) if r.name == rule.name), None)
        if existing_idx is not None:
            self._rules[existing_idx] = rule
        else:
            self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def remove_rule(self, name: str) -> bool:
        """이름으로 규칙을 제거합니다."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                _ = self._rules.pop(i)
                return True
        return False

    def get_rule(self, name: str) -> Rule | None:
        """이름으로 규칙을 조회합니다."""
        for rule in self._rules:
            if rule.name == name:
                return rule
        return None

    def evaluate(self, ctx: StateContext) -> AgentState:
        """컨텍스트를 평가하여 다음 상태를 결정합니다.

        우선순위 순으로 규칙을 평가하여 첫 번째 매칭되는 규칙의 target_state를 반환합니다.
        """
        start_time = time.time()

        for rule in self._rules:
            if not rule.enabled:
                continue

            matched = rule.matches(ctx)
            decision_time_ms = round((time.time() - start_time) * 1000, 2)

            # 결정 로그 기록
            decision_record: JsonObject = {
                "timestamp": time.time(),
                "rule_name": rule.name,
                "matched": matched,
                "target_state": rule.target_state.value,
                "priority": rule.priority,
                "evaluation_time_ms": decision_time_ms,
            }
            self._decision_log.append(cast(JsonObject, cast(object, decision_record)))

            if matched:
                logger.info(
                    "[RuleEngine] Rule '%s' matched (priority=%s) → %s (%.2fms)",
                    rule.name,
                    rule.priority,
                    rule.target_state.value,
                    decision_time_ms,
                )
                return rule.target_state

        # 매칭되는 규칙 없음 (이론상 default_fallback 때문에 발생 안 함)
        logger.warning("[RuleEngine] No rule matched, falling back to AGENT_EXECUTE")
        return AgentState.AGENT_EXECUTE

    def get_decision_log(self) -> list[JsonObject]:
        """결정 로그를 반환합니다."""
        return self._decision_log.copy()

    def clear_log(self) -> None:
        """결정 로그를 초기화합니다."""
        self._decision_log.clear()

    def get_rules_summary(self) -> list[JsonObject]:
        """규칙 요약을 반환합니다 (디버깅용)."""
        return [
            {
                "name": r.name,
                "description": r.description,
                "priority": r.priority,
                "enabled": r.enabled,
                "target_state": r.target_state.value,
                "condition_count": len(r.conditions),
            }
            for r in self._rules
        ]

    def visualize(self) -> str:
        """규칙 세트를 텍스트로 시각화합니다."""
        lines = ["[RuleEngine] Routing Rules (priority order):"]
        for rule in self._rules:
            status = "✅" if rule.enabled else "❌"
            cond_desc = ", ".join([f"{c.field} {c.operator.value} {c.value}" for c in rule.conditions]) or "(always)"
            lines.append(f"  P{rule.priority:3d} {status} [{rule.name}] → {rule.target_state.value}")
            lines.append(f"       {cond_desc}")
        return "\n".join(cond_desc for cond_desc in lines)


# ─── 편의 함수 ───

_default_engine: RuleEngine | None = None


def get_rule_engine(config_path: str | Path | None = None) -> RuleEngine:
    """싱글톤 RuleEngine 인스턴스를 반환합니다."""
    global _default_engine
    if _default_engine is None:
        config_path = config_path or Path("config/rules.yaml")
        _default_engine = RuleEngine(config_path=config_path)
    return _default_engine


def route_decision_deterministic(ctx: StateContext) -> AgentState:
    """결정론적 라우팅 결정 함수 (StateGraph용).

    StateGraph의 add_conditional_edge에 등록할 수 있는 함수입니다.
    """
    # 파이프라인 명시적 단계 합성 (RuleEngine 평가 전 실행)
    handlers_module = import_module("antigravity_k.engine.orchestrator_handlers")
    synthesize = cast(Callable[[StateContext], object], getattr(handlers_module, "_synthesize_explicit_pipeline"))
    _ = synthesize(ctx)
    engine = get_rule_engine()
    return engine.evaluate(ctx)


def route_decision_with_log(ctx: StateContext) -> AgentState:
    """결정 로그를 포함한 결정 함수 (디버깅용)."""
    engine = get_rule_engine()
    result = engine.evaluate(ctx)
    # 마지막 결정 로그를 컨텍스트에 저장 (디버깅용)
    routing_log = cast(list[JsonObject], getattr(ctx, "_routing_log"))
    routing_log.append(
        {
            "state": "ROUTE",
            "target": engine.get_decision_log()[-1] if engine.get_decision_log() else None,
        }
    )
    return result
