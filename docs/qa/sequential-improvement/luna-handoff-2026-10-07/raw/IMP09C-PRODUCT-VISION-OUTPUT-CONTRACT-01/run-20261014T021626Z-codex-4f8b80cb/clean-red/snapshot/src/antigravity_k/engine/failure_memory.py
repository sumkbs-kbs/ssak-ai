"""Ssak-Ai: 실패 학습 메모리 (FailureMemory).

===============================================
E-3: 실패 패턴을 기록하고 동일 실수를 방지합니다.
"""

import json
import logging
import os
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from antigravity_k.engine.gbrain import global_gbrain

logger = logging.getLogger(__name__)

_DEFAULT_LOG = ".antigravity/failure_log.jsonl"
type FailureValue = str | bool
type FailureRecord = dict[str, FailureValue]


class FailureMemory:
    """에이전트의 실패를 기억하고, 같은 실수를 반복하지 않도록 합니다.

    동작:
    1. record(): 실패 발생 시 패턴/원인/해결책을 기록
    2. find_similar(): 새 작업 전 유사 실패 이력 검색
    3. build_prompt(): 에이전트에게 "이전 실패" 컨텍스트 주입
    """

    def __init__(self, project_root: str = ".") -> None:
        """Initialize the FailureMemory.

        Args:
            project_root (str): str project root.

        """
        self.project_root: str = project_root
        self._log_path: str = os.path.join(project_root, _DEFAULT_LOG)
        self._session_failures: list[FailureRecord] = []
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

    def record(
        self,
        tool: str,
        error_text: str,
        args_summary: str = "",
        fix_applied: str = "",
        success_after_fix: bool = False,
    ) -> None:
        """실패를 기록합니다."""
        entry: FailureRecord = {
            "tool": tool,
            "error_pattern": self._extract_pattern(error_text),
            "error_text": error_text[:500],
            "args_summary": args_summary[:200],
            "fix_applied": fix_applied,
            "success_after_fix": success_after_fix,
            "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        }

        self._session_failures.append(entry)

        # GBrain(그래프+벡터 DB)에 저장
        node_id = f"fail_{uuid.uuid4().hex[:8]}"
        content = f"Tool: {tool}\nArgs: {args_summary[:200]}\nError: {error_text[:500]}\nFix: {fix_applied}"

        global_gbrain.add_node(
            node_id=node_id,
            label="failure",
            content=content,
            metadata={
                "tool": tool,
                "error_pattern": entry["error_pattern"],
                "success_after_fix": success_after_fix,
                "timestamp": entry["timestamp"],
            },
        )

        # 하위 호환을 위해 JSONL에도 백업
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                _ = f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # 로테이션: 1000줄 초과 시 최신 500줄만 유지 (디스크 고갈 방지)
            self._rotate_log_if_needed()
        except (OSError, TypeError, ValueError):
            logger.exception("[FailureMemory] Failed to write fallback log")

    def _rotate_log_if_needed(self, max_lines: int = 1000, keep_lines: int = 500) -> None:
        """JSONL 로그가 max_lines를 초과하면 최신 keep_lines줄만 유지합니다."""
        try:
            if not os.path.exists(self._log_path):
                return
            with open(self._log_path, encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > max_lines:
                logger.info("[FailureMemory] Rotating log: %s → %s lines", len(lines), keep_lines)
                with open(self._log_path, "w", encoding="utf-8") as f:
                    _ = f.write("".join(lines[-keep_lines:]))
        except (OSError, ValueError) as e:
            logger.exception("Unhandled exception")
            logger.debug("[FailureMemory] Log rotation failed: %s", e)

    def find_similar(self, task_or_error: str, max_results: int = 3) -> list[FailureRecord]:
        """GBrain 의미론적 검색을 사용하여 유사한 과거 실패를 검색합니다."""
        results: list[FailureRecord] = []

        # 1. 먼저 GBrain VectorDB 조회
        try:
            gbrain_results = global_gbrain.search_semantic(
                query=task_or_error,
                limit=max_results,
                filter_label="failure",
            )
            for r in gbrain_results:
                # FailureMemory의 포맷에 맞게 변환
                raw_pattern = r.get("error_pattern")
                if isinstance(raw_pattern, str):
                    error_pattern = raw_pattern
                else:
                    raw_content = r.get("content", "")
                    error_pattern = raw_content[:50] if isinstance(raw_content, str) else ""
                raw_tool = r.get("tool", "unknown")
                tool = raw_tool if isinstance(raw_tool, str) else "unknown"
                results.append(
                    {
                        "tool": tool,
                        "error_pattern": error_pattern,
                        "fix_applied": "",
                        "source": "gbrain",
                    },
                )
        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.exception("Unhandled exception")
            logger.debug("[FailureMemory] GBrain search failed, fallback to keyword: %s", e)

        if len(results) >= max_results:
            return results[:max_results]

        # 2. 결과가 부족하면 세션 로그에서 키워드 검색
        keywords = set(re.findall(r"[a-zA-Z_]{3,}", task_or_error.lower()))
        for entry in reversed(self._session_failures):
            if self._is_similar(entry, keywords):
                if entry not in results:
                    results.append(entry)
                if len(results) >= max_results:
                    return results[:max_results]

        return results

    def build_prompt(self, task: str) -> str:
        """에이전트에게 주입할 실패 학습 컨텍스트를 생성합니다."""
        similar = self.find_similar(task)
        if not similar:
            return ""

        lines = ["\n<failure_memory>"]
        lines.append("⚠️ 과거 유사 작업에서의 실패 기록 (같은 실수를 반복하지 마세요):")
        for f in similar:
            fix_info = f" → 해결: {f['fix_applied']}" if f.get("fix_applied") else ""
            lines.append(f"- [{f['tool']}] {f['error_pattern']}{fix_info}")
        lines.append("</failure_memory>")
        return "\n".join(lines)

    def get_session_stats(self) -> dict[str, int]:
        """현재 세션의 실패 통계를 반환합니다."""
        total = len(self._session_failures)
        if total == 0:
            return {"total": 0, "unique_tools": 0, "fixed": 0}

        tools = {f["tool"] for f in self._session_failures}
        fixed = sum(1 for f in self._session_failures if f.get("success_after_fix"))
        return {"total": total, "unique_tools": len(tools), "fixed": fixed}

    def _extract_pattern(self, error_text: str) -> str:
        """에러 텍스트에서 핵심 패턴을 추출합니다."""
        # Python 에러 타입 추출
        match = re.search(r"(\w+Error|\w+Exception):\s*(.{0,100})", error_text)
        if match:
            return f"{match.group(1)}: {match.group(2).strip()}"

        # 일반적인 에러 메시지
        if "command not found" in error_text.lower():
            return "command_not_found"
        if "permission denied" in error_text.lower():
            return "permission_denied"
        if "no such file" in error_text.lower():
            return "file_not_found"

        # 첫 줄만 반환
        first_line = error_text.strip().split("\n")[0]
        return first_line[:100]

    def _is_similar(self, entry: Mapping[str, FailureValue], keywords: set[str]) -> bool:
        """키워드 기반 유사도 판단."""
        entry_text = f"{entry.get('tool', '')} {entry.get('error_pattern', '')} {entry.get('args_summary', '')}".lower()
        entry_words = set(re.findall(r"[a-zA-Z_]{3,}", entry_text))
        overlap = len(keywords & entry_words)
        return overlap >= 2
