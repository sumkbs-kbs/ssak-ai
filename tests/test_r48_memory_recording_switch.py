"""Agent Vault recording opt-out leaves project JSON memory independent."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from antigravity_k.engine.memory_provider import MemoryManager
from antigravity_k.engine.memory_recorder import MemoryRecorder
from antigravity_k.engine.project_memory import ProjectMemoryProvider
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy


class RecordingVault:
    """Narrow downstream write port counting attempted note mutations."""

    def __init__(self, *, sync_rag: bool = True) -> None:
        self.sync_rag = sync_rag
        self.writes: list[str] = []

    def write_note(self, relative_path: str, metadata: Mapping[str, str | list[str]], content: str, commit_message: str) -> None:
        _ = metadata, content, commit_message
        self.writes.append(relative_path)


class RecordingModel:
    """Narrow summarizer port counting requests without a physical provider."""

    def __init__(self) -> None:
        self.calls = 0

    def stream_generate(self, *, prompt: str, target: str, raw_messages: list[dict[str, str]], system_prompt: str) -> Iterator[str]:
        _ = prompt, target, raw_messages, system_prompt
        self.calls += 1
        return iter(["synthetic summary"])


@pytest.fixture(autouse=True)
def isolated_recording_setting(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", raising=False)
    token = set_tool_policy(None)
    try:
        yield
    finally:
        reset_tool_policy(token)


@pytest.mark.parametrize("setting", [None, "true", "1", "yes", "on", " TRUE "])
def test_recording_default_and_explicit_enable_preserve_normal_behavior(monkeypatch: pytest.MonkeyPatch, setting: str | None) -> None:
    # Given: an enabled recording path and a recordable request.
    if setting is not None:
        monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", setting)
    vault, model = RecordingVault(), RecordingModel()
    recorder = MemoryRecorder(vault, model, lambda role: "selected-model")
    # When: the real recorder processes that completed task.
    chunks = list(recorder.record("synthetic request", "synthetic answer", "reasoning"))
    # Then: the existing summary and note-write path remains intact.
    assert model.calls == 1
    assert len(vault.writes) == 1
    assert chunks


@pytest.mark.parametrize("setting", ["false", "0", "no", "off", " FALSE ", "No"])
def test_explicit_opt_out_skips_summary_and_note_write(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    # Given: full access and a recordable type, but explicit recording opt-out.
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", setting)
    vault, model = RecordingVault(), RecordingModel()
    recorder = MemoryRecorder(vault, model, lambda role: "selected-model")
    # When: the recorder is asked to persist that turn.
    chunks = list(recorder.record("synthetic request", "synthetic answer", "coding"))
    # Then: both the extra model call and the potential Git-first write are absent.
    assert chunks == []
    assert model.calls == 0
    assert vault.writes == []


@pytest.mark.parametrize("setting", ["", "unrecognized-option", "2"])
def test_invalid_setting_fails_closed_with_reason_without_raw_value(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, setting: str) -> None:
    # Given: an invalid operational boolean setting.
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", setting)
    vault, model = RecordingVault(), RecordingModel()
    recorder = MemoryRecorder(vault, model, lambda role: "selected-model")
    # When: a normally recordable task completes.
    with caplog.at_level(logging.WARNING, logger="antigravity_k.engine.memory_recorder"):
        chunks = list(recorder.record("synthetic request", "synthetic answer", "complex"))
    # Then: no side effects occur, and the invalid setting has a visible reason.
    assert chunks == []
    assert model.calls == 0
    assert vault.writes == []
    assert any(record.levelno == logging.WARNING and "AGK_AGENT_MEMORY_RECORDING_ENABLED" in record.getMessage() for record in caplog.records)
    if setting:
        assert setting not in caplog.text


@pytest.mark.parametrize("policy_case", [(True, True, "coding"), (False, False, "coding"), (False, True, "simple_chat"), (False, True, "unknown")])
def test_explicit_enable_cannot_override_existing_guards(monkeypatch: pytest.MonkeyPatch, policy_case: tuple[bool, bool, str]) -> None:
    # Given: recording is enabled but an existing request/Vault/type guard denies it.
    safe_only, sync_rag, task_type = policy_case
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", "true")
    vault, model = RecordingVault(sync_rag=sync_rag), RecordingModel()
    recorder = MemoryRecorder(vault, model, lambda role: "selected-model")
    token = set_tool_policy(ToolPolicy(safe_only=safe_only))
    # When: the completed task reaches recording.
    try:
        chunks = list(recorder.record("synthetic request", "synthetic answer", task_type))
    finally:
        reset_tool_policy(token)
    # Then: explicit enable never grants permission that the prior gates denied.
    assert chunks == []
    assert model.calls == 0
    assert vault.writes == []


def test_agent_recording_opt_out_keeps_real_project_json_sync(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: a real project provider under full access and agent Vault opt-out.
    monkeypatch.setenv("AGK_AGENT_MEMORY_RECORDING_ENABLED", "false")
    project = tmp_path / "synthetic-project"
    project.mkdir()
    memory = MemoryManager(project_root=str(project))
    memory.add_provider(ProjectMemoryProvider(project))
    token = set_tool_policy(ToolPolicy(safe_only=False))
    # When: the normal canonical memory manager synchronizes an explicit fact.
    try:
        memory.sync_all("프로젝트 사실: database = CEDAR-4881", "stored")
    finally:
        reset_tool_policy(token)
    # Then: actual JSON persists and a newly constructed provider reloads it.
    payload = json.loads((project / ".antigravity/memory/project_facts.json").read_bytes())
    assert payload["fact:database"]["value"] == "CEDAR-4881"
    facts = ProjectMemoryProvider(project).authoritative_facts()
    assert [(fact.key, fact.value) for fact in facts] == [("project:fact:database", "CEDAR-4881")]
