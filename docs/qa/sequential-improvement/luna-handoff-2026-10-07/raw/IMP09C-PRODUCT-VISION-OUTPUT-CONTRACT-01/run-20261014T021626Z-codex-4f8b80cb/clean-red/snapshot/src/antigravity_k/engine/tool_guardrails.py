"""ToolCallGuardrail — 도구 호출 루프 가드레일 시스템.

====================================================
Hermes Agent의 tool_guardrails.py 패턴을 Ssak-Ai에 이식.

순수 관찰 기반 컨트롤러:
- 동일 인자로 반복 실패하는 도구 호출 감지 → 경고/차단
- 읽기 전용 도구의 비진행성 감지 (동일 결과 반복)
- 동일 도구의 누적 실패 감지
- 구성 가능 임계값 (config.yaml 연동)

사용법:
    controller = ToolCallGuardrailController()

    # 각 턴 시작 시
    controller.reset_for_turn()

    # 도구 실행 전
    decision = controller.before_call("read_file", {"path": "foo.py"})
    if not decision.allows_execution:
        inject_synthetic_error(decision)
        continue

    # 도구 실행 후
    decision = controller.after_call("read_file", {"path": "foo.py"}, result, failed=False)
    if decision.action == "warn":
        append_guidance(result, decision)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

logger = logging.getLogger("antigravity_k.engine.tool_guardrails")

JsonObject = dict[str, object]


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value).items()
        return {str(key): item for key, item in items}
    return {}


def _as_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default if value is None else str(value)


# ── 읽기 전용 (비진행성 감지 대상) 도구 목록 ──
# 실제 ToolRegistry에 등록된 이름과 반드시 일치해야 함

IDEMPOTENT_TOOL_NAMES = frozenset(
    {
        "read_file",
        "glob_search",
        "grep_search",
        "web_search",
        "web_scrape",
        "fetch_dom",
        "git_status",
        "git_log",
        "git_diff",
        "list_directory",
        "hex_dump",
        "search_knowledge",
        "impact_analyzer",
        "read_context_artifact",
    },
)

# ── 변경 가능 도구 목록 ──

MUTATING_TOOL_NAMES = frozenset(
    {
        "run_bash_command",
        "run_persistent_command",
        "send_command_input",
        "interactive_pty",
        "write_file",
        "edit_file",
        "multi_replace_file_content",
        "replace_file_content",
        "write_artifact",
        "git_commit",
        "run_tests",
        "auto_lint",
        "create_pr",
        "run_docker_bash",
        "computer_use",
        "agent_spawn",
        "cowork_delegate",
        "db_migration",
        "store_knowledge",
    },
)


# ── 설정 ──


@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    """도구 호출 루프 감지 임계값 설정.

    경고(warn)는 기본 활성화: 도구 실행을 막지 않고 안내 메시지만 추가.
    차단(hard_stop)은 명시적 opt-in: config.yaml에서 활성화해야 동작.
    """

    warnings_enabled: bool = True
    hard_stop_enabled: bool = False

    # 동일 도구+인자 반복 실패
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5

    # 동일 도구 (다른 인자) 누적 실패
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8

    # 읽기 전용 도구 비진행성 (동일 결과 반복)
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5

    idempotent_tools: frozenset[str] = field(default_factory=lambda: IDEMPOTENT_TOOL_NAMES)
    mutating_tools: frozenset[str] = field(default_factory=lambda: MUTATING_TOOL_NAMES)

    @classmethod
    def from_config(cls, data: Mapping[str, object] | None = None) -> ToolCallGuardrailConfig:
        """config.yaml의 `tool_loop_guardrails` 섹션에서 설정 로드."""
        if not isinstance(data, Mapping):
            return cls()

        warn_after = _as_mapping(data.get("warn_after", {}))
        hard_stop_after = _as_mapping(data.get("hard_stop_after", {}))

        defaults = cls()
        return cls(
            warnings_enabled=_as_bool(data.get("warnings_enabled"), defaults.warnings_enabled),
            hard_stop_enabled=_as_bool(data.get("hard_stop_enabled"), defaults.hard_stop_enabled),
            exact_failure_warn_after=_positive_int(
                warn_after.get("exact_failure"),
                defaults.exact_failure_warn_after,
            ),
            same_tool_failure_warn_after=_positive_int(
                warn_after.get("same_tool_failure"),
                defaults.same_tool_failure_warn_after,
            ),
            no_progress_warn_after=_positive_int(
                warn_after.get("idempotent_no_progress"),
                defaults.no_progress_warn_after,
            ),
            exact_failure_block_after=_positive_int(
                hard_stop_after.get("exact_failure"),
                defaults.exact_failure_block_after,
            ),
            same_tool_failure_halt_after=_positive_int(
                hard_stop_after.get("same_tool_failure"),
                defaults.same_tool_failure_halt_after,
            ),
            no_progress_block_after=_positive_int(
                hard_stop_after.get("idempotent_no_progress"),
                defaults.no_progress_block_after,
            ),
        )


# ── 도구 호출 시그니처 (해시 기반 비교) ──


@dataclass(frozen=True)
class ToolCallSignature:
    """도구 이름 + 인자의 정규화된 해시 시그니처."""

    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, object]) -> ToolCallSignature:
        """From Call.

        Args:
            tool_name (str): str tool name.
            args (Mapping[str, Any]): Mapping[str, Any] args.

        Returns:
            'ToolCallSignature': The 'toolcallsignature' result.

        """
        canonical = _canonical_args(args or {})
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))

    def to_dict(self) -> dict[str, str]:
        """To Dict.

        Returns:
            dict[str, str]: The dict[str, str] result.

        """
        return {"tool_name": self.tool_name, "args_hash": self.args_hash}


# ── 가드레일 판정 결과 ──


@dataclass(frozen=True)
class ToolGuardrailDecision:
    """가드레일 판정 결과."""

    action: str = "allow"  # allow | warn | block | halt
    code: str = "allow"  # 판정 코드
    message: str = ""  # 사용자/에이전트 안내 메시지
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None

    @property
    def allows_execution(self) -> bool:
        """도구 실행이 허용되는지 여부."""
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        """턴을 강제 중단해야 하는지 여부."""
        return self.action in {"block", "halt"}

    def to_dict(self) -> JsonObject:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        data: JsonObject = {
            "action": self.action,
            "code": self.code,
            "message": self.message,
            "tool_name": self.tool_name,
            "count": self.count,
        }
        if self.signature is not None:
            data["signature"] = self.signature.to_dict()
        return data


# ── 실패 분류 헬퍼 ──


def classify_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """도구 실행 결과에서 실패 여부를 추정합니다.

    호출자가 명시적으로 failed= 를 전달하지 않을 때의 폴백 분류기.
    """
    if result is None:
        return False, ""

    # run_bash_command surfaces [exit_code=N] for non-zero exits — may carry an ErrorDistiller prefix, so match anywhere.
    stripped = result.strip()
    exit_match = re.search(r"\[exit_code=(\d+)\]", stripped)
    if tool_name == "run_bash_command" and exit_match and exit_match.group(1) != "0":
        return True, " [non-zero exit]"

    # 터미널: exit_code 기반
    if tool_name == "terminal":
        try:
            data = cast(object, json.loads(result))
            if isinstance(data, Mapping):
                exit_code = cast(Mapping[str, object], data).get("exit_code")
                if exit_code is not None and exit_code != 0:
                    return True, f" [exit {exit_code}]"
        except (json.JSONDecodeError, TypeError):
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)
        return False, ""

    # 일반: 에러 패턴 매칭 ("Error" 프리픽스, ErrorDistiller의 "❌ [tool Error]" 형식 포함)
    lower = result[:500].lower()
    if '"error"' in lower or '"failed"' in lower or result.startswith("Error") or stripped.startswith("❌ ["):
        return True, " [error]"

    return False, ""


# ── 메인 컨트롤러 ──


class ToolCallGuardrailController:
    """턴별 도구 호출 루프 감지 컨트롤러.

    사이드이펙트 없음: 관찰 후 Decision을 반환할 뿐,
    실행 중단은 호출자(Orchestrator)가 결정합니다.
    """

    def __init__(self, config: ToolCallGuardrailConfig | None = None):
        """Initialize the ToolCallGuardrailController.

        Args:
            config (ToolCallGuardrailConfig | None): ToolCallGuardrailConfig | None config.

        """
        self.config: ToolCallGuardrailConfig = config or ToolCallGuardrailConfig()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        """새 턴 시작 시 모든 카운터 초기화."""
        self._exact_failure_counts: dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: dict[str, int] = {}
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
        self._halt_decision: ToolGuardrailDecision | None = None

    @property
    def halt_decision(self) -> ToolGuardrailDecision | None:
        """마지막 차단 판정. None이면 아직 차단 없음."""
        return self._halt_decision

    def before_call(
        self,
        tool_name: str,
        args: Mapping[str, object] | None = None,
    ) -> ToolGuardrailDecision:
        """도구 실행 전 사전 검사.

        hard_stop이 비활성이면 항상 allow를 반환합니다.
        """
        signature = ToolCallSignature.from_call(tool_name, _coerce_args(args))

        # Check Declarative Security Policies
        from .security_policy import get_policy_engine

        engine = get_policy_engine()

        if tool_name in ["run_bash_command", "run_persistent_command"] and args:
            cmd = _as_text(args.get("command"), "")
            if not engine.is_command_allowed(cmd):
                return ToolGuardrailDecision(
                    action="block",
                    code="policy_denied",
                    message=f"Command '{cmd}' is blocked by declarative security policy.",
                    tool_name=tool_name,
                    signature=signature,
                )
            # Claude Deny Patterns (Sidabari claude_safety.rs 이식)
            try:
                from .claude_deny_patterns import is_command_blocked_by_deny

                if is_command_blocked_by_deny(cmd):
                    return ToolGuardrailDecision(
                        action="block",
                        code="claude_deny_pattern",
                        message=(
                            "Command blocked by safety deny pattern. "
                            "This is a protective rule from claude_deny_patterns."
                        ),
                        tool_name=tool_name,
                        signature=signature,
                    )
            except ImportError:
                logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

        if tool_name in ["web_search", "web_scrape", "fetch_dom"] and args:
            url = _as_text(args.get("url") or args.get("query"), "")
            if not engine.is_domain_allowed(url):
                return ToolGuardrailDecision(
                    action="block",
                    code="policy_denied",
                    message=f"Domain '{url}' is blocked by declarative security policy.",
                    tool_name=tool_name,
                    signature=signature,
                )

        if not self.config.hard_stop_enabled:
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        # 동일 인자 반복 실패 차단
        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = ToolGuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"{tool_name} 도구가 동일한 인자로 {exact_count}회 실패했습니다. "
                    "인자를 변경하거나 다른 전략을 시도하세요."
                ),
                tool_name=tool_name,
                count=exact_count,
                signature=signature,
            )
            self._halt_decision = decision
            return decision

        # 비진행성 차단 (읽기 전용 도구)
        if self._is_idempotent(tool_name):
            record = self._no_progress.get(signature)
            if record is not None:
                _, repeat_count = record
                if repeat_count >= self.config.no_progress_block_after:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"{tool_name} 도구가 동일한 결과를 {repeat_count}회 반환했습니다. "
                            "이미 제공된 결과를 사용하거나 다른 쿼리를 시도하세요."
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                        signature=signature,
                    )
                    self._halt_decision = decision
                    return decision

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, object] | None = None,
        result: str | None = None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        """도구 실행 후 결과 분석.

        실패/비진행성 카운터를 업데이트하고 경고/차단을 반환합니다.
        """
        args = _coerce_args(args)
        signature = ToolCallSignature.from_call(tool_name, args)

        if failed is None:
            failed, _ = classify_tool_failure(tool_name, result)

        if failed:
            return self._handle_failure(tool_name, signature)

        # 성공 시 카운터 리셋
        _ = self._exact_failure_counts.pop(signature, None)
        _ = self._same_tool_failure_counts.pop(tool_name, None)

        if not self._is_idempotent(tool_name):
            _ = self._no_progress.pop(signature, None)
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        # 비진행성 추적 (읽기 전용 도구)
        result_hash = _result_hash(result)
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (result_hash, repeat_count)

        if self.config.warnings_enabled and repeat_count >= self.config.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} 도구가 동일한 결과를 {repeat_count}회 반환했습니다. "
                    "이미 제공된 결과를 사용하거나 쿼리를 변경하세요."
                ),
                tool_name=tool_name,
                count=repeat_count,
                signature=signature,
            )

        return ToolGuardrailDecision(tool_name=tool_name, count=repeat_count, signature=signature)

    def _handle_failure(
        self,
        tool_name: str,
        signature: ToolCallSignature,
    ) -> ToolGuardrailDecision:
        """실패 시 카운터 업데이트 및 경고/차단 판정."""
        # 동일 인자 반복 실패 카운트
        exact_count = self._exact_failure_counts.get(signature, 0) + 1
        self._exact_failure_counts[signature] = exact_count
        _ = self._no_progress.pop(signature, None)

        # 동일 도구 누적 실패 카운트
        same_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
        self._same_tool_failure_counts[tool_name] = same_count

        # 차단 판정 (hard_stop 활성 시)
        if self.config.hard_stop_enabled and same_count >= self.config.same_tool_failure_halt_after:
            decision = ToolGuardrailDecision(
                action="halt",
                code="same_tool_failure_halt",
                message=(
                    f"{tool_name} 도구가 이번 턴에서 {same_count}회 실패했습니다. 다른 도구나 접근 방법을 사용하세요."
                ),
                tool_name=tool_name,
                count=same_count,
                signature=signature,
            )
            self._halt_decision = decision
            return decision

        # 경고 판정
        if self.config.warnings_enabled:
            if exact_count >= self.config.exact_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=(
                        f"{tool_name} 도구가 동일한 인자로 {exact_count}회 실패했습니다. "
                        "에러를 확인하고 인자를 변경하세요."
                    ),
                    tool_name=tool_name,
                    count=exact_count,
                    signature=signature,
                )

            if same_count >= self.config.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(f"{tool_name} 도구가 이번 턴에서 {same_count}회 실패했습니다. 접근 방법을 변경해 보세요."),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )

        return ToolGuardrailDecision(tool_name=tool_name, count=exact_count, signature=signature)

    def _is_idempotent(self, tool_name: str) -> bool:
        """도구가 읽기 전용(비진행성 추적 대상)인지 확인."""
        if tool_name in self.config.mutating_tools:
            return False
        return tool_name in self.config.idempotent_tools


# ── 합성 결과 생성 ──


def guardrail_synthetic_result(decision: ToolGuardrailDecision) -> str:
    """차단된 도구 호출에 대한 합성 에러 결과를 생성합니다."""
    return json.dumps(
        {
            "error": decision.message,
            "guardrail": decision.to_dict(),
        },
        ensure_ascii=False,
    )


def append_guardrail_guidance(result: str, decision: ToolGuardrailDecision) -> str:
    """경고 메시지를 도구 결과에 추가합니다."""
    if decision.action not in {"warn", "halt"} or not decision.message:
        return result
    label = "⛔ Tool loop 강제 중단" if decision.action == "halt" else "⚠️ Tool loop 경고"
    suffix = f"\n\n[{label}: {decision.code}; count={decision.count}; {decision.message}]"
    return (result or "") + suffix


# ── 유틸리티 ──


def _canonical_args(args: Mapping[str, object]) -> str:
    """인자를 정규화된 JSON 문자열로 변환."""
    return json.dumps(
        args,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _coerce_args(args: Mapping[str, object] | None) -> Mapping[str, object]:
    return args if isinstance(args, Mapping) else {}


def _result_hash(result: str | None) -> str:
    """결과 문자열의 정규화된 해시."""
    content = result or ""
    try:
        parsed = cast(object, json.loads(content))
        canonical = json.dumps(
            parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (json.JSONDecodeError, TypeError):
        canonical = content
    return _sha256(canonical)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _positive_int(value: object, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = int(value)
        return parsed if parsed >= 1 else default
    except (TypeError, ValueError):
        return default
