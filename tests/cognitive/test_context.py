"""T03 — Context reconstruction 시험."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.context import (
    ContextBuilder,
    ContextBuildError,
    ContextBuildResult,
    ContextFailureReason,
    ContextPrincipal,
    HandleResolutionStatus,
    estimate_tokens,
)
from antigravity_k.engine.cognitive.models import (
    ContextBudget,
    ContextHandleRef,
    DisclosureLevel,
    ProjectionState,
    to_wire,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest
from tests.cognitive._fixtures import (
    build_constitution_rule,
    build_evidence,
    build_experience,
    build_goal,
    build_material_unknown,
    build_open_decision,
    build_project,
)

NOW = datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC)


def populated_store(project: str, *, tmp_path: Path) -> tuple[CanonicalStore, dict[str, str]]:
    store = CanonicalStore(tmp_path / "canonical", git_enabled=False)
    rule = build_constitution_rule(project)
    goal = build_goal(project)
    evidence = build_evidence(project)
    decision = build_open_decision(project)
    unknown = build_material_unknown(project)
    experience = build_experience(project)
    project_record = build_project(project, protected_constraints=(rule.id,))
    store.commit_records([project_record, rule, goal, evidence, decision, unknown, experience])
    return store, {
        "project": project_record.id,
        "rule": rule.id,
        "goal": goal.id,
        "evidence": evidence.id,
        "decision": decision.id,
        "unknown": unknown.id,
        "experience": experience.id,
    }


def build_context(
    store: CanonicalStore,
    project: str,
    ids: dict[str, str],
    *,
    budget: int = 100_000,
    principal: ContextPrincipal | None = None,
    state_revision: int = 7,
) -> ContextBuildResult:
    builder = ContextBuilder(store, clock=lambda: NOW)
    return builder.build(
        goal_id=ids["goal"],
        state_revision=state_revision,
        principal=principal or ContextPrincipal(subject="human:mr.k", project_id=project),
        budget=ContextBudget(token_budget=budget, tokens_used=0, l0_reserved_tokens=0),
    )


def test_l0_protected_constraints_are_always_present(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)

    result = build_context(store, project, ids)

    assert [item.record_id for item in result.payload.l0_constraints] == [ids["rule"]]
    assert result.payload.l0_constraints[0].disclosure_level is DisclosureLevel.L0_SIGNAL
    assert result.l0_tokens > 0
    assert result.payload.integrity.value == "COMPLETE"


def test_l0_over_budget_fails_loudly(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)

    with pytest.raises(ContextBuildError) as excinfo:
        build_context(store, project, ids, budget=1)

    assert excinfo.value.reason is ContextFailureReason.L0_OVER_BUDGET


def test_all_layers_carry_selection_reasons_and_token_counts(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)

    result = build_context(store, project, ids, state_revision=7)

    assert result.payload.state_revision == 7
    assert {item.record_id for item in result.payload.l1_state} >= {ids["goal"], ids["decision"], ids["unknown"]}
    assert [item.record_id for item in result.payload.l2_history] == [ids["experience"]]
    assert ids["evidence"] in {item.record_id for item in result.payload.l3_evidence}
    for item in (*result.payload.l0_constraints, *result.payload.l1_state, *result.payload.l2_history):
        assert item.reason_selected
        assert item.token_estimate > 0
    assert result.payload.budget.tokens_used == result.tokens_used
    assert result.payload.budget.l0_reserved_tokens == result.l0_tokens


def test_budget_overflow_is_explicit_with_handle(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)

    result = build_context(store, project, ids, budget=result_l0_budget(store, project, ids) + 5)

    excluded = {item.record_id for item in result.payload.exclusions}
    assert excluded, "예산 초과 항목은 제외로 기록되어야 한다"
    assert any(item.reason_excluded.startswith("BUDGET") for item in result.payload.exclusions)
    assert {handle.record_id for handle in result.payload.handles}, "제외 항목은 handle로 다시 요청 가능해야 한다"
    assert result.payload.budget.tokens_used <= result.payload.budget.token_budget


def result_l0_budget(store: CanonicalStore, project: str, ids: dict[str, str]) -> int:
    builder = ContextBuilder(store, clock=lambda: NOW)
    result = builder.build(
        goal_id=ids["goal"],
        state_revision=1,
        principal=ContextPrincipal(subject="human:mr.k", project_id=project),
        budget=ContextBudget(token_budget=100_000, tokens_used=0, l0_reserved_tokens=0),
    )
    return result.l0_tokens


def test_missing_required_id_reports_incomplete(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)
    absent_goal_id = new_id(EntityType.GOAL)

    result = build_context(store, project, {"goal": absent_goal_id}, budget=1_000)

    assert result.payload.integrity.value == "INCOMPLETE"
    assert absent_goal_id in result.payload.missing_ids
    assert absent_goal_id not in {item.record_id for item in result.payload.l1_state}


def test_project_record_missing_blocks_context(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)

    with pytest.raises(ContextBuildError) as excinfo:
        build_context(store, new_id(EntityType.PROJECT), ids)

    assert excinfo.value.reason is ContextFailureReason.PROJECT_NOT_FOUND
    assert excinfo.value.missing_ids


def test_other_project_records_are_never_injected(tmp_path: Path) -> None:
    project_a = new_id(EntityType.PROJECT)
    project_b = new_id(EntityType.PROJECT)
    store, ids = populated_store(project_a, tmp_path=tmp_path)
    foreign = build_evidence(project_b, claim="다른 project 증거")
    store.commit_records([foreign])

    result = build_context(store, project_a, ids)

    injected = {
        item.record_id
        for item in (
            *result.payload.l0_constraints,
            *result.payload.l1_state,
            *result.payload.l2_history,
            *result.payload.l3_evidence,
        )
    }
    assert foreign.id not in injected
    assert foreign.id not in {handle.record_id for handle in result.payload.handles}


def test_owner_scope_filter_records_exclusion(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)
    principal = ContextPrincipal(subject="human:mr.k", project_id=project, allowed_owner_scopes=frozenset({"human"}))

    result = build_context(store, project, ids, principal=principal)

    excluded = {item.record_id for item in result.payload.exclusions}
    assert ids["goal"] not in {item.record_id for item in result.payload.l1_state}
    assert ids["goal"] in excluded


def test_handle_resolution_checks_permission_expiry_and_digest(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    other_project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)
    builder = ContextBuilder(store, clock=lambda: NOW)
    principal = ContextPrincipal(subject="human:mr.k", project_id=project)
    result = builder.build(
        goal_id=ids["goal"],
        state_revision=1,
        principal=principal,
        budget=ContextBudget(
            token_budget=result_l0_budget(store, project, ids) + 5, tokens_used=0, l0_reserved_tokens=0
        ),
    )
    handle = next(handle for handle in result.payload.handles if handle.record_id == ids["goal"])

    assert builder.resolve_handle(handle, principal).status is HandleResolutionStatus.OK
    assert builder.resolve_handle(handle, principal, max_bytes=1).status is HandleResolutionStatus.TOO_LARGE

    expired = handle.model_copy(update={"expires_at": NOW - timedelta(minutes=1)})
    assert builder.resolve_handle(expired, principal).status is HandleResolutionStatus.EXPIRED

    wrong_digest = handle.model_copy(update={"content_digest": "sha256:" + "f" * 64})
    assert builder.resolve_handle(wrong_digest, principal).status is HandleResolutionStatus.DIGEST_MISMATCH

    foreign_principal = ContextPrincipal(subject="human:other", project_id=other_project)
    assert builder.resolve_handle(handle, foreign_principal).status is HandleResolutionStatus.FORBIDDEN

    low_disclosure = ContextPrincipal(
        subject="human:mr.k", project_id=project, max_disclosure=DisclosureLevel.L0_SIGNAL
    )
    assert builder.resolve_handle(handle, low_disclosure).status is HandleResolutionStatus.FORBIDDEN

    missing = handle.model_copy(update={"record_id": new_id(EntityType.GOAL)})
    assert builder.resolve_handle(missing, principal).status is HandleResolutionStatus.DELETED


def test_projection_staleness_triggers_replay(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)
    builder = ContextBuilder(store, clock=lambda: NOW)

    projection = builder.projection_state()
    refreshed, changed = builder.refresh_projection(projection)
    assert refreshed == projection
    assert changed is False

    store.commit_records([build_evidence(project, claim="새 증거")])
    refreshed, changed = builder.refresh_projection(projection)

    assert changed is True
    assert refreshed.last_event_sequence > projection.last_event_sequence
    assert store.index_path.exists()


def test_handle_digest_matches_record_canonical_digest(tmp_path: Path) -> None:
    project = new_id(EntityType.PROJECT)
    store, ids = populated_store(project, tmp_path=tmp_path)
    builder = ContextBuilder(store, clock=lambda: NOW)
    record = store.read(ids["experience"])
    assert record is not None

    handle = ContextHandleRef(
        handle_id="H-check",
        project_id=project,
        owner_scope="project",
        record_id=record.id,
        content_digest=canonical_digest(to_wire(record)),
        disclosure_level=DisclosureLevel.L2_DETAIL,
    )
    resolution = builder.resolve_handle(handle, ContextPrincipal(subject="human:mr.k", project_id=project))
    assert resolution.status is HandleResolutionStatus.OK
    assert resolution.record is not None


def test_estimate_tokens_is_deterministic() -> None:
    assert estimate_tokens("abc") == estimate_tokens("abc")
    assert estimate_tokens("a" * 100) > estimate_tokens("a" * 10)


def test_projection_state_model_roundtrip() -> None:
    state = ProjectionState(projection_version="1", last_event_sequence=3)
    assert state.last_event_sequence == 3
