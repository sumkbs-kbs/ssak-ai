"""Live inference consumes bounded real canonical content without evaluator secrets."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.growth import ArmRole, GrowthBenchmarkError, default_corpus_tasks
from antigravity_k.engine.cognitive.live_context import model_task
from antigravity_k.engine.cognitive.live_pilot import LiveTrialRequest, TrialOrder
from antigravity_k.engine.cognitive.live_trial_adapter import LiveTrialAdapter, ScriptedModelPort
from antigravity_k.engine.cognitive.models import ContextPackagePayload
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port


class CaptureModel(ScriptedModelPort):
    def __post_init__(self):
        self.inputs = []

    def choose(self, request, task, **kwargs):
        if not hasattr(self, "inputs"):
            self.inputs = []
        self.inputs.append(task)
        return super().choose(request, task, **kwargs)


def test_model_receives_selected_actual_train_readback_and_payload(tmp_path: Path) -> None:
    model = CaptureModel()
    adapter = LiveTrialAdapter(tmp_path, model, fixture_tool_port)
    adapter.run_train_validation()
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.MATURE, 0, TrialOrder.FRESH_FIRST, None, ())
    adapter.run_trial(request)
    wire = json.loads(model.inputs[-1].context_json)
    assert wire["history"]
    assert any(
        entry["payload"]["episode_reference"].startswith("live-observed:TRAIN:")
        for entry in wire["history"]
        if entry["entity_type"] == "Experience"
    )
    lineage = wire["selected_experience_observed_lineage"]
    assert any(entry["payload"].get("raw_measurement_or_handle") == json.dumps("GT-T2 appended\n") for entry in lineage)
    assert any(entry["payload"].get("observed") == "GT-T2 appended\n" for entry in lineage)
    assert all(entry["payload"] for entry in wire["evidence"])


def test_private_oracle_never_enters_rendered_model_context(tmp_path: Path) -> None:
    tasks = list(default_corpus_tasks())
    task = replace(tasks[0], append_content="PRIVATE_APPEND_ORACLE", expected_outcome="PRIVATE_EXPECTED_ORACLE")
    tasks[0] = task
    model = CaptureModel()
    adapter = LiveTrialAdapter(tmp_path, model, fixture_tool_port, tasks=tasks)
    adapter.run_trial(
        LiveTrialRequest(task.task_id, task.split.value, ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    )
    assert all("PRIVATE_" not in entry.context_json for entry in model.inputs)


def test_complete_context_overflow_refuses_before_provider(tmp_path: Path) -> None:
    model = CaptureModel()
    adapter = LiveTrialAdapter(tmp_path, model, fixture_tool_port)
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    adapter.run_trial(request)
    store = adapter._seed(adapter.arm_root(ArmRole.FRESH))
    record = next(record for record in store.list_committed() if isinstance(record.payload, ContextPackagePayload))
    calls = model.calls
    with pytest.raises(GrowthBenchmarkError, match="context unavailable|byte budget"):
        visible = model_task("PT-01", record, store, limit=100)
        model.choose(request, visible, missing_refs=(), workspace=tmp_path)
    assert model.calls == calls
