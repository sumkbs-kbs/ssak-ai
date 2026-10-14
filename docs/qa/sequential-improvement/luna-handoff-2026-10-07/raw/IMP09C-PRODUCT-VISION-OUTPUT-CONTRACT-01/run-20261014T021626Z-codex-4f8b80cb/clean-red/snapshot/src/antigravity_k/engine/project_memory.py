from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal, final, override

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from antigravity_k.engine.secret_scanner import redact_full

from .memory_contracts import (
    InvalidRetentionAgeError,
    JsonValue,
    MemoryFact,
    MemoryFactAuthority,
    MemoryProvider,
    MemoryScope,
    normalize_memory_scope,
)
from .project_memory_keys import (
    ProjectKeyAliases,
    load_project_key_aliases,
    project_read_query_target,
)
from .project_memory_paths import (
    UnsafeProjectMemoryPathError as UnsafeProjectMemoryPathError,
)
from .project_memory_paths import project_memory_dir

logger = logging.getLogger("antigravity_k.engine.memory_provider")
ProjectFactKind = Literal["decision", "fact"]
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DECISION_PATTERN = re.compile(
    r"이\s*프로젝트(?:에서는|에서|는)?\s*"
    + r"(?P<key>데이터베이스|DB|프론트엔드|백엔드|패키지\s*매니저|테스트\s*프레임워크)"
    + r"(?:로|으로|은|는)?\s*(?P<value>[A-Za-z][A-Za-z0-9+.#_-]{0,63})"
    + r"(?:을|를)?\s*(?:사용|선택|채택|쓰기|쓰기로).{0,16}?(?:했|하기로|한다|할\s*거)",
    re.IGNORECASE,
)
_EN_DECISION_PATTERN = re.compile(
    r"\b(?:for\s+)?this\s+project\b.{0,20}?"
    + r"(?P<key>database|frontend|backend|package\s+manager|test\s+framework)"
    + r".{0,12}?\b(?:use|choose|adopt)\s+(?P<value>[A-Za-z][A-Za-z0-9+.#_-]{0,63})\b",
    re.IGNORECASE,
)
_EXPLICIT_FACT_PATTERN = re.compile(
    r"(?:프로젝트\s*(?P<ko_kind>결정|사실)|project\s+(?P<en_kind>decision|fact))\s*:\s*"
    + r"(?P<key>[a-z][a-z0-9_]{0,63})\s*=\s*(?P<value>[^\n]{1,500})",
    re.IGNORECASE,
)
_KEYS = {
    "데이터베이스": "database",
    "db": "database",
    "프론트엔드": "frontend",
    "백엔드": "backend",
    "패키지매니저": "package_manager",
    "테스트프레임워크": "test_framework",
    "database": "database",
    "frontend": "frontend",
    "backend": "backend",
    "packagemanager": "package_manager",
    "testframework": "test_framework",
}


class StoredProjectFact(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: ProjectFactKind
    value: str = Field(min_length=1, max_length=500)
    observed_at: float


class ProjectMemoryFacts(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    decisions: dict[str, str] = Field(default_factory=dict)
    facts: dict[str, str] = Field(default_factory=dict)

    @field_validator("decisions", "facts")
    @classmethod
    def validate_entries(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if _KEY_PATTERN.fullmatch(key) is None or not 1 <= len(value.strip()) <= 500:
                raise InvalidProjectMemoryFactError(key)
        return {key: value.strip() for key, value in values.items()}


class InvalidProjectMemoryFactError(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Invalid project memory fact: {key}")


_STORE_ADAPTER = TypeAdapter(dict[str, StoredProjectFact])


def extract_project_memory_facts(
    text: str,
    aliases: ProjectKeyAliases | None = None,
) -> dict[str, str]:
    key_aliases = aliases or ProjectKeyAliases()
    if explicit := _EXPLICIT_FACT_PATTERN.search(text):
        raw_kind = (explicit.group("ko_kind") or explicit.group("en_kind")).lower()
        kind = "decision" if raw_kind in {"결정", "decision"} else "fact"
        key = key_aliases.canonical_key(explicit.group("key"))
        return {f"{kind}:{key}": explicit.group("value").strip()}
    match = _DECISION_PATTERN.search(text) or _EN_DECISION_PATTERN.search(text)
    if match is None:
        return {}
    raw_key = re.sub(r"\s+", "", match.group("key").lower())
    canonical_key = _KEYS.get(raw_key)
    if canonical_key is None:
        return {}
    return {f"decision:{canonical_key}": match.group("value").lower()}


def parse_project_memory_facts(
    value: JsonValue,
    aliases: ProjectKeyAliases | None = None,
) -> dict[str, tuple[ProjectFactKind, str]]:
    if not isinstance(value, dict):
        return {}
    parsed = ProjectMemoryFacts.model_validate(value)
    key_aliases = aliases or ProjectKeyAliases()
    result: dict[str, tuple[ProjectFactKind, str]] = {
        key_aliases.canonical_key(key): ("decision", item) for key, item in parsed.decisions.items()
    }
    result.update({key_aliases.canonical_key(key): ("fact", item) for key, item in parsed.facts.items()})
    return result


@final
class ProjectMemoryProvider(MemoryProvider):
    def __init__(self, project_root: str | Path, clock: Callable[[], float] = time.time) -> None:
        self.project_root = Path(project_root).resolve()
        self._memory_dir = project_memory_dir(self.project_root)
        self._aliases = load_project_key_aliases(self._memory_dir)
        self._path = self._memory_dir / "project_facts.json"
        self._clock = clock
        self._records = self._load()
        if self._canonicalize_records():
            self._save()

    @property
    @override
    def name(self) -> str:
        return "project"

    def _load(self) -> dict[str, StoredProjectFact]:
        if not self._path.exists():
            return {}
        try:
            return _STORE_ADAPTER.validate_json(self._path.read_bytes())
        except (OSError, ValidationError):
            logger.warning("[ProjectMemory] load failed", exc_info=True)
            return {}

    def _save(self) -> None:
        payload = {key: record.model_dump(mode="json") for key, record in self._records.items()}
        try:
            _ = self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("[ProjectMemory] save failed", exc_info=True)

    def _canonicalize_records(self) -> bool:
        canonical: dict[str, StoredProjectFact] = {}
        for raw_key, record in self._records.items():
            key = self._aliases.canonical_record_key(raw_key)
            current = canonical.get(key)
            if current is None or record.observed_at >= current.observed_at:
                canonical[key] = record
        changed = canonical != self._records
        self._records = canonical
        return changed

    def _update(self, key: str, kind: ProjectFactKind, value: str) -> None:
        record_key = f"{kind}:{self._aliases.canonical_key(key)}"
        current = self._records.get(record_key)
        if current is not None and current.value == value:
            return
        self._records[record_key] = StoredProjectFact(kind=kind, value=value, observed_at=self._clock())
        self._save()

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        _ = query, session_id
        if not self._records:
            return ""
        markers = [f"[project:{key}] {record.value}" for key, record in sorted(self._records.items())]
        return "[Project Memory]\n" + "\n".join(markers[:20])

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        _ = assistant_response
        for raw_key, value in extract_project_memory_facts(user_message, self._aliases).items():
            kind, _, key = raw_key.partition(":")
            self._update(key, "decision" if kind == "decision" else "fact", value)
        if metadata is None:
            return
        for key, (kind, value) in parse_project_memory_facts(
            metadata.get("project_memory_facts", {}),
            self._aliases,
        ).items():
            self._update(key, kind, value)

    def canonicalize_context(self, text: str) -> str:
        return self._aliases.canonicalize_text(text)

    def read_query_target(self, query: str) -> tuple[str | None, str] | None:
        return project_read_query_target(query, self._aliases)

    @override
    def authoritative_facts(self) -> tuple[MemoryFact, ...]:
        return tuple(
            MemoryFact(
                key=f"project:{key}",
                value=record.value,
                source=self.name,
                scope="project",
                authority=MemoryFactAuthority.PROJECT_DECISION,
                observed_at=record.observed_at,
            )
            for key, record in sorted(self._records.items())
        )

    @override
    def clear(self, scope: MemoryScope = "all") -> int:
        if normalize_memory_scope(scope) not in ("project", "all"):
            return 0
        count = len(self._records)
        self._records.clear()
        self._save()
        return count

    def delete_entry(self, key: str) -> bool:
        """개별 프로젝트 팩트를 삭제합니다.

        키 형식: decision:<key> | fact:<key> | 별칭 키만으로도 삭제 가능.
        """
        if ":" in key:
            kind, _, raw_key = key.partition(":")
            if kind not in ("decision", "fact"):
                return False
            record_key = f"{kind}:{self._aliases.canonical_key(raw_key)}"
            if record_key not in self._records:
                return False
            del self._records[record_key]
            self._save()
            return True
        canonical = self._aliases.canonical_key(key)
        for record_key in (f"decision:{canonical}", f"fact:{canonical}"):
            if record_key not in self._records:
                continue
            del self._records[record_key]
            self._save()
            return True
        return False

    @override
    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        if normalize_memory_scope(scope) not in ("project", "all"):
            return []
        return [
            {
                "category": f"project_{record.kind}",
                "key": key.partition(":")[2],
                "value": record.value,
                "observed_at": record.observed_at,
                "project_root": str(self.project_root),
            }
            for key, record in sorted(self._records.items())
        ]

    @override
    def redact(self, scope: MemoryScope = "all") -> int:
        if normalize_memory_scope(scope) not in ("project", "all"):
            return 0
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

    @override
    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise InvalidRetentionAgeError(max_age_days)
        cutoff = self._clock() - (max_age_days * 86400)
        kept = {key: record for key, record in self._records.items() if record.observed_at >= cutoff}
        deleted = len(self._records) - len(kept)
        if deleted:
            self._records = kept
            self._save()
        return deleted
