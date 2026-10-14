"""Workspace change review handler for the orchestrator state graph."""

import logging
import subprocess
from collections.abc import Callable, Generator, Iterable, Mapping
from typing import Protocol, cast

from antigravity_k.engine.state_graph import StateContext
from antigravity_k.engine.tool_guardrails import MUTATING_TOOL_NAMES

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")

__all__ = ["_agent_used_mutating_tool", "code_review_handler"]


class _ToolExecutorLike(Protocol):
    tool_call_history: Iterable[Mapping[str, object]]


class _OrchestratorContextLike(Protocol):
    tool_executor: _ToolExecutorLike


class _ManagerLike(Protocol):
    def generate(self, *args: object, **kwargs: object) -> object: ...


class _OrchestratorLike(Protocol):
    ctx: _OrchestratorContextLike
    project_root: str
    manager: _ManagerLike | None

    def _get_model_for_role(self, role: str) -> str: ...


def _model_for_role(orch: _OrchestratorLike, role: str) -> str:
    resolver = cast(Callable[[str], str], getattr(orch, "_get_model_for_role"))
    return resolver(role)


def _agent_used_mutating_tool(orch: _OrchestratorLike, started_at: float) -> bool:
    history = orch.ctx.tool_executor.tool_call_history
    for entry in history:
        if entry.get("name") not in MUTATING_TOOL_NAMES:
            continue
        timestamp = entry.get("timestamp")
        if not isinstance(timestamp, (int, float)):
            continue
        timestamp_value = float(timestamp)
        if timestamp_value >= started_at:
            return True
    return False


def code_review_handler(ctx: StateContext, orch: _OrchestratorLike) -> Generator[str, None, None]:
    """코드 변경 사항을 자동 리뷰합니다. (After CoV)

    COV_VERIFY 완료 후 호출되어:
    1. Git diff 확인
    2. LLM 리뷰 요청 (버그/타입/품질)
    3. 심각한 문제 발견 시 retry 루프백 (validation_passed=False)
    """
    if not ctx.agent_output or len(ctx.agent_output.strip()) < 100:
        return

    # coding/debug 태스크만 리뷰
    if ctx.task_type not in ("coding", "complex"):
        return
    if not _agent_used_mutating_tool(orch, ctx.started_at):
        return

    try:
        # Git diff 확인
        diff_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=orch.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_stat = diff_result.stdout.strip()

        if not diff_stat:
            return  # 변경 사항 없으면 스킵

        # 변경된 파일이 적을 때만 상세 diff 확인
        changed_lines = diff_stat.count("\n")
        if changed_lines > 15:
            yield f"\n\n📋 **변경된 파일**: {diff_stat[:300]}\n"
            return  # 너무 많은 변경은 스킵

        # 상세 diff 가져오기
        diff_detail = subprocess.run(
            ["git", "diff"],
            cwd=orch.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_content = diff_detail.stdout

        if len(diff_content) > 8000:
            diff_content = diff_content[:8000] + "\n... (diff truncated)"

        # LLM 리뷰 요청
        manager = orch.manager
        if manager is not None:
            review_prompt = f"""Review the following code changes for bugs or issues.

Original user request: {ctx.user_message[:200]}

```diff
{diff_content}
```

Respond in EXACTLY this format (one line per category, 'None' if none):
BUGS: <brief description or None>
TYPES: <type error description or None>
QUALITY: <quality concern or None>
"""
            try:
                generated = manager.generate(
                    prompt=review_prompt,
                    target=_model_for_role(orch, "QA"),
                    max_tokens=256,
                )
                review_response = generated if isinstance(generated, str) else str(generated)
                review_response = review_response.strip()

                # 결과 파싱
                has_bugs = "BUGS:" in review_response and "None" not in review_response.split("BUGS:")[1][:20]
                has_types = "TYPES:" in review_response and "None" not in review_response.split("TYPES:")[1][:20]

                if has_bugs or has_types:
                    yield "\n\n🔍 **[Auto Review]** 잠재적 이슈 발견:\n"
                    for line in review_response.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("Respond"):
                            yield f"> {line}\n"

                    # 심각한 버그 감지 시 루프백 플래그 — 예산(retry_count) 가산은
                    # quality_check_handler에서만 수행한다. 여기서도 가산하면
                    # 한 번의 실패에 예산이 이중 차감되어 실제 재시도가
                    # max_retries의 절반 이하로 줄어든다.
                    if has_bugs:
                        yield "> ⚠️ 버그가 감지되어 자가 수정을 시도합니다...\n"
                        ctx.validation_passed = False
                else:
                    logger.debug("[AutoReview] Code review passed — no issues")
            except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - provider boundary
                logger.warning("[AutoReview] 코드 리뷰 LLM 호출 실패 (non-critical): %s", e, exc_info=True)
    except OSError:
        logger.warning("[AutoReview] git diff 조회 실패 (non-critical)", exc_info=True)
