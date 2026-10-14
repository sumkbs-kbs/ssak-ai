"""Ssak-Ai: 인지 루프 엔진 (CognitiveLoop).

==============================================
E-1: AI 에이전트의 사고 패턴을 구현합니다.

현재 Ssak-Ai: CEO 분류 → 에이전트 실행 → 끝 (1-pass)
개선 후:          Plan → Execute → Verify → Reflect → Adapt (순환)

이 모듈은 에이전트가 "생각하고 → 실행하고 → 검증하고 → 배우는"
인간 전문가의 인지 패턴을 에뮬레이트합니다.
"""

import ast
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, cast, final

import anyio

from antigravity_k.engine.external_brain import BrainResponse
from antigravity_k.engine.failure_memory import FailureMemory
from antigravity_k.engine.memory.cavemem_store import CavememStore
from antigravity_k.engine.project_memory_paths import project_memory_dir
from antigravity_k.engine.tool_guardrails import classify_tool_failure

logger = logging.getLogger(__name__)


class StepHistoryEntry(TypedDict):
    tool: str
    grade: str
    passed: bool
    issues: list[str]
    timestamp: NotRequired[str]


class VerificationResult(TypedDict):
    passed: bool
    grade: str
    issues: list[str]
    suggestion: str
    dialectic_applied: bool


class ExecutionTrace(TypedDict):
    plan_goal: str
    total_steps: int
    replans: int
    success: bool
    timestamp: str


class ExternalBrainRouterLike(Protocol):
    async def send(self, prompt: str, strategy: str = "fallback") -> BrainResponse: ...


@dataclass
class ReflectionResult:
    """작업 완료 후 성찰 결과."""

    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    should_retry: bool = False
    retry_strategy: str = ""


def _split_explicit_steps(task: str) -> list[str]:
    """Deterministically split a task with explicit numbered or bulleted sub-items.

    Detects "1. ... 2. ..." / "1) ... 2) ..." / "- ... - ..." patterns and returns each
    item as a separate step. Returns an empty list when no multi-part structure is found,
    so a single-part task stays a single step. No LLM call — pure structural parsing.
    """
    import re

    lines = task.strip().splitlines()
    # Numbered list: "1." "1)" "①" (optionally preceded by whitespace), each on its own line.
    numbered = [ln for ln in lines if re.match(r"\s*\d+[.)]\s+\S", ln)]
    if len(numbered) >= 2:
        cleaned = [re.sub(r"^\s*\d+[.)]\s+", "", ln).strip() for ln in numbered]
        return [c for c in cleaned if c]
    # Bulleted list: "- " or "* " lines (excluding markdown code fences).
    bulleted = [ln for ln in lines if re.match(r"\s*[-*]\s+\S", ln) and not ln.strip().startswith("```")]
    if len(bulleted) >= 2:
        cleaned = [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in bulleted]
        return [c for c in cleaned if c]
    return []


@final
class CognitiveLoop:
    """Plan → Execute → Verify → Reflect → Adapt 인지 순환 엔진.

    Orchestrator의 _run_single_agent() 내부에서 사용되어,
    각 도구 실행 후 자동 검증 및 실패 시 전략 변경을 수행합니다.

    사용자 이익 원칙:
    - 검증 실패 시 자동으로 다른 접근법 시도
    - 반복 실패 시 사용자에게 솔직하게 보고
    - 모든 학습 내용을 영속적으로 저장
    """

    def __init__(
        self,
        project_root: str = ".",
        failure_memory: FailureMemory | None = None,
        external_brain_router: ExternalBrainRouterLike | None = None,
        enable_caveman: bool = False,
        max_retries: int | None = None,
        dialectic_enabled: bool | None = None,
    ):
        """Initialize the CognitiveLoop.

        Args:
            project_root (str): str project root.
            failure_memory: failure memory.
            external_brain_router: external brain router.
            enable_caveman (bool): bool enable caveman.
            max_retries: 실패 시 재시도 한계 (None=기본값 2). 작은 모델은 늘려 추론 깊이 보완.
            dialectic_enabled: 정반합 자기 비판 적용 여부 (None=기본값 True).

        """
        self.project_root: str = str(Path(project_root).resolve())
        self.failure_memory: FailureMemory | None = failure_memory
        self._external_brain_router: ExternalBrainRouterLike | None = external_brain_router
        self._step_history: list[StepHistoryEntry] = []
        self._retry_count: int = 0
        self._max_retries: int = 2 if max_retries is None else max_retries
        # amplification.cognitive.dialectic_enabled로 오버라이드 가능 (기본 True).
        self._dialectic_enabled: bool = True if dialectic_enabled is None else dialectic_enabled
        self.enable_caveman: bool = enable_caveman
        cavemem_path = project_memory_dir(self.project_root) / "cavemem.sqlite3"
        self.cavemem_store: CavememStore = CavememStore(str(cavemem_path))

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def dialectic_enabled(self) -> bool:
        return self._dialectic_enabled

    # ─── Phase 2: VERIFY ─────────────────────────────────────

    def verify_tool_result(self, tool_name: str, tool_args: dict[str, object], result: str) -> VerificationResult:
        """도구 실행 결과를 자동 검증합니다.

        Returns:
            {
                "passed": bool,
                "grade": "A" | "B" | "C" | "F",
                "issues": [...],
                "suggestion": "..."
            }

        """
        issues: list[str] = []
        grade: str = "A"

        # 에러 감지
        result_lower = result.lower()

        # 명시적 에러
        tool_failed, _ = classify_tool_failure(tool_name, result)
        if tool_failed or result.strip().startswith(
            "There was an error",
        ):
            grade = "F"
            issues.append(f"도구 '{tool_name}'이 에러를 반환했습니다")

            # 파일 관련 도구: 파일 존재 여부 확인
            raw_file_path = tool_args.get("file_path") or tool_args.get("path", "")
            file_path = raw_file_path if isinstance(raw_file_path, str) else ""
            if tool_name in ("write_file", "edit_file", "replace_file_content"):
                if file_path and not os.path.exists(file_path):
                    # 상대 경로면 프로젝트 루트 기준
                    abs_path = os.path.join(self.project_root, file_path)
                    if not os.path.exists(abs_path):
                        grade = "C"
                        issues.append(f"파일이 생성/수정되었으나 확인할 수 없음: {file_path}")

            # 코드 생성 도구: AST 검증
            if tool_name in ("write_file", "edit_file") and file_path and file_path.endswith(".py"):
                try:
                    actual_path = file_path if os.path.exists(file_path) else os.path.join(self.project_root, file_path)
                    if os.path.exists(actual_path):
                        with open(actual_path, encoding="utf-8") as f:
                            _ = ast.parse(f.read())
                except SyntaxError as e:
                    grade = "F"
                    issues.append(f"생성된 Python 코드에 구문 오류: {e}")

            # bash 명령: exit code 확인
            if tool_name == "run_bash_command":
                if "command not found" in result_lower:
                    grade = "C"
                    issues.append("명령어를 찾을 수 없음")
                elif "permission denied" in result_lower:
                    grade = "C"
                    issues.append("권한 거부됨")
                elif "traceback" in result_lower or "error:" in result_lower:
                    grade = "C"
                    issues.append("명령 실행 중 에러 발생")

            # 빈 결과
            if not result.strip():
                grade = "C"
                issues.append("도구가 빈 결과를 반환했습니다")

        passed = grade in ("A", "B")

        # 실패 시 제안
        suggestion = ""
        if not passed:
            suggestion = self._suggest_fix(tool_name, tool_args, result, issues)

        # 이력 기록 (Local memory)
        self._step_history.append(
            {
                "tool": tool_name,
                "grade": grade,
                "passed": passed,
                "issues": issues,
                "timestamp": datetime.now().isoformat(),
            },
        )

        # 영구 장기 기억 (Cavemem)
        obs_content = (
            f"Tool '{tool_name}' returned grade {grade}. Passed: {passed}. Issues: {issues}. Suggestion: {suggestion}"
        )
        _ = self.cavemem_store.store_observation(session_id="cognitive_loop", content=obs_content)

        return {
            "passed": passed,
            "grade": grade,
            "issues": issues,
            "suggestion": suggestion,
            "dialectic_applied": not passed and self._dialectic_enabled,
        }

    def _suggest_fix(self, _tool_name: str, _args: dict[str, object], _result: str, issues: list[str]) -> str:
        """검증 실패 시 수정 제안을 생성합니다."""
        if "구문 오류" in str(issues):
            return "코드를 다시 검토하고, 들여쓰기와 괄호 매칭을 확인하세요."
        if "찾을 수 없음" in str(issues):
            return "명령어 또는 패키지가 설치되어 있는지 확인하세요."
        if "권한 거부" in str(issues):
            return "sudo를 사용하거나 파일 권한을 확인하세요."
        if "에러를 반환" in str(issues):
            return "에러 메시지를 분석하고 다른 접근법을 시도하세요."
        return "결과를 재검토하고 다른 전략을 시도하세요."

    # ─── Phase 2.5: Auto Memory Extraction (SurfSense 패턴) ───

    def auto_extract_memory(self, user_message: str, model_fn: Callable[[str], str] | None = None) -> None:
        """사용자 메시지에서 장기 기억할 가치가 있는 정보를 자동 추출합니다.

        SurfSense의 memory_extraction.py 패턴을 적용하여,
        대화 턴마다 fire-and-forget으로 호출합니다.
        """
        # 기억 추출 실패가 메인 루프를 막지 않도록 모든 예외를 안전하게 처리
        try:
            _ = self.cavemem_store.extract_memory(
                user_message=user_message,
                session_id="cognitive_loop",
                model_fn=model_fn,
            )
        except (IOError, OSError, ValueError) as e:
            logger.warning("Memory extraction I/O or data error: %s", e, exc_info=True)
        except RuntimeError as e:
            logger.error("Memory extraction runtime error: %s", e, exc_info=True)

    # ─── Phase 3: REFLECT ─────────────────────────────────────

    def reflect(self, task: str, _full_output: str) -> ReflectionResult:
        """작업 완료 후 성찰을 수행합니다."""
        result = ReflectionResult()

        # 이력 기반 자동 성찰
        for step in self._step_history:
            if step["passed"]:
                result.what_worked.append(f"{step['tool']}: 성공 (등급 {step['grade']})")
            else:
                result.what_failed.append(f"{step['tool']}: 실패 — {', '.join(step['issues'])}")

        # 실패율 계산
        total = len(self._step_history)
        if total > 0:
            fail_rate = len(result.what_failed) / total
            if fail_rate > 0.5:
                result.lessons.append(
                    f"이 작업의 실패율이 {fail_rate:.0%}로 높습니다. 접근 방식을 근본적으로 재검토해야 합니다.",
                )
                result.should_retry = self._retry_count < self._max_retries
                result.retry_strategy = "이전에 실패한 도구/접근법을 피하고 완전히 다른 전략 사용"
            elif fail_rate > 0.2:
                result.lessons.append(
                    f"일부 단계({len(result.what_failed)}건)에서 문제가 발생했습니다. 해당 패턴을 기억합니다.",
                )

        # Persist lessons to failure memory so future tasks with the same pattern can
        # recall them — without this the reflection is computed and thrown away.
        if result.lessons and self.failure_memory:
            failed_tools = {step["tool"] for step in self._step_history if not step["passed"]}
            for lesson in result.lessons:
                self.failure_memory.record(
                    tool=",".join(sorted(failed_tools)) if failed_tools else "unknown",
                    error_text=lesson,
                    args_summary=task[:200],
                    fix_applied=result.retry_strategy,
                )

        return result

    def format_reflection_prompt(self, reflection: ReflectionResult) -> str:
        """성찰 결과를 에이전트 프롬프트에 주입할 텍스트로 포맷합니다."""
        if not reflection.what_failed and not reflection.lessons:
            return ""

        lines = ["\n<reflection>"]
        if reflection.what_worked:
            lines.append("✅ 성공한 것: " + "; ".join(reflection.what_worked[:3]))
        if reflection.what_failed:
            lines.append("❌ 실패한 것: " + "; ".join(reflection.what_failed[:3]))
        if reflection.lessons:
            lines.append("💡 교훈: " + "; ".join(reflection.lessons[:2]))
        if reflection.should_retry:
            lines.append("🔄 재시도 전략: " + reflection.retry_strategy)
        lines.append("</reflection>")

        return "\n".join(lines)

    # ─── Phase 4: ADAPT ──────────────────────────────────────

    async def adapt_strategy(self, task: str, _step_ctx: object) -> str | None:
        """StepContext 상태를 분석하여 반복되는 오류가 있는지 확인하고,.

        필요 시 에이전트의 전략을 동적으로 적응(Adapt)시킵니다.
        3회 이상 연속 실패 시 External Brain에 자동 위임합니다.
        """
        if not self._step_history:
            return None

        recent_failures = [s for s in self._step_history[-3:] if not s["passed"]]

        # 최근 3번 모두 실패 → External Brain 자동 위임
        if len(recent_failures) >= 3 and self._external_brain_router:
            delegation_result = await self.auto_delegate_to_external_brain(task, recent_failures)
            if delegation_result:
                self._retry_count += 1
                self._publish_cognitive_adaptation(
                    reason="반복 실패 감지 — External Brain 자동 위임",
                    adaptation=delegation_result,
                )
                self._publish_anti_patterns(
                    reason="반복 실패 감지 — External Brain 자동 위임",
                    tools=[str(f["tool"]) for f in recent_failures],
                )
                return delegation_result

        # 최근 3번 중 2번 이상 실패한 경우 전략 변경 제안
        if len(recent_failures) >= 2:
            self._retry_count += 1
            tools_failed = list(set([f["tool"] for f in recent_failures]))

            adaptation = (
                "\n\n🚨 **[Cognitive Adapt] 전략 변경 필요** 🚨\n"
                f"최근 시도에서 계속 문제가 발생하고 있습니다 (실패 도구: {', '.join(tools_failed)}).\n"
                "기존 접근 방식을 완전히 버리고, 다음과 같이 적응하세요:\n"
                "1. 사용하던 도구를 바꾸거나, 인자를 근본적으로 다르게 설정하세요.\n"
                "2. 문제를 더 작은 단위로 쪼개어 단순한 도구부터 검증하세요.\n"
                "3. 파일 권한이나 환경의 제약이 있는지 확인하는 도구(예: run_bash_command로 ls -la)를 먼저 실행하세요.\n"  # noqa: E501
            )
            self._publish_cognitive_adaptation(
                reason=f"반복 실패 감지 (실패 도구: {', '.join(tools_failed)})",
                adaptation=adaptation,
            )
            self._publish_anti_patterns(
                reason=f"반복 실패 감지 (실패 도구: {', '.join(tools_failed)})",
                tools=tools_failed,
            )
            return adaptation

        return None

    def _publish_cognitive_adaptation(self, reason: str, adaptation: str) -> None:
        """EventBus로 CognitiveAdaptation 이벤트를 발행합니다.

        Dashboard WebSocket(useEventWebSocket)이 이 이벤트를 수신하여
        에이전트 모니터링 패널에 전략 적응(Adapt) 로그를 표시합니다.
        이벤트 발행은 선택적(non-critical)이므로 실패해도 적응 로직은 계속됩니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            global_event_bus.publish(
                "CognitiveAdaptation",
                reason=reason,
                adaptation=adaptation,
            )
        except Exception:
            logger.exception("[CognitiveLoop] CognitiveAdaptation publish failed")

    def _publish_anti_patterns(self, reason: str, tools: list[str]) -> None:
        """EventBus로 AntiPatternsDetected 이벤트를 발행합니다.

        반복 실패(안티패턴) 감지 시 세션에서 누적된 실패 패턴을 전달합니다.
        Dashboard WebSocket(useEventWebSocket)과 Kanban 보드(kanban_api)가
        이 이벤트를 소비합니다.
        이벤트 발행은 선택적(non-critical)이므로 실패해도 적응 로직은 계속됩니다.
        """
        try:
            from antigravity_k.engine.event_bus import global_event_bus

            global_event_bus.publish(
                "AntiPatternsDetected",
                reason=reason,
                tools=tools,
                patterns=self.get_anti_patterns(),
            )
        except Exception:
            logger.exception("[CognitiveLoop] AntiPatternsDetected publish failed")

    async def auto_delegate_to_external_brain(
        self,
        task: str,
        failures: Sequence[Mapping[str, object]],
    ) -> str | None:
        """반복 실패 시 External Brain(Gemini/ChatGPT)에 자동 위임하여.

        전문가 조언을 받아 다음 시도에 주입합니다.

        Returns:
            외부 두뇌의 조언을 포함한 적응 프롬프트, 또는 None

        """
        if not self._external_brain_router:
            return None

        # 위임 프롬프트 구성: 실패 이력 + 원래 목표
        def format_failure(failure: Mapping[str, object]) -> str:
            tool = str(failure.get("tool", "unknown"))
            raw_issues = failure.get("issues", [])
            issues = cast(list[object], raw_issues) if isinstance(raw_issues, list) else [raw_issues]
            return f"- 도구 '{tool}': {', '.join(str(issue) for issue in issues)}"

        failure_summary = "\n".join(format_failure(failure) for failure in failures[:3])

        delegation_prompt = (
            f"다음 작업을 수행하려 했으나 {len(failures)}회 연속 실패했습니다.\n\n"
            f"## 작업 목표\n{task}\n\n"
            f"## 실패 이력\n{failure_summary}\n\n"
            "위 실패 패턴을 분석하고, 이 문제를 해결하기 위한 "
            "구체적이고 실행 가능한 접근법을 3가지 제안해주세요. "
            "각 접근법에 사용할 도구/명령어와 예상 결과를 포함하세요."
        )

        try:
            with anyio.fail_after(30):
                result = await self._external_brain_router.send(
                    delegation_prompt,
                    strategy="fallback",
                )

            if result and result.success and result.text:
                advice = result.text[:2000]
                logger.info(
                    "[CognitiveLoop] External Brain advice received from %s (%sms)",
                    result.source,
                    result.latency_ms,
                )

                # 실패 메모리에 저장
                if self.failure_memory:
                    failed_tool = str(failures[0].get("tool", "unknown"))
                    self.failure_memory.record(
                        tool=failed_tool,
                        error_text=f"3x_failure_{failed_tool}",
                        args_summary=task,
                        fix_applied=f"external_brain_delegation_{result.source}",
                    )

                return (
                    "\n\n🧠 **[External Brain 자동 위임]** 🧠\n"
                    f"반복 실패를 감지하여 외부 AI({result.source})에 자동 위임했습니다.\n\n"
                    f"### 전문가 조언\n{advice}\n\n"
                    "위 조언을 참고하여 완전히 다른 접근법으로 재시도하세요."
                )

        except Exception:
            logger.exception("[CognitiveLoop] External Brain delegation failed")

        return None

    # ─── Phase 4: ADAPT ─────────────────────────────────────

    def adapt_for_retry(self) -> bool:
        """재시도 가능 여부를 판단하고, 가능하면 전략을 변경합니다."""
        if self._retry_count >= self._max_retries:
            return False

        self._retry_count += 1

        # 실패한 도구/접근법 목록을 다음 시도에서 제외
        failed_tools = [s["tool"] for s in self._step_history if not s["passed"]]

        logger.info(
            "[CognitiveLoop] Adapting for retry %s/%s. Excluding failed tools: %s",
            self._retry_count,
            self._max_retries,
            failed_tools,
        )
        return True

    def get_anti_patterns(self) -> list[str]:
        """이번 세션에서 실패한 패턴 목록을 반환합니다 (프롬프트 주입용)."""
        patterns: list[str] = []
        for step in self._step_history:
            if not step["passed"]:
                patterns.append(
                    f"'{step['tool']}' 사용 시 다음 문제 발생: {', '.join(step['issues'])}",
                )
        return patterns

    def reset(self) -> None:
        """새 작업을 위해 루프를 초기화합니다."""
        self._step_history = []
        self._retry_count = 0
