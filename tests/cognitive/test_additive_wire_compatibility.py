"""Additive payload fields must not change immutable pre-upgrade wire digests."""

import pytest

from antigravity_k.engine.cognitive.models import (
    ExecutionReceiptPayload,
    ReceiptStatus,
    Record,
    from_wire,
    to_wire,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import canonical_digest
from tests.cognitive._fixtures import NOW, PRODUCER, build_experience, build_judgment


def original_wire(kind: str):
    project = new_id(EntityType.PROJECT)
    if kind == "experience":
        record = build_experience(project)
        additive = ("episode_reference", "evidence_refs")
    elif kind == "judgment":
        record = build_judgment(project, new_id(EntityType.EVIDENCE))
        additive = ("delta",)
    else:
        record = Record.create(
            entity_type=EntityType.EXECUTION_RECEIPT,
            project_id=project,
            producer=PRODUCER,
            payload=ExecutionReceiptPayload(
                action_id=new_id(EntityType.ACTION),
                idempotency_key="retry-key",
                dispatch_attempt=1,
                started_at=NOW,
                status=ReceiptStatus.DISPATCHED,
            ),
            created_at=NOW,
        )
        additive = ("detail",)
    wire = record.model_dump(mode="json")
    for name in additive:
        del wire["payload"][name]
    return wire, additive


@pytest.mark.parametrize("kind", ["experience", "judgment", "receipt"])
def test_absent_additive_fields_preserve_preupgrade_wire_digest(kind: str) -> None:
    # Given a pre-upgrade wire with only newly introduced fields absent.
    wire, _ = original_wire(kind)
    expected_digest = canonical_digest(wire)
    # When the new schema parses and canonically serializes the immutable record.
    roundtrip = to_wire(from_wire(wire))
    # Then previous defaulted fields remain present and historical identity is unchanged.
    assert roundtrip == wire
    assert canonical_digest(roundtrip) == expected_digest


@pytest.mark.parametrize("kind", ["experience", "judgment", "receipt"])
def test_explicit_new_defaults_are_preserved(kind: str) -> None:
    # Given a new producer that explicitly serialized every new field with its default.
    wire, _ = original_wire(kind)
    explicit_wire = from_wire(wire).model_dump(mode="json")
    # When this authored wire is parsed and serialized again.
    roundtrip = to_wire(from_wire(explicit_wire))
    # Then explicit field presence is not stripped because values happen to be defaults.
    assert roundtrip == explicit_wire


def test_preupgrade_persisted_record_keeps_issued_context_handle_valid(tmp_path, monkeypatch) -> None:
    from antigravity_k.engine.cognitive import store as store_module
    from antigravity_k.engine.cognitive.context import ContextBuilder, ContextPrincipal, HandleResolutionStatus
    from antigravity_k.engine.cognitive.models import ContextHandleRef, DisclosureLevel
    from antigravity_k.engine.cognitive.store import CanonicalStore

    # Given real persisted bytes and an issued handle from the pre-upgrade serializer.
    wire, _ = original_wire("experience")
    old_record = from_wire(wire)
    store = CanonicalStore(tmp_path, git_enabled=False)
    with monkeypatch.context() as old_writer:
        old_writer.setattr(store_module, "to_wire", lambda record: wire)
        store.commit_records([old_record])
    handle = ContextHandleRef(
        handle_id="issued-before-upgrade",
        project_id=old_record.project_id,
        owner_scope="project",
        record_id=old_record.id,
        content_digest=canonical_digest(wire),
        disclosure_level=DisclosureLevel.L2_DETAIL,
    )
    # When current code reopens the untouched store and resolves that old handle.
    reopened = CanonicalStore(tmp_path, git_enabled=False)
    resolution = ContextBuilder(reopened, clock=lambda: NOW).resolve_handle(
        handle, ContextPrincipal(subject="human:test", project_id=old_record.project_id)
    )
    # Then immutable history stays accessible and raw-file verification also agrees.
    assert resolution.status == HandleResolutionStatus.OK
    assert reopened.verify_digests() == 1


@pytest.mark.parametrize("kind", ["experience", "judgment", "receipt"])
def test_explicit_nondefault_additive_fields_survive(kind: str) -> None:
    # Given authored new data rather than absent legacy fields.
    wire, _ = original_wire(kind)
    if kind == "experience":
        wire["payload"].update(episode_reference="episode:explicit", evidence_refs=[new_id(EntityType.EVIDENCE)])
    elif kind == "judgment":
        wire["payload"]["delta"] = {
            "judgment": True,
            "ground": False,
            "alternative": False,
            "unknown": False,
            "risk": False,
            "action": False,
            "description": "observed change",
        }
    else:
        wire["payload"]["detail"] = "observed tool output"
    # When the current model performs its canonical roundtrip.
    roundtrip = to_wire(from_wire(wire))
    # Then no authored data is lost.
    assert roundtrip == wire
