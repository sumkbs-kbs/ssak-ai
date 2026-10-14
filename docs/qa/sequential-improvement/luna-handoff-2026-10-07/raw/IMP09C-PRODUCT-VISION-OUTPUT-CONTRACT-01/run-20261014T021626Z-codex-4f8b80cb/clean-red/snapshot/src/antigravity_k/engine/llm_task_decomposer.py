"""Ssak-Ai: LLM 기반 작업 분해 증폭.

========================================================
복잡한 멀티스텝 작업을 모델 자신에게 명시적 단계로 분해시킨 뒤, 각 단계를
따로 풀게 해 작은 모델의 멀티스텝 추론 약점을 구조적으로 보완한다.

격차 해소 대상: 장기 멀티스텝 워크플로/계획/실행 (lh-001 같은 영역)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger("antigravity_k.llm_task_decomposer")

GenerateFn = Callable[[str], str]

_COMPLEX_HINTS = (
    "워크플로",
    "파이프라인",
    "마이그레이션",
    "단계",
    "멀티",
    "계획",
    "workflow",
    "pipeline",
    "migration",
    "multi",
    "orchestrat",
)

_STEPS_ADAPTER = TypeAdapter(list[str])


@dataclass
class Decomposition:
    """작업 분해 결과."""

    original_task: str
    steps: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def is_complex_task(task: str) -> bool:
    """작업이 분해 가치가 있는 복잡한 멀티스텝 과제인지 판정한다.

    단순 함수 작성/단일 질문은 분해 비용을 낭비하므로 스킵한다.
    순차 실행 특성(워크플로/마이그레이션/파이프라인)이 있는 과제만 대상으로
    한다. 아키텍처 설계 같은 단일 산출물 과제는 실측(arc-002)에서 분해
    이득이 0이고 지연만 4배 증가해 게이트에서 제외한다.
    """
    # 한국어는 글자당 정보 밀도가 높아 영어 길이 기준보다 짧아도 복잡할 수 있다.
    if not task or len(task.strip()) < 15:
        return False
    t = task.lower()
    return any(h in t for h in _COMPLEX_HINTS)


def _extract_steps(raw: str) -> list[str]:
    """LLM 응답에서 단계 리스트를 추출한다.

    LLM은 JSON 배열 또는 번호/불릿 목록으로 반환할 수 있으므로 양쪽을 처리한다.
    """
    text = (raw or "").strip()
    if not text:
        return []
    # 1. JSON 배열 시도 (가장 신뢰)
    # JSON 블록은 보통 ```json ... ``` 안에 있거나 bare array.
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        bare = re.search(r"\[\s*\".*?\]\s*", text, re.DOTALL)
        candidate = bare.group(0) if bare else None
    if candidate:
        try:
            steps = [step.strip() for step in _STEPS_ADAPTER.validate_json(candidate) if step.strip()]
            if steps:
                return steps
        except (ValidationError, ValueError):
            pass  # 폴백으로 목록 파싱
    # 2. 번호/불릿 목록 파싱
    lines = text.splitlines()
    numbered = [ln for ln in lines if re.match(r"\s*\d+[.)]\s+\S", ln)]
    if len(numbered) >= 2:
        return [re.sub(r"^\s*\d+[.)]\s+", "", ln).strip() for ln in numbered if ln.strip()]
    bulleted = [ln for ln in lines if re.match(r"\s*[-*]\s+\S", ln)]
    if len(bulleted) >= 2:
        return [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in bulleted if ln.strip()]
    return []


class LlmTaskDecomposer:
    """복잡한 작업을 LLM으로 명시적 단계로 분해한다.

    generate_fn(prompt) -> str 형태. None이면 비활성. 분해는 복잡한 작업에만
    적용하고 단순 작업은 비용 낭비를 막기 위해 스킵한다.
    """

    def __init__(
        self,
        generate_fn: GenerateFn | None = None,
        min_steps: int = 2,
        max_steps: int = 8,
    ) -> None:
        self._generate_fn: GenerateFn | None = generate_fn
        self.min_steps: int = max(1, int(min_steps))
        self.max_steps: int = max(self.min_steps, int(max_steps))

    def set_generate_fn(self, fn: GenerateFn) -> None:
        self._generate_fn = fn

    def _build_prompt(self, task: str) -> str:
        return (
            "아래 작업을 실행 가능한 순차적 하위 단계로 분해하세요. "
            f"최소 {self.min_steps}개, 최대 {self.max_steps}개 단계로, 각 단계는 독립적으로 "
            "실행 가능한 구체적 명령이어야 합니다.\n"
            "JSON 문자열 배열 형식으로만 응답하세요 (설명 없이). 예:\n"
            '["단계1 설명", "단계2 설명", "단계3 설명"]\n\n'
            f"작업:\n{task}"
        )

    def decompose(self, task: str) -> Decomposition:
        """작업을 분해한다. 단순 작업이거나 generate_fn이 없으면 스킵한다."""
        if self._generate_fn is None:
            return Decomposition(original_task=task, skipped=True, skip_reason="no generate_fn")
        if not is_complex_task(task):
            return Decomposition(original_task=task, skipped=True, skip_reason="not complex")
        try:
            raw = self._generate_fn(self._build_prompt(task))
        except Exception as exc:
            logger.debug("LLM 분해 호출 실패: %s", exc)
            return Decomposition(original_task=task, skipped=True, skip_reason=f"generate error: {exc}")
        steps = _extract_steps(raw)[: self.max_steps]
        if len(steps) < self.min_steps:
            return Decomposition(
                original_task=task,
                steps=steps,
                skipped=True,
                skip_reason=f"too few steps ({len(steps)})",
            )
        return Decomposition(original_task=task, steps=steps)

    def step_prompt(
        self,
        step: str,
        original_task: str,
        completed_results: list[str] | None = None,
    ) -> str:
        """분해된 단일 단계를 풀기 위한 프롬프트를 만든다.

        completed_results에 앞선 단계의 출력을 넘기면 다음 단계가 그 결과
        위에 얹혀 작성된다. 단계 간 의존성(event store가 command 모델 위에
        얹히는 등)을 유지하기 위한 순차 실행 컨텍스트다.
        """
        context = ""
        if completed_results:
            trimmed: list[str] = []
            budget = 8000
            for prev in reversed(completed_results):
                take = min(len(prev), budget, 2000)
                trimmed.append(prev[-take:] if take < len(prev) else prev)
                budget -= take
                if budget <= 0:
                    break
            trimmed.reverse()
            context = "\n\n".join(f"[{i}단계 결과]\n{result}" for i, result in enumerate(trimmed, start=1))
        sections = [f"[원본 작업 맥락] {original_task}\n\n"]
        if context:
            sections.append(f"{context}\n\n")
            sections.append("이전 단계 결과와 이름·용어·구조를 일관되게 이어서 작성하세요.\n")
        sections.append("위 작업의 한 단계를 수행하세요. 다른 단계는 무시하고 아래 단계만 집중적으로 다루세요.\n")
        sections.append(f"[이번 단계] {step}\n\n")
        sections.append("이 단계의 결과를 완성된 형태로 작성하세요.")
        return "".join(sections)
