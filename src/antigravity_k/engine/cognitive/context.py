"""Context reconstruction (P04) — L0~L3 ContextBuilder와 handle 권한.

계약(CONTEXT_AND_MEMORY.md):
- L0 protected constraints는 압축·예산으로 잃을 수 없다. 초과하면 조용히 버리지 않고 명시적으로 실패한다.
- 필수 필드가 없으면 빈 context로 성공하지 않는다. ``CONTEXT_INCOMPLETE``와 누락 ID를 남긴다.
- 검색은 넓게 하되 주입은 좁게. 다른 project/owner 자료는 주입하지 않는다.
- 선택/제외 이유와 token 수를 항목마다 기록한다.
- handle은 capability token이 아니다. 조회 시 현재 권한·digest·만료를 다시 확인한다.
- ``(projection_version, last_event_sequence)``로 stale projection을 표시하고 canonical replay로 복원한다.

이 모듈은 provider/UI를 import하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final, final

from antigravity_k.engine.cognitive.models import (
    ApplicabilityLevel,
    ContextBudget,
    ContextExclusion,
    ContextHandleRef,
    ContextItem,
    ContextPackagePayload,
    DisclosureLevel,
    IntegrityStatus,
    Producer,
    ProducerKind,
    ProjectionState,
    Record,
    same_enum,
    to_wire,
)
from antigravity_k.engine.cognitive.references import EntityType
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest

#: 대략적인 token 추정. 정확한 tokenizer 없이도 예산 초과를 조용히 넘기지 않기 위한 결정적 추정이다.
TOKENS_PER_CHAR: Final[float] = 0.25
DEFAULT_HANDLE_TTL: Final[timedelta] = timedelta(hours=1)
PROJECTION_VERSION: Final[str] = "1"

#: L0/L1/L2/L3 각 항목의 기본 상한. task별 조정 가능한 예산이며 헌법이 아니다.
DEFAULT_L1_LIMIT: Final[int] = 6
DEFAULT_L2_LIMIT: Final[int] = 4
DEFAULT_L3_LIMIT: Final[int] = 6

_L1_STATE_ORDER: Final[tuple[EntityType, ...]] = (
    EntityType.GOAL,
    EntityType.DECISION,
    EntityType.UNKNOWN,
    EntityType.BRAIN_JUDGMENT,
)
_L2_HISTORY_TYPES: Final[tuple[EntityType, ...]] = (
    EntityType.EXPERIENCE,
    EntityType.PATTERN,
    EntityType.STRATEGY,
    EntityType.PRINCIPLE,
)


class ContextFailureReason(StrEnum):
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"
    L0_OVER_BUDGET = "L0_OVER_BUDGET"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    STALE_PROJECTION = "STALE_PROJECTION"


class ContextBuildError(ValueError):
    def __init__(self, reason: ContextFailureReason, detail: str, missing_ids: Sequence[str] = ()) -> None:
        self.reason = reason
        self.missing_ids = tuple(missing_ids)
        super().__init__(f"{reason}: {detail}")


class HandleResolutionStatus(StrEnum):
    OK = "OK"
    EXPIRED = "EXPIRED"
    NOT_FOUND = "NOT_FOUND"
    DELETED = "DELETED"
    FORBIDDEN = "FORBIDDEN"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    TOO_LARGE = "TOO_LARGE"


@dataclass(frozen=True, slots=True)
class ContextPrincipal:
    """context를 요청한 주체. handle 조회 권한도 이 주체로 다시 검사한다."""

    subject: str
    project_id: str
    allowed_owner_scopes: frozenset[str] = frozenset({"project"})
    max_disclosure: DisclosureLevel = DisclosureLevel.L2_DETAIL


@dataclass(frozen=True, slots=True)
class HandleResolution:
    status: HandleResolutionStatus
    handle_id: str
    record: Record | None = None
    content: str | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ContextBuildResult:
    payload: ContextPackagePayload
    record: Record
    l0_tokens: int
    l1_tokens: int
    l2_tokens: int
    l3_tokens: int
    projected: ProjectionState

    @property
    def tokens_used(self) -> int:
        return self.l0_tokens + self.l1_tokens + self.l2_tokens + self.l3_tokens


def estimate_tokens(text: str) -> int:
    """문자 수 기반 결정적 추정. 구현 세부는 v1 계약이며 정확도 주장이 아니다."""

    return max(1, int(len(text) * TOKENS_PER_CHAR + 0.999))


def _record_text(record: Record) -> str:
    return str(to_wire(record))


@final
class ContextBuilder:
    """canonical store에서 최소 충분 context를 재구성한다."""

    def __init__(
        self,
        store: CanonicalStore,
        *,
        clock: Callable[[], datetime] | None = None,
        handle_ttl: timedelta = DEFAULT_HANDLE_TTL,
    ) -> None:
        self.store = store
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self.handle_ttl = handle_ttl

    # ── projection ──────────────────────────────────────
    def projection_state(self) -> ProjectionState:
        return ProjectionState(
            projection_version=PROJECTION_VERSION,
            last_event_sequence=len(self.store.committed_manifests()),
        )

    def refresh_projection(self, previous: ProjectionState) -> tuple[ProjectionState, bool]:
        """stale projection이면 canonical manifest에서 index를 재생성한다(replay)."""

        current = self.projection_state()
        if previous.last_event_sequence == current.last_event_sequence and previous.projection_version == (
            current.projection_version
        ):
            return current, False
        self.store.rebuild_index()
        return current, True

    # ── build ───────────────────────────────────────────
    def build(
        self,
        *,
        goal_id: str,
        state_revision: int,
        principal: ContextPrincipal,
        budget: ContextBudget,
        policy_version: str | None = None,
        brain_capabilities: Sequence[str] = (),
        l1_limit: int = DEFAULT_L1_LIMIT,
        l2_limit: int = DEFAULT_L2_LIMIT,
        l3_limit: int = DEFAULT_L3_LIMIT,
        requested_disclosure: DisclosureLevel = DisclosureLevel.L1_SUMMARY,
    ) -> ContextBuildResult:
        project = self._project_record(principal)
        records = self.store.list_committed(principal.project_id)
        by_type: dict[EntityType, list[Record]] = {}
        for record in records:
            by_type.setdefault(EntityType(str(record.entity_type)), []).append(record)

        exclusions: list[ContextExclusion] = []
        handles: list[ContextHandleRef] = []
        missing: list[str] = []

        l0_items, l0_tokens, l0_missing = self._build_l0(project)
        missing.extend(l0_missing)
        goal_record = self.store.read(goal_id)
        if goal_record is None or goal_record.project_id != principal.project_id:
            # 필수 항목(goal)이 없으면 빈 context로 성공하지 않는다.
            missing.append(goal_id)
        if l0_tokens > budget.token_budget:
            raise ContextBuildError(
                ContextFailureReason.L0_OVER_BUDGET,
                f"L0 protected constraints need {l0_tokens} tokens but budget is {budget.token_budget}",
            )

        remaining = budget.token_budget - l0_tokens
        l1_items, l1_tokens = self._build_layer(
            candidates=self._l1_candidates(by_type, goal_id),
            limit=l1_limit,
            disclosure=requested_disclosure,
            layer_reason="L1 current state",
            remaining=remaining,
            exclusions=exclusions,
            handles=handles,
            principal=principal,
        )
        remaining -= l1_tokens
        l2_items, l2_tokens = self._build_layer(
            candidates=self._l2_candidates(by_type),
            limit=l2_limit,
            disclosure=DisclosureLevel.L1_SUMMARY,
            layer_reason="L2 relevant history",
            remaining=remaining,
            exclusions=exclusions,
            handles=handles,
            principal=principal,
        )
        remaining -= l2_tokens
        l3_items, l3_tokens = self._build_layer(
            candidates=self._l3_candidates(by_type, (*l1_items, *l2_items)),
            limit=l3_limit,
            disclosure=DisclosureLevel.L3_RAW,
            layer_reason="L3 raw evidence",
            remaining=remaining,
            exclusions=exclusions,
            handles=handles,
            principal=principal,
        )

        tokens_used = l0_tokens + l1_tokens + l2_tokens + l3_tokens
        payload = ContextPackagePayload(
            goal_id=goal_id,
            state_revision=state_revision,
            policy_version=policy_version,
            l0_constraints=tuple(l0_items),
            l1_state=tuple(l1_items),
            l2_history=tuple(l2_items),
            l3_evidence=tuple(l3_items),
            handles=tuple(handles),
            budget=ContextBudget(
                token_budget=budget.token_budget,
                tokens_used=tokens_used,
                l0_reserved_tokens=l0_tokens,
            ),
            exclusions=tuple(exclusions),
            integrity=IntegrityStatus.INCOMPLETE if missing else IntegrityStatus.COMPLETE,
            missing_ids=tuple(dict.fromkeys(missing)),
            projection=self.projection_state(),
        )
        record = Record.create(
            entity_type=EntityType.CONTEXT_PACKAGE,
            project_id=principal.project_id,
            producer=Producer(kind=ProducerKind.BODY, actor_id=f"body:context-builder:{principal.subject}"),
            payload=payload,
            created_at=self._clock(),
        )
        return ContextBuildResult(
            payload=payload,
            record=record,
            l0_tokens=l0_tokens,
            l1_tokens=l1_tokens,
            l2_tokens=l2_tokens,
            l3_tokens=l3_tokens,
            projected=payload.projection if payload.projection is not None else self.projection_state(),
        )

    # ── handle ──────────────────────────────────────────
    def resolve_handle(
        self,
        handle: ContextHandleRef,
        principal: ContextPrincipal,
        *,
        max_bytes: int = 8_000,
    ) -> HandleResolution:
        """handle은 권한이 아니다. 매 조회마다 principal·만료·digest를 다시 확인한다."""

        if handle.project_id != principal.project_id:
            return HandleResolution(
                HandleResolutionStatus.FORBIDDEN, handle.handle_id, detail="handle belongs to another project"
            )
        if handle.owner_scope not in principal.allowed_owner_scopes:
            return HandleResolution(
                HandleResolutionStatus.FORBIDDEN,
                handle.handle_id,
                detail=f"owner scope {handle.owner_scope} not granted",
            )
        if handle.expires_at is not None and handle.expires_at <= self._clock():
            return HandleResolution(HandleResolutionStatus.EXPIRED, handle.handle_id, detail="handle expired")
        record = self.store.read(handle.record_id)
        if record is None:
            return HandleResolution(
                HandleResolutionStatus.DELETED, handle.handle_id, detail="record is not committed (not found)"
            )
        if record.project_id != principal.project_id:
            return HandleResolution(
                HandleResolutionStatus.FORBIDDEN, handle.handle_id, detail="record belongs to another project"
            )
        if canonical_digest(to_wire(record)) != handle.content_digest:
            return HandleResolution(
                HandleResolutionStatus.DIGEST_MISMATCH, handle.handle_id, detail="record changed since handle issued"
            )
        content = _record_text(record)
        if len(content.encode("utf-8")) > max_bytes:
            return HandleResolution(
                HandleResolutionStatus.TOO_LARGE,
                handle.handle_id,
                record=record,
                detail=f"content exceeds max_bytes={max_bytes}",
            )
        if _disclosure_rank(handle.disclosure_level) > _disclosure_rank(principal.max_disclosure):
            return HandleResolution(
                HandleResolutionStatus.FORBIDDEN,
                handle.handle_id,
                record=record,
                detail=f"disclosure {handle.disclosure_level} exceeds principal maximum",
            )
        return HandleResolution(HandleResolutionStatus.OK, handle.handle_id, record=record, content=content)

    # ── layer 구성 ──────────────────────────────────────
    def _project_record(self, principal: ContextPrincipal) -> Record:
        project = self.store.read(principal.project_id)
        if project is None or str(project.entity_type) != EntityType.PROJECT:
            raise ContextBuildError(
                ContextFailureReason.PROJECT_NOT_FOUND,
                f"project record is not committed: {principal.project_id}",
                missing_ids=(principal.project_id,),
            )
        return project

    def _build_l0(self, project: Record) -> tuple[list[ContextItem], int, list[str]]:
        protected = getattr(project.payload, "protected_constraints", ())
        items: list[ContextItem] = []
        missing: list[str] = []
        tokens = 0
        for rule_id in protected:
            rule = self.store.read(rule_id)
            if rule is None:
                missing.append(rule_id)
                continue
            token_estimate = estimate_tokens(_record_text(rule))
            tokens += token_estimate
            items.append(
                ContextItem(
                    record_id=rule_id,
                    reason_selected="L0 protected constraint — never dropped",
                    token_estimate=token_estimate,
                    disclosure_level=DisclosureLevel.L0_SIGNAL,
                )
            )
        return items, tokens, missing

    def _l1_candidates(self, by_type: dict[EntityType, list[Record]], goal_id: str) -> list[tuple[Record, str]]:
        candidates: list[tuple[Record, str]] = []
        for entity_type in _L1_STATE_ORDER:
            for record in by_type.get(entity_type, []):
                if same_enum(entity_type, EntityType.GOAL):
                    candidates.append((record, "L1 goal statement"))
                elif same_enum(entity_type, EntityType.DECISION):
                    closure = str(getattr(record.payload, "closure", ""))
                    if closure in ("open", "reopened"):
                        candidates.append((record, "L1 open decision"))
                elif same_enum(entity_type, EntityType.UNKNOWN):
                    materiality = str(getattr(record.payload, "materiality", ""))
                    if materiality in ("MATERIAL", "BLOCKING"):
                        candidates.append((record, "L1 material unknown"))
                elif same_enum(entity_type, EntityType.BRAIN_JUDGMENT):
                    candidates.append((record, "L1 recent judgment"))
        return sorted(candidates, key=lambda item: (not _goal_related(item[0], goal_id), item[0].id))

    def _l2_candidates(self, by_type: dict[EntityType, list[Record]]) -> list[tuple[Record, str]]:
        candidates: list[tuple[Record, str]] = []
        for entity_type in _L2_HISTORY_TYPES:
            for record in by_type.get(entity_type, []):
                lifecycle = str(getattr(record.payload, "lifecycle", ""))
                if lifecycle == "RETIRED":
                    continue
                candidates.append((record, f"L2 {entity_type.value.lower()} (advisory)"))
        return candidates

    def _l3_candidates(
        self, by_type: dict[EntityType, list[Record]], selected: Sequence[ContextItem]
    ) -> list[tuple[Record, str]]:
        evidence: list[tuple[Record, str]] = []
        seen: set[str] = set()
        for item in selected:
            record = self.store.read(item.record_id)
            if record is None:
                continue
            for reference in record.references:
                if not same_enum(reference.expected_type, EntityType.EVIDENCE) or reference.target_id in seen:
                    continue
                target = self.store.read(reference.target_id)
                if target is None:
                    continue
                seen.add(reference.target_id)
                evidence.append((target, f"L3 evidence referenced by {record.id}"))
        for record in by_type.get(EntityType.EVIDENCE, []):
            if record.id in seen:
                continue
            evidence.append((record, "L3 evidence (project scope)"))
        return evidence

    def _build_layer(
        self,
        *,
        candidates: Sequence[tuple[Record, str]],
        limit: int,
        disclosure: DisclosureLevel,
        layer_reason: str,
        remaining: int,
        exclusions: list[ContextExclusion],
        handles: list[ContextHandleRef],
        principal: ContextPrincipal,
    ) -> tuple[list[ContextItem], int]:
        items: list[ContextItem] = []
        tokens = 0
        for record, reason in candidates:
            if len(items) >= limit:
                exclusions.append(
                    ContextExclusion(
                        record_id=record.id, reason_excluded=f"{layer_reason}: limit reached", token_estimate=0
                    )
                )
                handles.append(self._handle_for(record))
                continue
            if record.project_id != principal.project_id:
                exclusions.append(
                    ContextExclusion(
                        record_id=record.id,
                        reason_excluded="PROJECT_SCOPE: 다른 project 자료는 주입하지 않는다",
                        token_estimate=0,
                    )
                )
                continue
            owner_scope = record.producer.kind if record.producer.kind != "body" else "project"
            if owner_scope not in principal.allowed_owner_scopes and "project" not in principal.allowed_owner_scopes:
                exclusions.append(
                    ContextExclusion(
                        record_id=record.id,
                        reason_excluded=f"OWNER_SCOPE: {owner_scope} 권한이 없다",
                        token_estimate=0,
                    )
                )
                continue
            token_estimate = estimate_tokens(_record_text(record))
            if token_estimate > remaining:
                exclusions.append(
                    ContextExclusion(
                        record_id=record.id,
                        reason_excluded="BUDGET: 남은 예산을 초과한다",
                        token_estimate=token_estimate,
                    )
                )
                handles.append(self._handle_for(record))
                continue
            remaining -= token_estimate
            tokens += token_estimate
            items.append(
                ContextItem(
                    record_id=record.id,
                    reason_selected=reason,
                    token_estimate=token_estimate,
                    disclosure_level=disclosure,
                    applicability=ApplicabilityLevel(_applicability_for(record)),
                )
            )
        return items, tokens

    def _handle_for(self, record: Record) -> ContextHandleRef:
        return ContextHandleRef(
            handle_id=f"H-{record.id}",
            project_id=record.project_id,
            owner_scope="project",
            record_id=record.id,
            content_digest=canonical_digest(to_wire(record)),
            disclosure_level=DisclosureLevel.L2_DETAIL,
            expires_at=self._clock() + self.handle_ttl,
        )


def _goal_related(record: Record, goal_id: str) -> bool:
    return record.id == goal_id or any(reference.target_id == goal_id for reference in record.references)


def _applicability_for(record: Record) -> str:
    profile = getattr(record.payload, "applicability", None) or getattr(record.payload, "applicability_profile", None)
    if profile is None:
        return "UNKNOWN"
    values = [str(getattr(profile, field, "UNKNOWN")) for field in ("goal_match", "context_match")]
    if "MISMATCH" in values:
        return "MISMATCH"
    if "PARTIAL" in values:
        return "PARTIAL"
    if all(value == "MATCH" for value in values):
        return "MATCH"
    return "UNKNOWN"


def _disclosure_rank(level: DisclosureLevel) -> int:
    order = (
        DisclosureLevel.L0_SIGNAL,
        DisclosureLevel.L1_SUMMARY,
        DisclosureLevel.L2_DETAIL,
        DisclosureLevel.L3_RAW,
    )
    return order.index(level)


def default_store(project_root: str | Path) -> CanonicalStore:
    """프로젝트 하위 기본 canonical store 위치."""

    return CanonicalStore(Path(project_root) / ".cognitive" / "canonical", git_enabled=False)


__all__ = [
    "DEFAULT_HANDLE_TTL",
    "DEFAULT_L1_LIMIT",
    "DEFAULT_L2_LIMIT",
    "DEFAULT_L3_LIMIT",
    "PROJECTION_VERSION",
    "ContextBuildError",
    "ContextBuildResult",
    "ContextBuilder",
    "ContextFailureReason",
    "ContextPrincipal",
    "HandleResolution",
    "HandleResolutionStatus",
    "default_store",
    "estimate_tokens",
]
