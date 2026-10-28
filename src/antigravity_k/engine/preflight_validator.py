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
        # r33: a disk-format/wipe *action* — a command form or an imperative aimed at a disk/volume.
        # The bare words "format"/"wipe" (e.g. "format URLs", "output format") are not actions.
        PreflightRule(
            re.compile(
                r"\bmkfs(?:\.\w+)?\b|\bdiskutil\s+(?:erase\w*|zerodisk|securerase|secureerase|reformat)\b|"
                r"\bdd\s+if=\S+\s+of=/dev/|\bformat\s+[a-z]:|"
                r"\b(?:format|wipe|erase|reformat|zero)\s+(?:out\s+)?(?:the\s+|my\s+|this\s+|all\s+|every\s+|entire\s+)*"
                r"(?:\w+\s+)?(?:disk|disks|drive|drives|volume|volumes|partition|partitions|ssd|hdd|filesystem|/dev/\S+)\b|"
                r"(?:디스크|드라이브|볼륨|파티션|하드|ssd|hdd)\S{0,3}\s*(?:\S+\s+){0,2}(?:포맷|초기화|와이프|전부\s*지워|다\s*지워)"
                r"(?:해|하|시켜|좀|줘|라|$)",
                re.IGNORECASE,
            ),
            "디스크 포맷 또는 데이터 삭제 요청은 안전상 거부됩니다.",
        ),
        PreflightRule(
            re.compile(r"\b(shutdown|reboot)\b", re.IGNORECASE),
            "시스템 종료/재시작은 명시적 별도 승인 없이 진행하지 않습니다.",
        ),
    )

    # r33: words that make a sentence an execution request even when it also explains or quotes.
    _EXEC_RE: ClassVar[Pattern[str]] = re.compile(
        r"\b(?:run|execute|exec|perform|go\s+ahead|now|then|please)\b|실행|돌려|수행|진행|해\s*줘|해라|하세요|해주세요|시켜|그리고|다음에",
        re.IGNORECASE,
    )
    # Explanation / quotation / refusal context (talking *about* deletion, not asking for it).
    _ABOUT_RE: ClassVar[Pattern[str]] = re.compile(
        r"\b(?:explain|describe|what\s+(?:is|does|do)|why|meaning|difference|refus\w*|declin\w*|reject\w*|"
        r"warn\w*)\b|설명|무엇|뭐야|뭔가요|의미|차이|왜|거부|거절|경고",
        re.IGNORECASE,
    )
    _QUOTED_RE: ClassVar[Pattern[str]] = re.compile(r"`[^`]*`|\"[^\"]*\"|“[^”]*”|「[^」]*」|『[^』]*』")

    @classmethod
    def _action_text(cls, text: str) -> str:
        """Text the deny rules judge. Unchanged whenever an execution verb is present (outside quotes).

        Only when the request is about deletion (explain/quote/refuse) and contains no execution
        verb is quoted material and the whole explanatory request excluded from the action scan.
        """
        unquoted = cls._QUOTED_RE.sub(" ", text)
        if cls._EXEC_RE.search(unquoted):
            return text
        if cls._ABOUT_RE.search(unquoted):
            return ""
        return text

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
        scan = self._action_text(text)
        for rule in self._DENY_RULES:
            if rule.pattern.search(scan):
                return False, rule.reason, EngineProfile.STRICT_ENGINEER

        lowered = text.lower()
        if any(hint in lowered for hint in self._FAST_HINTS):
            return True, "", EngineProfile.FAST_PROTOTYPER
        return True, "", EngineProfile.STRICT_ENGINEER
