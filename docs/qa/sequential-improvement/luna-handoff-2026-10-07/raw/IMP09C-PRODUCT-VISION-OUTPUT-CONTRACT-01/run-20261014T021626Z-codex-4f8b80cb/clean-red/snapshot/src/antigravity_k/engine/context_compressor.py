"""Ssak-Ai: Context Compressor (Memory Pruning + RAG Retrieval).

==================================================================
Monitors conversation history and automatically compresses or prunes
older messages into semantic summaries to prevent context window bloat
and reduce LLM hallucinations in long-running tasks.

격차 해소: 컨텍스트 윈도우 한계를 LLM 요약 + RAG 검색으로 보상
"""

import json
import logging
import os
from collections.abc import Callable
from typing import Final, TypeAlias

from pydantic import TypeAdapter

from antigravity_k.engine.adaptive_context_compaction import adaptive_compact, leading_prompt_cache_prefix
from antigravity_k.engine.context_budget_enforcer import enforce_context_budget
from antigravity_k.engine.context_compressor_policy import IMPORTANCE_WEIGHTS, TASK_COMPRESSION
from antigravity_k.engine.context_summary import summarize_messages
from antigravity_k.engine.tokenizer import TokenEstimator

logger = logging.getLogger("antigravity_k.context_compressor")
Message: TypeAlias = dict[str, str]
_MEMORY_ADAPTER: Final[TypeAdapter[dict[str, list[str]]]] = TypeAdapter(dict[str, list[str]])


class ContextCompressor:
    """Compresses conversation context to fit within token budgets."""

    def __init__(
        self,
        token_limit: int = 8000,
        keep_last_n: int = 10,
        summarize_fn: Callable[[str], str] | None = None,
        rag_search_fn: Callable[[str, int], str] | None = None,
        persistence_dir: str | None = None,
    ):
        """Args:
        token_limit: 메시지 히스토리의 토큰 한도
        keep_last_n: 항상 유지할 최근 메시지 수
        summarize_fn: LLM 요약 함수 (prompt -> summary)
        rag_search_fn: RAG 검색 함수 (query, n_results) -> context_str.

        """
        self.token_limit: int = token_limit
        self.keep_last_n: int = keep_last_n
        self._summarize_fn: Callable[[str], str] | None = summarize_fn
        self._rag_search_fn: Callable[[str, int], str] | None = rag_search_fn

        self.persistence_dir: str | None = persistence_dir
        self._memory_file: str | None = None
        if self.persistence_dir:
            os.makedirs(self.persistence_dir, exist_ok=True)
            self._memory_file = os.path.join(self.persistence_dir, "long_term_memory.json")

        # 시맨틱 메모리: pruning된 메시지 요약을 보존
        self._pruned_summaries: list[str] = self._load_memory()

    def _load_memory(self) -> list[str]:
        if not self._memory_file or not os.path.exists(self._memory_file):
            return []
        try:
            with open(self._memory_file, encoding="utf-8") as f:
                return _MEMORY_ADAPTER.validate_json(f.read()).get("pruned_summaries", [])
        except (OSError, ValueError):
            logger.exception("Failed to load long term memory")
        return []

    def _save_memory(self) -> None:
        if not self._memory_file:
            return
        try:
            with open(self._memory_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"pruned_summaries": self._pruned_summaries},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError:
            logger.exception("Failed to save long term memory")

    def estimate_tokens(self, text: str) -> int:
        """단일 진실 공급원(TokenEstimator)에 위임하는 토큰 추정.

        이전의 max(단어*1.3, len//4) 공식은 한국어를 ~4-5배 과소평가하여
        실제 컨텍스트 초과(Ollama 좌측 잘림)를 감지하지 못했다.
        """
        return TokenEstimator.estimate_text(text)

    def needs_compression(self, messages: list[Message]) -> bool:
        """Needs Compression.

        Args:
            messages (list[dict[str, str]]): list[dict[str, str]] messages.

        Returns:
            bool: The bool result.

        """
        total_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in messages)
        return total_tokens > self.token_limit

    def usage_percent(self, messages: list[Message]) -> float:
        """컨텍스트 사용률을 반환합니다 (IronClaw context_monitor.rs 패턴)."""
        total_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in messages)
        if self.token_limit <= 0:
            return 0.0
        return (total_tokens / self.token_limit) * 100.0

    def suggest_strategy(self, messages: list[dict[str, str]]) -> str | None:
        """사용률에 따른 압축 전략을 제안합니다 (IronClaw compaction.rs 패턴).

        IronClaw 3단계 Compaction Strategy:
        - 80-85%: MoveToWorkspace (RAG로 이관)
        - 85-95%: Summarize (요약 후 최근 5개 유지)
        - 95%+:   Truncate (긴급 절삭, 최근 3개만 유지)
        """
        usage = self.usage_percent(messages)
        if usage >= 95:
            return "truncate"
        elif usage >= 85:
            return "summarize"
        elif usage >= 80:
            return "move_to_workspace"
        return None

    def context_breakdown(self, messages: list[Message]) -> dict[str, int]:
        """역할별 토큰 사용량을 분석합니다 (IronClaw ContextBreakdown 패턴)."""
        breakdown = {
            "system": 0,
            "user": 0,
            "assistant": 0,
            "tool": 0,
            "total": 0,
            "message_count": len(messages),
        }
        for m in messages:
            tokens = self.estimate_tokens(m.get("content", ""))
            role = m.get("role", "user")
            if role in breakdown:
                breakdown[role] += tokens
            breakdown["total"] += tokens
        return breakdown

    def compress(self, messages: list[Message]) -> list[Message]:
        """Compresses the message history by keeping the system prompt,.

        summarizing the middle (via LLM if available), and keeping
        the most recent N messages intact.
        """
        if not messages or not self.needs_compression(messages):
            return messages

        logger.info("[Compressor] Context exceeds limit (%s). Compressing...", self.token_limit)

        system_msgs: list[Message] = [m for m in messages if m.get("role") == "system"]
        other_msgs: list[Message] = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= self.keep_last_n:
            return enforce_context_budget(messages, self.token_limit, self.estimate_tokens)

        recent_msgs = other_msgs[-self.keep_last_n :]
        old_msgs = other_msgs[: -self.keep_last_n]

        # LLM 기반 요약 (사용 가능한 경우)
        summary_text = self._summarize_old_messages(old_msgs)

        # 요약을 영구 메모리에도 보존
        if summary_text and summary_text not in self._pruned_summaries:
            self._pruned_summaries.append(summary_text)
            # 최대 10개 요약만 유지
            if len(self._pruned_summaries) > 10:
                self._pruned_summaries = self._pruned_summaries[-10:]
            self._save_memory()

        summary_msg: Message = {"role": "system", "content": summary_text}
        compressed: list[Message] = system_msgs + [summary_msg] + recent_msgs
        return enforce_context_budget(compressed, self.token_limit, self.estimate_tokens)

    # ─── 토큰 예산 시스템 (Adaptive Token Budget) ───

    def adaptive_compress(
        self,
        messages: list[Message],
        task_type: str = "GENERAL",
        token_budget: int | None = None,
        prompt_cache_prefix: int | None = None,
    ) -> list[dict[str, str]]:
        """캐시 prefix를 고정하고 작업 유형별 토큰 예산으로 메시지를 압축합니다."""
        budget = token_budget or self.token_limit
        total_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in messages)

        if total_tokens <= budget:
            return messages

        logger.info(
            "[AdaptiveCompress] %s tokens → target %s (task: %s)",
            total_tokens,
            budget,
            task_type,
        )

        result = adaptive_compact(
            messages,
            token_budget=budget,
            task_type=task_type,
            prompt_cache_prefix=(
                leading_prompt_cache_prefix(messages) if prompt_cache_prefix is None else prompt_cache_prefix
            ),
            estimate_tokens=self.estimate_tokens,
            summarize=self._summarize_old_messages,
            importance_weights=IMPORTANCE_WEIGHTS,
            task_strategies=TASK_COMPRESSION,
        )

        final_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in result)
        logger.info(
            "[AdaptiveCompress] 완료: %s → %s tokens (%s개 메시지 요약, %s개 선별 보존)",
            total_tokens,
            final_tokens,
            len(messages) - len(result),
            len(result),
        )
        return result

    def enrich_with_rag(
        self,
        messages: list[Message],
        user_query: str,
        max_rag_chars: int = 4000,
    ) -> list[Message]:
        """RAG 검색 결과를 메시지에 주입합니다.

        사용자 질문과 관련된 코드 청크를 VectorStore에서 검색하여
        시스템 메시지로 추가합니다.
        """
        if not self._rag_search_fn:
            return messages

        try:
            rag_context = self._rag_search_fn(user_query, 5)
            if not rag_context or len(rag_context.strip()) < 20:
                return messages
        except (OSError, RuntimeError, TypeError, ValueError):
            logger.exception("[Compressor] RAG search failed")
            return messages

        rag_context = rag_context[:max_rag_chars]

        # 토큰 예산 확인
        current_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in messages)
        rag_tokens = self.estimate_tokens(rag_context)

        if current_tokens + rag_tokens > self.token_limit:
            # 예산 초과 시 RAG 결과를 잘라서 주입
            available_chars = min(max_rag_chars, max((self.token_limit - current_tokens) * 4, 500))
            rag_context = rag_context[:available_chars]

        # 시스템 메시지 뒤에 RAG 컨텍스트 삽입
        rag_msg = {
            "role": "system",
            "content": (
                "[코드베이스 컨텍스트] 아래는 사용자 질문과 관련된 프로젝트 코드입니다. 이 정보를 참고하여 정확한 답변을 생성하세요.\n\n"
                + rag_context
            ),
        }

        # 시스템 메시지 바로 뒤에 삽입
        result: list[Message] = []
        system_inserted = False
        for m in messages:
            result.append(m)
            if m.get("role") == "system" and not system_inserted:
                result.append(rag_msg)
                system_inserted = True

        if not system_inserted:
            result.insert(0, rag_msg)

        logger.info("[Compressor] RAG context injected: %s chars", len(rag_context))
        return result

    def inject_memory(self, messages: list[Message]) -> list[Message]:
        """과거 pruning된 요약을 현재 대화에 재주입합니다 (장기 기억)."""
        if not self._pruned_summaries:
            return messages

        memory_text = "[장기 기억] 이전 대화에서의 핵심 내용:\n" + "\n".join(
            f"- {s}" for s in self._pruned_summaries[-3:]
        )

        memory_msg = {"role": "system", "content": memory_text}

        # 첫 시스템 메시지 뒤에 삽입
        result: list[Message] = []
        inserted = False
        for m in messages:
            result.append(m)
            if m.get("role") == "system" and not inserted:
                result.append(memory_msg)
                inserted = True

        return result if inserted else [memory_msg] + messages

    def get_pruned_summaries(self) -> list[str]:
        """보존된 과거 요약을 반환합니다."""
        return list(self._pruned_summaries)

    def _summarize_old_messages(self, old_msgs: list[dict[str, str]]) -> str:
        """오래된 메시지를 LLM으로 요약하거나 휴리스틱 요약합니다."""
        return summarize_messages(old_msgs, self._summarize_fn)
