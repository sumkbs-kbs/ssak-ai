"""MemoryProvider — 플러그인 기반 에이전트 메모리 시스템.

=====================================================
Hermes Agent의 memory_manager.py 패턴을 Ssak-Ai에 이식.

아키텍처:
- MemoryProvider (ABC): 메모리 제공자 인터페이스
- BuiltinMemoryProvider: SessionManager 기반 내장 메모리
- MemoryManager: 여러 메모리 제공자를 오케스트레이션

핵심 라이프사이클:
  세션 시작 → prefetch(query) → 대화 진행 → sync_turn(user, assistant) → 세션 종료

사용법:
    manager = MemoryManager()
    manager.add_provider(BuiltinMemoryProvider(session_manager))

    # 대화 시작 시 관련 기억 회상
    recalled = manager.prefetch_all("이전에 논의한 아키텍처")

    # 각 턴 종료 시 기억 동기화
    manager.sync_all(user_message, assistant_response)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Protocol, TypedDict, cast, override

from antigravity_k.engine.memory_conflicts import (
    MemoryRecallFragment,
    resolve_memory_fact_winners,
)
from antigravity_k.engine.memory_contracts import JsonValue, ProjectMemoryBindingError
from antigravity_k.engine.memory_contracts import (
    MemoryFact as MemoryFact,
)
from antigravity_k.engine.memory_contracts import (
    MemoryProvider as MemoryProvider,
)
from antigravity_k.engine.memory_contracts import (
    MemoryScope as MemoryScope,
)
from antigravity_k.engine.memory_contracts import (
    normalize_memory_scope as normalize_memory_scope,
)
from antigravity_k.engine.memory_importance import rank_facts
from antigravity_k.engine.memory_recall_budget import (
    MemoryRecallBudget,
    compose_bounded_recall,
)
from antigravity_k.engine.project_memory import ProjectMemoryProvider
from antigravity_k.engine.tool_policy import request_allows_side_effects

logger = logging.getLogger("antigravity_k.engine.memory_provider")


class _SessionManagerPort(Protocol):
    def get_working_memory(self) -> dict[str, object]: ...

    def add_turn(self, *, role: str, content: str) -> None: ...

    def start_session(self, project_path: str | None = None, resume: bool = True) -> str: ...

    def clear_memory(self, scope: MemoryScope) -> int: ...

    def export_memory(self, scope: MemoryScope) -> list[dict[str, JsonValue]]: ...

    def redact_memory(self, scope: MemoryScope) -> int: ...

    def apply_retention(self, max_age_days: int) -> int: ...


class _Episode(TypedDict):
    user: str
    assistant: str
    timestamp: str
    metadata: dict[str, JsonValue]


def _coerce_episode(value: object) -> _Episode | None:
    if not isinstance(value, dict):
        return None
    record = cast(dict[str, object], value)
    user = record.get("user")
    assistant = record.get("assistant")
    timestamp = record.get("timestamp")
    metadata = record.get("metadata", {})
    if not isinstance(user, str) or not isinstance(assistant, str) or not isinstance(timestamp, str):
        return None
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "user": user,
        "assistant": assistant,
        "timestamp": timestamp,
        "metadata": cast(dict[str, JsonValue], metadata),
    }


def _ko_stems(text: str) -> set[str]:
    """Split text on whitespace and strip trailing Korean particles from each token.

    Korean case particles attach to a stem, so stripping them lets recall match a
    concept across particle variation (이름은/이름이/이름을 all reduce to 이름), which
    exact-substring keyword matching misses. Longest-first so "으로" strips before "로".
    """
    particles = (
        "으로서",
        "으로써",
        "으로",
        "에서",
        "에게",
        "한테",
        "처럼",
        "까지",
        "부터",
        "보다",
        "마다",
        "로서",
        "로써",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "도",
        "만",
        "와",
        "과",
        "로",
        "에",
        "께",
    )
    stems: set[str] = set()
    for token in text.split():
        if len(token) <= 1:
            continue
        stripped = token
        for particle in particles:
            if stripped.endswith(particle) and len(stripped) - len(particle) >= 1:
                stripped = stripped[: -len(particle)]
                break
        if len(stripped) > 1:
            stems.add(stripped)
    return stems


def _is_durable_fact_statement(text: str) -> bool:
    """Detect statements encoding durable user knowledge (preferences, facts).

    Such episodes should be importance-protected from consolidation decay — a stated
    preference ("나는 탭을 써") is durable knowledge even when stated once with zero
    re-access, unlike transient filler. Conservative cues keep false positives low.
    """
    import re

    durable_cues = [
        r"나는\s*.{0,12}?(?:좋아|싫어|사용|선호|쓰|선호해)",
        r"내가\s*.{0,12}?(?:좋아|싫어|사용|선호|쓰)",
        r"(?:저는|전)\s*.{0,12}?(?:좋아|싫어|사용|선호)",
        r"\b(?:i\s+(?:prefer|like|use|hate|always|usually))\b",
        r"\b(?:my\s+(?:preference|favorite|stack))\b",
        r"(?:항상|보통|주로)\s",
    ]
    text_lower = text.lower()
    return any(re.search(cue, text_lower) or re.search(cue, text) for cue in durable_cues)


# ── 내장 메모리 제공자 (SessionManager 래핑) ──


class BuiltinMemoryProvider(MemoryProvider):
    """SessionManager의 Working Memory를 MemoryProvider 인터페이스로 래핑.

    SessionManager의 기존 기능을 그대로 활용하면서,
    MemoryManager의 통합 라이프사이클에 참여할 수 있게 합니다.
    """

    def __init__(self, session_manager: _SessionManagerPort) -> None:
        """Initialize the BuiltinMemoryProvider.

        Args:
            session_manager: session manager.

        """
        self._session_manager: _SessionManagerPort = session_manager

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "builtin"

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        """Working Memory에서 관련 기억을 회상합니다."""
        try:
            memories = self._session_manager.get_working_memory()
            if not memories:
                return ""

            # 쿼리 키워드 기반 단순 필터링
            query_lower = query.lower()
            relevant: list[str] = []
            for key, value in memories.items():
                if query_lower in str(key).lower() or query_lower in str(value).lower():
                    relevant.append(f"- {key}: {value}")

            if not relevant:
                # 전체 Working Memory 요약 반환
                items = [f"- {k}: {v}" for k, v in list(memories.items())[:10]]
                if items:
                    return "[Working Memory]\n" + "\n".join(items)
                return ""

            return "[Relevant Memory]\n" + "\n".join(relevant)
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("BuiltinMemoryProvider.prefetch error: %s", e)
            return ""

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        """턴 정보를 SessionManager에 동기화합니다."""
        try:
            self._session_manager.add_turn(role="user", content=user_message)
            self._session_manager.add_turn(role="assistant", content=assistant_response)
        except Exception as e:
            from antigravity_k.engine.session_manager import SessionPersistenceError

            if isinstance(e, SessionPersistenceError):
                # CR-02: 턴 저장 실패를 debug 로그로 숨기지 않는다(턴 유실 신호).
                # 이 훅은 응답 이후 호출되고 반환 오류 채널이 없어 비치명적으로 둔다.
                logger.error("BuiltinMemoryProvider.sync_turn persistence failed: %s", e)
                return
            logger.exception("Unhandled exception")
            logger.debug("BuiltinMemoryProvider.sync_turn error: %s", e)

    @override
    def on_session_switch(self, new_session_id: str) -> None:
        """세션 전환 시 SessionManager의 세션을 전환합니다."""
        try:
            _ = self._session_manager.start_session(resume=True)
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("BuiltinMemoryProvider.on_session_switch error: %s", e)

    @override
    def clear(self, scope: MemoryScope = "all") -> int:
        scope = normalize_memory_scope(scope)
        if scope in ("session", "working", "all"):
            return self._session_manager.clear_memory(scope)
        return 0

    @override
    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        normalized = normalize_memory_scope(scope)
        if normalized == "project":
            return []
        return self._session_manager.export_memory(normalized)

    @override
    def redact(self, scope: MemoryScope = "all") -> int:
        normalized = normalize_memory_scope(scope)
        if normalized == "project":
            return 0
        return self._session_manager.redact_memory(normalized)

    @override
    def apply_retention(self, max_age_days: int) -> int:
        return self._session_manager.apply_retention(max_age_days)


# ── 메모리 매니저 (오케스트레이터) ──


class MemoryManager:
    """여러 메모리 제공자를 통합 관리하는 오케스트레이터.

    Hermes Agent 패턴:
    - 내장 제공자: 제한 없이 여러 개 등록 가능
    - 외부 제공자: 최대 1개만 (스키마 충돌 방지)
    - prefetch_all(): 모든 제공자에서 병렬 회상
    - sync_all(): 모든 제공자에 턴 동기화
    """

    MAX_EXTERNAL_PROVIDERS: ClassVar[int] = 1

    def __init__(self, project_root: str | None = None, recall_budget: MemoryRecallBudget | None = None) -> None:
        """Initialize the MemoryManager."""
        self._providers: list[MemoryProvider] = []
        self._external_count: int = 0
        self._project_root: Path | None = Path(project_root).resolve() if project_root is not None else None
        self._recall_budget = recall_budget if recall_budget is not None else MemoryRecallBudget()

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    def bind_project_root(self, project_root: str | Path) -> None:
        requested = Path(project_root).resolve()
        if self._project_root is not None and self._project_root != requested:
            raise ProjectMemoryBindingError(self._project_root, requested)
        self._project_root = requested

    @property
    def providers(self) -> list[MemoryProvider]:
        """Providers.

        Returns:
            list[MemoryProvider]: The list[memoryprovider] result.

        """
        return list(self._providers)

    def add_provider(self, provider: MemoryProvider) -> None:
        """메모리 제공자를 등록합니다.

        외부 제공자는 최대 1개만 등록 가능합니다.

        Raises:
            ValueError: 외부 제공자 한도 초과 시

        """
        if isinstance(provider, ProjectMemoryProvider):
            self.bind_project_root(provider.project_root)
        if provider.is_external:
            if self._external_count >= self.MAX_EXTERNAL_PROVIDERS:
                raise ValueError(
                    f"외부 메모리 제공자는 최대 {self.MAX_EXTERNAL_PROVIDERS}개만 등록할 수 있습니다. 현재: {self._external_count}",
                )
            self._external_count += 1

        self._providers.append(provider)
        logger.info(
            "Memory provider registered: %s (external=%s)",
            provider.name,
            provider.is_external,
        )

    def remove_provider(self, name: str) -> bool:
        """이름으로 메모리 제공자를 제거합니다."""
        for i, p in enumerate(self._providers):
            if p.name == name:
                removed = self._providers.pop(i)
                if removed.is_external:
                    self._external_count -= 1
                logger.info("Memory provider removed: %s", name)
                return True
        return False

    def prefetch_all(self, query: str, session_id: str | None = None) -> str:
        """모든 제공자에서 관련 기억을 회상합니다.

        각 제공자의 결과를 결합하여 하나의 컨텍스트 문자열로 반환합니다.
        """
        if not self._providers:
            return ""

        fragments: list[MemoryRecallFragment] = []
        facts: list[MemoryFact] = []
        for provider in self._providers:
            try:
                start = time.time()
                result = provider.prefetch(query, session_id)
                elapsed = time.time() - start
                if result and result.strip():
                    fragments.append(MemoryRecallFragment(provider=provider.name, content=result.strip()))
                    logger.debug(
                        "Memory prefetch [%s]: %s chars in %ss",
                        provider.name,
                        len(result),
                        elapsed,
                    )
            except Exception:
                logger.exception("Memory prefetch error [%s]", provider.name)
            try:
                facts.extend(provider.authoritative_facts())
            except Exception:
                logger.exception("Memory fact error [%s]", provider.name)

        if not fragments:
            return ""
        project_provider = self._project_provider()
        resolution_query = query
        if project_provider is not None:
            resolution_query = project_provider.canonicalize_context(query)
            fragments = [
                MemoryRecallFragment(
                    provider=fragment.provider,
                    content=project_provider.canonicalize_context(fragment.content),
                )
                for fragment in fragments
            ]
        resolution = compose_bounded_recall(
            resolution_query,
            tuple(facts),
            tuple(fragments),
            self._recall_budget,
        )
        if resolution.conflicts:
            logger.info(
                "Memory conflicts resolved: %s",
                ", ".join(conflict.key for conflict in resolution.conflicts),
            )
        return resolution.context

    def authoritative_project_fact_for_query(self, query: str) -> MemoryFact | None:
        project_provider = self._project_provider()
        if project_provider is None:
            return None
        target = project_provider.read_query_target(query)
        if target is None:
            return None
        kind, key = target
        candidates = tuple(
            fact
            for fact in project_provider.authoritative_facts()
            if fact.scope == "project"
            and fact.key.startswith("project:")
            and fact.key.partition(":")[2].partition(":")[2] == key
            and (kind is None or fact.key == f"project:{kind}:{key}")
        )
        if len(candidates) != 1:
            return None
        candidate = candidates[0]
        if len(candidate.value) > 120 or "\n" in candidate.value:
            return None
        return candidate

    def _project_provider(self) -> ProjectMemoryProvider | None:
        return next(
            (provider for provider in self._providers if isinstance(provider, ProjectMemoryProvider)),
            None,
        )

    def sync_all(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        """모든 제공자에 턴 데이터를 동기화합니다."""
        if not request_allows_side_effects():
            return
        for provider in self._providers:
            try:
                provider.sync_turn(user_message, assistant_response, metadata=metadata)
            except Exception:
                logger.exception("Memory sync error [%s]", provider.name)

    def resolved_preferences(self, query: str) -> dict[str, str]:
        facts: list[MemoryFact] = []
        for provider in self._providers:
            try:
                facts.extend(provider.authoritative_facts())
            except Exception:
                logger.exception("Memory fact error [%s]", provider.name)
        winners = resolve_memory_fact_winners(query, tuple(facts))
        return {
            key.removeprefix("preference:"): fact.value
            for key, fact in winners.items()
            if key.startswith("preference:")
        }

    def on_session_switch(self, new_session_id: str) -> None:
        """세션 전환을 모든 제공자에 전파합니다."""
        for provider in self._providers:
            try:
                provider.on_session_switch(new_session_id)
            except Exception:
                logger.exception("Session switch error [%s]", provider.name)

    def clear(self, scope: str = "all") -> dict[str, int]:
        normalized_scope = normalize_memory_scope(scope)
        return {provider.name: provider.clear(normalized_scope) for provider in self._providers}

    def export(self, scope: str = "all") -> dict[str, object]:
        normalized_scope = normalize_memory_scope(scope)
        from datetime import UTC, datetime

        from antigravity_k.engine.secret_scanner import redact_full

        def redact_value(value: JsonValue) -> JsonValue:
            if isinstance(value, str):
                return redact_full(value)
            if isinstance(value, dict):
                return {key: redact_value(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact_value(item) for item in value]
            return value

        return {
            "scope": normalized_scope,
            "exported_at": datetime.now(UTC).isoformat(),
            "providers": {
                provider.name: redact_value(cast(JsonValue, provider.export(normalized_scope)))
                for provider in self._providers
            },
        }

    def redact(self, scope: str = "all") -> dict[str, int]:
        normalized_scope = normalize_memory_scope(scope)
        return {provider.name: provider.redact(normalized_scope) for provider in self._providers}

    def apply_retention(self, max_age_days: int) -> dict[str, int]:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        return {provider.name: provider.apply_retention(max_age_days) for provider in self._providers}

    def ranked_facts(self, top_k: int = 20) -> list[tuple[MemoryFact, float]]:
        """전체 제공자의 권위 사실을 중요도 점수 내림차순으로 반환합니다."""
        facts: list[MemoryFact] = []
        for provider in self._providers:
            try:
                facts.extend(provider.authoritative_facts())
            except Exception:
                logger.exception("Memory fact error [%s]", provider.name)
        return rank_facts(facts, top_k=top_k)

    def delete_entry(self, provider_name: str, key: str) -> bool:
        """특정 제공자의 개별 메모리 항목을 삭제합니다.

        제공자가 delete_entry를 지원하지 않거나 항목이 없으면 False를 반환합니다.
        """
        for provider in self._providers:
            if provider.name != provider_name:
                continue
            deleter = getattr(provider, "delete_entry", None)
            if deleter is None:
                return False
            delete_fn = cast(Callable[[str], object], deleter)
            return bool(delete_fn(key))
        return False

    def get_all_tool_schemas(self) -> list[dict[str, JsonValue]]:
        """모든 제공자의 도구 스키마를 수집합니다."""
        schemas: list[dict[str, JsonValue]] = []
        for provider in self._providers:
            try:
                schemas.extend(provider.get_tool_schemas())
            except Exception:
                logger.exception("Tool schema error [%s]", provider.name)
        return schemas

    def get_stats(self) -> dict[str, JsonValue]:
        """메모리 시스템 통계를 반환합니다."""
        return {
            "total_providers": len(self._providers),
            "external_providers": self._external_count,
            "provider_names": [p.name for p in self._providers],
        }


# ── 에피소딕 메모리 제공자 (4-Tier Cognitive Memory Layer 2) ──


class EpisodicMemoryProvider(MemoryProvider):
    """과거 이벤트/대화를 시간순으로 저장하고 회상하는 에피소딕 메모리.

    인간의 일화적 기억(Episodic Memory)을 모델링합니다.
    - 시간순 이벤트 시퀀스 저장
    - 키워드 기반 관련 에피소드 회상
    - 오래된 기억 자동 감쇠(decay) + 요약 통합(consolidation)

    사용법:
        episodic = EpisodicMemoryProvider(max_episodes=200)
        manager.add_provider(episodic)
    """

    def __init__(self, max_episodes: int = 200, decay_threshold: float = 0.3, persist_dir: str | None = None):
        """Initialize the EpisodicMemoryProvider.

        Args:
            max_episodes (int): int max episodes.
            decay_threshold (float): float decay threshold.
            persist_dir: 디스크 영속화 디렉토리 (작업 3). None이면 ~/.antigravity-k/memory.

        """
        import os

        self._episodes: list[_Episode] = []
        self._max_episodes: int = max_episodes
        self._decay_threshold: float = decay_threshold
        self._access_counts: dict[int, int] = {}  # episode_id → access count
        # 작업 3: 디스크 영속화 — 재시작 후에도 에피소드 유지
        self._persist_dir: str = persist_dir or os.path.join(os.path.expanduser("~"), ".antigravity-k", "memory")
        self._persist_path: str = os.path.join(self._persist_dir, "episodes.json")
        os.makedirs(self._persist_dir, exist_ok=True)
        self._load()

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "episodic"

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        """쿼리와 관련된 과거 에피소드를 회상합니다."""
        if not self._episodes:
            return ""

        query_lower = query.lower()
        scored: list[tuple[float, int, _Episode]] = []

        for i, ep in enumerate(self._episodes):
            score = 0.0
            content = (ep.get("user", "") + " " + ep.get("assistant", "")).lower()

            # 키워드 매칭 점수 (한국어 조사 변형을 흡수한 어간 매칭 포함)
            content_stems = _ko_stems(content)
            query_words = query_lower.split()
            for word in query_words:
                if len(word) > 1 and word in content:
                    score += 1.0
            for stem in _ko_stems(query_lower):
                if stem in content_stems:
                    score += 1.0
                elif stem in content:
                    score += 0.5

            # 시간 감쇠 (최근 에피소드일수록 높은 점수)
            recency = (i + 1) / len(self._episodes)  # 0~1, 최근이 1에 가까움
            score *= 0.5 + 0.5 * recency

            # 접근 빈도 부스트 (자주 회상된 기억은 강화)
            access = self._access_counts.get(i, 0)
            score *= 1.0 + 0.1 * min(access, 5)

            if score > 0:
                scored.append((score, i, ep))

        if not scored:
            return ""

        # 상위 5개 에피소드 반환
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:5]

        # 접근 카운트 증가
        for _, idx, _ in top:
            self._access_counts[idx] = self._access_counts.get(idx, 0) + 1

        lines = ["[Episodic Memory — 관련 과거 경험]"]
        for score, _, ep in top:
            ts = ep.get("timestamp", "")[:16]
            user_summary = ep["user"][:80] + "..." if len(ep.get("user", "")) > 80 else ep.get("user", "")
            asst_summary = (
                ep["assistant"][:120] + "..." if len(ep.get("assistant", "")) > 120 else ep.get("assistant", "")
            )
            lines.append(f"  [{ts}] Q: {user_summary}")
            lines.append(f"           A: {asst_summary}")

        return "\n".join(lines)

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        """대화 턴을 에피소드로 저장합니다."""
        from datetime import datetime as _dt

        episode: _Episode = {
            "user": user_message,
            "assistant": assistant_response,
            "timestamp": _dt.now().isoformat(),
            "metadata": metadata or {},
        }
        self._episodes.append(episode)

        # 용량 초과 시 오래된 저관련 에피소드 감쇠
        if len(self._episodes) > self._max_episodes:
            self._consolidate()
        else:
            self._save()  # 작업 3: 디스크 영속화

    @override
    def clear(self, scope: MemoryScope = "all") -> int:
        scope = normalize_memory_scope(scope)
        if scope not in ("session", "all"):
            return 0
        deleted = len(self._episodes)
        self._episodes.clear()
        self._access_counts.clear()
        self._save()
        return deleted

    def delete_entry(self, key: str) -> bool:
        """개별 에피소드를 삭제합니다 (키 형식: episode:<인덱스>)."""
        if not key.startswith("episode:"):
            return False
        try:
            idx = int(key.partition(":")[2])
        except ValueError:
            return False
        if idx < 0 or idx >= len(self._episodes):
            return False
        _ = self._episodes.pop(idx)
        _ = self._access_counts.pop(idx, None)
        # pop 이후 인덱스가 앞당겨진 항목들의 접근 횟수 보정
        self._access_counts = {i - 1 if i > idx else i: count for i, count in self._access_counts.items()}
        self._save()
        return True

    @override
    def export(self, scope: MemoryScope = "all") -> list[dict[str, JsonValue]]:
        scope = normalize_memory_scope(scope)
        if scope not in ("session", "all"):
            return []
        return cast(list[dict[str, JsonValue]], [dict(episode) for episode in self._episodes])

    @override
    def redact(self, scope: MemoryScope = "all") -> int:
        scope = normalize_memory_scope(scope)
        if scope not in ("session", "all"):
            return 0
        from antigravity_k.engine.secret_scanner import redact_full

        changed = 0

        def redact_value(value: JsonValue) -> JsonValue:
            nonlocal changed
            if isinstance(value, str):
                redacted = redact_full(value)
                changed += int(redacted != value)
                return redacted
            if isinstance(value, dict):
                return {key: redact_value(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact_value(item) for item in value]
            return value

        redacted = redact_value(cast(JsonValue, self._episodes))
        if isinstance(redacted, list):
            self._episodes = [episode for item in redacted if (episode := _coerce_episode(item)) is not None]
        self._save()
        return changed

    @override
    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        kept: list[_Episode] = []
        deleted = 0
        for episode in self._episodes:
            try:
                timestamp = datetime.fromisoformat(str(episode.get("timestamp", "")))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                kept.append(episode)
                continue
            if timestamp < cutoff:
                deleted += 1
            else:
                kept.append(episode)
        self._episodes = kept
        if deleted:
            self._save()
        return deleted

    def _consolidate(self):
        """메모리 통합: 오래되고 접근 빈도 낮은 에피소드 제거."""
        if len(self._episodes) <= self._max_episodes:
            return

        # 접근 빈도가 낮은 오래된 에피소드부터 제거
        scored_indices: list[tuple[float, int]] = []
        for i in range(len(self._episodes)):
            access = self._access_counts.get(i, 0)
            recency = (i + 1) / len(self._episodes)
            importance = access * 0.5 + recency * 0.5
            # durable-fact episodes carry knowledge that should not decay with recency
            # alone, so boost them above the eviction floor.
            ep = self._episodes[i]
            if _is_durable_fact_statement(ep.get("user", "")) or _is_durable_fact_statement(ep.get("assistant", "")):
                importance += 10.0
            scored_indices.append((importance, i))

        scored_indices.sort(key=lambda x: x[0])

        # 하위 20% 제거
        remove_count = len(self._episodes) - self._max_episodes + int(self._max_episodes * 0.1)
        remove_indices: set[int] = {idx for _, idx in scored_indices[:remove_count]}

        self._episodes = [ep for i, ep in enumerate(self._episodes) if i not in remove_indices]
        # 접근 카운트 재인덱싱
        new_counts: dict[int, int] = {}
        new_idx = 0
        for i in range(len(self._episodes) + remove_count):
            if i not in remove_indices:
                if i in self._access_counts:
                    new_counts[new_idx] = self._access_counts[i]
                new_idx += 1
        self._access_counts = new_counts

        logger.info(
            "[EpisodicMemory] Consolidation: %s개 에피소드 감쇠, 남은: %s",
            remove_count,
            len(self._episodes),
        )
        self._save()

    def _load(self):
        """디스크에서 에피소드를 로드합니다 (작업 3)."""
        import json
        import os

        if not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, encoding="utf-8") as f:
                data = cast(object, json.load(f))
                if isinstance(data, list):
                    items = cast(list[object], data)
                    self._episodes = [
                        episode
                        for item in items[-self._max_episodes :]
                        if (episode := _coerce_episode(item)) is not None
                    ]
                    logger.info("[EpisodicMemory] 디스크에서 %s개 에피소드 로드", len(self._episodes))
        except Exception:
            logger.warning("[EpisodicMemory] 로드 실패 (non-critical)", exc_info=True)

    def _save(self) -> None:
        """에피소드를 디스크에 저장합니다 (작업 3)."""
        import json

        try:
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(self._episodes, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("[EpisodicMemory] 저장 실패 (non-critical)", exc_info=True)

    def get_stats(self) -> dict[str, JsonValue]:
        """Retrieve stats.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "total_episodes": len(self._episodes),
            "max_episodes": self._max_episodes,
            "most_accessed": [
                list(item) for item in sorted(self._access_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            ],
        }


# ── 워킹 메모리 버퍼 (4-Tier Cognitive Memory Layer 1) ──


class WorkingMemoryBuffer(MemoryProvider):
    """슬라이딩 윈도우 기반 워킹 메모리.

    현재 세션의 최근 대화를 제한된 크기로 유지합니다.
    컨텍스트 윈도우 관리를 지능적으로 수행합니다.

    - 최근 N턴 유지 (FIFO)
    - 중요 턴은 고정(pin) 가능
    - 세션별 독립 관리
    """

    def __init__(self, max_turns: int = 20):
        """Initialize the WorkingMemoryBuffer.

        Args:
            max_turns (int): int max turns.

        """
        self._turns: list[dict[str, str]] = []
        self._pinned: set[int] = set()  # 고정된 턴 인덱스
        self._max_turns: int = max_turns

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return "working_memory"

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        """워킹 메모리에서 최근 컨텍스트를 반환합니다."""
        if not self._turns:
            return ""

        lines = ["[Working Memory — 최근 대화 컨텍스트]"]
        start_index = max(len(self._turns) - 10, 0)
        for i, turn in enumerate(self._turns[start_index:], start=start_index):
            prefix = "📌 " if i in self._pinned else ""
            lines.append(f"  {prefix}{turn['role']}: {turn['content'][:100]}")

        return "\n".join(lines)

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        """턴을 워킹 메모리에 추가합니다."""
        self._turns.append({"role": "user", "content": user_message})
        self._turns.append({"role": "assistant", "content": assistant_response})

        # 윈도우 초과 시 오래된 비고정 턴 제거
        while len(self._turns) > self._max_turns * 2:
            # 고정되지 않은 가장 오래된 턴 제거
            for i in range(len(self._turns)):
                if i not in self._pinned:
                    self._remove_turn(i)
                    break
            else:
                # 모두 고정이면 가장 오래된 것 강제 제거
                self._remove_turn(0)

    def _remove_turn(self, turn_index: int) -> None:
        _ = self._turns.pop(turn_index)
        self._pinned = {index - 1 if index > turn_index else index for index in self._pinned if index != turn_index}

    def pin_turn(self, turn_index: int):
        """특정 턴을 고정하여 감쇠되지 않도록 합니다."""
        self._pinned.add(turn_index)

    def get_recent(self, n: int = 5) -> list[dict[str, str]]:
        """최근 N개 턴을 반환합니다."""
        return self._turns[-n * 2 :]

    @override
    def clear(self, scope: MemoryScope = "working") -> int:
        scope = normalize_memory_scope(scope)
        if scope not in ("working", "all"):
            return 0
        deleted = len(self._turns)
        self._turns.clear()
        self._pinned.clear()
        return deleted

    @override
    def export(self, scope: MemoryScope = "working") -> list[dict[str, JsonValue]]:
        scope = normalize_memory_scope(scope)
        if scope not in ("working", "all"):
            return []
        return cast(list[dict[str, JsonValue]], [dict(turn) for turn in self._turns])

    @override
    def redact(self, scope: MemoryScope = "working") -> int:
        scope = normalize_memory_scope(scope)
        if scope not in ("working", "all"):
            return 0
        from antigravity_k.engine.secret_scanner import redact_full

        changed = 0
        for turn in self._turns:
            content = turn.get("content", "")
            redacted = redact_full(content)
            changed += int(redacted != content)
            turn["content"] = redacted
        return changed


from antigravity_k.engine.global_memory_provider import (
    GlobalMemoryProvider as GlobalMemoryProvider,
)
from antigravity_k.engine.global_memory_provider import (
    extract_identity_facts as extract_identity_facts,
)
