"""r34: write_artifact resume safety with interruption injection (synthetic tmp dirs only)."""

from __future__ import annotations

import json

import pytest

from antigravity_k.engine import tool_execution_journal as tej
from antigravity_k.engine.artifact_engine import ArtifactEngine
from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.task_runner import is_orchestrator_banner_chunk, join_resume_chunk


class Crash(BaseException):
    pass


@pytest.fixture()
def eng(tmp_path):
    tej.FAULT_HOOK = None
    yield ArtifactEngine(str(tmp_path))
    tej.FAULT_HOOK = None


def _ctx(resuming: bool):
    return tej.CURRENT_TASK.set(("task-syn-1", resuming))


def _crash_at(point: str):
    def hook(p: str) -> None:
        if p == point:
            raise Crash(p)

    return hook


def _writes(eng) -> list[str]:
    path = tej.Journal(eng.artifacts_dir).path
    if not path.exists():
        return []
    return [json.loads(x)["state"] for x in path.read_text().splitlines()]


def _run(eng, content: str, resuming: bool):
    tok = _ctx(resuming)
    try:
        return eng.write_artifact("plan.md", content)
    finally:
        tej.CURRENT_TASK.reset(tok)


def test_completed_write_is_not_rerun_on_resume(eng) -> None:
    assert _run(eng, "v1", False)["success"]
    r = _run(eng, "v1-regenerated-by-llm", True)
    assert r["success"] and "not re-executed" in r["message"]
    assert open(eng.artifacts_dir + "/plan.md").read() == "v1"
    assert _writes(eng) == ["intent", "executed"]


def test_crash_before_exec_is_not_executed_then_written_once(eng) -> None:
    tej.FAULT_HOOK = _crash_at("before_exec")
    with pytest.raises(Crash):
        _run(eng, "v1", False)
    tej.FAULT_HOOK = None
    j = tej.Journal(eng.artifacts_dir)
    assert (
        tej.classify(j, tej.execution_id("task-syn-1", "plan.md"), eng.artifacts_dir + "/plan.md")[0] == "not_executed"
    )
    assert _run(eng, "v1", True)["success"]
    assert open(eng.artifacts_dir + "/plan.md").read() == "v1"


@pytest.mark.parametrize("point", ["after_exec", "after_result"])
def test_crash_after_write_is_completed_and_not_rewritten(eng, point: str) -> None:
    tej.FAULT_HOOK = _crash_at(point)
    with pytest.raises(Crash):
        _run(eng, "v1", False)
    tej.FAULT_HOOK = None
    j = tej.Journal(eng.artifacts_dir)
    assert tej.classify(j, tej.execution_id("task-syn-1", "plan.md"), eng.artifacts_dir + "/plan.md")[0] == "completed"
    r = _run(eng, "different", True)
    assert "not re-executed" in r["message"] and open(eng.artifacts_dir + "/plan.md").read() == "v1"
    assert _writes(eng).count("intent") == 1


def test_checkpoint_save_crash_does_not_cause_rewrite(eng) -> None:
    # The task checkpoint (output/step) is lost, but the journal is independent of it.
    assert _run(eng, "v1", False)["success"]
    # simulate: checkpoint save crashed -> resume restarts from an older checkpoint
    r = _run(eng, "v1", True)
    assert "not re-executed" in r["message"] and _writes(eng).count("intent") == 1


def test_externally_modified_artifact_is_held_unknown(eng) -> None:
    tej.FAULT_HOOK = _crash_at("before_exec")
    with pytest.raises(Crash):
        _run(eng, "v1", False)
    tej.FAULT_HOOK = None
    with open(eng.artifacts_dir + "/plan.md", "w") as fh:
        fh.write("someone else")
    r = _run(eng, "v1", True)
    assert not r["success"] and "side_effect_unknown" in r["error"]
    assert open(eng.artifacts_dir + "/plan.md").read() == "someone else"


def test_no_task_context_is_legacy_overwrite(eng) -> None:
    assert eng.write_artifact("plan.md", "a")["success"] and eng.write_artifact("plan.md", "b")["success"]
    assert open(eng.artifacts_dir + "/plan.md").read() == "b"


def test_banner_filter_only_drops_banner_display_events() -> None:
    assert is_orchestrator_banner_chunk(ProgressChunk("🛡️ **[정밀 엔지니어링 모드]**"))
    assert is_orchestrator_banner_chunk("🏢")
    assert not is_orchestrator_banner_chunk(ProgressChunk("🔧 write_artifact plan.md 실행 중"))
    assert not is_orchestrator_banner_chunk(ProgressChunk("2. 두 번째 항목"))


def test_resume_join_mid_line_verbatim_and_no_duplicate_line() -> None:
    assert join_resume_chunk("s0;s1;", "s2;") == "s2;"  # mid-line cursor: verbatim, no invented newline
    prior = "🏢 회의 요약\n1. 첫 항목\n"
    assert join_resume_chunk(prior, "1. 첫 항목\n2. 둘째") == "2. 둘째"
    assert join_resume_chunk(prior, "2. 둘째") == "2. 둘째"
    # banner chunks are filtered before join; the body then continues on a clean line
    stream = ["🏢", "🛡️ **[정밀 엔지니어링 모드]**", "1. 첫 항목\n2. 둘째\n", "3. 셋째\n"]
    out, skip = prior, True
    for c in stream:
        if skip:
            if is_orchestrator_banner_chunk(c):
                continue
            skip = False
            c = join_resume_chunk(prior, c)
        out += c
    lines = out.splitlines()
    assert lines == ["🏢 회의 요약", "1. 첫 항목", "2. 둘째", "3. 셋째"] and len(set(lines)) == len(lines)
