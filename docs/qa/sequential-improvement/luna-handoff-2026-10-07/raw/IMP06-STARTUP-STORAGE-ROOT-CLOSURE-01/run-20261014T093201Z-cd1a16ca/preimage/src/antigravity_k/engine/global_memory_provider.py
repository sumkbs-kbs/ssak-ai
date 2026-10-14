from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import final, override

from pydantic import TypeAdapter, ValidationError

from antigravity_k.engine.secret_scanner import redact_full

from .identity_memory import extract_identity_facts as extract_identity_facts
from .memory_contracts import (
    InvalidRetentionAgeError,
    JsonValue,
    MemoryFact,
    MemoryFactAuthority,
    MemoryProvider,
    MemoryScope,
    normalize_memory_scope,
)
from .preference_memory import (
    PreferenceFactStore,
    extract_explicit_preference_facts,
    extract_learned_preference_facts,
    parse_learned_preference_facts,
)

logger = logging.getLogger("antigravity_k.engine.memory_provider")
_IDENTITY_ADAPTER = TypeAdapter(dict[str, str])
_CATEGORY_ADAPTER = TypeAdapter(list[str])


@final
class GlobalMemoryProvider(MemoryProvider):
    def __init__(self, memory_dir: str | None = None, max_entries: int = 200) -> None:
        default_dir = Path.home() / ".antigravity-k" / "memory"
        self._memory_dir = Path(memory_dir) if memory_dir else default_dir
        self._max_entries = max_entries
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._memory = self._load_categories()
        self._identity = self._load_identity()
        self._preferences = PreferenceFactStore(self._memory_dir)
        self._migrate_known_preferences()

    @property
    @override
    def name(self) -> str:
        return "global"

    @property
    def _identity_path(self) -> Path:
        return self._memory_dir / "identity.json"

    def _category_path(self, category: str) -> Path:
        return self._memory_dir / f"{category}.json"

    def _load_identity(self) -> dict[str, str]:
        if not self._identity_path.exists():
            return {}
        try:
            return _IDENTITY_ADAPTER.validate_json(self._identity_path.read_bytes())
        except (OSError, ValidationError):
            logger.warning("[GlobalMemory] identity load failed", exc_info=True)
            return {}

    def _save_identity(self) -> None:
        try:
            _ = self._identity_path.write_text(
                json.dumps(self._identity, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("[GlobalMemory] identity save failed", exc_info=True)

    def _load_categories(self) -> dict[str, list[str]]:
        memory: dict[str, list[str]] = {"preferences": [], "patterns": [], "facts": []}
        for category in memory:
            path = self._category_path(category)
            if not path.exists():
                continue
            try:
                values = _CATEGORY_ADAPTER.validate_json(path.read_bytes())
            except (OSError, ValidationError):
                logger.warning("[GlobalMemory] %s load failed", category, exc_info=True)
                continue
            memory[category] = values[-self._max_entries :]
        return memory

    def _save_category(self, category: str) -> None:
        try:
            _ = self._category_path(category).write_text(
                json.dumps(self._memory.get(category, []), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("[GlobalMemory] %s save failed", category, exc_info=True)

    def get_identity_fact(self, key: str) -> str | None:
        return self._identity.get(key)

    def set_identity_fact(self, key: str, value: str) -> None:
        if key and value and self._identity.get(key) != value:
            self._identity[key] = value
            self._save_identity()

    def get_preference_fact(self, key: str) -> str | None:
        return self._preferences.get(key)

    def _migrate_known_preferences(self) -> None:
        legacy = self._memory["preferences"]
        known = extract_learned_preference_facts(legacy)
        if not known:
            return
        _ = self._preferences.update_many(known, MemoryFactAuthority.INFERRED_PREFERENCE)
        remaining = [value for value in legacy if not extract_learned_preference_facts([value])]
        if remaining != legacy:
            self._memory["preferences"] = remaining
            self._save_category("preferences")

    @override
    def authoritative_facts(self) -> tuple[MemoryFact, ...]:
        try:
            observed_at = self._identity_path.stat().st_mtime
        except OSError:
            observed_at = 0.0
        identity = tuple(
            MemoryFact(
                key=f"identity:{key}",
                value=value,
                source=self.name,
                scope="global",
                authority=MemoryFactAuthority.DURABLE_IDENTITY,
                observed_at=observed_at,
            )
            for key, value in sorted(self._identity.items())
        )
        return identity + self._preferences.authoritative_facts(self.name)

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        relevant = [f"[identity:{key}] {value}" for key, value in self._identity.items()]
        relevant.extend(self._preferences.markers())
        words = [word for word in query.lower().split() if len(word) > 2]
        for category, entries in self._memory.items():
            relevant.extend(
                f"[{category}] {entry}" for entry in entries if any(word in entry.lower() for word in words)
            )
        if not relevant:
            relevant = [f"[preferences] {value}" for value in self._memory["preferences"][:3]]
        if not relevant:
            return ""
        return "[Global User Memory]\n" + "\n".join(relevant[:10])

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        for key, value in extract_identity_facts(user_message).items():
            self.set_identity_fact(key, value)
        _ = self._preferences.update_many(
            extract_explicit_preference_facts(user_message),
            MemoryFactAuthority.DURABLE_PREFERENCE,
        )
        if metadata is None:
            return
        preferences = _CATEGORY_ADAPTER.validate_python(metadata.get("learned_preferences", []))
        patterns = _CATEGORY_ADAPTER.validate_python(metadata.get("learned_patterns", []))
        learned_facts = extract_learned_preference_facts(preferences)
        learned_facts.update(
            parse_learned_preference_facts(metadata.get("learned_preference_facts", {})),
        )
        _ = self._preferences.update_many(learned_facts, MemoryFactAuthority.INFERRED_PREFERENCE)
        unstructured = [value for value in preferences if not extract_learned_preference_facts([value])]
        self._append_values("preferences", unstructured, bounded=True)
        self._append_values("patterns", patterns, bounded=False)

    def _append_values(self, category: str, values: list[str], *, bounded: bool) -> None:
        changed = False
        for value in values:
            if value and value not in self._memory[category]:
                self._memory[category].append(value)
                changed = True
        if bounded:
            self._memory[category] = self._memory[category][-self._max_entries :]
        if changed:
            self._save_category(category)

    def add_preference(self, preference: str) -> None:
        self._append_values("preferences", [preference], bounded=True)

    def add_fact(self, fact: str) -> None:
        self._append_values("facts", [fact], bounded=True)

    def get_all(self) -> dict[str, list[str]]:
        return {category: list(values) for category, values in self._memory.items()}

    def delete_entry(self, key: str) -> bool:
        """개별 글로벌 항목을 삭제합니다.

        키 형식: identity:<key> | preference:<key> | category:<이름>:<값>.
        """
        if key.startswith("identity:"):
            identity_key = key.partition(":")[2]
            if identity_key not in self._identity:
                return False
            del self._identity[identity_key]
            self._save_identity()
            return True
        if key.startswith("preference:"):
            return self._preferences.delete(key.partition(":")[2])
        if key.startswith("category:"):
            _, _, rest = key.partition(":")
            name, _, value = rest.partition(":")
            entries = self._memory.get(name)
            if entries is None or value not in entries:
                return False
            entries.remove(value)
            self._save_category(name)
            return True
        return False

    @override
    def clear(self, scope: MemoryScope = "all") -> int:
        normalized_scope = normalize_memory_scope(scope)
        if normalized_scope not in ("global", "all"):
            return 0
        deleted = len(self._identity) + sum(len(entries) for entries in self._memory.values())
        self._identity.clear()
        self._save_identity()
        deleted += self._preferences.clear()
        for category in self._memory:
            self._memory[category] = []
            self._save_category(category)
        return deleted

    @override
    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        normalized_scope = normalize_memory_scope(scope)
        if normalized_scope not in ("global", "all"):
            return []
        identity: list[dict[str, JsonValue]] = [
            {"category": "identity", "key": key, "value": value} for key, value in self._identity.items()
        ]
        categories: list[dict[str, JsonValue]] = [
            {"category": category, "value": value} for category, values in self._memory.items() for value in values
        ]
        return identity + self._preferences.export() + categories

    @override
    def redact(self, scope: MemoryScope = "all") -> int:
        normalized_scope = normalize_memory_scope(scope)
        if normalized_scope not in ("global", "all"):
            return 0
        changed = 0
        redacted_identity = {key: redact_full(value) for key, value in self._identity.items()}
        changed += sum(self._identity[key] != value for key, value in redacted_identity.items())
        self._identity = redacted_identity
        self._save_identity()
        changed += self._preferences.redact()
        for category, values in self._memory.items():
            redacted = [redact_full(value) for value in values]
            changed += sum(old != new for old, new in zip(values, redacted, strict=True))
            self._memory[category] = redacted
            self._save_category(category)
        return changed

    @override
    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise InvalidRetentionAgeError(max_age_days)
        cutoff = time.time() - (max_age_days * 86400)
        deleted = 0
        if self._expired(self._identity_path, cutoff):
            deleted += len(self._identity)
            self._identity.clear()
            self._save_identity()
        deleted += self._preferences.apply_retention(cutoff)
        for category, entries in self._memory.items():
            if not self._expired(self._category_path(category), cutoff):
                continue
            deleted += len(entries)
            self._memory[category] = []
            self._save_category(category)
        return deleted

    @staticmethod
    def _expired(path: Path, cutoff: float) -> bool:
        try:
            return path.exists() and path.stat().st_mtime < cutoff
        except OSError:
            return False
