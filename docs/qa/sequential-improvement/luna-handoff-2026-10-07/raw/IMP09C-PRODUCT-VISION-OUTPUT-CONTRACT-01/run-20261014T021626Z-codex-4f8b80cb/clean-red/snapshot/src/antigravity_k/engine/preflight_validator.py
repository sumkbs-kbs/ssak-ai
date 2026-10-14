"""Preflight Validator module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from re import Pattern
from typing import ClassVar

from antigravity_k.engine.engine_profile import EngineProfile


@dataclass(frozen=True)
class PreflightRule:
    """A single pre-flight validation rule with a check function and severity."""

    pattern: Pattern[str]
    reason: str


class PreflightValidator:
    """Lightweight request gate before the expensive agent loop starts."""

    _DENY_RULES: ClassVar[tuple[PreflightRule, ...]] = (
        PreflightRule(
            re.compile(r"\brm\s+-rf\s+/(?:\s|$)", re.IGNORECASE),
            "루트 파일시스템 삭제처럼 되돌리기 어려운 명령은 실행할 수 없습니다.",
        ),
        PreflightRule(
            re.compile(r"\b(format|mkfs|diskutil\s+erase|wipe)\b", re.IGNORECASE),
            "디스크 포맷 또는 데이터 삭제 요청은 안전상 거부됩니다.",
        ),
        PreflightRule(
            re.compile(r"\b(shutdown|reboot)\b", re.IGNORECASE),
            "시스템 종료/재시작은 명시적 별도 승인 없이 진행하지 않습니다.",
        ),
    )

    _FAST_HINTS: ClassVar[tuple[str, ...]] = (
        "prototype",
        "프로토타입",
        "quick",
        "빠르게",
        "demo",
        "mock",
        "샘플",
    )

    def __init__(self, model_manager: object | None = None) -> None:
        """Initialize the PreflightValidator.

        Args:
            model_manager: model manager.

        """
        self.model_manager: object | None = model_manager

    def validate(self, user_text: str) -> tuple[bool, str, EngineProfile]:
        """Validate.

        Args:
            user_text (str): str user text.

        Returns:
            tuple[bool, str, EngineProfile]: The tuple[bool, str, engineprofile] result.

        """
        text = user_text or ""
        for rule in self._DENY_RULES:
            if rule.pattern.search(text):
                return False, rule.reason, EngineProfile.STRICT_ENGINEER

        lowered = text.lower()
        if any(hint in lowered for hint in self._FAST_HINTS):
            return True, "", EngineProfile.FAST_PROTOTYPER
        return True, "", EngineProfile.STRICT_ENGINEER
