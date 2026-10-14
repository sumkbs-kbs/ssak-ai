"""Long-Horizon Working Memory Compactor — Infinite-turn state condensation.

Eliminates attention dilution during 50+ turn sessions by distilling raw message history
into a dense, immutable 3-part Working State:
1. Pinned Architectural Decisions (ADRs)
2. Current Modified Symbol Map
3. Pending Subgoal DAG Tasks
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass
class WorkingMemoryState:
    """Structured, token-efficient working state."""

    architectural_decisions: list[str] = field(default_factory=list)
    active_files: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    recent_failures: list[str] = field(default_factory=list)
    next_action: str = ""
    compressed_summary: str = ""

    def format_pinned_working_memory(self) -> str:
        """Format as high-priority pinned context block."""
        lines = [
            "<!-- PINNED_WORKING_MEMORY_STATE: HIGHEST ATTENTION -->",
            "🧠 **[ACTIVE WORKING MEMORY & ADR STATE]**",
        ]
        if self.architectural_decisions:
            lines.append("📌 Architectural Decisions:")
            for adr in self.architectural_decisions:
                lines.append(f"  • {adr}")

        if self.active_files:
            lines.append("📂 Modified Files in Context:")
            for f in self.active_files:
                lines.append(f"  • {f}")

        if self.pending_tasks:
            lines.append("⏳ Remaining Pending Subgoals:")
            for t in self.pending_tasks:
                lines.append(f"  • {t}")

        if self.recent_failures:
            lines.append("⚠️ Recent Failure Evidence:")
            for failure in self.recent_failures:
                lines.append(f"  • {failure}")

        if self.next_action:
            lines.append(f"➡️ Next Action: {self.next_action}")

        if self.compressed_summary:
            lines.append(f"📝 Trajectory Summary: {self.compressed_summary}")

        lines.append("<!-- END_PINNED_WORKING_MEMORY -->")
        return "\n".join(lines)


class WorkingMemoryCompactor:
    """Condenses verbose multi-turn history into compact WorkingMemoryState."""

    # 도구 결과/시스템 지시는 "다음 행동"이 아니다 — tool_loop가 도구 결과를
    # role="user"로 append하므로 마지막 user 메시지 무조건 채택 시
    # next_action이 원시 도구 출력 조각으로 오염된다.
    _NON_ACTION_MARKERS: tuple[str, ...] = (
        "<tool_response>",
        "[TOOL_EVIDENCE]",
        "[UNTRUSTED_TOOL_RESULT]",
        "[SYSTEM]",
        "[시스템 피드백]",
        "[BENCHMARK READ-ONLY]",
        "[Tool Blocked]",
    )

    @classmethod
    def _is_actionable_user_content(cls, content: str) -> bool:
        stripped = content.strip()
        if not stripped:
            return False
        return not any(marker in stripped for marker in cls._NON_ACTION_MARKERS)

    @staticmethod
    def compact(
        messages: Sequence[Mapping[str, object]],
        adrs: list[str] | None = None,
        pending_subgoals: list[str] | None = None,
    ) -> WorkingMemoryState:
        """Distill raw message stream into pure state."""
        modified_files: set[str] = set()
        recent_failures: list[str] = []
        next_action = ""

        for msg in messages:
            content = str(msg.get("content", ""))
            # Extract mentioned file paths
            for line in content.splitlines():
                if any(ext in line for ext in (".py", ".json", ".yaml", ".md", ".ts", ".js")):
                    for word in line.split():
                        clean_word = word.strip("`'\",:()")
                        if "." in clean_word and (
                            "/" in clean_word
                            or clean_word.endswith((".py", ".json", ".yaml", ".md", ".ts", ".tsx", ".js", ".rs"))
                        ):
                            modified_files.add(clean_word)

            role = str(msg.get("role", ""))
            if role in {"tool", "assistant"}:
                for line in content.splitlines():
                    normalized = " ".join(line.split())
                    lowered = normalized.casefold()
                    if (
                        normalized
                        and any(
                            marker in lowered for marker in ("error", "failed", "failure", "exception", "traceback")
                        )
                        and normalized not in recent_failures
                    ):
                        recent_failures.append(normalized[:240])

            if role == "user" and WorkingMemoryCompactor._is_actionable_user_content(content):
                next_action = content.strip()[:240]

        if not next_action:
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and str(msg.get("content", "")).strip():
                    next_action = str(msg["content"]).strip()[:240]
                    break

        summary = f"Total turns: {len(messages)}. Tracking {len(modified_files)} active files."

        return WorkingMemoryState(
            architectural_decisions=adrs or [],
            active_files=sorted(modified_files)[:10],
            pending_tasks=pending_subgoals or [],
            recent_failures=recent_failures[-3:],
            next_action=next_action,
            compressed_summary=summary,
        )
