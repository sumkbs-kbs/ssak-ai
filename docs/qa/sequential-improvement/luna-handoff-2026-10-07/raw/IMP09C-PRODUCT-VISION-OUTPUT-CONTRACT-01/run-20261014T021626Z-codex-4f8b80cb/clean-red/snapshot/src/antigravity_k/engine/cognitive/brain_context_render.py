"""Lossless selected-context rendering with a conservative provider budget."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from antigravity_k.engine.cognitive.models import ContextPackagePayload, Record, to_wire


@dataclass(frozen=True, slots=True)
class BrainContextRender:
    wire: Mapping[str, object]
    omitted_required: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def ready_for_provider(self) -> bool:
        return not self.omitted_required


def render_context_for_brain(
    package: ContextPackagePayload,
    *,
    project_id: str,
    context_digest: str,
    load_record: Callable[[str], Record | None],
    context_limit: int,
    snippet_chars: int = 400,
) -> BrainContextRender:
    """Send complete selected records or refuse; snippet_chars is legacy-only.

    UTF-8 byte length is a conservative token upper bound for byte tokenizers.
    Metadata, all selected layers, exclusions and handles count toward the limit.
    """
    _ = snippet_chars  # Retained call compatibility; selected content is never shortened.
    omitted = list(package.missing_ids)

    def take(record_id: str) -> dict[str, object] | None:
        record = load_record(record_id)
        if record is None or record.id != record_id or record.project_id != project_id:
            omitted.append(record_id)
            return None
        payload = to_wire(record)["payload"]
        text = next(
            (
                value
                for attr in ("statement", "claim", "meaning", "title", "summary", "text")
                if isinstance(value := getattr(record.payload, attr, None), str) and value
            ),
            str(payload),
        )
        return {"id": record.id, "entity_type": str(record.entity_type), "text": text, "payload": payload}

    wire: dict[str, object] = {
        "schema_version": "1.0",
        "entity_type": "ContextPackage",
        "project_id": project_id,
        "context_digest": context_digest,
        "content_digest": context_digest,
        "integrity": str(package.integrity),
        "missing_ids": list(package.missing_ids),
        "state_revision": package.state_revision,
        "goal": take(package.goal_id),
        "payload": package.model_dump(mode="json"),
        "context_limit": context_limit,
    }
    for label, items in (
        ("constraints", package.l0_constraints),
        ("state", package.l1_state),
        ("history", package.l2_history),
        ("evidence", package.l3_evidence),
    ):
        wire[label] = [entry for item in items if (entry := take(item.record_id)) is not None]
    wire["evidence_ids"] = [item.record_id for item in package.l3_evidence]
    wire["omitted_required"] = omitted
    # Reserve enough space for the accounting fields themselves.
    used = len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 128
    wire["tokens_used_estimate"] = used
    if used > context_limit:
        omitted.append("context_budget")
    return BrainContextRender(wire=wire, omitted_required=tuple(dict.fromkeys(omitted)), truncated=bool(omitted))
