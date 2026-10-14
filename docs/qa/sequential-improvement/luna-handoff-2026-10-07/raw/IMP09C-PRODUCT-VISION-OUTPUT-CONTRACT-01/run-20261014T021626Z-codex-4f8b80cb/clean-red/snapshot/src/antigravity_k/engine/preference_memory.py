from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import ClassVar, Literal, final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from antigravity_k.engine.secret_scanner import redact_full

from .memory_contracts import JsonValue, MemoryFact, MemoryFactAuthority

logger = logging.getLogger("antigravity_k.engine.memory_provider")


class StoredPreferenceFact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    value: str = Field(min_length=1, max_length=200)
    authority: MemoryFactAuthority
    observed_at: float


class LearnedPreferenceFacts(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    response_language: Literal["ko", "en", "mixed"] | None = None
    response_detail: Literal["concise", "detailed"] | None = None
    explanation_level: Literal["beginner", "intermediate", "advanced"] | None = None
    task_domain: str | None = Field(default=None, min_length=1, max_length=200)

    def facts(self) -> dict[str, str]:
        values = {
            "response_language": self.response_language,
            "response_detail": self.response_detail,
            "explanation_level": self.explanation_level,
            "task_domain": self.task_domain,
        }
        return {key: value for key, value in values.items() if value is not None}


_FACTS_ADAPTER = TypeAdapter(dict[str, StoredPreferenceFact])
_DURABLE_CUE = r"(?:앞으로|이제부터|항상|계속|보통|나는|저는|내가|제가)"
_DETAIL_PATTERN = re.compile(
    rf"{_DURABLE_CUE}.{{0,16}}?(?:답변|대답|응답)(?:은|을|는)?\s*" + r"(?P<value>간결|짧|상세|자세)",
)
_DETAIL_REVERSED_PATTERN = re.compile(
    rf"{_DURABLE_CUE}.{{0,12}}?(?P<value>간결|짧|상세|자세).{{0,8}}?(?:답변|대답|응답)",
)
_LANGUAGE_PATTERN = re.compile(
    rf"{_DURABLE_CUE}.{{0,16}}?(?:답변|대답|응답)(?:은|을|는)?\s*" + r"(?P<value>한국어|영어|한영\s*(?:혼용|혼합))",
)
_LANGUAGE_REVERSED_PATTERN = re.compile(
    rf"{_DURABLE_CUE}.{{0,12}}?(?P<value>한국어|영어|한영\s*(?:혼용|혼합))" + r".{0,8}?(?:답변|대답|응답)",
)
_EN_DETAIL_PATTERN = re.compile(
    r"\b(?:from\s+now\s+on|always|i\s+prefer)\b.{0,20}"
    + r"(?P<value>concise|brief|detailed)\b.{0,12}\b(?:answers?|responses?|replies?)\b",
    re.IGNORECASE,
)
_EN_DETAIL_REVERSED_PATTERN = re.compile(
    r"\b(?:from\s+now\s+on|always|i\s+prefer)\b.{0,20}"
    + r"(?:answers?|responses?|replies?)\b.{0,12}\b(?P<value>concise|brief|detailed)\b",
    re.IGNORECASE,
)
_EN_LANGUAGE_PATTERN = re.compile(
    r"\b(?:from\s+now\s+on|always|i\s+prefer)\b.{0,24}"
    + r"(?:respond|answer|reply)(?:\s+to\s+me)?\s+(?:in\s+)?(?P<value>korean|english|mixed)\b",
    re.IGNORECASE,
)
_EN_LANGUAGE_REVERSED_PATTERN = re.compile(
    r"\b(?:from\s+now\s+on|always|i\s+prefer)\b.{0,20}"
    + r"(?P<value>korean|english|mixed)\b.{0,12}\b(?:answers?|responses?|replies?)\b",
    re.IGNORECASE,
)
_LEARNED_EXACT = {
    "한국어 응답 선호": ("response_language", "ko"),
    "영어 응답 선호": ("response_language", "en"),
    "한영 혼용": ("response_language", "mixed"),
    "초보자 친화적 설명 선호": ("explanation_level", "beginner"),
    "고급 기술 답변 선호": ("explanation_level", "advanced"),
    "간결한 응답 선호": ("response_detail", "concise"),
    "상세한 응답 선호": ("response_detail", "detailed"),
}


def extract_explicit_preference_facts(text: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    detail_match = _DETAIL_PATTERN.search(text) or _DETAIL_REVERSED_PATTERN.search(text)
    if detail_match:
        detail = detail_match.group("value")
        facts["response_detail"] = "concise" if detail in {"간결", "짧"} else "detailed"
    language_match = _LANGUAGE_PATTERN.search(text) or _LANGUAGE_REVERSED_PATTERN.search(text)
    if language_match:
        language = language_match.group("value").replace(" ", "")
        facts["response_language"] = {"한국어": "ko", "영어": "en"}.get(language, "mixed")
    if match := _EN_DETAIL_PATTERN.search(text) or _EN_DETAIL_REVERSED_PATTERN.search(text):
        facts["response_detail"] = "concise" if match.group("value").lower() in {"concise", "brief"} else "detailed"
    if match := _EN_LANGUAGE_PATTERN.search(text) or _EN_LANGUAGE_REVERSED_PATTERN.search(text):
        facts["response_language"] = {"korean": "ko", "english": "en", "mixed": "mixed"}[match.group("value").lower()]
    return facts


def extract_learned_preference_facts(values: list[str]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for value in values:
        if exact := _LEARNED_EXACT.get(value.strip()):
            facts[exact[0]] = exact[1]
            continue
        if value.startswith("주요 작업 도메인:"):
            domain = value.partition(":")[2].strip()
            if domain:
                facts["task_domain"] = domain[:200]
        elif value.startswith("기술 수준:"):
            level = value.partition(":")[2].strip()
            if level:
                facts["explanation_level"] = level[:200]
    return facts


def parse_learned_preference_facts(value: JsonValue) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return LearnedPreferenceFacts.model_validate(value).facts()


@final
class PreferenceFactStore:
    def __init__(self, memory_dir: Path) -> None:
        self._path = memory_dir / "preference_facts.json"
        self._records = self._load()

    def _load(self) -> dict[str, StoredPreferenceFact]:
        if not self._path.exists():
            return {}
        try:
            return _FACTS_ADAPTER.validate_json(self._path.read_bytes())
        except (OSError, ValidationError):
            logger.warning("[GlobalMemory] preference facts load failed", exc_info=True)
            return {}

    def _save(self) -> None:
        payload = {key: record.model_dump(mode="json") for key, record in self._records.items()}
        try:
            _ = self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("[GlobalMemory] preference facts save failed", exc_info=True)

    def update(self, key: str, value: str, authority: MemoryFactAuthority) -> bool:
        current = self._records.get(key)
        if current is not None and current.authority > authority:
            return False
        if current is not None and current.authority == authority and current.value == value:
            return False
        self._records[key] = StoredPreferenceFact(value=value, authority=authority, observed_at=time.time())
        self._save()
        return True

    def update_many(self, facts: dict[str, str], authority: MemoryFactAuthority) -> int:
        return sum(self.update(key, value, authority) for key, value in facts.items())

    def get(self, key: str) -> str | None:
        record = self._records.get(key)
        return record.value if record is not None else None

    def delete(self, key: str) -> bool:
        """개별 선호 팩트를 삭제하고 저장합니다."""
        if key not in self._records:
            return False
        del self._records[key]
        self._save()
        return True

    def markers(self) -> tuple[str, ...]:
        return tuple(f"[preference:{key}] {record.value}" for key, record in sorted(self._records.items()))

    def authoritative_facts(self, source: str) -> tuple[MemoryFact, ...]:
        return tuple(
            MemoryFact(
                key=f"preference:{key}",
                value=record.value,
                source=source,
                scope="global",
                authority=record.authority,
                observed_at=record.observed_at,
            )
            for key, record in sorted(self._records.items())
        )

    def export(self) -> list[dict[str, JsonValue]]:
        return [
            {
                "category": "preference_fact",
                "key": key,
                "value": record.value,
                "authority": int(record.authority),
                "observed_at": record.observed_at,
            }
            for key, record in sorted(self._records.items())
        ]

    def clear(self) -> int:
        count = len(self._records)
        self._records.clear()
        self._save()
        return count

    def redact(self) -> int:
        changed = 0
        for key, record in tuple(self._records.items()):
            redacted = redact_full(record.value)
            if redacted == record.value:
                continue
            self._records[key] = record.model_copy(update={"value": redacted})
            changed += 1
        if changed:
            self._save()
        return changed

    def apply_retention(self, cutoff: float) -> int:
        try:
            expired = self._path.exists() and self._path.stat().st_mtime < cutoff
        except OSError:
            expired = False
        return self.clear() if expired else 0
