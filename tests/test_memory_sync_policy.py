from pathlib import Path

import pytest

from antigravity_k.engine.memory_provider import EpisodicMemoryProvider, MemoryManager
from antigravity_k.engine.tool_policy import ToolPolicy, reset_tool_policy, set_tool_policy


def test_readonly_request_does_not_persist_episode_when_manager_syncs(tmp_path: Path) -> None:
    manager = MemoryManager()
    manager.add_provider(EpisodicMemoryProvider(persist_dir=str(tmp_path)))
    token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        manager.sync_all("numeric test", "42")
    finally:
        reset_tool_policy(token)

    assert not (tmp_path / "episodes.json").exists()


@pytest.mark.parametrize("policy", [None, ToolPolicy(safe_only=False)])
def test_allowed_request_persists_episode_when_manager_syncs(tmp_path: Path, policy: ToolPolicy | None) -> None:
    manager = MemoryManager()
    manager.add_provider(EpisodicMemoryProvider(persist_dir=str(tmp_path)))
    token = set_tool_policy(policy)
    try:
        manager.sync_all("numeric test", "42")
    finally:
        reset_tool_policy(token)

    provider = EpisodicMemoryProvider(persist_dir=str(tmp_path))
    episodes = provider.export("session")
    assert len(episodes) == 1
    assert episodes[0]["user"] == "numeric test"
    assert episodes[0]["assistant"] == "42"
