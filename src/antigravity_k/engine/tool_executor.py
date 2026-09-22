"""Ssak-Ai: 도구 실행 엔진 (ToolExecutor).

=============================================
I-1 리팩터링: Orchestrator에서 분리된 도구 실행/등록 로직.
도구 스키마 검증, 권한 검사, 에러 복구(Immune System), 자동 롤백을 담당합니다.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, TypedDict, cast, final

from antigravity_k.engine.failure_classifier import (
    ClassifiedFailure,
    RecoveryAction,
    RecoveryStrategyRegistry,
    classify_tool_failure,
)
from antigravity_k.engine.immune_system import ImmuneSystem
from antigravity_k.engine.task_state_store import current_task_execution_context
from antigravity_k.engine.tool_policy import tool_policy_denial as _tool_policy_denial
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_path import effective_project_root
from antigravity_k.tools.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from antigravity_k.engine.model_manager import ModelManager
    from antigravity_k.engine.vault import VaultEngine

logger = logging.getLogger(__name__)


# 요청 단위 정책(ToolPolicy·set/reset_tool_policy)은 engine.tool_policy 로 옮겼다 —
# 도구 계층(MCP 도구)이 같은 규칙을 import 순환 없이 재사용하기 위해서다.


def result_indicates_failure(result: object) -> bool:
    """Classify a tool result as a failure.

    Typed 결과(`MCPToolOutcome`)는 도구가 보고한 `is_error` 플래그가 우선한다 — 서버가
    `isError=true` 로 답한 호출을 텍스트 모양으로 판정하면 성공으로 새어 나간다.
    플래그가 없는 레거시 문자열 결과는 종전 규칙을 그대로 쓴다: "Error:" 접두어,
    ErrorDistiller 형식("❌ [tool Error]..."), run_bash_command 의 [exit_code=N] 마커.
    마커는 ErrorDistiller 가 접두어를 붙일 수 있어 텍스트 어디에서든 찾는다.
    """
    if getattr(result, "is_error", False):
        return True
    text = result if isinstance(result, str) else str(result)
    stripped = text.strip()
    if stripped.startswith("Error") or stripped.startswith("❌ ["):
        return True
    exit_match = re.search(r"\[exit_code=(\d+)\]", stripped)
    return exit_match is not None and exit_match.group(1) != "0"


class _GuardDecisionLike(Protocol):
    allows_execution: bool
    message: str


class _PlanGuardLike(Protocol):
    def evaluate_tool_call(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, object],
        execution_mode: str,
    ) -> _GuardDecisionLike: ...


class _GateDecisionLike(Protocol):
    is_denied: bool
    is_paused: bool
    reason: str


class _GatePipelineLike(Protocol):
    def evaluate(self, context: object) -> _GateDecisionLike: ...


class _ReshapedActionLike(Protocol):
    @property
    def arguments(self) -> Mapping[str, object]: ...


class _GovernanceOutcomeLike(Protocol):
    """P05 GovernanceOutcome의 최소 표면. disposition/reason은 로그·차단 사유에 쓴다."""

    @property
    def disposition(self) -> object: ...

    @property
    def reason(self) -> str: ...

    @property
    def admits_execution(self) -> bool: ...

    @property
    def reshaped_action(self) -> _ReshapedActionLike | None: ...


class _GovernanceGateLike(Protocol):
    def admit(
        self,
        tool_name: str,
        args: Mapping[str, object],
        *,
        execution_mode: str = "interactive",
    ) -> _GovernanceOutcomeLike: ...


class _VaultEngineLike(Protocol):
    def create_snapshot(self, message: str) -> str | None: ...

    def restore_snapshot(self, commit_hash: str) -> bool: ...


class _EventBusLike(Protocol):
    def publish(self, event_name: str, **kwargs: object) -> None: ...


class _SelfEvolutionModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> str | None: ...

    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class _ToolRegistryInstallLike(Protocol):
    def install_many(self, *tools: object) -> ToolRegistry: ...

    def install(self, tool: object) -> ToolRegistry: ...


class _ToolCallRecord(TypedDict):
    name: str
    arguments: dict[str, object]
    success: bool
    timestamp: float
    permission: str | None


@final
class ToolExecutor:
    """도구 실행 책임을 Orchestrator에서 분리한 모듈.

    책임:
    - 도구 스키마 사전 검증
    - PermissionGate 기반 권한 검사
    - PlanGuard 모드 기반 도구 차단 (Phase 1 D3)
    - GatePipeline 우선순위 게이트 평가 (Phase 1 D3)
    - 연속 에러 추적 및 자동 복구 (Immune System / Vault Rollback)
    - 도구 자동 등록 (_register_claw_tools)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        permission_gate: PermissionGate,
        model_manager: object | None = None,
        vault_engine: object | None = None,
        project_root: str = ".",
        capability_policy_config: Mapping[str, object] | None = None,
        plan_guard: object | None = None,
        gate_pipeline: object | None = None,
    ):
        """Initialize the ToolExecutor.

        Args:
            tool_registry (ToolRegistry): ToolRegistry tool registry.
            permission_gate (PermissionGate): PermissionGate permission gate.
            model_manager: model manager.
            vault_engine: vault engine.
            project_root (str): str project root.
            capability_policy_config (dict[str, Any] | None): dict[str, Any] | None capability policy config.
            plan_guard (PlanGuard | None): PlanGuard — PLAN/BUILD 모드 도구 권한 검사.
            gate_pipeline (GatePipeline | None): GatePipeline — 우선순위 기반 다단계 게이트 평가.

        """
        self.tool_registry = tool_registry
        self.permission_gate = permission_gate
        self.manager: object | None = model_manager
        self.vault_engine: _VaultEngineLike | None = (
            cast(_VaultEngineLike, vault_engine) if vault_engine is not None else None
        )
        self.project_root = project_root
        self.capability_policy_config: dict[str, object] = dict(capability_policy_config or {})
        self.plan_guard: _PlanGuardLike | None = cast(_PlanGuardLike, plan_guard) if plan_guard is not None else None
        self.gate_pipeline: _GatePipelineLike | None = (
            cast(_GatePipelineLike, gate_pipeline) if gate_pipeline is not None else None
        )
        # P05 cognitive request governance (opt-in). 연결 전에는 기존 동작 그대로다.
        self._governance_gate: _GovernanceGateLike | None = None
        self._consecutive_errors = 0
        self.current_objective = ""
        self.failure_registry = RecoveryStrategyRegistry()
        self._last_failure: ClassifiedFailure | None = None

        # Hermes Self-Evolution: 도구 호출 이력 (SEC가 패턴 감지용으로 사용)
        self.tool_call_history: list[_ToolCallRecord] = []

        # Singleton instantiation to avoid lazy init costs during active error recovery
        self._immune_system: ImmuneSystem | None = None
        try:
            self._immune_system = ImmuneSystem(
                self.project_root,
                cast("ModelManager", self.manager),
                cast("VaultEngine | None", self.vault_engine),
            )
        except Exception:
            logger.exception("Failed to initialize ImmuneSystem in ToolExecutor")

    def set_objective(self, objective: str) -> None:
        """현재 턴 목표를 capability policy 판단에 제공합니다."""
        self.current_objective = objective or ""

    def set_governance_gate(self, gate: _GovernanceGateLike | None) -> None:
        """P05 Cognitive Request governance adapter를 연결한다(None이면 기존 동작).

        adapter는 ``admit(tool, args, execution_mode=...)``로 판정하고, 실행 불가면
        ``admits_execution``이 False다. RESHAPE 결과는 ``reshaped_action``의 args로 실행한다.
        """

        self._governance_gate = gate

    def execute(
        self,
        name: str,
        args: dict[str, object],
        objective: str = "",
        execution_mode: str = "interactive",
        *,
        guardrail_prechecked: bool = False,
    ) -> str:
        """ToolRegistry를 통해 도구를 실행합니다. (사전 검증 및 구조화된 에러 반환 포함).

        Args:
            name: 도구 이름
            args: 도구 인자
            objective: 현재 목표
            execution_mode: 실행 모드 ("plan", "build", "interactive")
                          Phase 1 D3: PlanGuard/GatePipeline에 전달되어 모드별 도규 차단/승인 처리.
            guardrail_prechecked: True면 RateLimitGate의 before_call을 건너뛴다
                          (tool_loop가 이미 평가한 allow-path). 직접 호출 경로는 False 유지.
        """
        try:
            if name not in self.tool_registry:
                return (
                    f"There was an error when executing the function: {name}\n"
                    f"Here's the error traceback: Unknown tool '{name}'\n"
                    f"Please call this function again with a valid tool name within XML tags <tool_call></tool_call>"
                )

            # ─── 요청 단위 도구 정책 (대시보드 Search/Code/MCP 칩) ───
            policy_tool = self.tool_registry.get_tool(name)
            policy_denial = _tool_policy_denial(name, policy_tool)
            if policy_denial is not None:
                logger.info("ToolPolicy blocked '%s'", name)
                return (
                    f"There was an error when executing the function: {name}\n"
                    f"Here's the error traceback: [BLOCKED] {policy_denial}\n"
                    f"Please continue without this tool."
                )

            # ─── P05: Cognitive Request Governance (opt-in adapter) ───
            if self._governance_gate is not None:
                governance = self._governance_gate.admit(name, args, execution_mode=execution_mode)
                if not governance.admits_execution:
                    logger.info("Governance %s blocked '%s': %s", governance.disposition, name, governance.reason)
                    return (
                        f"There was an error when executing the function: {name}\n"
                        f"Here's the error traceback: [GOVERNANCE {governance.disposition}] {governance.reason}\n"
                        f"Please reconsider your approach."
                    )
                reshaped = governance.reshaped_action
                if reshaped is not None:
                    args = dict(reshaped.arguments)

            # ─── Phase 1 D3: PlanGuard 모드 기반 도구 차단 ───
            if self.plan_guard is not None:
                guard_decision = self.plan_guard.evaluate_tool_call(
                    tool_name=name,
                    tool_args=args,
                    execution_mode=execution_mode,
                )
                if not guard_decision.allows_execution:
                    logger.info(
                        "PlanGuard blocked '%s' in %s mode: %s",
                        name,
                        execution_mode,
                        guard_decision.message,
                    )
                    return (
                        f"There was an error when executing the function: {name}\n"
                        f"Here's the error traceback: [BLOCKED] {guard_decision.message}\n"
                        f"Please reconsider your approach."
                    )

            # ─── Phase 1 D3: GatePipeline 우선순위 게이트 평가 ───
            if self.gate_pipeline is not None:
                from antigravity_k.engine.gate_pipeline import GateContext

                gate_ctx = GateContext(
                    tool_name=name,
                    args=args,
                    execution_mode=execution_mode,
                    auto_approved_tools=self._user_contracted_tools(),
                    guardrail_prechecked=guardrail_prechecked,
                )
                gate_decision = self.gate_pipeline.evaluate(gate_ctx)
                if gate_decision.is_denied:
                    self._consecutive_errors += 1
                    logger.info(
                        "GatePipeline denied '%s': %s",
                        name,
                        gate_decision.reason,
                    )
                    return (
                        f"There was an error when executing the function: {name}\n"
                        f"Here's the error traceback: [DENIED] {gate_decision.reason}\n"
                        f"Please reconsider your approach."
                    )
                if gate_decision.is_paused:
                    # Pause = 사용자 승인 필요 — ApprovalManager에 요청을 등록해
                    # 대시보드/승인 API로 처리 가능하게 한다. '항상 허용' 도구나
                    # 소비 대기 중인 일회성 승인(재시도)이면 즉시 실행한다.
                    proceed, approval_request_id = self._register_approval_request(name, args, gate_decision)
                    if proceed:
                        pass  # 승인 확정 — 아래 실행 단계로 진행
                    else:
                        request_note = f" (승인 요청 ID: {approval_request_id}) " if approval_request_id else " "
                        return (
                            f"[APPROVAL REQUIRED] {gate_decision.reason}{request_note}"
                            f"Please stop executing tools immediately and ask the user for permission. "
                            f"Wait for their 'Yes' before retrying."
                        )

            # ─── Pre-Execution Validation + Preflight ───
            error_msg = self._validate_and_preflight(name, args)
            if error_msg:
                return error_msg

            perm, result = self.tool_registry.execute_with_permission(
                name,
                args,
                objective=objective or self.current_objective,
            )

            if perm == Permission.DENY:
                self._record_tool_call(name, args, result, permission=perm)
                return (
                    f"There was an error when executing the function: {name}\n"
                    f"Here's the error traceback: [DENIED] Tool execution blocked by permission rules.\n"
                    f"Please reconsider your approach."
                )
            elif perm == Permission.PROMPT:
                # 레지스트리 권한 게이트(PROMPT)도 승인 시스템과 연동한다 —
                # '항상 허용'/소비 대기 일회성 승인이 있으면 승인 실행하고,
                # 없으면 승인 요청을 등록해 사용자가 API/대시보드로 결정한다.
                proceed, approval_request_id = self._register_approval_request(name, args, f"{name} 실행 승인")
                if proceed:
                    approved_result = str(self.tool_registry.execute_approved(name, args))
                    self._post_execute(name, args, approved_result, permission=perm)
                    return approved_result
                self._record_tool_call(name, args, result, permission=perm)
                request_note = f" (승인 요청 ID: {approval_request_id}) " if approval_request_id else " "
                return (
                    f"[APPROVAL REQUIRED] This tool ({name}) requires user approval to execute.{request_note}"
                    f"Please stop executing tools immediately and ask the user for permission. "
                    f"Wait for their 'Yes' before retrying."
                )

            # ─── Post-Execution: history, events, error tracking ───
            self._post_execute(name, args, result, permission=perm)

            # Auto-Rollback & Self-Healing logic — 현재 결과가 실제 실패일 때만
            # (과거 스키마 실수 누적으로 성공 호출 직후 롤백되는 것 방지)
            if self._consecutive_errors >= 3 and result_indicates_failure(result):
                return self._trigger_recovery(name, args, result)

            return result
        except Exception as e:
            logger.exception("Unhandled exception")
            self._consecutive_errors += 1
            return (
                f"There was an error when executing the function: {name}\n"
                f"Here's the error traceback: {e!s}\n"
                f"Please call this function again with correct arguments within XML tags <tool_call></tool_call>"
            )

    def _register_approval_request(
        self,
        name: str,
        args: dict[str, object],
        reason: object,
    ) -> tuple[bool, str]:
        """게이트 일시정지를 승인 시스템에 등록한다.

        반환: (즉시 실행 여부, 승인 요청 ID — 등록 실패 시 빈 문자열).
        - 소비 대기 중인 일회성 승인 → 소비 후 즉시 실행 (재시도 경로)
        - '항상 허용' 도구 → 즉시 실행 (새 요청/일시정지 없음)
        - 동일 도구 PENDING 요청이 있으면 재사용 (중복 등록 방지)
        - 그 외 → PENDING 요청 등록 후 일시정지
        등록 실패는 기존 문자열 일시정지로 폴백한다(보안 경계 유지).
        """
        try:
            from antigravity_k.engine.approval_manager import (
                ApprovalStatus,
                get_approval_manager,
            )

            manager = get_approval_manager()

            # 재시도 우선: 이미 승인된 일회성 허가가 있으면 새 요청 없이 소비
            if manager.consume_one_time_approval(name):
                return True, ""

            # '항상 허용'은 새 요청/일시정지 없이 즉시 실행 — 단, **동의 없이 실행된 횟수**를
            # 부여 기록에 남긴다(F-33: 보이지 않는 자동 승인은 감사할 수 없다).
            if manager.is_always_allowed(name):
                manager.record_auto_approval(name)
                return True, ""

            from pydantic import JsonValue

            json_args: dict[str, JsonValue] = {
                key: value if isinstance(value, (str, int, float, bool)) or value is None else str(value)
                for key, value in args.items()
            }
            description = (
                str(getattr(reason, "reason", "")) if not isinstance(reason, str) else reason
            ) or f"{name} 실행"

            # 동일 도구의 PENDING 요청이 있으면 재사용 (중복 등록·UI 스팸 방지)
            for pending_request in manager.get_pending():
                if pending_request.tool_name == name:
                    self._broadcast_approval_required(name, pending_request.request_id, description)
                    return False, pending_request.request_id

            request = manager.request_approval(
                tool_name=name,
                tool_args=json_args,
                description=description,
                project_root=str(self.project_root),
            )
            if request.status == ApprovalStatus.ALWAYS_ALLOW:
                return True, request.request_id
            self._broadcast_approval_required(name, request.request_id, description)
            return False, request.request_id
        except Exception:
            logger.debug(
                "approval registration failed — string pause fallback",
                exc_info=True,
            )
            return False, ""

    def _broadcast_approval_required(self, name: str, request_id: str, reason: str) -> None:
        """승인 대기(APPROVAL REQUIRED) 상태를 Dashboard에 ApprovalRequired 이벤트로 브로드캐스트합니다.

        GatePipeline 일시정지와 Permission PROMPT 승인 요청이 등록될 때 호출되어
        useEventWebSocket의 onApprovalRequired 핸들러(에이전트 모니터링 패널)가
        승인 대기 도구를 실시간으로 표시할 수 있게 합니다.
        이벤트 발행은 선택적(non-critical)이므로 실패해도 실행 경로는 계속됩니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            event_bus = cast(_EventBusLike, global_event_bus)
            event_bus.publish(
                "ApprovalRequired",
                tool=name,
                request_id=request_id,
                reason=reason,
            )
        except Exception:
            logger.exception("Failed to broadcast approval-required event")

    def _user_contracted_tools(self) -> frozenset[str]:
        """Tools the user explicitly named in the active task's prompt.

        These are treated as pre-approved for the ApprovalGate: the act of naming a
        tool in the request is itself consent, so the loop runs it instead of pausing
        for interactive confirmation (which would make a local model narrate execution
        rather than perform it). Tools are still subject to every other gate
        (security policy, dangerous-command block, path sandbox, PlanGuard).
        """
        context = current_task_execution_context()
        if context is None:
            return frozenset()
        checkpoint = context.state_store.get_last_checkpoint(context.task_id)
        if checkpoint is None:
            return frozenset()
        try:
            payload = cast(object, json.loads(checkpoint["context_json"]))
        except (json.JSONDecodeError, TypeError, KeyError):
            return frozenset()
        payload_map = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        expected = payload_map.get("expected_tools")
        if not isinstance(expected, (list, tuple, set)):
            return frozenset()
        expected_values = cast(list[object] | tuple[object, ...] | set[object], expected)
        named = frozenset(str(tool) for tool in expected_values if str(tool).strip())
        # Executing code authorizes materializing it first: a user who asked to run
        # code via run_bash_command also consents to writing the script to run.
        # Path sandbox + dangerous-command gates still apply to the writes themselves.
        if "run_bash_command" in named:
            named = named | {"write_file", "edit_file", "replace_file_content"}
        return named

    def _validate_and_preflight(self, name: str, args: dict[str, object]) -> str | None:
        """Validate required arguments and run preflight directory checks.

        Returns an error message string if validation fails, or None to proceed.
        """
        # ─── Pre-Execution Validation (스키마 사전 검증) ───
        tool_obj = self.tool_registry.get(name)
        if tool_obj:
            try:
                schema = tool_obj.parameters_schema
                raw_required = schema.get("required", [])
                required_args = (
                    [str(arg) for arg in cast(list[object], raw_required)] if isinstance(raw_required, list) else []
                )
                missing = [arg for arg in required_args if arg not in args]
                if missing:
                    return (
                        f"There was an error when executing the function: {name}\n"
                        f"Here's the error traceback: Missing required arguments: {', '.join(missing)}\n"
                        f"Please call this function again with correct arguments within XML tags"
                        f"<tool_call></tool_call>"
                    )
            except Exception:
                logger.exception("Validation check failed for %s", name)

        # ─── Preflight Validator (Hermes 차용) ───
        # 검증 단계에서 디렉터리를 생성하는 쓰기 부수효과는 제거했다 — 오타 경로가
        # 조용히 잘못된 디렉터리 트리를 만들었다. 실제 쓰기 도구가 필요 시 생성한다.
        file_path = args.get("file_path") or args.get("path") or args.get("target")
        if isinstance(file_path, str) and file_path:
            root = effective_project_root(str(self.project_root))
            abs_path = file_path if os.path.isabs(file_path) else os.path.join(root, file_path)
            if name in ("write_file", "write_to_file", "edit_file", "replace_file_content"):
                parent_dir = os.path.dirname(abs_path)
                if parent_dir and not os.path.exists(parent_dir):
                    logger.info(
                        "Preflight Validator: 대상 디렉터리가 없음(생성은 쓰기 도구가 수행): %s",
                        parent_dir,
                    )
        return None

    def _record_tool_call(
        self,
        name: str,
        args: dict[str, object],
        result: str,
        permission: Permission | None = None,
    ) -> None:
        """Record a tool call in history (capped at 20 entries)."""
        entry: _ToolCallRecord = {
            "name": name,
            "arguments": args,
            "success": not result_indicates_failure(result),
            "timestamp": time.time(),
            "permission": permission.value if permission is not None else None,
        }
        self.tool_call_history.append(entry)
        if len(self.tool_call_history) > 20:
            self.tool_call_history = self.tool_call_history[-20:]

    def _post_execute(
        self,
        name: str,
        args: dict[str, object],
        result: str,
        permission: Permission | None = None,
    ) -> None:
        """Post-execution: record history, broadcast file events, track errors."""
        self._record_tool_call(name, args, result, permission=permission)

        if result_indicates_failure(result):
            self._consecutive_errors += 1
            self._last_failure = classify_tool_failure(name, str(result))
            self._broadcast_failure_event(name, result)
        else:
            self._consecutive_errors = 0  # Reset on success
            self._last_failure = None
            self._broadcast_file_event(name, args)

    def _broadcast_failure_event(self, name: str, result: str) -> None:
        """실패한 도구 호출을 Dashboard에 FailureDetected 이벤트로 브로드캐스트합니다.

        useEventWebSocket의 onFailureDetected 핸들러(에이전트 모니터링 패널의
        오류 로그/타임라인, ChatPage 활동 레일)가 이 이벤트를 소비합니다.
        이벤트 발행은 선택적(non-critical)이므로 실패해도 실행 경로는 계속됩니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            event_bus = cast(_EventBusLike, global_event_bus)
            event_bus.publish(
                "FailureDetected",
                tool=name,
                error=str(result)[:400],
                message=f"'{name}' 도구 실행 실패",
            )
        except Exception:
            logger.exception("Failed to broadcast failure event")

    def _broadcast_file_event(self, name: str, args: dict[str, object]) -> None:
        """Broadcast FileOpened / FileModified events to the dashboard."""
        if name not in ("read_file", "write_file", "edit_file", "replace_file_content", "multi_replace_file_content"):
            return
        file_path = args.get("file_path") or args.get("path")
        if not isinstance(file_path, str) or not file_path:
            return
        root = effective_project_root(str(self.project_root))
        abs_path = file_path if os.path.isabs(file_path) else os.path.join(root, file_path)
        if not os.path.exists(abs_path):
            return
        try:
            with open(abs_path, encoding="utf-8") as f:
                content = f.read()
            from antigravity_k.engine.event_bus import global_event_bus

            evt_type = "FileOpened" if name == "read_file" else "FileModified"
            event_bus = cast(_EventBusLike, global_event_bus)
            event_bus.publish(evt_type, filepath=abs_path, content=content)
        except Exception:
            logger.exception("Failed to read file for event broadcast")

    async def execute_async(
        self,
        name: str,
        args: dict[str, object],
        execution_mode: str = "interactive",
        *,
        guardrail_prechecked: bool = False,
    ) -> str:
        """비동기 스레드 풀에서 도구를 실행하여 메인 이벤트 루프를 블로킹하지 않습니다."""
        return await asyncio.to_thread(
            self.execute,
            name,
            args,
            execution_mode=execution_mode,
            guardrail_prechecked=guardrail_prechecked,
        )

    def _trigger_recovery(self, name: str, args: dict[str, object], result: str) -> str:
        """연속 에러 3회 시 실패 유형별 복구 플레이북 → Immune System → Vault Rollback 순으로 복구 시도."""
        self._consecutive_errors = 0

        # 0. 실패 유형 분류 + 복구 플레이북 우선 (면역 시스템은 코드 버그 수복 전용)
        classified = self._last_failure or classify_tool_failure(name, str(result))
        strategy = self.failure_registry.strategy_for(name, classified.category)
        if strategy.action is not RecoveryAction.ESCALATE_IMMUNE:
            logger.info(
                "Recovery playbook for %s (%s): %s",
                name,
                classified.category.value,
                strategy.action.value,
            )
            return str(result) + "\n\n" + strategy.render(classified)

        # 1. Trigger Immune System (Self-Healing)
        if self._immune_system:
            try:
                error_trace = str(result)
                args_context = json.dumps(args, ensure_ascii=False) if args else "None"
                heal_msg = self._immune_system.heal(error_trace, name, args_context)
                return str(result) + "\n\n" + heal_msg
            except Exception:
                logger.exception("Immune System recovery failed")

        # 2. Fallback to Vault Rollback if Immune System fails
        rollback_msg = "\n\n🚨 **[SANDBOX RECOVERY]** Consecutive tool errors detected! "
        if self.vault_engine:
            try:
                snapshot = self.vault_engine.create_snapshot(
                    "Auto-rollback checkpoint before recovery",
                )
                if snapshot:
                    success = self.vault_engine.restore_snapshot(snapshot)
                    if success:
                        rollback_msg += (
                            f"Workspace has been safely rolled back to checkpoint ({snapshot[:7]}). "
                            f"Please analyze why the error occurred and formulate a completely different plan."
                        )
                    else:
                        rollback_msg += "Restore attempted but failed."
                else:
                    rollback_msg += "No recent snapshot found to rollback to."
            except Exception as ge:
                logger.exception("Unhandled exception")
                rollback_msg += f"Vault rollback failed: {ge}."
        else:
            rollback_msg += "VaultEngine is not available, so automatic rollback could not be performed."
        return str(result) + rollback_msg

    def register_default_tools(self) -> None:
        """모든 기본 도구를 ToolRegistry에 등록합니다."""
        try:
            from antigravity_k.tools.agent_spawn import AgentSpawnTool
            from antigravity_k.tools.artifact_tools import WriteArtifactTool
            from antigravity_k.tools.binary_tools import HexDumpTool
            from antigravity_k.tools.browser_tools import BrowserDOMTool
            from antigravity_k.tools.ci_tools import (
                AutoLintTool,
                PRCreationTool,
                TestRunnerTool,
            )
            from antigravity_k.tools.computer_use import ComputerUseTool
            from antigravity_k.tools.config_editor_tool import ConfigEditorTool
            from antigravity_k.tools.context_artifact_tools import ReadContextArtifactTool
            from antigravity_k.tools.cowork_delegate import CoworkDelegateTool
            from antigravity_k.tools.docker_tools import DockerBashCommandTool
            from antigravity_k.tools.file_tools import (
                ApplyPatchTool,
                EditFileTool,
                GlobSearchTool,
                GrepSearchTool,
                WriteFileTool,
            )
            from antigravity_k.tools.git_tools import (
                GitCommitTool,
                GitDiffTool,
                GitLogTool,
                GitStatusTool,
            )
            from antigravity_k.tools.hashline_tools import (
                HashlineEditTool,
                MultiReplaceFileContentTool,
                ReadHashFileTool,
            )
            from antigravity_k.tools.impact_analyzer import ImpactAnalyzerTool
            from antigravity_k.tools.self_evolution_tool import SelfEvolutionTool
            from antigravity_k.tools.system_control import SystemControlTool
            from antigravity_k.tools.system_tools import (
                ListDirectoryTool,
                ReadFileTool,
                ReplaceFileContentTool,
                RunBashCommandTool,
            )
            from antigravity_k.tools.terminal_tools import InteractivePTYTool
            from antigravity_k.tools.web_search import WebSearchTool

            registry = cast(_ToolRegistryInstallLike, cast(object, self.tool_registry))
            _ = registry.install_many(
                ComputerUseTool(),
                SystemControlTool(),
                InteractivePTYTool(),
                HexDumpTool(),
                DockerBashCommandTool(),
                ReadFileTool(),
                ReplaceFileContentTool(),
                MultiReplaceFileContentTool(),
                RunBashCommandTool(),
                WriteFileTool(),
                EditFileTool(),
                ApplyPatchTool(),
                GlobSearchTool(),
                GrepSearchTool(),
                ListDirectoryTool(),
                ReadHashFileTool(),
                HashlineEditTool(),
                GitStatusTool(),
                GitDiffTool(),
                GitCommitTool(),
                GitLogTool(),
                TestRunnerTool(),
                AutoLintTool(),
                PRCreationTool(),
                ImpactAnalyzerTool(),
                ConfigEditorTool(),
                ReadContextArtifactTool(self.project_root),
                AgentSpawnTool(model_manager=self.manager, tool_registry=self.tool_registry),
                CoworkDelegateTool(model_manager=self.manager),
                SelfEvolutionTool(model_manager=cast(_SelfEvolutionModelManagerLike | None, self.manager)),
                WriteArtifactTool(),
                BrowserDOMTool(),
                WebSearchTool(),
            )
            logger.info("Registered %s tools via ToolRegistry", len(self.tool_registry))

            # MCP 동적 도구 로딩: 감사 통과한 서버만 ToolRegistry에 편입합니다.
            self._load_mcp_tools()

            # Auto-Skill 동적 로딩 (ECA)
            self._load_auto_skills()

        except Exception:
            logger.exception("Failed to register tools")

    def _load_auto_skills(self) -> None:
        """auto_skill_ 프리픽스 도구를 동적으로 로드합니다."""
        tools_dir = os.path.join(self.project_root, "src", "antigravity_k", "tools")
        if not os.path.exists(tools_dir):
            return

        import importlib.util
        import inspect

        from antigravity_k.tools.base_tool import BaseTool

        auto_skills = [f for f in os.listdir(tools_dir) if f.startswith("auto_skill_") and f.endswith(".py")]
        for skill_file in auto_skills:
            try:
                module_name = skill_file[:-3]
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    os.path.join(tools_dir, skill_file),
                )
                if spec is None or spec.loader is None:
                    logger.warning("Unable to load auto-skill metadata: %s", skill_file)
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj is not BaseTool:
                        _ = cast(_ToolRegistryInstallLike, cast(object, self.tool_registry)).install(obj())
                        logger.info("Dynamically loaded auto-skill: %s from %s", name, skill_file)
            except Exception:
                logger.exception("Failed to load auto-skill %s", skill_file)

    def _load_mcp_tools(self) -> None:
        """프로젝트 MCP 설정을 감사한 뒤 안전한 MCP 도구를 동적으로 등록합니다."""
        config_path = os.environ.get("AGK_MCP_CONFIG") or os.path.join(
            self.project_root,
            ".mcp.json",
        )
        if self.capability_policy_config.get("auto_load_mcp", True) is False:
            logger.info("MCP auto-load disabled by autonomous_capabilities config.")
            return
        if not os.path.exists(config_path):
            return

        try:
            from antigravity_k.tools.mcp_tool_loader import MCPToolLoader

            loader = MCPToolLoader(
                config_path=config_path,
                include_system_tools=False,
            )
            for tool in loader.load_tools():
                if tool.name in self.tool_registry:
                    logger.warning(
                        "Skipping MCP tool '%s' because a local tool already exists.",
                        tool.name,
                    )
                    continue
                _ = cast(_ToolRegistryInstallLike, cast(object, self.tool_registry)).install(tool)
            logger.info("Registered MCP tools from %s", config_path)
        except Exception:
            logger.exception("Failed to load MCP tools from %s", config_path)

    def reset_error_counter(self) -> None:
        """턴 시작 시 에러 카운터를 리셋합니다."""
        self._consecutive_errors = 0
