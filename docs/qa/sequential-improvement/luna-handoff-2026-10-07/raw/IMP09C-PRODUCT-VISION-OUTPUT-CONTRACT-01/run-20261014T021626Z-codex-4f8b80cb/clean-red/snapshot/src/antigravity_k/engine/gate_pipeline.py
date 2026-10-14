"""GatePipeline — 우선순위 기반 다단계 도구 실행 게이트.

====================================================
IronClaw approval.rs + Engine V2 gate/pipeline.rs 패턴 이식.

핵심 패턴:
- ExecutionGate 추상 프로토콜: name(), priority(), evaluate() 인터페이스
- Priority-Sorted Pipeline: 게이트를 우선순위순으로 순차 평가
- GateDecision 3분기: Allow / Pause(reason, resume_kind) / Deny(reason)
- 기존 ToolCallGuardrailController를 RateLimitGate로 래핑

게이트 우선순위:
    P50:  RateLimitGate     — 레이트 리밋 (기존 guardrails 래핑)
    P80:  CostBudgetGate    — 비용 예산 게이트 (CostGuard 래핑)
    P100: ApprovalGate      — 도구별 승인 정책
    P150: SecurityPolicyGate — 보안 정책 (SecurityPolicyEngine 래핑)
    P200: CapabilityGate    — 능력 정책 (AutonomousCapabilityPolicy 래핑)

사용법:
    pipeline = GatePipeline()
    pipeline.add_gate(RateLimitGate(guardrails))
    pipeline.add_gate(ApprovalGate())

    ctx = GateContext(tool_name="run_bash_command", args={"command": "ls"})
    decision = await pipeline.evaluate(ctx)
    if decision.is_denied:
        inject_error(decision.reason)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, TypeAlias, runtime_checkable

logger = logging.getLogger("antigravity_k.engine.gate_pipeline")

GateValue: TypeAlias = str | int | float | bool | None | list["GateValue"] | dict[str, "GateValue"]


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def _empty_gate_args() -> dict[str, GateValue]:
    return {}


class _GuardrailDecisionLike(Protocol):
    should_halt: bool
    message: str
    code: str


class _GuardrailsLike(Protocol):
    def before_call(self, tool_name: str, args: Mapping[str, object]) -> _GuardrailDecisionLike: ...


class _CostDecisionLike(Protocol):
    allowed: bool
    reason: str
    estimated_cost_usd: float
    remaining_budget_usd: float
    daily_spend_usd: float


class _CostGuardLike(Protocol):
    def check_budget(
        self,
        *,
        model: str,
        tokens_in: int,
        tokens_out: int,
        user_id: str,
    ) -> _CostDecisionLike: ...


class _SecurityPolicyLike(Protocol):
    def is_command_allowed(self, command: str) -> bool: ...

    def is_domain_allowed(self, domain: str) -> bool: ...


# ── 게이트 판정 ──


class GateAction(str, Enum):
    """게이트 판정 결과."""

    ALLOW = "allow"
    PAUSE = "pause"  # 사용자 승인 대기
    DENY = "deny"  # 즉시 거부


class ResumeKind(str, Enum):
    """Pause 후 재개 유형."""

    APPROVAL = "approval"  # 사용자 승인
    RETRY = "retry"  # 자동 재시도 (시간 경과 후)


@dataclass(frozen=True)
class GateDecision:
    """게이트 평가 결과."""

    action: GateAction = GateAction.ALLOW
    reason: str = ""
    gate_name: str = ""
    resume_kind: ResumeKind | None = None
    allow_always: bool = False  # "항상 허용" 옵션 제공 여부
    metadata: dict[str, GateValue] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        """Check if allowed.

        Returns:
            bool: The bool result.

        """
        return self.action == GateAction.ALLOW

    @property
    def is_paused(self) -> bool:
        """Check if paused.

        Returns:
            bool: The bool result.

        """
        return self.action == GateAction.PAUSE

    @property
    def is_denied(self) -> bool:
        """Check if denied.

        Returns:
            bool: The bool result.

        """
        return self.action == GateAction.DENY

    def to_dict(self) -> dict[str, GateValue]:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "action": self.action.value,
            "reason": self.reason,
            "gate_name": self.gate_name,
            "resume_kind": self.resume_kind.value if self.resume_kind else None,
            "allow_always": self.allow_always,
        }


# ── 게이트 컨텍스트 ──


@dataclass
class GateContext:
    """게이트 평가에 필요한 컨텍스트."""

    tool_name: str
    args: Mapping[str, object] = field(default_factory=_empty_gate_args)
    user_id: str = "default"
    session_id: str = ""
    execution_mode: str = "interactive"  # interactive / autonomous / container
    auto_approved_tools: frozenset[str] = field(default_factory=frozenset)
    source_channel: str = "web"
    # When True, RateLimitGate skips ToolCallGuardrailController.before_call
    # because the caller (tool_loop) already evaluated it for this invocation.
    guardrail_prechecked: bool = False


# ── ExecutionGate 프로토콜 ──


@runtime_checkable
class ExecutionGate(Protocol):
    """도구 실행 게이트 프로토콜.

    IronClaw Engine V2의 ExecutionGate 트레이트를 Python Protocol로 이식.
    """

    def name(self) -> str:
        """게이트 이름."""
        ...

    def priority(self) -> int:
        """평가 우선순위 (낮은 값 = 먼저 실행)."""
        ...

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """게이트 평가. Allow/Pause/Deny 반환."""
        ...


# ── 기본 게이트 구현 ──


class RateLimitGate:
    """기존 ToolCallGuardrailController를 래핑하는 게이트.

    Priority: 50 (가장 먼저 실행 — 빠른 거부).
    """

    def __init__(self, guardrails: _GuardrailsLike | None = None) -> None:
        """Initialize the RateLimitGate.

        Args:
            guardrails: guardrails.

        """
        self._guardrails: _GuardrailsLike | None = guardrails

    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "rate_limit"

    def priority(self) -> int:
        """Priority.

        Returns:
            int: The int result.

        """
        return 50

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """Evaluate.

        Args:
            ctx (GateContext): GateContext ctx.

        Returns:
            GateDecision: The gatedecision result.

        """
        # PLAN 모드: 읽기 전용 도구가 아니면 모두 차단 (Phase 1 D5: ctx.execution_mode는 OrchestratorAgent가 GateContext 생성 시 설정)
        if ctx.execution_mode == "plan":
            from antigravity_k.engine.execution_mode import PLAN_ALLOWED_TOOLS

            if ctx.tool_name not in PLAN_ALLOWED_TOOLS:
                return GateDecision(
                    action=GateAction.DENY,
                    reason=(
                        f"[PLAN MODE] '{ctx.tool_name}' 도구는 계획 수립 모드에서 실행할 수 없습니다. "
                        f"읽기 전용 도구만 허용됩니다."
                    ),
                    gate_name=self.name(),
                )

        # BUILD 모드: restricted 도구만 승인 필요
        if ctx.execution_mode == "build":
            from antigravity_k.engine.execution_mode import BUILD_RESTRICTED_TOOLS

            if ctx.tool_name in BUILD_RESTRICTED_TOOLS:
                return GateDecision(
                    action=GateAction.PAUSE,
                    reason=f"도구 '{ctx.tool_name}'은(는) BUILD 모드에서 승인이 필요합니다.",
                    gate_name=self.name(),
                    resume_kind=ResumeKind.APPROVAL,
                    allow_always=True,
                )

        if self._guardrails is None:
            return GateDecision(gate_name=self.name())

        # tool_loop already ran before_call for this allow-path invocation —
        # skip the duplicate policy/rate check (A4) without dropping PLAN/BUILD
        # mode gates above or SecurityPolicyGate later in the pipeline.
        if ctx.guardrail_prechecked:
            return GateDecision(gate_name=self.name())

        decision = self._guardrails.before_call(ctx.tool_name, dict(ctx.args))
        if decision.should_halt:
            return GateDecision(
                action=GateAction.DENY,
                reason=decision.message,
                gate_name=self.name(),
                metadata={"guardrail_code": decision.code},
            )

        return GateDecision(gate_name=self.name())


class CostBudgetGate:
    """CostGuard를 래핑하는 비용 예산 게이트.

    Priority: 80 (레이트 리밋 후, 승인 전).
    """

    def __init__(self, cost_guard: _CostGuardLike | None = None) -> None:
        """Initialize the CostBudgetGate.

        Args:
            cost_guard: cost guard.

        """
        self._cost_guard: _CostGuardLike | None = cost_guard

    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "cost_budget"

    def priority(self) -> int:
        """Priority.

        Returns:
            int: The int result.

        """
        return 80

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """Evaluate.

        비용 게이트는 LLM 호출을 동반하는 도구에 대해 예산과 rate limit을 검사합니다.
        CostGuard가 None이면 게이트를 통과시킵니다(하위 호환).

        Args:
            ctx (GateContext): GateContext ctx.

        Returns:
            GateDecision: The gatedecision result.

        """
        if self._cost_guard is None:
            return GateDecision(gate_name=self.name())

        # 비용 게이트는 LLM 호출을 유발하는 도구에만 적용.
        # 대부분의 도구는 비용이 없으므로 바로 Allow.
        if not self._is_llm_incurring_tool(ctx.tool_name):
            return GateDecision(gate_name=self.name())

        # ctx.args에서 토큰 추정 정보 추출 (있으면 사용, 없으면 기본값)
        tokens_in = _as_int(ctx.args.get("_estimated_tokens_in", 0))
        tokens_out = _as_int(ctx.args.get("_estimated_tokens_out", 0))
        model = _as_text(ctx.args.get("model", ctx.args.get("target", "default")), "default")

        try:
            decision = self._cost_guard.check_budget(
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                user_id=ctx.user_id,
            )
        except Exception:
            logger.exception("CostBudgetGate check_budget 실패 — Allow로 폴백")
            return GateDecision(gate_name=self.name())

        if not decision.allowed:
            return GateDecision(
                action=GateAction.DENY,
                reason=f"비용 예산 초과: {decision.reason}",
                gate_name=self.name(),
                metadata={
                    "estimated_cost_usd": decision.estimated_cost_usd,
                    "remaining_budget_usd": decision.remaining_budget_usd,
                    "daily_spend_usd": decision.daily_spend_usd,
                },
            )

        return GateDecision(gate_name=self.name())

    @staticmethod
    def _is_llm_incurring_tool(tool_name: str) -> bool:
        """LLM 호출을 유발하는 도구인지 판별.

        에이전트 루프 자체(generate/stream)는 ModelManager가 추적하므로,
        여기서는 추가 LLM 호출을 만드는 메타 도구들만 비용 게이트 대상으로 봅니다.
        일반 도구(file edit, bash 등)는 Allow.
        """
        llm_tools = {
            "generate",
            "stream_generate",
            "max_execute",  # 병렬 워커 N배 비용
            "debate",
            "collective_review",
            "self_evolve",
            "prompt_evolve",
        }
        return tool_name in llm_tools


class ApprovalGate:
    """도구별 승인 정책 게이트.

    IronClaw approval.rs 패턴:
    - Interactive 모드: 승인 필요 도구 → Pause
    - Autonomous 모드: 승인 필요 도구 → Deny
    - Container 모드: 모두 Allow

    Priority: 100.
    """

    # 항상 승인 필요한 도구 (IronClaw ApprovalRequirement::Always)
    ALWAYS_REQUIRE_APPROVAL: frozenset[str] = frozenset(
        {
            "db_migration",
            "deploy",
            "create_pr",
            "git_push",
            "payment",
        },
    )

    # 자동 승인 제외 시 승인 필요 (IronClaw ApprovalRequirement::UnlessAutoApproved)
    UNLESS_AUTO_APPROVED: frozenset[str] = frozenset(
        {
            "run_bash_command",
            "run_persistent_command",
            "write_file",
            "edit_file",
            "multi_replace_file_content",
            "replace_file_content",
            "git_commit",
            "agent_spawn",
            "computer_use",
        },
    )

    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "approval"

    def priority(self) -> int:
        """Priority.

        Returns:
            int: The int result.

        """
        return 100

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """Evaluate.

        Args:
            ctx (GateContext): GateContext ctx.

        Returns:
            GateDecision: The gatedecision result.

        """
        tool = ctx.tool_name

        # Container 모드: 모두 허용
        if ctx.execution_mode == "container":
            return GateDecision(gate_name=self.name())

        # 항상 승인 필요
        if tool in self.ALWAYS_REQUIRE_APPROVAL:
            if ctx.execution_mode == "autonomous":
                return GateDecision(
                    action=GateAction.DENY,
                    reason=f"도구 '{tool}'은(는) 명시적 승인이 필요하며 자율 모드에서 실행할 수 없습니다.",
                    gate_name=self.name(),
                )
            return GateDecision(
                action=GateAction.PAUSE,
                reason=f"도구 '{tool}'은(는) 이 작업에 대해 명시적 승인이 필요합니다.",
                gate_name=self.name(),
                resume_kind=ResumeKind.APPROVAL,
                allow_always=False,
            )

        # 자동 승인 가능 도구
        if tool in self.UNLESS_AUTO_APPROVED:
            if tool in ctx.auto_approved_tools:
                return GateDecision(gate_name=self.name())

            if ctx.execution_mode == "autonomous":
                # Autonomous 모드에서는 UnlessAutoApproved도 허용
                # (IronClaw 회귀 수정: 0e5f1b12)
                return GateDecision(gate_name=self.name())

            if ctx.execution_mode == "interactive_auto_approve":
                return GateDecision(gate_name=self.name())

            return GateDecision(
                action=GateAction.PAUSE,
                reason=f"도구 '{tool}'의 실행을 승인하시겠습니까?",
                gate_name=self.name(),
                resume_kind=ResumeKind.APPROVAL,
                allow_always=True,
            )

        # 기본: 허용
        return GateDecision(gate_name=self.name())


class SecurityPolicyGate:
    """보안 정책 게이트.

    Priority: 150 (승인 후).
    """

    def __init__(self, policy_engine: _SecurityPolicyLike | None = None) -> None:
        """Initialize the SecurityPolicyGate.

        Args:
            policy_engine: policy engine.

        """
        self._policy_engine: _SecurityPolicyLike | None = policy_engine

    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "security_policy"

    def priority(self) -> int:
        """Priority.

        Returns:
            int: The int result.

        """
        return 150

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """Evaluate.

        Args:
            ctx (GateContext): GateContext ctx.

        Returns:
            GateDecision: The gatedecision result.

        """
        if self._policy_engine is None:
            return GateDecision(gate_name=self.name())

        # 커맨드 실행 도구
        if ctx.tool_name in {"run_bash_command", "run_persistent_command"}:
            cmd = _as_text(ctx.args.get("command", ""))
            if cmd and not self._policy_engine.is_command_allowed(cmd):
                return GateDecision(
                    action=GateAction.DENY,
                    reason=f"보안 정책에 의해 명령어 '{cmd[:50]}' 차단됨.",
                    gate_name=self.name(),
                )

        # 네트워크 도구
        if ctx.tool_name in {"web_search", "web_scrape", "fetch_dom"}:
            url = _as_text(ctx.args.get("url", "") or ctx.args.get("query", ""))
            if url and not self._policy_engine.is_domain_allowed(url):
                return GateDecision(
                    action=GateAction.DENY,
                    reason=f"보안 정책에 의해 도메인 '{url[:50]}' 차단됨.",
                    gate_name=self.name(),
                )

        return GateDecision(gate_name=self.name())


# ── 메인 파이프라인 ──


class GatePipeline:
    """우선순위 기반 다단계 게이트 파이프라인.

    IronClaw Engine V2 gate/pipeline.rs 패턴:
    게이트를 우선순위순으로 정렬하고, 첫 번째 비-Allow 결과에서 즉시 반환합니다.
    """

    def __init__(self) -> None:
        """Initialize the GatePipeline."""
        self._gates: list[ExecutionGate] = []
        self._sorted: bool = False

    def add_gate(self, gate: ExecutionGate) -> "GatePipeline":
        """게이트를 파이프라인에 추가합니다."""
        self._gates.append(gate)
        self._sorted = False
        return self

    def _ensure_sorted(self) -> None:
        """게이트를 우선순위순으로 정렬합니다."""
        if not self._sorted:
            self._gates.sort(key=lambda gate: gate.priority())
            self._sorted = True

    def evaluate(self, ctx: GateContext) -> GateDecision:
        """모든 게이트를 우선순위순으로 평가합니다.

        첫 번째 비-Allow 결과에서 즉시 반환 (short-circuit).
        """
        self._ensure_sorted()

        for gate in self._gates:
            try:
                decision = gate.evaluate(ctx)
                if not decision.is_allowed:
                    logger.info(
                        "GatePipeline: %s → %s for '%s': %s",
                        gate.name(),
                        decision.action.value,
                        ctx.tool_name,
                        decision.reason,
                    )
                    return decision
            except Exception:
                # IronClaw 패턴: 게이트 에러는 fail-open (보수적으로 허용)
                logger.exception("GatePipeline: gate '%s' error (fail-open)", gate.name())
                continue

        return GateDecision(gate_name="pipeline", reason="all_gates_passed")

    def list_gates(self) -> list[dict[str, str | int]]:
        """등록된 게이트 목록을 반환합니다."""
        self._ensure_sorted()
        return [{"name": gate.name(), "priority": gate.priority()} for gate in self._gates]


# ── 팩토리 ──


def create_default_pipeline(
    guardrails: _GuardrailsLike | None = None,
    cost_guard: _CostGuardLike | None = None,
    policy_engine: _SecurityPolicyLike | None = None,
) -> GatePipeline:
    """기본 게이트 파이프라인을 생성합니다.

    IronClaw의 기본 게이트 구성을 재현합니다.
    """
    pipeline = GatePipeline()
    _ = pipeline.add_gate(RateLimitGate(guardrails))
    _ = pipeline.add_gate(CostBudgetGate(cost_guard))
    _ = pipeline.add_gate(ApprovalGate())
    _ = pipeline.add_gate(SecurityPolicyGate(policy_engine))
    return pipeline
