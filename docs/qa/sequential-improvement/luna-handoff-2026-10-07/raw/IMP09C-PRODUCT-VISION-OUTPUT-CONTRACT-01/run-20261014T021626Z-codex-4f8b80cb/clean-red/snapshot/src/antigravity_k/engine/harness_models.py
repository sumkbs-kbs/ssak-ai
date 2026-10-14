"""Data models for the test harness.

Extracted from ``harness.py`` for clarity. These are pure value objects with no
behavior beyond serialization — safe to import anywhere without pulling in
Playwright or HTTP client deps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class TestStatus(str, Enum):
    """Test status for a single intent execution."""

    __test__: ClassVar[bool]
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    HEALED = "healed"  # Self-healing으로 복구됨
    SKIPPED = "skipped"


@dataclass
class TestIntent:
    """자연어 의도 기반 테스트 케이스."""

    __test__: ClassVar[bool] = False
    id: str
    intent: str  # "채팅에 메시지를 보내면 응답이 온다"
    category: str = "ui"  # ui, api, integration
    priority: int = 1  # 1(높음) ~ 5(낮음)
    timeout_sec: float = 30.0
    max_heal_attempts: int = 3
    tags: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    """테스트 실행 결과."""

    __test__: ClassVar[bool]
    intent_id: str
    status: TestStatus
    duration_ms: float
    message: str = ""
    screenshot_path: str | None = None
    healed: bool = False
    heal_details: str | None = None
    dom_snapshot: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return {
            "intent_id": self.intent_id,
            "status": self.status.value,
            "duration_ms": round(self.duration_ms, 1),
            "message": self.message,
            "screenshot_path": self.screenshot_path,
            "healed": self.healed,
            "heal_details": self.heal_details,
            "timestamp": self.timestamp,
        }


@dataclass
class HarnessReport:
    """전체 테스트 하네스 실행 결과."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    healed: int = 0
    skipped: int = 0
    duration_ms: float = 0
    results: list[TestResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "healed": self.healed,
            "skipped": self.skipped,
            "duration_ms": round(self.duration_ms, 1),
            "pass_rate": f"{(self.passed + self.healed) / max(self.total, 1) * 100:.1f}%",
            "results": [r.to_dict() for r in self.results],
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """Render the report as a Markdown summary."""
        lines = [
            "# 🧪 Ssak-Ai Self-Test Report",
            "",
            "| 항목 | 값 |",
            "|------|-----|",
            f"| 총 테스트 | {self.total} |",
            f"| ✅ 통과 | {self.passed} |",
            f"| 🔧 자가치유 | {self.healed} |",
            f"| ❌ 실패 | {self.failed} |",
            f"| ⏭ 스킵 | {self.skipped} |",
            f"| 소요시간 | {self.duration_ms:.0f}ms |",
            f"| 합격률 | {(self.passed + self.healed) / max(self.total, 1) * 100:.1f}% |",
            "",
            "## 상세 결과",
            "",
        ]
        for r in self.results:
            icon = {"passed": "✅", "failed": "❌", "healed": "🔧", "skipped": "⏭"}.get(
                r.status.value,
                "❓",
            )
            lines.append(f"- {icon} **{r.intent_id}**: {r.message} ({r.duration_ms:.0f}ms)")
            if r.healed and r.heal_details:
                lines.append(f"  - 🩹 치유: {r.heal_details}")
        return "\n".join(lines)


TestStatus.__test__ = False
TestIntent.__test__ = False
TestResult.__test__ = False
