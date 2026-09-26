"""Brain engagement (P04) — provider 독립 adapter와 구조 검증.

계약(BRAIN_ENGAGEMENT_PROTOCOL.md):
- ``think(context, request_id, capabilities) -> BrainJudgment | BrainFailure``
- ``rethink(previous_judgment_id, feedback_ids, affected_ground_ids, context_delta) -> BrainJudgment | BrainFailure``
- 모델 출력은 신뢰할 수 없는 입력이다: 알 수 없는 enum, 잘못된 ID, 다른 project reference, oversize 응답을 거부한다.
- 형식 오류는 **1회**만 repair한다. repair에도 모델·비용·시간을 계상하고 실패하면 ``BRAIN_PROTOCOL_ERROR``다.
  adapter가 선언한 ``timeout_seconds``를 넘긴 유효 응답은 ``TIMEOUT``으로 거부한다(늦은 응답은
  선언된 능력 밖이다). token 비용은 시도를 합쳐 judgment에 기록한다.
- 원래 판단은 수정하지 않는다. rethink 결과는 새 judgment이며 ``supersedes`` reference로 연결한다.
- provider fallback은 같은 frozen ContextPackage를 새 adapter에 전달하고 **새 judgment ID**를 만든다.
- plain-text 응답을 FACT/READY로 포장하지 않는다.

Secondary는 conditional이다. 여러 Secondary를 불러도 각자의 응답은 **그대로** MODEL_JUDGMENT evidence로
Primary에 전달될 뿐 최종 통합 권한이 없다 — Body가 다수결·merge·치환으로 결론을 만들지 않는다.
이 모듈은 provider SDK/UI를 import하지 않는다 — adapter가 주입된다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.models import (
    AssumptionPayload,
    BrainJudgmentPayload,
    ContextPackagePayload,
    EvidenceKind,
    EvidencePayload,
    IntegrityStatus,
    Producer,
    ProducerKind,
    Provenance,
    Record,
    UnknownCategory,
    UnknownMateriality,
    UnknownPayload,
    same_enum,
    to_wire,
)
from antigravity_k.engine.cognitive.references import (
    REL_GROUND,
    REL_JUDGMENT,
    REL_SUPERSEDES,
    EntityType,
    Reference,
    new_id,
)

#: provider 응답 크기 상한(문자). 초과 응답은 실행하지 않는다.
MAX_RESPONSE_CHARS: Final[int] = 200_000
#: schema repair 시도 횟수 상한. 1회를 넘기지 않는다.
MAX_REPAIR_ATTEMPTS: Final[int] = 1


class BrainFailureKind(StrEnum):
    BRAIN_PROTOCOL_ERROR = "BRAIN_PROTOCOL_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


@dataclass(frozen=True, slots=True)
class BrainCapabilities:
    structured_output: bool
    tool_request: bool
    context_limit: int
    timeout_seconds: float
    provider_model_version: str

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "structured_output": self.structured_output,
            "tool_request": self.tool_request,
            "context_limit": self.context_limit,
            "timeout_seconds": self.timeout_seconds,
            "provider_model_version": self.provider_model_version,
        }


@dataclass(frozen=True, slots=True)
class BrainFailure:
    request_id: str
    kind: BrainFailureKind
    detail: str
    repair_attempts: int = 0
    provider_model_version: str = ""
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class BrainResponse:
    """adapter(모델)의 검증 전 응답. 여기의 값은 아직 신뢰할 수 없다."""

    text: str = ""
    structured: Mapping[str, object] | None = None
    provider_model_version: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True, slots=True)
class BrainJudgment:
    """검증을 통과한 판단 + canonical record. 판단은 Body가 소유한다."""

    request_id: str
    record: Record
    payload: BrainJudgmentPayload
    provider_model_version: str
    repair_attempts: int = 0
    supersedes_record_id: str | None = None
    #: 시간·비용 계상 — repair 시도를 합친 값이다(선언된 능력 안에서 돌았는지의 근거).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return True


BrainOutcome = BrainJudgment | BrainFailure


@runtime_checkable
class BrainAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BrainCapabilities: ...

    def respond(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        repair_of: Mapping[str, object] | None = None,
    ) -> BrainResponse: ...


def _now() -> datetime:
    return datetime.now(UTC)


class StructuredBrainClient:
    """adapter 응답을 검증해 canonical BrainJudgment로 바꾼다."""

    def __init__(
        self,
        adapter: BrainAdapter,
        *,
        project_id: str,
        producer: Producer | None = None,
        clock: Callable[[], datetime] | None = None,
        max_response_chars: int = MAX_RESPONSE_CHARS,
        timer: Callable[[], float] | None = None,
    ) -> None:
        self.adapter = adapter
        self.project_id = project_id
        self.producer = (
            producer if producer is not None else Producer(kind=ProducerKind.BRAIN, actor_id=f"brain:{adapter.name}")
        )
        self._clock = clock if clock is not None else _now
        self._timer = timer if timer is not None else time.monotonic
        self.max_response_chars = max_response_chars

    # ── think ───────────────────────────────────────────
    def think(self, context_wire: Mapping[str, object], request_id: str) -> BrainOutcome:
        return self._engage(context_wire, request_id, supersedes=None, feedback_ids=(), context_delta=None)

    # ── rethink ─────────────────────────────────────────
    def rethink(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        previous_judgment_id: str,
        feedback_ids: Sequence[str] = (),
        affected_ground_ids: Sequence[str] = (),
        context_delta: Mapping[str, object] | None = None,
    ) -> BrainOutcome:
        """이전 판단을 수정하지 않는다. 새 judgment가 supersedes로 연결된다."""

        if not previous_judgment_id.startswith("brain_judgment:"):
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.BRAIN_PROTOCOL_ERROR,
                detail=f"previous_judgment_id is not a canonical judgment id: {previous_judgment_id}",
            )
        return self._engage(
            context_wire,
            request_id,
            supersedes=previous_judgment_id,
            feedback_ids=tuple(feedback_ids),
            context_delta=context_delta,
            affected_ground_ids=tuple(affected_ground_ids),
        )

    # ── 내부 ────────────────────────────────────────────
    def _engage(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        supersedes: str | None,
        feedback_ids: Sequence[str],
        context_delta: Mapping[str, object] | None,
        affected_ground_ids: Sequence[str] = (),
    ) -> BrainOutcome:
        if not self.adapter.capabilities.structured_output:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.UNSUPPORTED_CAPABILITY,
                detail="adapter does not support structured output",
                provider_model_version=self.adapter.capabilities.provider_model_version,
            )
        if "project_id" not in context_wire:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.BRAIN_PROTOCOL_ERROR,
                detail="context wire has no project_id",
            )
        context_project = str(context_wire["project_id"])
        if context_project != self.project_id:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.BRAIN_PROTOCOL_ERROR,
                detail=f"context project {context_project} != adapter project {self.project_id}",
            )

        started = self._timer()
        response = self.adapter.respond(context_wire, request_id)
        prompt_tokens = response.prompt_tokens
        completion_tokens = response.completion_tokens
        attempts = 0
        rejection = self._validate(response, request_id)
        if rejection is not None:
            attempts = 1
            repair_response = self.adapter.respond(context_wire, request_id, repair_of=dict(context_wire))
            # repair에도 모델·비용을 계상한다 — 원래 시도의 비용은 사라지지 않는다.
            prompt_tokens += repair_response.prompt_tokens
            completion_tokens += repair_response.completion_tokens
            rejection = self._validate(repair_response, request_id)
            response = repair_response
        elapsed = self._timer() - started
        if rejection is not None:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.BRAIN_PROTOCOL_ERROR,
                detail=rejection,
                repair_attempts=attempts,
                provider_model_version=response.provider_model_version,
                elapsed_seconds=elapsed,
            )
        timeout_seconds = self.adapter.capabilities.timeout_seconds
        if timeout_seconds > 0 and elapsed > timeout_seconds:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.TIMEOUT,
                detail=(
                    f"adapter elapsed {elapsed:.3f}s exceeds declared timeout_seconds={timeout_seconds}"
                    " — 선언된 능력 밖의 응답은 쓰지 않는다"
                ),
                repair_attempts=attempts,
                provider_model_version=response.provider_model_version,
                elapsed_seconds=elapsed,
            )
        if attempts > MAX_REPAIR_ATTEMPTS:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.BRAIN_PROTOCOL_ERROR,
                detail="schema repair exceeded the single allowed attempt",
                repair_attempts=attempts,
                elapsed_seconds=elapsed,
            )

        assert response.structured is not None
        payload = BrainJudgmentPayload.model_validate(response.structured["judgment"])
        references = self._build_references(payload, supersedes=supersedes)
        record = Record.create(
            entity_type=EntityType.BRAIN_JUDGMENT,
            project_id=self.project_id,
            producer=self.producer,
            payload=payload,
            references=references,
            created_at=self._clock(),
        )
        return BrainJudgment(
            request_id=request_id,
            record=record,
            payload=payload,
            provider_model_version=response.provider_model_version,
            repair_attempts=attempts,
            supersedes_record_id=supersedes,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            elapsed_seconds=elapsed,
        )

    def _validate(self, response: BrainResponse, request_id: str) -> str | None:
        if len(response.text) > self.max_response_chars:
            return f"response exceeds {self.max_response_chars} chars"
        if response.structured is None:
            payload_text = response.text.strip()
            if len(payload_text) > self.max_response_chars:
                return "oversize plain-text response rejected"
            return "response is not structured (plain text is never promoted to a judgment)"
        judgment = response.structured.get("judgment")
        if not isinstance(judgment, dict):
            return "structured response has no judgment object"
        for field_name, ids in (
            ("grounds", judgment.get("grounds")),
            ("assumptions", judgment.get("assumptions")),
            ("unknowns", judgment.get("unknowns")),
        ):
            if ids is None:
                continue
            if not isinstance(ids, (list, tuple)):
                return f"{field_name} must be a list"
            for item in ids:
                if not isinstance(item, str) or not item.startswith(("evidence:", "assumption:", "unknown:")):
                    return f"{field_name} contains a non-canonical id: {item!r}"
        context_digest = judgment.get("context_digest")
        if not isinstance(context_digest, str) or not context_digest:
            return "judgment has no context_digest"
        return None

    def _build_references(self, payload: BrainJudgmentPayload, *, supersedes: str | None) -> tuple[Reference, ...]:
        references: list[Reference] = []
        for ground_id in payload.grounds:
            references.append(Reference(relation=REL_GROUND, target_id=ground_id, expected_type=EntityType.EVIDENCE))
        for unknown_id in payload.unknowns:
            if unknown_id.startswith("unknown:"):
                references.append(Reference(relation="unknown", target_id=unknown_id, expected_type=EntityType.UNKNOWN))
        for assumption_id in payload.assumptions:
            if assumption_id.startswith("assumption:"):
                references.append(
                    Reference(relation="assumption", target_id=assumption_id, expected_type=EntityType.ASSUMPTION)
                )
        if supersedes is not None:
            references.append(
                Reference(relation=REL_SUPERSEDES, target_id=supersedes, expected_type=EntityType.BRAIN_JUDGMENT)
            )
        return tuple(references)


@dataclass(frozen=True, slots=True)
class SecondaryEngagement:
    """Secondary는 conditional이다. 결과는 Primary에 줄 evidence일 뿐이다."""

    requested_by_judgment_id: str
    approved_by_governance_id: str | None
    evidence: Record
    judgment: BrainJudgment

    @property
    def has_authority(self) -> bool:
        """Secondary 응답은 결론 권한이 없다(다수결 금지)."""

        return False


class BrainDirector:
    """Primary/Secondary 역할 구분과 provider fallback."""

    def __init__(
        self,
        *,
        project_id: str,
        primary: StructuredBrainClient,
        secondary: StructuredBrainClient | None = None,
        secondaries: Sequence[StructuredBrainClient] = (),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_id = project_id
        self.primary = primary
        self.secondary = secondary
        self.secondaries = tuple(secondaries)
        self._clock = clock if clock is not None else _now

    def think(self, context_wire: Mapping[str, object], request_id: str) -> BrainOutcome:
        return self.primary.think(context_wire, request_id)

    def think_with_fallback(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        fallback: StructuredBrainClient,
    ) -> BrainOutcome:
        """같은 frozen context를 그대로 넘긴다. fallback도 새 judgment ID를 만든다."""

        outcome = self.primary.think(context_wire, request_id)
        if outcome.ok:
            return outcome
        return fallback.think(context_wire, request_id)

    def engage_secondary(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        requested_by: BrainJudgment,
        governance_decision_id: str | None,
        project_id: str | None = None,
    ) -> SecondaryEngagement | BrainFailure:
        """승인된 경우에만 secondary를 부른다. 응답은 MODEL_JUDGMENT evidence로 남긴다."""

        if self.secondary is None:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.UNSUPPORTED_CAPABILITY,
                detail="no secondary adapter is configured",
            )
        if governance_decision_id is None:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.UNSUPPORTED_CAPABILITY,
                detail="secondary engagement requires an approved governance decision",
            )
        return self._engage_one_secondary(
            self.secondary,
            context_wire,
            request_id,
            requested_by=requested_by,
            governance_decision_id=governance_decision_id,
            project_id=project_id,
        )

    def engage_secondaries(
        self,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        requested_by: BrainJudgment,
        governance_decision_id: str | None,
        project_id: str | None = None,
    ) -> list[SecondaryEngagement] | BrainFailure:
        """여러 Secondary를 같은 frozen context로 부른다.

        각 응답은 **그대로** 각자의 MODEL_JUDGMENT evidence로 남는다 — 다수결·merge·치환으로
        합쳐진 결론을 만들지 않는다(최종 통합은 Primary다). 하나라도 실패하면 전체 실패다:
        일부 의견만 남은 자료는 "여럿이 다수로 말했다" 로 읽히므로 부분 결과를 내지 않는다.
        """

        clients = self.secondaries or ((self.secondary,) if self.secondary is not None else ())
        if not clients:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.UNSUPPORTED_CAPABILITY,
                detail="no secondary adapters are configured",
            )
        if governance_decision_id is None:
            return BrainFailure(
                request_id=request_id,
                kind=BrainFailureKind.UNSUPPORTED_CAPABILITY,
                detail="secondary engagement requires an approved governance decision",
            )
        engagements: list[SecondaryEngagement] = []
        for client in clients:
            engaged = self._engage_one_secondary(
                client,
                context_wire,
                request_id,
                requested_by=requested_by,
                governance_decision_id=governance_decision_id,
                project_id=project_id,
            )
            if isinstance(engaged, BrainFailure):
                return engaged
            engagements.append(engaged)
        return engagements

    def _engage_one_secondary(
        self,
        client: StructuredBrainClient,
        context_wire: Mapping[str, object],
        request_id: str,
        *,
        requested_by: BrainJudgment,
        governance_decision_id: str,
        project_id: str | None,
    ) -> SecondaryEngagement | BrainFailure:
        outcome = client.think(context_wire, request_id)
        if isinstance(outcome, BrainFailure):
            return outcome
        evidence = Record.create(
            entity_type=EntityType.EVIDENCE,
            project_id=project_id if project_id is not None else self.project_id,
            producer=Producer(kind=ProducerKind.TOOL, actor_id=f"brain-secondary:{client.adapter.name}"),
            payload=EvidencePayload(
                kind=EvidenceKind.MODEL_JUDGMENT,
                claim=outcome.payload.current_judgment,
                provenance=Provenance(
                    source_uri=f"brain:{client.adapter.name}",
                    source_version=outcome.provider_model_version,
                    content_digest=outcome.record.id,
                    observed_at=self._clock(),
                    ingested_at=self._clock(),
                ),
                time=self._clock(),
                digest=outcome.record.id,
                independence_group=f"secondary:{client.adapter.name}",
            ),
            references=(
                Reference(
                    relation=REL_JUDGMENT, target_id=requested_by.record.id, expected_type=EntityType.BRAIN_JUDGMENT
                ),
            ),
            created_at=self._clock(),
        )
        return SecondaryEngagement(
            requested_by_judgment_id=requested_by.record.id,
            approved_by_governance_id=governance_decision_id,
            evidence=evidence,
            judgment=outcome,
        )


@dataclass(frozen=True, slots=True)
class BrainContextRender:
    """Bounded provider wire built from a canonical ContextPackage (not opaque IDs alone)."""

    wire: Mapping[str, object]
    omitted_required: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def ready_for_provider(self) -> bool:
        return not self.omitted_required


def _snippet_from_record(record: Record, *, max_chars: int) -> str:
    payload = record.payload
    for attr in ("statement", "content", "verbatim_text", "claim", "meaning", "title", "summary", "text"):
        value = getattr(payload, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:max_chars]
    wire = to_wire(record)
    text = str(wire.get("payload", wire))
    return text[:max_chars]


def render_context_for_brain(
    package: ContextPackagePayload,
    *,
    project_id: str,
    context_digest: str,
    load_record: Callable[[str], Record | None],
    context_limit: int,
    snippet_chars: int = 400,
) -> BrainContextRender:
    """Expand ContextPackage items into provider wire with real goal/state/evidence text.

    When ``context_limit`` cannot hold required goal/state/evidence snippets, those IDs are
    listed in ``omitted_required`` — callers must not hide the omission or call the provider.
    """

    if context_limit < 1:
        return BrainContextRender(
            wire={
                "schema_version": "1.0",
                "entity_type": "ContextPackage",
                "project_id": project_id,
                "context_digest": context_digest,
                "integrity": str(package.integrity),
                "missing_ids": list(package.missing_ids),
                "goal": None,
                "state": [],
                "evidence": [],
                "omitted_required": ["goal", "state", "evidence"],
                "context_limit": context_limit,
            },
            omitted_required=("goal", "state", "evidence"),
            truncated=True,
        )

    omitted: list[str] = []
    used = 0

    def take(label: str, record_id: str, required: bool) -> dict[str, object] | None:
        nonlocal used
        record = load_record(record_id)
        if record is None:
            if required:
                omitted.append(record_id)
            return None
        snippet = _snippet_from_record(record, max_chars=snippet_chars)
        entry: dict[str, object] = {
            "id": record_id,
            "entity_type": str(record.entity_type),
            "text": snippet,
        }
        cost = max(1, len(str(entry)) // 4)
        if used + cost > context_limit:
            if required:
                omitted.append(record_id)
            return None
        used += cost
        return entry

    goal_entry = take("goal", package.goal_id, required=True)
    state_entries: list[dict[str, object]] = []
    for item in package.l1_state:
        entry = take("state", item.record_id, required=True)
        if entry is not None:
            state_entries.append(entry)
    evidence_entries: list[dict[str, object]] = []
    for item in package.l3_evidence:
        entry = take("evidence", item.record_id, required=True)
        if entry is not None:
            evidence_entries.append(entry)

    # Required surface: at least goal text when package is COMPLETE.
    if same_enum(package.integrity, IntegrityStatus.COMPLETE) and goal_entry is None:
        if package.goal_id not in omitted:
            omitted.append(package.goal_id)

    wire: dict[str, object] = {
        "schema_version": "1.0",
        "entity_type": "ContextPackage",
        "project_id": project_id,
        "context_digest": context_digest,
        "content_digest": context_digest,
        "integrity": str(package.integrity),
        "missing_ids": list(package.missing_ids),
        "state_revision": package.state_revision,
        "goal": goal_entry,
        "state": state_entries,
        "evidence": evidence_entries,
        "evidence_ids": [e["id"] for e in evidence_entries],
        "payload": {
            "goal_id": package.goal_id,
            "state_revision": package.state_revision,
            "integrity": str(package.integrity),
        },
        "omitted_required": list(omitted),
        "context_limit": context_limit,
        "tokens_used_estimate": used,
    }
    return BrainContextRender(
        wire=wire,
        omitted_required=tuple(omitted),
        truncated=bool(omitted),
    )


def assumption_record(
    statement: str, scope: str, *, project_id: str, actor_id: str = "body:brain-engagement"
) -> Record:
    """Brain이 제시한 assumption을 canonical record로 옮긴다(판단 소유는 Body)."""

    return Record.create(
        entity_type=EntityType.ASSUMPTION,
        project_id=project_id,
        producer=Producer(kind=ProducerKind.BODY, actor_id=actor_id),
        payload=AssumptionPayload(statement=statement, validity_scope=scope),
    )


def unknown_record(
    question: str,
    *,
    project_id: str,
    materiality: str = "MATERIAL",
    reason: str = "Brain이 표시한 unknown",
    action_change: bool = True,
    actor_id: str = "body:brain-engagement",
) -> Record:
    return Record.create(
        entity_type=EntityType.UNKNOWN,
        project_id=project_id,
        producer=Producer(kind=ProducerKind.BODY, actor_id=actor_id),
        payload=UnknownPayload(
            question=question,
            category=UnknownCategory.SEMANTIC,
            materiality=UnknownMateriality(materiality),
            materiality_reason=reason,
            potential_action_change=action_change,
        ),
    )


def new_judgment_id() -> str:
    return new_id(EntityType.BRAIN_JUDGMENT)


__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "MAX_RESPONSE_CHARS",
    "BrainAdapter",
    "BrainCapabilities",
    "BrainDirector",
    "BrainFailure",
    "BrainFailureKind",
    "BrainJudgment",
    "BrainOutcome",
    "BrainResponse",
    "SecondaryEngagement",
    "BrainContextRender",
    "StructuredBrainClient",
    "render_context_for_brain",
    "assumption_record",
    "new_judgment_id",
    "unknown_record",
]
