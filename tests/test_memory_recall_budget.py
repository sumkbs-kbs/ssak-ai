import os
from pathlib import Path
from tempfile import mkdtemp
from typing import override

_TEST_HOME = Path(mkdtemp(prefix="ssak-memory-recall-home-"))
os.environ["HOME"] = str(_TEST_HOME)

from antigravity_k.engine.memory_conflicts import MemoryRecallFragment
from antigravity_k.engine.memory_contracts import JsonValue, MemoryFact, MemoryFactAuthority, MemoryProvider
from antigravity_k.engine.memory_provider import EpisodicMemoryProvider, MemoryManager
from antigravity_k.engine.memory_recall_budget import (
    DEFAULT_MEMORY_RECALL_MAX_CHARACTERS,
    MemoryRecallBudget,
    compose_bounded_recall,
)
from antigravity_k.engine.project_memory import ProjectMemoryProvider


class _StaticMemoryProvider(MemoryProvider):
    def __init__(self, provider_name: str, content: str, facts: tuple[MemoryFact, ...] = ()) -> None:
        self._provider_name = provider_name
        self._content = content
        self._facts = facts

    @property
    @override
    def name(self) -> str:
        return self._provider_name

    @override
    def prefetch(self, query: str, session_id: str | None = None) -> str:
        _ = query, session_id
        return self._content

    @override
    def sync_turn(
        self,
        user_message: str,
        assistant_response: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        _ = user_message, assistant_response, metadata

    @override
    def authoritative_facts(self) -> tuple[MemoryFact, ...]:
        return self._facts


def test_bounded_recall_deduplicates_exact_cross_provider_fragments() -> None:
    # Given: two providers recall the same complete fragment.
    fragments = (
        MemoryRecallFragment(provider="episodic", content="shared recall"),
        MemoryRecallFragment(provider="global", content="shared recall"),
    )

    # When: the combined recall is composed within its budget.
    recalled = compose_bounded_recall("shared", (), fragments, MemoryRecallBudget(max_characters=100))

    # Then: the first provider's whole fragment is retained once.
    assert recalled.context == "shared recall"


def test_bounded_recall_skips_oversized_fragment_and_backfills_later_fragment() -> None:
    # Given: the first relevant fragment cannot fit but a later one can.
    fragments = (
        MemoryRecallFragment(provider="episodic", content="x" * 80),
        MemoryRecallFragment(provider="project", content="smaller retained recall"),
    )

    # When: the composer walks fragments in provider order.
    recalled = compose_bounded_recall("recall", (), fragments, MemoryRecallBudget(max_characters=30))

    # Then: it skips the oversized unit and backfills the smaller complete fragment.
    assert recalled.context == "smaller retained recall"
    assert len(recalled.context) <= 30


def test_bounded_recall_respects_zero_and_positive_character_budgets() -> None:
    # Given: one complete optional fragment.
    fragments = (MemoryRecallFragment(provider="episodic", content="small recall"),)

    # When: the same fragment is composed under two explicit limits.
    empty = compose_bounded_recall("recall", (), fragments, MemoryRecallBudget(max_characters=0))
    kept = compose_bounded_recall("recall", (), fragments, MemoryRecallBudget(max_characters=12))

    # Then: zero omits optional recall and an exact positive budget preserves it whole.
    assert empty.context == ""
    assert kept.context == "small recall"


def test_bounded_recall_omits_conflict_prefix_that_exceeds_positive_budget() -> None:
    # Given: authoritative facts conflict while the only optional fragment is too large.
    facts = (
        MemoryFact(
            key="identity:name",
            value="old-name",
            source="global",
            scope="global",
            authority=MemoryFactAuthority.DURABLE_IDENTITY,
            observed_at=1.0,
        ),
        MemoryFact(
            key="identity:name",
            value="new-name",
            source="current_user",
            scope="session",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=2.0,
        ),
    )
    fragments = (MemoryRecallFragment(provider="episodic", content="x" * 80),)

    # When: a positive but too-small budget composes the recall.
    recalled = compose_bounded_recall("", facts, fragments, MemoryRecallBudget(max_characters=1))

    # Then: no partial resolution header or fact escapes the strict serialized budget.
    assert recalled.context == ""


def test_bounded_recall_preserves_complete_conflict_winner_when_prefix_fits() -> None:
    # Given: current-user identity evidence outranks an older durable value.
    facts = (
        MemoryFact(
            key="identity:name",
            value="old-name",
            source="global",
            scope="global",
            authority=MemoryFactAuthority.DURABLE_IDENTITY,
            observed_at=1.0,
        ),
        MemoryFact(
            key="identity:name",
            value="new-name",
            source="current_user",
            scope="session",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=2.0,
        ),
    )

    # When: no provider fragment is needed and the complete prefix fits.
    recalled = compose_bounded_recall("", facts, (), MemoryRecallBudget(max_characters=500))

    # Then: the whole winner and its provenance remain available.
    assert "[resolved:identity:name source=current_user scope=session] new-name" in recalled.context
    assert "old-name" not in recalled.context
    assert len(recalled.context) <= 500


def test_bounded_recall_zero_budget_omits_conflict_prefix_without_fragments() -> None:
    # Given: conflicting authoritative facts exist without optional provider fragments.
    facts = (
        MemoryFact(
            key="identity:name",
            value="old-name",
            source="global",
            scope="global",
            authority=MemoryFactAuthority.DURABLE_IDENTITY,
            observed_at=1.0,
        ),
        MemoryFact(
            key="identity:name",
            value="new-name",
            source="current_user",
            scope="session",
            authority=MemoryFactAuthority.CURRENT_USER,
            observed_at=2.0,
        ),
    )

    # When: the strict budget is explicitly zero.
    recalled = compose_bounded_recall("", facts, (), MemoryRecallBudget(max_characters=0))

    # Then: no memory context is serialized.
    assert recalled.context == ""


def test_manager_deduplicates_real_episodic_recall_against_another_provider(tmp_path: Path) -> None:
    # Given: a real persisted episodic result is also returned by a second provider.
    episodic = EpisodicMemoryProvider(persist_dir=str(tmp_path / "episodic"))
    episodic.sync_turn("shared memory topic", "shared recall answer")
    duplicate = episodic.prefetch("shared")
    manager = MemoryManager(recall_budget=MemoryRecallBudget(max_characters=1_000))
    manager.add_provider(episodic)
    manager.add_provider(_StaticMemoryProvider("duplicate", duplicate))

    # When: the manager collects memories from both providers.
    recalled = manager.prefetch_all("shared")

    # Then: the episodic record structure remains complete and appears once.
    assert recalled.count("[Episodic Memory") == 1
    assert "shared recall answer" in recalled


def test_default_manager_deduplicates_and_backfills_after_oversized_fragment() -> None:
    # Given: the default manager sees an oversized fragment, duplicate fragments, and a later small one.
    manager = MemoryManager()
    manager.add_provider(_StaticMemoryProvider("oversized", "x" * (DEFAULT_MEMORY_RECALL_MAX_CHARACTERS + 1)))
    manager.add_provider(_StaticMemoryProvider("first-duplicate", "duplicate recall"))
    manager.add_provider(_StaticMemoryProvider("second-duplicate", "duplicate recall"))
    manager.add_provider(_StaticMemoryProvider("later-small", "backfilled recall"))

    # When: callers use the legacy no-argument manager constructor.
    recalled = manager.prefetch_all("recall")

    # Then: the result is bounded, deduplicated, and retains the later fitting fragment.
    assert len(recalled) <= DEFAULT_MEMORY_RECALL_MAX_CHARACTERS
    assert recalled.count("duplicate recall") == 1
    assert "backfilled recall" in recalled
    assert "x" * 80 not in recalled


def test_manager_budget_keeps_current_project_fact_winner_without_orphaned_headers(tmp_path: Path) -> None:
    # Given: a large optional fragment precedes an older persisted project decision.
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = ProjectMemoryProvider(project_root)
    project.sync_turn("프로젝트 결정: frontend=react", "stored")
    manager = MemoryManager(
        project_root=str(project_root),
        recall_budget=MemoryRecallBudget(max_characters=500),
    )
    manager.add_provider(_StaticMemoryProvider("oversized", "x" * 600))
    manager.add_provider(project)

    # When: the current request corrects the same project fact before turn sync.
    recalled = manager.prefetch_all("프로젝트 결정: ui_framework=svelte")

    # Then: the oversized optional fragment is absent while the authoritative winner remains intact.
    assert len(recalled) <= 500
    assert "[resolved:project:decision:frontend source=current_user scope=project] svelte" in recalled
    assert "react" not in recalled
    assert "[Project Memory]" not in recalled
