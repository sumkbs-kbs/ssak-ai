"""Durable feedback receipt contracts for targeted Primary rethink."""

from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.models import to_wire
from antigravity_k.engine.cognitive.store import canonical_digest
from tests.cognitive.test_brain import _r14_fixture


def test_rethink_loads_receipt_and_persists_new_judgment(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive.models import ExecutionReceiptPayload, Record
    from antigravity_k.engine.cognitive.references import EntityType, new_id
    from antigravity_k.engine.cognitive.runtime import RequestFeedback
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive._fixtures import NOW, PRODUCER
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given a canonical execution receipt and a durable prior judgment.
    project, store, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    receipt = Record.create(
        entity_type=EntityType.EXECUTION_RECEIPT,
        project_id=project,
        producer=PRODUCER,
        payload=ExecutionReceiptPayload(
            action_id=new_id(EntityType.ACTION),
            idempotency_key="key",
            dispatch_attempt=1,
            started_at=NOW,
            status="UNKNOWN",
            effects_observed=False,
        ),
    )
    store.commit_records((receipt,))
    adapter = FakeAdapter(
        "primary",
        [
            structured(
                {
                    "judgment": judgment_dict(
                        grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))
                    )
                }
            )
        ],
    )
    port = StructuredSurfaceBrainPort(
        adapter,
        project_id=project,
        load_context_package=load_package,
        load_record=load,
        record_sink=store.commit_records,
    )
    prior = port.think(context_ref=built.record.id, request_signature="first", attempt=1)
    original = store.read(prior.judgment_ref)
    # When the executed request requires rethink.
    result = port.rethink(
        previous_judgment_ref=prior.judgment_ref,
        feedback_refs=("request",),
        affected_grounds=(),
        round_index=1,
        feedback=(RequestFeedback("request", "signature", "APPROVE", True, receipt_ref=receipt.id),),
    )
    # Then actual receipt facts reach Primary and both judgments remain canonical.
    assert not result.failed
    assert adapter.calls[-1]["context"]["rethink"]["context_delta"]["receipts"] == [to_wire(receipt)]
    assert store.read(prior.judgment_ref) == original
    revised = store.read(result.judgment_ref)
    assert any(ref.target_id == prior.judgment_ref and ref.relation == "supersedes" for ref in revised.references)


@pytest.mark.parametrize("with_reference", [False, True])
def test_rethink_refuses_unloadable_receipt_before_provider(tmp_path: Path, with_reference: bool) -> None:
    from antigravity_k.engine.cognitive.references import EntityType, new_id
    from antigravity_k.engine.cognitive.runtime import RequestFeedback
    from antigravity_k.engine.cognitive_surface import StructuredSurfaceBrainPort
    from tests.cognitive.test_brain import FakeAdapter, judgment_dict, structured

    # Given feedback that references a receipt absent from the canonical store.
    project, _, built, _, evidence, load_package, load = _r14_fixture(tmp_path)
    adapter = FakeAdapter(
        "primary",
        [
            structured(
                {
                    "judgment": judgment_dict(
                        grounds=(evidence.id,), context_digest=canonical_digest(to_wire(built.record))
                    )
                }
            )
        ],
    )
    port = StructuredSurfaceBrainPort(adapter, project_id=project, load_context_package=load_package, load_record=load)
    prior = port.think(context_ref=built.record.id, request_signature="first", attempt=1)
    # When rethinking tries to consume that absent receipt.
    result = port.rethink(
        previous_judgment_ref=prior.judgment_ref,
        feedback_refs=("request",),
        affected_grounds=(),
        round_index=1,
        feedback=(
            RequestFeedback(
                "request",
                "signature",
                "APPROVE",
                True,
                receipt_ref=new_id(EntityType.EXECUTION_RECEIPT) if with_reference else None,
            ),
        ),
    )
    # Then no second provider call presents incomplete execution evidence.
    assert result.failed
    assert port.provider_calls == 1
