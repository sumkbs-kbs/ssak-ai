"""Rejected writes must remain failures and must not enter post-write reads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from antigravity_k.engine.code_verifier import DeterministicCodeVerifier
from antigravity_k.engine.tool_call_parser import ToolCall
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure
from antigravity_k.engine.tool_guardrails import ToolCallGuardrailController
from antigravity_k.engine.tool_loop import ToolLoopEngine
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.file_tools import WriteFileTool
from antigravity_k.tools.system_tools import ReadFileTool
from antigravity_k.tools.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_actual_readonly_write_rejection_never_enters_syntax_file_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the real executor rejects a real registered write under read-only policy.
    tools = ToolRegistry(project_root=str(tmp_path))
    tools.install(WriteFileTool())
    executor = ToolExecutor(tools, PermissionGate(project_root=str(tmp_path), mode="balanced"), project_root=str(tmp_path))
    orch = MagicMock()
    orch.project_root = str(tmp_path)
    orch.task_execution_context = None
    orch.ctx = SimpleNamespace(tool_executor=executor, tool_guardrail=ToolCallGuardrailController(), cognitive_loop=None)
    validations: list[str] = []
    original = DeterministicCodeVerifier.verify_file

    def observe_validation(path: str | Path, content: str | None = None):
        validations.append(str(path))
        return original(path, content)

    monkeypatch.setattr(DeterministicCodeVerifier, "verify_file", observe_validation)
    token = set_tool_policy(ToolPolicy(safe_only=True))
    # When: the production tool loop receives that executor's actual BLOCKED response.
    try:
        result = await ToolLoopEngine(orch)._run_tool_task_async(ToolCall(name="write_file", arguments={"file_path": "artifacts/answer.txt", "content": "SYNTHETIC-ANSWER"}), "기억 값만 답해줘.")
    finally:
        reset_tool_policy(token)
    # Then: no phantom file is read or reported as a syntax repair task.
    assert result_indicates_failure(result[3]) is True
    assert validations == []
    assert "FileReadError" not in result[3]
    assert not (tmp_path / "artifacts/answer.txt").exists()


@pytest.mark.parametrize(("value", "failed"), [
    ("There was an error when executing the function: write_file\nHere's the error traceback: [BLOCKED] denied\nPlease continue without this tool.", True),
    ("A saved troubleshooting document:\nThere was an error when executing the function: write_file\nExample only.", False),
    ("Successful file read with error statistics: zero failures.", False),
])
def test_legacy_error_envelope_is_anchored_not_a_substring(value: str, failed: bool) -> None:
    # Given: exact executor failure envelopes versus ordinary successful read content.
    # When / Then: only the actual envelope shape is a failure.
    assert result_indicates_failure(value) is failed


def test_actual_successful_read_containing_error_example_stays_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a synthetic troubleshooting file containing the executor error envelope as data.
    from antigravity_k.config import config

    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    contents = "Troubleshooting example:\nThere was an error when executing the function: write_file\nExample only.\n"
    note = tmp_path / "example.txt"
    note.write_text(contents)
    tools = ToolRegistry(project_root=str(tmp_path))
    tools.install(ReadFileTool())
    executor = ToolExecutor(tools, PermissionGate(project_root=str(tmp_path), mode="balanced"), project_root=str(tmp_path))
    token = set_tool_policy(ToolPolicy(safe_only=True))
    # When: the real safe read tool returns the file under read-only policy.
    try:
        result = executor.execute("read_file", {"file_path": str(note)})
    finally:
        reset_tool_policy(token)
    # Then: data in the body is preserved and classified as a successful read.
    assert result == contents
    assert result_indicates_failure(result) is False
