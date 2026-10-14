"""Structured Primary bridge from canonical context into runtime outcomes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import final

from antigravity_k.engine.cognitive.brain import (
    BrainAdapter,
    BrainCapabilities,
    BrainFailure,
    BrainJudgment,
    BrainResponse,
    StructuredBrainClient,
    render_context_for_brain,
)
from antigravity_k.engine.cognitive.models import (
    CognitiveRequestPayload,
    ContextPackagePayload,
    ExecutionReceiptPayload,
    IntegrityStatus,
    Record,
    same_enum,
    to_wire,
)
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRequestEnvelope,
    EpisodeDelta,
    RequestFeedback,
    ThinkOutcome,
)
from antigravity_k.engine.cognitive.store import CommitReceipt, canonical_digest

from .cognitive_surface_legacy_brain import SurfaceBrainPort


@final
class _CountingBrainAdapter:
    """Wraps a BrainAdapter to count respond() calls (R14 provider-call0 assertions)."""

    def __init__(self, inner: BrainAdapter) -> None:
        self._inner = inner
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> BrainCapabilities:
        return self._inner.capabilities

    def respond(
        self, context_wire: Mapping[str, object], request_id: str, *, repair_of: Mapping[str, object] | None = None
    ) -> BrainResponse:
        self.call_count += 1
        return self._inner.respond(context_wire, request_id, repair_of=repair_of)


@final
class StructuredSurfaceBrainPort:
    """Canonical ContextPackage → bounded wire → StructuredBrainClient.

    Opaque ``context_ref`` alone is never sent to the provider. INCOMPLETE packages and
    required omissions under a low context window fail closed with provider call count 0.
    When ``legacy_observation`` is set and the ref cannot be loaded as a ContextPackage,
    the legacy one-sentence observation path runs (still delta=None — not material THINK).
    """

    def __init__(
        self,
        adapter: BrainAdapter,
        *,
        project_id: str,
        load_context_package: Callable[[str], Record | None],
        load_record: Callable[[str], Record | None],
        legacy_observation: Callable[[str], str] | None = None,
        record_sink: Callable[[Sequence[Record]], CommitReceipt | None] | None = None,
        request_resolver: Callable[[Record], CognitiveRequestEnvelope | None] | None = None,
    ) -> None:
        self._adapter = _CountingBrainAdapter(adapter)
        self._project_id = project_id
        self._load_package = load_context_package
        self._load_record = load_record
        self._legacy = legacy_observation
        self._client = StructuredBrainClient(self._adapter, project_id=project_id)
        self._record_sink = record_sink
        self._request_resolver = request_resolver
        self._contexts: dict[str, str] = {}

    @property
    def provider_calls(self) -> int:
        return self._adapter.call_count

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        return self._engage(context_ref, request_signature or f"{context_ref}:{attempt}")

    def rethink(
        self,
        *,
        previous_judgment_ref: str,
        feedback_refs: Sequence[str],
        affected_grounds: Sequence[str],
        round_index: int,
        feedback: Sequence[RequestFeedback] = (),
    ) -> ThinkOutcome:
        context_ref = self._contexts.get(previous_judgment_ref)
        if context_ref is None:
            return ThinkOutcome(judgment_ref="", failed=True, detail="RETHINK_CONTEXT_UNRESOLVED")
        return self._engage(
            context_ref,
            f"{previous_judgment_ref}:rethink:{round_index}",
            previous=previous_judgment_ref,
            feedback_refs=feedback_refs,
            affected_grounds=affected_grounds,
            feedback=feedback,
        )

    def _engage(
        self,
        context_ref: str,
        request_signature: str,
        *,
        previous: str | None = None,
        feedback_refs: Sequence[str] = (),
        affected_grounds: Sequence[str] = (),
        feedback: Sequence[RequestFeedback] = (),
    ) -> ThinkOutcome:
        package_record = self._load_package(context_ref)
        if package_record is None:
            if self._legacy is not None:
                return SurfaceBrainPort(self._legacy).think(
                    context_ref=context_ref, request_signature=request_signature, attempt=1
                )
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"CONTEXT_UNRESOLVED: {context_ref} is not a loadable ContextPackage",
            )
        if package_record.project_id != self._project_id:
            return ThinkOutcome(judgment_ref="", failed=True, detail="CONTEXT_PROJECT_MISMATCH")
        payload = package_record.payload
        if not isinstance(payload, ContextPackagePayload):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"CONTEXT_WRONG_TYPE: {context_ref} payload is not ContextPackage",
            )
        if same_enum(payload.integrity, IntegrityStatus.INCOMPLETE):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=("CONTEXT_INCOMPLETE: adapter blocked; missing_ids=" + ",".join(payload.missing_ids)),
            )
        digest = canonical_digest(to_wire(package_record))
        rendered = render_context_for_brain(
            payload,
            project_id=self._project_id,
            context_digest=digest,
            load_record=self._load_record,
            context_limit=int(self._adapter.capabilities.context_limit),
        )
        if not rendered.ready_for_provider:
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=(
                    "CONTEXT_OVERFLOW: required goal/state/evidence omitted under context_limit="
                    f"{self._adapter.capabilities.context_limit}; omitted={list(rendered.omitted_required)}"
                ),
            )
        # Count only actual adapter.respond invocations via wrapping — use a counter hook.
        if previous is None:
            outcome = self._client.think(rendered.wire, request_signature)
        else:
            receipts: list[dict[str, object]] = []
            for item in feedback:
                if item.receipt_ref is None:
                    if item.executed:
                        return ThinkOutcome(judgment_ref="", failed=True, detail="EXECUTED_RECEIPT_MISSING")
                    continue
                receipt = self._load_record(item.receipt_ref)
                if (
                    receipt is None
                    or receipt.id != item.receipt_ref
                    or receipt.project_id != self._project_id
                    or not isinstance(receipt.payload, ExecutionReceiptPayload)
                ):
                    return ThinkOutcome(judgment_ref="", failed=True, detail=f"RECEIPT_UNRESOLVED: {item.receipt_ref}")
                receipts.append(to_wire(receipt))
            outcome = self._client.rethink(
                rendered.wire,
                request_signature,
                previous_judgment_id=previous,
                feedback_ids=feedback_refs,
                affected_ground_ids=affected_grounds,
                context_delta={"feedback": [asdict(item) for item in feedback], "receipts": receipts},
            )
        if isinstance(outcome, BrainFailure):
            return ThinkOutcome(
                judgment_ref="",
                failed=True,
                detail=f"brain failure {outcome.kind}: {outcome.detail}",
            )
        assert isinstance(outcome, BrainJudgment)
        self._contexts[outcome.record.id] = context_ref
        if self._record_sink is not None:
            _ = self._record_sink((outcome.record,))
        requests: list[CognitiveRequestEnvelope] = []
        for request_id in outcome.payload.requests:
            record = self._load_record(request_id)
            if record is None or record.id != request_id or record.project_id != self._project_id:
                return ThinkOutcome(
                    judgment_ref=outcome.record.id, failed=True, detail=f"REQUEST_UNRESOLVED: {request_id}"
                )
            if not isinstance(record.payload, CognitiveRequestPayload):
                return ThinkOutcome(
                    judgment_ref=outcome.record.id, failed=True, detail=f"REQUEST_WRONG_TYPE: {request_id}"
                )
            request = record.payload
            resolved = self._request_resolver(record) if self._request_resolver is not None else None
            if resolved is None:
                return ThinkOutcome(
                    judgment_ref=outcome.record.id, failed=True, detail=f"REQUEST_UNBOUND: {request_id}"
                )
            if (
                resolved.request_id != record.id
                or not same_enum(resolved.request_type, request.request_type)
                or resolved.purpose != request.purpose
                or resolved.target != request.target
                or resolved.expected_decision_impact != request.expected_decision_impact
            ):
                return ThinkOutcome(
                    judgment_ref=outcome.record.id, failed=True, detail=f"REQUEST_BINDING_MISMATCH: {request_id}"
                )
            requests.append(resolved)
        delta = outcome.payload.delta
        return ThinkOutcome(
            judgment_ref=outcome.record.id,
            requests=tuple(requests),
            delta=EpisodeDelta(
                judgment=delta.judgment,
                ground=delta.ground,
                alternative=delta.alternative,
                unknown=delta.unknown,
                risk=delta.risk,
                action=delta.action,
                description=delta.description,
            )
            if delta is not None
            else None,
            detail=outcome.payload.current_judgment,
        )
