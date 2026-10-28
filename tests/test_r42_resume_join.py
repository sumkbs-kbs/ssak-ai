"""r42: resume continuation is fed to the direct-response generator (root cause of the r41 A-b
duplicate), exact-only join check, verified artifact facts, ledger aborted_unknown on stop."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from antigravity_k.engine import call_ledger
from antigravity_k.engine import task_tool_contract as ttc
from antigravity_k.engine.task_execution_context import (
    TaskExecutionContext,
    bind_task_execution_context,
    resume_output_prefix,
)
from antigravity_k.engine.task_runner import ResumeJoiner, _verified_artifact_block, resume_join_issue
from antigravity_k.engine.tool_loop import _resume_delivered_output
from tests.test_tool_loop import _engine, _mock_call_args, _set_mock_return, mock_orch  # noqa: F401

PRIOR = "R42 인사 목록 (direct)\n1. 안녕 친구 🌈 빨강\n2. 안녕 친구 🎨 파랑\n3. 반가워요 친구, 초록"  # stops mid-line


class _Store:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def get_last_checkpoint(self, task_id: str) -> None:
        return None

    def append_execution_event(self, task_id: str, event_type: str, payload_json: str) -> int:
        self.events.append({"task_id": task_id, "event_type": event_type, "payload_json": payload_json})
        return len(self.events)

    def list_execution_events(self, task_id: str) -> list[dict[str, object]]:
        return [e for e in self.events if e["task_id"] == task_id]


def _direct_prompt(orch: MagicMock, task_id: str | None, owner: str, prefix: str) -> str:
    _set_mock_return(orch, ("manager", "router", "get_combo"), None)
    _set_mock_return(orch, ("manager", "generate"), "rest")
    token = resume_output_prefix.set((owner, prefix))
    try:
        run = lambda: list(  # noqa: E731
            _engine(orch).run_loop(
                [{"role": "user", "content": "write greetings"}, {"role": "assistant", "content": prefix}],
                "SELF",
                "chat",
                target_model="qwen3.8:latest",
                direct_response=True,
            )
        )
        if task_id:
            with bind_task_execution_context(TaskExecutionContext(task_id=task_id, state_store=_Store())):
                run()
        else:
            run()
    finally:
        resume_output_prefix.reset(token)
    _, kwargs = _mock_call_args(orch, ("manager", "generate"))
    return str(kwargs["prompt"])


def test_direct_prompt_carries_delivered_output_for_owning_task(mock_orch: MagicMock) -> None:  # noqa: F811
    prompt = _direct_prompt(mock_orch, "t-own", "t-own", PRIOR)
    assert "<<<DELIVERED\n" + PRIOR + "\nDELIVERED>>>" in prompt
    assert "Return only the continuation" in prompt and prompt.rstrip().endswith("Continuation:")
    assert "Return the complete final answer" not in prompt


@pytest.mark.parametrize(("task_id", "owner"), [("t-other", "t-own"), (None, "t-own")])
def test_direct_prompt_ignores_prefix_of_another_task(mock_orch: MagicMock, task_id: str | None, owner: str) -> None:  # noqa: F811
    prompt = _direct_prompt(mock_orch, task_id, owner, PRIOR)
    assert "DELIVERED" not in prompt and "Return the complete final answer" in prompt


def test_delivered_helper_requires_owner_match() -> None:
    token = resume_output_prefix.set(("a", "x"))
    try:
        assert _resume_delivered_output() == ""
        with bind_task_execution_context(TaskExecutionContext(task_id="a", state_store=_Store())):
            assert _resume_delivered_output() == "x"
    finally:
        resume_output_prefix.reset(token)


@pytest.mark.parametrize(
    ("new", "issue"),
    [
        (" 🌳\n4. 안녕 친구 💜 보라\n", None),  # mid-line continuation, emoji / Korean
        ("\n4. 같은 인사 반복\n5. 2. 안녕 친구 🎨 파랑\n", None),
        ("\n2. 안녕 친구 🎨 파랑\n9. 새 줄\n", None),  # one legitimately repeated sentence
        ("\nR42 인사 목록 (direct)\n1. 안녕 친구 🌈 빨강\n", "restarts"),  # model regenerated from the top
        ("\n1. 안녕 친구 🌈 빨강\n2. 안녕 친구 🎨 파랑\n3. 반가워요 친구, 초록\n", "repeats"),
    ],
)
def test_resume_join_issue_exact_only(new: str, issue: str | None) -> None:
    got = resume_join_issue(PRIOR, PRIOR + new)
    assert (got is None) if issue is None else (got is not None and issue in got)


def test_resume_join_issue_prefix_not_extended_and_utf8_boundary() -> None:
    assert resume_join_issue(PRIOR, "다른 출력") is not None
    assert resume_join_issue("", "x") is None
    prior = "줄 하나 🌈"  # cursor after a 4-byte emoji, str-level (never bytes)
    assert resume_join_issue(prior, prior + "🎨 끝") is None
    joiner = ResumeJoiner(PRIOR)
    out = joiner.feed("3. 반가워요 친구, 초록") + joiner.feed("색 🌳\n4. 다음\n") + joiner.flush()
    assert out == "색 🌳\n4. 다음\n" and joiner.dropped_chars == len("3. 반가워요 친구, 초록")


def test_resume_join_duplicate_chunk_events_not_double_appended() -> None:
    joiner = ResumeJoiner(PRIOR)
    first = joiner.feed("3. 반가워요 친구, 초록 🌳\n")
    assert first == " 🌳\n"  # exact partial restart dropped once
    assert joiner.feed("3. 반가워요 친구, 초록 🌳\n") == "3. 반가워요 친구, 초록 🌳\n"  # later text verbatim


def _record(store: _Store, task_id: str, path: Path) -> None:
    ttc.record_completed(
        store, task_id, "write_artifact", "k1", f"[ARTIFACT GENERATED: x]\nSuccessfully saved to {path}. "
    )


def test_verified_block_uses_real_file_and_flags_mismatch(tmp_path: Path) -> None:
    f = tmp_path / "artifacts" / "r42-a-record.md"
    f.parent.mkdir()
    f.write_bytes("r42 합성\nline-1 🟠\n".encode())
    store = _Store()
    _record(store, "t1", f)
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    block = _verified_artifact_block(store, "t1", "산출물 sha256 deadbeef1234, 길이 148자")
    assert digest in block and f"{f.stat().st_size} bytes" in block and "chars" in block
    assert "불일치" in block and "deadbeef1234" in block
    ok = _verified_artifact_block(store, "t1", f"sha256: {digest[:16]}")
    assert "불일치" not in ok
    assert _verified_artifact_block(store, "other", "") == ""


def test_verified_block_unreadable_or_symlink_is_unknown(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_text("x")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    store = _Store()
    _record(store, "t2", link)
    _record(store, "t3", tmp_path / "missing.md")
    assert "확인 불가" in _verified_artifact_block(store, "t2", "")
    block = _verified_artifact_block(store, "t3", "")
    assert "확인 불가" in block and "sha256 `" not in block


def test_write_artifact_result_has_verified_file(tmp_path: Path) -> None:
    from antigravity_k.tools.artifact_tools import WriteArtifactTool

    out = str(WriteArtifactTool(project_root=str(tmp_path)).execute(artifact_name="v.md", content="합성 🌈\n"))
    data = (tmp_path / "artifacts" / "v.md").read_bytes()
    assert f"[VERIFIED FILE] sha256={hashlib.sha256(data).hexdigest()} bytes={len(data)}" in out


def test_ledger_abort_open_marks_aborted_unknown_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(call_ledger.LEDGER_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(call_ledger.LIMIT_ENVS["llm"], "5")
    (tmp_path / "llm.count").write_text("0")
    n1 = call_ledger.reserve("llm")
    call_ledger.mark("llm", n1, "dispatched", {"purpose": "bg"})
    n2 = call_ledger.reserve("llm")
    call_ledger.mark("llm", n2, "dispatched")
    call_ledger.mark("llm", n2, "succeeded")
    assert ("llm", n1) in call_ledger.open_reservations()
    assert call_ledger.abort_open("server_shutdown") == 1
    assert call_ledger.abort_open("server_shutdown") == 0  # idempotent, nothing re-sent
    assert (tmp_path / "llm.count").read_text() == "2"
    s = call_ledger.summary("llm", str(tmp_path))
    assert s.get("aborted_unknown") == 1 and s.get("succeeded") == 1
    recs = [json.loads(x) for x in (tmp_path / "llm.journal").read_text().splitlines()]
    assert [r["state"] for r in recs if r["n"] == n1][-1] == "aborted_unknown"
    assert os.environ[call_ledger.LEDGER_DIR_ENV] == str(tmp_path)


def test_resumed_loop_counts_really_completed_side_effect_tools(mock_orch: MagicMock) -> None:  # noqa: F811
    store = _Store()
    ttc.record_completed(store, "t9", "write_artifact", "k1", "Successfully saved to /x. ")
    mock_orch.task_execution_context = TaskExecutionContext(task_id="t9", state_store=store)
    used, _evidence = _engine(mock_orch)._resumed_tool_loop_state()
    assert used == ["write_artifact"]
    mock_orch.task_execution_context = TaskExecutionContext(task_id="other", state_store=store)
    assert _engine(mock_orch)._resumed_tool_loop_state()[0] == []
