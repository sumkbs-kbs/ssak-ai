from collections.abc import Iterator, Mapping
from typing import final

from antigravity_k.engine.memory_recorder import MemoryRecorder
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy


@final
class Vault:
    sync_rag: bool = True

    def __init__(self) -> None:
        self.writes: list[str] = []

    def write_note(
        self,
        relative_path: str,
        metadata: Mapping[str, str | list[str]],
        content: str,
        commit_message: str,
    ) -> None:
        _ = metadata, content, commit_message
        self.writes.append(relative_path)


@final
class Manager:
    def __init__(self) -> None:
        self.calls = 0

    def stream_generate(
        self,
        *,
        prompt: str,
        target: str,
        raw_messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]:
        _ = prompt, target, raw_messages, system_prompt
        self.calls += 1
        return iter(["summary"])


def test_read_only_request_skips_memory_summary_and_vault_mutation() -> None:
    vault, manager = Vault(), Manager()
    recorder = MemoryRecorder(vault, manager, lambda role: "selected-model")
    token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        chunks = list(recorder.record("user-task", "answer", "reasoning"))
    finally:
        reset_tool_policy(token)
    assert chunks == []
    assert manager.calls == 0
    assert vault.writes == []

    _ = list(recorder.record("user-task", "answer", "reasoning"))
    assert manager.calls == 1
    assert len(vault.writes) == 1
