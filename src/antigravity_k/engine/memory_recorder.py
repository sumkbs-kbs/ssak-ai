"""Ssak-Ai: 에이전트 기억 기록기 (MemoryRecorder).

=====================================================
에이전트의 작업 결과를 LLM Wiki(Vault)에 자동 기록합니다.

책임:
  1. 에이전트 출력을 LLM을 사용해 핵심 기억으로 정제 (Memory Consolidation)
  2. Vault에 마크다운 형식으로 기록
  3. 메모리 기록 대상 태스크 유형 필터링

설계 원칙:
  - orchestrator.py의 run_stream() 하단 기억 기록 블록을 독립 모듈로 추출
  - Generator 패턴으로 UI 스트리밍과 호환
"""

import datetime
import logging
import re
from collections.abc import Callable, Generator, Iterator
from typing import Protocol, cast

from antigravity_k.engine.tool_policy import request_allows_side_effects

logger = logging.getLogger(__name__)

# 기억 기록 대상 태스크 유형
RECORDABLE_TASK_TYPES = frozenset({"complex", "debate", "reasoning", "coding"})


class _VaultLike(Protocol):
    sync_rag: bool


class _ModelManagerLike(Protocol):
    pass


class _ModelGenerator(Protocol):
    def stream_generate(
        self,
        *,
        prompt: str,
        target: str,
        raw_messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]: ...


class MemoryRecorder:
    """에이전트의 작업 결과를 LLM Wiki에 자동 기록하는 엔진.

    사용법:
        recorder = MemoryRecorder(vault_engine, model_manager, get_model_fn)
        yield from recorder.record(user_message, agent_output, task_type)
    """

    vault_engine: _VaultLike | None
    manager: _ModelManagerLike | None
    _get_model: Callable[[str], str]

    def __init__(
        self,
        vault_engine: _VaultLike | None,
        model_manager: _ModelManagerLike | None,
        get_model_for_role_fn: Callable[[str], str],
    ) -> None:
        """Initialize the MemoryRecorder.

        Args:
            vault_engine: vault engine.
            model_manager: model manager.
            get_model_for_role_fn: get model for role fn.

        """
        self.vault_engine = vault_engine
        self.manager = model_manager
        self._get_model = get_model_for_role_fn

    def should_record(self, task_type: str) -> bool:
        """이 태스크 유형이 기억 기록 대상인지 확인합니다."""
        if not request_allows_side_effects() or not self.vault_engine:
            return False
        if not self.vault_engine.sync_rag:
            return False
        return task_type in RECORDABLE_TASK_TYPES

    def record(
        self,
        user_message: str,
        agent_output: str,
        task_type: str,
        preferred_model: str | None = None,
    ) -> Generator[str, None, None]:
        """에이전트 기억을 정제하여 Vault에 기록합니다.

        Generator로 구현되어 UI 스트리밍에 통합됩니다.

        Args:
            user_message: 사용자 메시지.
            agent_output: 에이전트 출력.
            task_type: 태스크 유형.
            preferred_model: 정제에 사용할 모델. None이면 기본 역할 모델 사용.

        Yields:
            진행 상태 메시지 (UI에 표시)

        """
        vault_engine = self.vault_engine
        manager = self.manager
        if vault_engine is None or manager is None or not self.should_record(task_type):
            return

        try:
            yield "\n\n⏳ **[Agent Memory]** 이번 논의의 핵심을 세컨드 브레인(Wiki)에 기록하기 위해 정제 중입니다...\n"

            # ── Memory Consolidation ──
            summary_prompt = (
                "당신은 에이전트의 작업 로그를 분석하여 세컨드 브레인(Wiki)에 저장할 핵심 기억(Memory)을 추출하는 전문가입니다.\n"  # noqa: E501
                f"아래는 사용자의 요청과 에이전트의 결정(Decision)입니다.\n\n"
                f"<user_request>\n{user_message}\n</user_request>\n\n"
                f"<agent_decision>\n{agent_output[-6000:]}\n</agent_decision>\n\n"
                "다음 항목을 마크다운 포맷으로 작성해주세요:\n"
                "1. **핵심 요약 (Lessons Learned)**: 이 작업에서 성공적으로 해결한 문제와 배운 점을 3~4줄로 요약.\n"
                "2. **도구 및 에러 이력 (Tool Trajectory)**: 사용한 주요 도구들과 직면했던 에러, 극복 방법 요약."
            )

            summarizer_model = preferred_model or self._get_model("default")
            response_gen = cast(_ModelGenerator, manager).stream_generate(
                prompt=summary_prompt,
                target=summarizer_model,
                raw_messages=[{"role": "user", "content": summary_prompt}],
                system_prompt="출력은 오직 마크다운으로 작성된 분석 결과여야 합니다. /no_think",
            )

            extracted_text = ""
            for chunk in response_gen:
                extracted_text += chunk
            extracted_text = re.sub(
                r"<think>.*?</think>",
                "",
                extracted_text,
                flags=re.DOTALL,
            ).strip()

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f".agent/memory/decision_{timestamp}.md"

            memory_content = (
                f"# User Request\n{user_message}\n\n"
                f"## 🧠 Memory Consolidation (자가 학습)\n\n{extracted_text}\n\n"
                f"## Raw Decision\n\n<details>\n<summary>자세히 보기</summary>\n\n{agent_output}\n\n</details>"
            )

            write_note = getattr(vault_engine, "write_note", None)
            if not callable(write_note):
                raise AttributeError("Vault engine does not provide write_note")
            _ = write_note(
                relative_path=filename,
                metadata={
                    "type": "agent_memory",
                    "task": task_type,
                    "date": timestamp,
                    "tags": ["memory", "decision"],
                },
                content=memory_content,
                commit_message=f"Agent memory recorded and consolidated for {task_type}",
            )
            yield f"💾 **[Agent Memory]** 정제 완료! LLM Wiki(`{filename}`)에 영구 기록되었습니다.\n"
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            logger.exception("Failed to record agent memory")
            yield f"⚠️ **[Agent Memory]** 기록 중 오류가 발생했습니다: {e}\n"
