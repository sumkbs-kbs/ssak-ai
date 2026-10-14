"""Collective intelligence execution for Ssak-Ai.

This module turns a model combo into a small council:
independent proposals, focused criticism, and a final synthesis.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

logger = logging.getLogger("antigravity_k.collective_intelligence")

GenerateFn = Callable[[str, str, dict[str, object]], str]


@dataclass(frozen=True)
class CollectiveEntry:
    """One model contribution in a collective run."""

    model: str
    role: str
    content: str


@dataclass(frozen=True)
class CollectiveRun:
    """Structured result of a collective intelligence run."""

    final_answer: str
    proposals: list[CollectiveEntry]
    critiques: list[CollectiveEntry]
    arbiter: str


class CollectiveIntelligenceEngine:
    """Run proposal, critique, and synthesis rounds across multiple local models."""

    def __init__(self, generate_fn: GenerateFn) -> None:
        """Initialize the CollectiveIntelligenceEngine.

        Args:
            generate_fn (GenerateFn): GenerateFn generate fn.

        """
        self._generate_fn: GenerateFn = generate_fn

    def run(
        self,
        prompt: str,
        *,
        proposers: Iterable[str],
        critics: Iterable[str],
        arbiter: str,
        max_proposers: int = 3,
        max_critics: int = 2,
        min_participants: int = 2,
        expose_trace: bool = True,
        generation_kwargs: dict[str, object] | None = None,
    ) -> str:
        """Execute a collective reasoning run and return the final answer."""
        kwargs = dict(generation_kwargs or {})
        proposer_models = self._unique_nonempty(proposers)[:max_proposers]
        critic_models = self._unique_nonempty(critics)[:max_critics]

        if len(proposer_models) < min_participants:
            raise ValueError(f"집단지성 실행에는 최소 {min_participants}개 모델이 필요합니다.")

        proposals = self._collect_proposals(prompt, proposer_models, kwargs)
        if len(proposals) == 0:
            return "[API Error] 집단지성에 참여할 가용 모델이 없습니다. (API 500 에러 또는 네트워크 연결 확인 필요)"
        elif len(proposals) < min_participants:
            logger.warning(
                "유효 후보 답변이 %s개뿐입니다. 최소 %s개에 미달하지만 부족한 대로 진행합니다.",
                len(proposals),
                min_participants,
            )

        if not critic_models:
            critic_models = proposer_models[:max_critics]

        critiques = self._collect_critiques(prompt, proposals, critic_models, kwargs)
        final = self._synthesize(prompt, proposals, critiques, arbiter, kwargs)
        run = CollectiveRun(
            final_answer=final.strip(),
            proposals=proposals,
            critiques=critiques,
            arbiter=arbiter,
        )
        return self._format_result(run, expose_trace=expose_trace)

    def _collect_proposals(
        self,
        prompt: str,
        models: list[str],
        kwargs: dict[str, object],
    ) -> list[CollectiveEntry]:
        proposals: list[CollectiveEntry] = []
        for model in models:
            proposal_prompt = self._proposal_prompt(prompt, model)
            text = self._safe_generate(model, proposal_prompt, kwargs)
            if self._is_error_response(text):
                logger.warning("Collective proposal skipped for %s: %s", model, text[:160])
                continue
            proposals.append(CollectiveEntry(model=model, role="proposal", content=text.strip()))
        return proposals

    def _collect_critiques(
        self,
        prompt: str,
        proposals: list[CollectiveEntry],
        models: list[str],
        kwargs: dict[str, object],
    ) -> list[CollectiveEntry]:
        critiques: list[CollectiveEntry] = []
        critique_context = self._format_entries(proposals, "후보 답변")
        for model in models:
            critique_prompt = self._critique_prompt(prompt, critique_context)
            text = self._safe_generate(model, critique_prompt, kwargs)
            if self._is_error_response(text):
                logger.warning("Collective critique skipped for %s: %s", model, text[:160])
                continue
            critiques.append(CollectiveEntry(model=model, role="critique", content=text.strip()))
        return critiques

    def _synthesize(
        self,
        prompt: str,
        proposals: list[CollectiveEntry],
        critiques: list[CollectiveEntry],
        arbiter: str,
        kwargs: dict[str, object],
    ) -> str:
        synthesis_prompt = self._synthesis_prompt(
            prompt=prompt,
            proposal_context=self._format_entries(proposals, "후보 답변"),
            critique_context=self._format_entries(critiques, "비판 의견"),
        )
        text = self._safe_generate(arbiter, synthesis_prompt, kwargs)
        if self._is_error_response(text):
            logger.warning("Collective arbiter failed for %s: %s", arbiter, text[:160])
            return self._fallback_synthesis(proposals, critiques)
        return text

    def _safe_generate(self, target: str, prompt: str, kwargs: dict[str, object]) -> str:
        try:
            phase_kwargs = dict(kwargs)
            _ = phase_kwargs.setdefault("temperature", 0.4)
            _ = phase_kwargs.setdefault("max_tokens", 2048)
            return self._generate_fn(target, prompt, phase_kwargs)
        except Exception as exc:
            logger.exception("Unhandled exception")
            return f"[Collective Error for {target}] {exc}"

    @staticmethod
    def _proposal_prompt(prompt: str, model_name: str) -> str:
        return (
            "[Ssak-Ai 집단지성 제안 라운드]\n"
            f"참여 모델: {model_name}\n\n"
            "역할: 다른 모델의 답변을 보지 않고 독립적으로 최선의 후보 답변을 작성합니다.\n"
            "규칙:\n"
            "- 내부 사고 과정, chain-of-thought, <think>, <thought>를 출력하지 마세요.\n"
            "- 확실한 사실, 가정, 리스크를 구분하세요.\n"
            "- 사용자의 언어를 따르고, 한국어 요청이면 자연스러운 한국어로 답하세요.\n"
            "- 모르면 모른다고 말하고 검증 방법을 제시하세요.\n\n"
            f"사용자 요청:\n{prompt}"
        )

    @staticmethod
    def _critique_prompt(prompt: str, proposal_context: str) -> str:
        return (
            "[Ssak-Ai 집단지성 비판 라운드]\n\n"
            "역할: 후보 답변들의 오류, 누락, 과장, 실행 위험, 품질 저하 지점을 찾습니다.\n"
            "규칙:\n"
            "- 내부 사고 과정은 출력하지 말고 검증 가능한 지적만 작성하세요.\n"
            "- 장점 나열보다 수정이 필요한 문제를 우선하세요.\n"
            "- 최종 사용자가 바로 개선에 쓸 수 있게 짧고 구체적으로 쓰세요.\n\n"
            f"원 요청:\n{prompt}\n\n"
            f"{proposal_context}"
        )

    @staticmethod
    def _synthesis_prompt(
        *,
        prompt: str,
        proposal_context: str,
        critique_context: str,
    ) -> str:
        return (
            "[Ssak-Ai 집단지성 최종 합성]\n\n"
            "역할: 후보 답변과 비판 의견을 비교하여 최종 답변 하나로 합성합니다.\n"
            "필수 규칙:\n"
            "- 내부 사고 과정, 토론 로그 원문, <think>/<thought>를 출력하지 마세요.\n"
            "- 가장 정확하고 실행 가능한 결론만 남기세요.\n"
            "- 상충되는 의견은 더 근거가 강한 쪽을 선택하고 불확실성은 명시하세요.\n"
            "- 사용자의 원래 목적과 언어를 우선하세요.\n"
            "⚠️ 언어 규칙 (위반 시 출력 전체 무효):\n"
            "- 반드시 한국어로 작성하세요. 영어 코드 블록과 기술 용어는 허용됩니다.\n"
            "- 중국어(简体/繁體) 문자를 절대 사용하지 마세요. "
            "시간복잡도→시간복잡도, 更加高效→더 효율적, 空间复杂度→공간복잡도.\n"
            "- 설명 텍스트는 반드시 한국어 문장으로 작성하세요.\n\n"
            f"원 요청:\n{prompt}\n\n"
            f"{proposal_context}\n\n"
            f"{critique_context}\n\n"
            "최종 답변:"
        )

    @staticmethod
    def _format_entries(entries: list[CollectiveEntry], title: str) -> str:
        if not entries:
            return f"## {title}\n- 없음"
        blocks = [f"## {title}"]
        for idx, entry in enumerate(entries, start=1):
            blocks.append(f"### {idx}. {entry.model} ({entry.role})\n{entry.content}")
        return "\n\n".join(blocks)

    @staticmethod
    def _fallback_synthesis(
        proposals: list[CollectiveEntry],
        critiques: list[CollectiveEntry],
    ) -> str:
        critique_note = ""
        if critiques:
            critique_note = "\n\n비판 라운드 핵심:\n" + critiques[0].content
        return proposals[0].content + critique_note

    @staticmethod
    def _format_result(run: CollectiveRun, *, expose_trace: bool) -> str:
        if not expose_trace:
            return run.final_answer

        proposal_models = ", ".join(entry.model for entry in run.proposals)
        critic_models = ", ".join(entry.model for entry in run.critiques) or "비판 생략"
        trace = (
            f"> 집단지성: 후보 {len(run.proposals)}개({proposal_models})를 비교하고 "
            f"비판 {len(run.critiques)}개({critic_models})를 반영해 "
            f"`{run.arbiter}`가 최종 합성했습니다.\n\n"
        )
        return trace + run.final_answer

    @staticmethod
    def _unique_nonempty(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _is_error_response(text: str) -> bool:
        stripped = (text or "").strip()
        lowered = stripped.lower()
        return not stripped or lowered.startswith(("[api error", "[collective error", "error:"))
