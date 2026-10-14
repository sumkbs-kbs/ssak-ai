"""ContextShaper — 5단계 컨텍스트 압축 파이프라인.

================================================
Claw Code의 Context Compaction Shapers 아키텍처 이식.

긴 코딩 세션에서 토큰 예산을 지키면서 핵심 컨텍스트를 유지하는 엔진.

5단계 파이프라인:
1. BudgetReducer — 남은 토큰 예산 기반 허용량 계산
2. Snip         — 오래된 메시지 우선순위 기반 절삭
3. MicroCompact — 최근 대화 턴의 경량 요약
4. ContextCollapse — 긴 도구 출력을 참조 ID로 교체
5. AutoCompact  — LLM을 활용한 전체 세션 요약
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Mapping
from typing import TypedDict, cast, final

from pydantic import JsonValue

from antigravity_k.engine.context_budget import context_budget_for_model
from antigravity_k.engine.long_context_policy import LongContextExecutionPlan
from antigravity_k.engine.tokenizer import TokenEstimator
from antigravity_k.engine.tool_evidence_compactor import compact_structured_tool_response

logger = logging.getLogger(__name__)

Message = dict[str, str]


class _TokenUsage(TypedDict):
    total_tokens: int
    max_tokens: int
    usage_pct: float
    by_role: dict[str, int]
    budget_remaining: int


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


@final
class ContextShaper:
    """5단계 컨텍스트 압축 파이프라인.

    Claw Code의 Shaper 체인 패턴:
    messages → BudgetReducer → Snip → MicroCompact → ContextCollapse → AutoCompact → shaped
    """

    # 메시지 역할별 우선순위 (낮을수록 절삭 대상)
    ROLE_PRIORITY: dict[str, int] = {
        "system": 10,  # 절대 삭제 안 됨
        "user": 7,  # 높은 보존
        "assistant": 5,  # 중간
        "tool": 3,  # 낮음 (긴 출력 → 참조 ID)
    }

    def __init__(
        self,
        max_tokens: int = 128_000,
        reserve_tokens: int = 4_096,  # 응답 예약
        collapse_threshold: int = 2000,  # 이 길이 초과 도구 출력 → collapse
        storage_dir: str | None = None,
    ):
        """Initialize the ContextShaper.

        Args:
            max_tokens (int): int max tokens.
            reserve_tokens (int): int reserve tokens.
            collapse_threshold (int): int collapse threshold.
            storage_dir (str | None): str | None storage dir.

        """
        self.max_tokens: int = max_tokens
        self.reserve_tokens: int = reserve_tokens
        self.collapse_threshold: int = collapse_threshold
        self.storage_dir: str = storage_dir or os.path.join(
            os.path.expanduser("~"),
            ".antigravity",
            "context_store",
        )
        os.makedirs(self.storage_dir, exist_ok=True)

        # 압축 통계
        self._stats: dict[str, int] = {
            "total_shaped": 0,
            "tokens_saved": 0,
            "collapses": 0,
            "snips": 0,
        }

    def shape(
        self,
        messages: list[Message],
        budget: int | None = None,
        force_compact: bool = False,
    ) -> list[Message]:
        """메시지 리스트에 5단계 압축 파이프라인을 적용합니다.

        Args:
            messages: [{"role": "...", "content": "..."}] 리스트
            budget: 사용 가능한 최대 토큰 (None이면 self.max_tokens)
            force_compact: True이면 예산 이내라도 강제 압축 수행
                          (API 에러 분류기의 context_overflow 감지 시 사용)

        Returns:
            압축된 메시지 리스트

        """
        budget = budget or (self.max_tokens - self.reserve_tokens)
        # 원본 측정은 비캐시로 수행한다 — 캐시 기록(_tokens 키)이 복사 이전
        # 호출자의 원본 딕셔너리에 남으면 "변이 없음" 계약이 깨진다.
        original_size = self._estimate_tokens(messages, use_cache=False)

        if not force_compact and original_size <= budget:
            return messages  # 예산 내 → 그대로 반환

        # force_compact 시 더 공격적인 예산 설정
        if force_compact:
            budget = int(budget * 0.6)  # 60% 수준으로 강제 축소

        # 메시지 딕셔너리를 복사해 작업한다 — 하위 스테이지(_micro_compact 등)가
        # content를 제자리 수정하므로 얕은 리스트 복사만으로는 호출자(세션
        # 히스토리)의 원본이 영구 훼손된다.
        shaped = [dict(message) for message in messages]

        # Stage 1: Budget Reducer — 허용량 계산
        target = self._budget_reduce(original_size, budget)

        # Stage 2: Snip — 오래된 저우선 메시지 절삭
        shaped = self._snip(shaped, target)

        # Stage 3: MicroCompact — 연속 도구 결과 압축
        shaped = self._micro_compact(shaped)

        # Stage 4: ContextCollapse — 긴 출력 → 참조 ID
        shaped = self._context_collapse(shaped)

        # Stage 5: AutoCompact — 여전히 초과 시 요약 주입
        current_size = self._estimate_tokens(shaped)
        if current_size > budget:
            shaped = self._auto_compact(shaped, budget)

        self._stats["total_shaped"] += 1
        self._stats["tokens_saved"] += original_size - self._estimate_tokens(shaped)

        logger.info(
            "Context shaped: %s → %s tokens (saved %s)",
            original_size,
            self._estimate_tokens(shaped),
            original_size - self._estimate_tokens(shaped),
        )

        return shaped

    def shape_for_model(
        self,
        messages: list[Message],
        config: Mapping[str, JsonValue],
        model_name: str,
        force_compact: bool = False,
        execution_plan: LongContextExecutionPlan | None = None,
        aux_token_overhead: int = 0,
    ) -> list[Message]:
        """Shape messages against the effective budget of a selected model.

        ``aux_token_overhead`` reserves room for system/tools/skills/memory/artifacts
        that are serialized into the final prompt outside the message list (CTX-02).
        """
        budget = context_budget_for_model(config, model_name)
        token_limit = budget.token_limit
        if execution_plan is not None and execution_plan["context_token_limit"] > 0:
            token_limit = min(token_limit, execution_plan["context_token_limit"])
        if aux_token_overhead > 0:
            token_limit = max(1, token_limit - int(aux_token_overhead))
        return self.shape(messages, budget=token_limit, force_compact=force_compact)

    def clear_old_tool_results(self, messages: list[Message], keep_last: int = 3) -> list[Message]:
        """오래된 도구 실행 결과(tool_response/tool_result)를 정리합니다.

        연속된 tool 결과 메시지 중 최근 keep_last개만 유지하고,
        나머지는 요약된 참조로 축약하여 컨텍스트를 정리합니다.

        Args:
            messages: 메시지 리스트
            keep_last: 유지할 최근 tool 결과 수

        Returns:
            정리된 메시지 리스트
        """
        if not messages:
            return messages

        # tool 결과 역할 식별 (role이 tool/function이거나 content가 <tool_response> 포함)
        tool_result_indices: list[int] = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role in ("tool", "function", "tool_result"):
                tool_result_indices.append(i)
            elif "<tool_response>" in content or "<tool_result>" in content:
                tool_result_indices.append(i)

        # 유지할 최근 결과를 제외한 나머지가 너무 많으면 축약
        if len(tool_result_indices) <= keep_last:
            return messages

        to_compact = tool_result_indices[:-keep_last] if keep_last > 0 else tool_result_indices
        result: list[Message] = []
        for i, msg in enumerate(messages):
            if i in to_compact:
                content = str(msg.get("content", ""))
                # 긴 tool 결과는 요약된 참조로 축약
                if len(content) > 200:
                    compacted = compact_structured_tool_response(content)
                    result.append(
                        {
                            **msg,
                            "content": compacted or f"[이전 도구 결과 축약 — {len(content)} chars]",
                        }
                    )
                else:
                    result.append(msg)
            else:
                result.append(msg)
        return result

    def inject_budget_awareness(self, messages: list[Message]) -> list[Message]:
        """시스템 메시지에 비용/예산 인식 지시문을 주입합니다.

        에이전트가 비용을 의식하며 동작하도록 유도합니다.
        (CostGuard 연동을 위한 컨텍스트 프라이밍)

        Args:
            messages: 메시지 리스트

        Returns:
            예산 인식 지시문이 주입된 메시지 리스트
        """
        if not messages:
            return messages

        budget_directive = (
            "[Budget Awareness] 비용 효율적으로 동작하세요: "
            "불필요한 반복 호출을 피하고, 한 번에 정확한 결과를 산출하세요."
        )

        result = list(messages)
        # 첫 번째 시스템 메시지에 주입
        if result and result[0].get("role") == "system":
            content = str(result[0].get("content", ""))
            if "[Budget Awareness]" not in content:
                result[0] = {**result[0], "content": f"{content}\n\n{budget_directive}"}
        else:
            result.insert(0, {"role": "system", "content": budget_directive})

        return result

    # ─────────── Stage 1: Budget Reducer ───────────

    def _budget_reduce(self, current: int, budget: int) -> int:
        """목표 토큰 수를 계산합니다."""
        # 80% 수준으로 타겟 설정 (여유 확보)
        target = int(budget * 0.8)
        logger.debug("BudgetReducer: current=%s, budget=%s, target=%s", current, budget, target)
        return target

    # ─────────── Stage 2: Snip ───────────

    def _snip(self, messages: list[Message], target: int) -> list[Message]:
        """오래된 저우선 메시지를 절삭합니다.

        시스템 메시지와 최근 5턴은 보존.
        """
        if self._estimate_tokens(messages) <= target:
            return messages

        # 시스템 메시지 보존
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 최근 5턴(10메시지) 보존
        preserve_count = min(10, len(non_system))
        preserved = non_system[-preserve_count:]
        candidates = non_system[:-preserve_count]

        protected_evidence: list[Message] = []
        removable_candidates: list[Message] = []
        for message in candidates:
            compacted = compact_structured_tool_response(message.get("content", ""))
            if compacted is None:
                removable_candidates.append(message)
            else:
                protected_evidence.append({**message, "content": compacted})
        protected_evidence = protected_evidence[-5:]
        candidates = removable_candidates

        # 우선순위 낮은 순서로 제거
        candidates.sort(key=lambda m: self.ROLE_PRIORITY.get(m.get("role", ""), 0))

        result = system_msgs + protected_evidence + candidates + preserved

        while self._estimate_tokens(result) > target and candidates:
            _ = candidates.pop(0)
            result = system_msgs + protected_evidence + candidates + preserved
            self._stats["snips"] += 1

        return result

    # ─────────── Stage 3: MicroCompact ───────────

    def _micro_compact(self, messages: list[Message]) -> list[Message]:
        """연속 도구 결과를 합치고, 긴 내용을 축약합니다.

        Claw Code의 'consecutive tool results merge' 패턴.
        """
        if len(messages) < 3:
            return messages

        result: list[Message] = []
        tool_buffer: list[Message] = []

        for msg in messages:
            if msg.get("role") == "tool":
                tool_buffer.append(msg)
            else:
                if tool_buffer:
                    # 연속 도구 결과 → 하나로 합침
                    if len(tool_buffer) > 1:
                        merged_content = "\n---\n".join(
                            f"[{t.get('name', 'tool')}] {self._truncate(t.get('content', ''), 500)}"
                            for t in tool_buffer
                        )
                        result.append(
                            {
                                "role": "tool",
                                "content": merged_content,
                                "name": "merged_tools",
                            },
                        )
                    else:
                        # 단일 도구 결과도 축약
                        t = tool_buffer[0]
                        t["content"] = self._truncate(t.get("content", ""), 1000)
                        # 콘텐츠가 변했으므로 토큰 캐시를 무효화한다
                        _ = t.pop("_tokens", None)
                        result.append(t)
                    tool_buffer = []
                result.append(msg)

        # 잔여 버퍼 처리
        if tool_buffer:
            if len(tool_buffer) > 1:
                merged = "\n---\n".join(
                    f"[{t.get('name', 'tool')}] {self._truncate(t.get('content', ''), 500)}" for t in tool_buffer
                )
                result.append({"role": "tool", "content": merged, "name": "merged_tools"})
            else:
                tool_buffer[0]["content"] = self._truncate(tool_buffer[0].get("content", ""), 1000)
                # 콘텐츠가 변했으므로 토큰 캐시를 무효화한다
                _ = tool_buffer[0].pop("_tokens", None)
                result.append(tool_buffer[0])

        return result

    # ─────────── Stage 4: Context Collapse ───────────

    def _context_collapse(self, messages: list[Message]) -> list[Message]:
        """긴 도구 출력(파일 내용, grep 결과)을 참조 ID로 교체하고 디스크에 저장.

        Claw Code의 'reference ID replacement' 패턴.
        """
        result: list[Message] = []
        for msg in messages:
            content = msg.get("content", "")

            if msg.get("role") == "tool" and len(content) > self.collapse_threshold:
                # 참조 ID 생성 (P0 보안 일관성: MD5 → SHA256)
                ref_id = hashlib.sha256(content.encode()).hexdigest()[:12]

                # 저장 전 비밀 마스킹 — 전역 스토어에 원문 비밀이 남지 않게
                # 한다 (복원 시 마스킹본이 돌아오는 것도 의도된 보안 경계).
                from antigravity_k.engine.secret_scanner import redact

                stored_content = redact(content)

                # 디스크 저장
                ref_path = os.path.join(self.storage_dir, f"{ref_id}.json")
                with open(ref_path, "w", encoding="utf-8") as f:
                    json.dump({"content": stored_content, "ts": time.time()}, f)
                self._gc_storage()

                # 축약 버전 (첫 200자 + 참조 ID)
                preview = content[:200]
                collapsed = f"{preview}...\n[Full output stored as ref:{ref_id}, {len(content)} chars]"

                result.append({**msg, "content": collapsed})
                self._stats["collapses"] += 1
            else:
                result.append(msg)

        return result

    _STORE_MAX_FILES: int = 200

    def _gc_storage(self) -> None:
        """전역 context_store 용량 상한 — 최신 200개 ref만 유지한다."""
        try:
            entries: list[tuple[float, str]] = []
            for name in os.listdir(self.storage_dir):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(self.storage_dir, name)
                try:
                    entries.append((os.path.getmtime(path), path))
                except OSError:
                    continue
            if len(entries) <= self._STORE_MAX_FILES:
                return
            entries.sort()
            for _mtime, path in entries[: len(entries) - self._STORE_MAX_FILES]:
                try:
                    os.remove(path)
                except OSError:
                    continue
        except OSError:
            logger.debug("context store GC skipped", exc_info=True)

    def restore_collapsed(self, ref_id: str) -> str | None:
        """참조 ID로 저장된 전체 내용을 복원합니다."""
        ref_path = os.path.join(self.storage_dir, f"{ref_id}.json")
        if os.path.exists(ref_path):
            with open(ref_path, encoding="utf-8") as f:
                data = _mapping(cast(object, json.load(f)))
            content = data.get("content")
            return content if isinstance(content, str) else None
        return None

    # ─────────── Stage 5: Auto Compact ───────────

    def _auto_compact(self, messages: list[Message], budget: int) -> list[Message]:
        """여전히 예산 초과 시, 이전 대화를 요약문으로 교체합니다.

        Claw Code의 'auto-compact with LLM summary' 패턴.

        Note: LLM 호출 없이 규칙 기반 요약으로 구현 (로컬 LLM 호출은 추후).
        """
        _ = budget
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 최근 3턴(6메시지) 보존
        preserve = min(6, len(non_system))
        old = non_system[:-preserve] if preserve else non_system
        recent = non_system[-preserve:] if preserve else []

        if not old:
            return messages

        preserved_evidence = [
            compacted
            for message in old
            if (compacted := compact_structured_tool_response(message.get("content", ""))) is not None
        ][-5:]

        # 규칙 기반 요약 생성
        summary_parts: list[str] = []
        for msg in old:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                summary_parts.append(f"- User asked: {self._truncate(content, 100)}")
            elif role == "assistant":
                summary_parts.append(f"- Assistant: {self._truncate(content, 100)}")
            elif role == "tool":
                name = msg.get("name", "tool")
                summary_parts.append(f"- Tool '{name}' executed")

        summary = "\n".join(
            ["[Previous conversation summary]", *summary_parts[:20], *preserved_evidence],
        )

        summary_msg = {"role": "system", "content": summary}

        return system_msgs + [summary_msg] + recent

    # ─────────── 유틸리티 ───────────

    @staticmethod
    def _estimate_tokens(messages: list[Message], use_cache: bool = True) -> int:
        """메시지 리스트의 대략적인 토큰 수를 추정합니다.
        TokenEstimator 통일 모듈에 위임합니다.
        """
        return TokenEstimator.estimate_messages(messages, use_cache=use_cache)

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """텍스트를 max_len 길이로 잘라냅니다."""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"... ({len(text)} total chars)"

    def get_stats(self) -> dict[str, int]:
        """압축 통계를 반환합니다."""
        return dict(self._stats)

    def get_token_usage(self, messages: list[Message]) -> _TokenUsage:
        """현재 컨텍스트 토큰 사용량을 분석합니다."""
        total = self._estimate_tokens(messages)
        by_role = TokenEstimator.estimate_messages_by_role(messages)

        return {
            "total_tokens": total,
            "max_tokens": self.max_tokens,
            "usage_pct": round(total / self.max_tokens * 100, 1),
            "by_role": by_role,
            "budget_remaining": self.max_tokens - self.reserve_tokens - total,
        }
