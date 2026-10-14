"""FailureClassifier + RecoveryStrategy — 도구 실패 분류 및 복구 플레이북.

========================================================
P0 개선: "연속 에러 카운터 → Immune System → Vault Rollback"의 단순 복구를
실패 유형 분류 + 유형별 복구 전략 레지스트리로 격상.

분류 파이프라인 (결정론적, LLM 불필요):
  1. 실패 마커 정밀 매칭 ([BLOCKED], [DENIED], [APPROVAL REQUIRED], [exit_code=N])
  2. 에러 메시지 패턴 매칭 (timeout, sandbox, git conflict 등)
  3. 폴백: unknown (재시도 가능)

사용법:
    from antigravity_k.engine.failure_classifier import (
        classify_tool_failure,
        RecoveryStrategyRegistry,
    )

    classified = classify_tool_failure("git_commit", result_text)
    strategy = registry.strategy_for(classified.tool_name, classified.category)
    guidance = strategy.render(classified)
"""

from __future__ import annotations

import enum
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger("antigravity_k.engine.failure_classifier")


# ── 실패 유형 분류 ──


class FailureCategory(enum.Enum):
    """도구 실행 실패 유형 — 복구 전략 선택의 기준."""

    unknown_tool = "unknown_tool"  # 존재하지 않는 도구 이름
    missing_arguments = "missing_arguments"  # 필수 인자 누락
    invalid_arguments = "invalid_arguments"  # 인자 타입/포맷 오류
    file_not_found = "file_not_found"  # 대상 파일/경로 없음
    permission_denied = "permission_denied"  # 권한 규칙 차단 (DENY)
    blocked_by_guard = "blocked_by_guard"  # PlanGuard/GatePipeline 차단
    approval_required = "approval_required"  # 사용자 승인 필요 (PROMPT/PAUSE)
    timeout = "timeout"  # 실행/연결 타임아웃
    external_service = "external_service"  # 외부 서비스 실패 (웹 검색 등)
    sandbox_violation = "sandbox_violation"  # 샌드박스 격리 위반
    git_conflict = "git_conflict"  # git 저장소 상태 충돌
    test_failure = "test_failure"  # 테스트 실패
    lint_failure = "lint_failure"  # 린트 실패
    resource_exhausted = "resource_exhausted"  # 메모리/디스크 등 자원 고갈
    unknown = "unknown"  # 분류 불가 — 기존 복구 경로 유지


@dataclass
class ClassifiedFailure:
    """도구 실패의 구조화된 분류 결과."""

    category: FailureCategory
    tool_name: str
    message: str = ""
    matched_pattern: str = ""

    @property
    def retryable(self) -> bool:
        """일시적 원인으로 재시도가 합리적인 유형인지."""
        return self.category in (
            FailureCategory.timeout,
            FailureCategory.external_service,
            FailureCategory.unknown,
        )


# ── 분류 패턴 테이블 (우선순위 순) ──


_PATTERNS: list[tuple[FailureCategory, re.Pattern[str]]] = [
    (FailureCategory.unknown_tool, re.compile(r"Unknown tool '([^']+)'")),
    (FailureCategory.missing_arguments, re.compile(r"Missing required arguments:")),
    (FailureCategory.blocked_by_guard, re.compile(r"\[BLOCKED\]")),
    (FailureCategory.approval_required, re.compile(r"\[APPROVAL REQUIRED\]")),
    (FailureCategory.permission_denied, re.compile(r"\[DENIED\]")),
    (
        FailureCategory.sandbox_violation,
        re.compile(
            r"(?:sandbox-exec|Seatbelt|Operation not permitted|sandbox deny)",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.timeout,
        re.compile(r"(?:timed? ?out|timeout|TimeoutError|TimeLimitExceeded)", re.IGNORECASE),
    ),
    (
        FailureCategory.git_conflict,
        re.compile(
            r"(?:not a git repository|nothing to commit|Your local changes|merge conflict|fatal:)",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.file_not_found,
        re.compile(r"(?:No such file or directory|FileNotFoundError|does not exist)"),
    ),
    (
        FailureCategory.test_failure,
        re.compile(r"(?:FAILED|AssertionError|pytest|tests? failed)"),
    ),
    (
        FailureCategory.lint_failure,
        re.compile(r"(?:ruff|mypy|lint)", re.IGNORECASE),
    ),
    (
        FailureCategory.resource_exhausted,
        re.compile(
            r"(?:out of memory|MemoryError|No space left|Resource temporarily unavailable)",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.external_service,
        re.compile(
            r"(?:connection (?:error|refused|reset)|ECONNREFUSED|no results found|unavailable|HTTP \d{3})",
            re.IGNORECASE,
        ),
    ),
    (
        FailureCategory.invalid_arguments,
        re.compile(r"(?:invalid|must be (?:a|an)|TypeError|ValueError)", re.IGNORECASE),
    ),
]


def classify_tool_failure(tool_name: str, result_text: str) -> ClassifiedFailure:
    """도구 실패 문자열을 유형으로 분류합니다."""
    text = str(result_text)

    for category, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            return ClassifiedFailure(category, tool_name, text, matched_pattern=m.group(0))

    return ClassifiedFailure(FailureCategory.unknown, tool_name, text)


# ── 복구 전략 ──


class RecoveryAction(enum.Enum):
    """실패 유형에 대응하는 복구 동작."""

    RETRY = "retry"  # 동일 인자 재시도
    RETRY_FIXED = "retry_fixed"  # 인자/접근 수정 후 재시도
    SUGGEST_ALTERNATIVE = "suggest_alternative"  # 대체 도구/방식 제안
    ASK_USER = "ask_user"  # 사용자 승인/정보 요청
    STOP = "stop"  # 영구 중단 (보안/자원)
    ESCALATE_IMMUNE = "escalate_immune"  # Immune System 자가 수복 경로로


@dataclass(frozen=True)
class RecoveryStrategy:
    """실패 유형 → 복구 동작 + 모델용 안내 문구."""

    action: RecoveryAction
    max_attempts: int = 1
    guidance_template: str = ""

    def render(self, failure: ClassifiedFailure) -> str:
        """모델 컨텍스트에 넣을 복구 안내 문자열을 생성합니다."""
        if not self.guidance_template:
            return (
                f"[RECOVERY:{self.action.value}] Tool '{failure.tool_name}' failed "
                f"with category '{failure.category.value}'. {failure.message[:300]}"
            )
        return self.guidance_template.format(
            tool=failure.tool_name,
            message=failure.message[:300],
        )


# ── 기본 플레이북 (유형별) ──


DEFAULT_PLAYBOOK: dict[FailureCategory, RecoveryStrategy] = {
    FailureCategory.unknown_tool: RecoveryStrategy(
        RecoveryAction.SUGGEST_ALTERNATIVE,
        guidance_template=(
            "Tool '{tool}' does not exist. Check the ToolRegistry for a valid tool name and call it again."
        ),
    ),
    FailureCategory.missing_arguments: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Tool '{tool}' failed: missing required arguments. Fill every required "
            "field from the tool schema and call it again: {message}"
        ),
    ),
    FailureCategory.invalid_arguments: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Tool '{tool}' failed: invalid arguments. Fix the argument types/formats and call it again: {message}"
        ),
    ),
    FailureCategory.file_not_found: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Tool '{tool}' failed: target file or directory does not exist. Verify "
            "the path and call it again: {message}"
        ),
    ),
    FailureCategory.permission_denied: RecoveryStrategy(
        RecoveryAction.ASK_USER,
        guidance_template=(
            "Tool '{tool}' was blocked by permission rules. Stop and ask the user "
            "whether to allow this action before retrying."
        ),
    ),
    FailureCategory.blocked_by_guard: RecoveryStrategy(
        RecoveryAction.SUGGEST_ALTERNATIVE,
        guidance_template=(
            "Tool '{tool}' was blocked by the plan guard in the current execution "
            "mode. Reconsider the approach and choose a different action: {message}"
        ),
    ),
    FailureCategory.approval_required: RecoveryStrategy(
        RecoveryAction.ASK_USER,
        guidance_template=(
            "Tool '{tool}' requires user approval. Stop executing tools immediately "
            "and ask the user for permission. Wait for 'Yes' before retrying."
        ),
    ),
    FailureCategory.timeout: RecoveryStrategy(
        RecoveryAction.RETRY,
        max_attempts=2,
        guidance_template=(
            "Tool '{tool}' timed out. Retry once after a short pause; if it fails "
            "again, simplify the request or split it into smaller steps."
        ),
    ),
    FailureCategory.external_service: RecoveryStrategy(
        RecoveryAction.RETRY,
        max_attempts=2,
        guidance_template=(
            "Tool '{tool}' hit an external service failure. Retry once; if it fails "
            "again, use a fallback query or an alternative source: {message}"
        ),
    ),
    FailureCategory.sandbox_violation: RecoveryStrategy(
        RecoveryAction.STOP,
        guidance_template=(
            "Tool '{tool}' attempted an operation blocked by the sandbox. Stop this "
            "approach and choose a different, sandbox-compatible action."
        ),
    ),
    FailureCategory.git_conflict: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Tool '{tool}' failed because of the git working-tree state. Inspect "
            "'git status' and resolve conflicts or uncommitted changes first: {message}"
        ),
    ),
    FailureCategory.test_failure: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Tests failed while running '{tool}'. Read the failing test output, fix "
            "the root cause, and run the tests again: {message}"
        ),
    ),
    FailureCategory.lint_failure: RecoveryStrategy(
        RecoveryAction.RETRY_FIXED,
        guidance_template=(
            "Lint check failed while running '{tool}'. Fix the reported style/type "
            "issues and run the check again: {message}"
        ),
    ),
    FailureCategory.resource_exhausted: RecoveryStrategy(
        RecoveryAction.STOP,
        guidance_template=(
            "Tool '{tool}' exhausted a system resource. Stop and inform the user; do not retry with the same approach."
        ),
    ),
    FailureCategory.unknown: RecoveryStrategy(
        RecoveryAction.ESCALATE_IMMUNE,
        guidance_template="",
    ),
}


# ── 도구별 플레이북 오버라이드 ──


TOOL_PLAYBOOKS: dict[str, dict[FailureCategory, RecoveryStrategy]] = {
    "web_search": {
        FailureCategory.external_service: RecoveryStrategy(
            RecoveryAction.SUGGEST_ALTERNATIVE,
            guidance_template=(
                "Web search failed for '{tool}'. Rewrite the query into a shorter, "
                "keyword-focused fallback and retry with a different engine."
            ),
        ),
    },
    "run_bash_command": {
        FailureCategory.external_service: RecoveryStrategy(
            RecoveryAction.RETRY_FIXED,
            guidance_template=(
                "Command failed with an external/network error. Check connectivity or use a simpler command: {message}"
            ),
        ),
    },
}


# ── 레지스트리 ──


class RecoveryStrategyRegistry:
    """유형별 기본 전략 + 도구별 오버라이드를 합성하는 복구 전략 레지스트리."""

    def __init__(self) -> None:
        self._defaults: dict[FailureCategory, RecoveryStrategy] = dict(DEFAULT_PLAYBOOK)
        self._overrides: dict[str, dict[FailureCategory, RecoveryStrategy]] = defaultdict(dict)
        for tool, playbook in TOOL_PLAYBOOKS.items():
            self._overrides[tool].update(playbook)

    def strategy_for(self, tool_name: str, category: FailureCategory) -> RecoveryStrategy:
        """도구 이름 → 유형 순으로 전략을 결정합니다 (오버라이드 우선)."""
        tool_playbook = self._overrides.get(tool_name)
        if tool_playbook and category in tool_playbook:
            return tool_playbook[category]
        return self._defaults.get(category, DEFAULT_PLAYBOOK[FailureCategory.unknown])

    def register_override(
        self,
        tool_name: str,
        category: FailureCategory,
        strategy: RecoveryStrategy,
    ) -> None:
        """런타임에 도구별 오버라이드 전략을 등록합니다."""
        self._overrides[tool_name][category] = strategy

    def suggest_recovery(self, failure: ClassifiedFailure) -> str:
        """분류 결과에 맞는 복구 안내 문자열을 반환합니다."""
        return self.strategy_for(failure.tool_name, failure.category).render(failure)
