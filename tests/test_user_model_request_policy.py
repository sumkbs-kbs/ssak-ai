from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

import pytest

_SOURCE_ROOT: Final = Path(__file__).resolve().parents[1] / "src"
_SETUP: Final = """
import json
import logging
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

logging.disable(logging.CRITICAL)
home_patch = patch.object(Path, "home", return_value=Path.cwd())
home_patch.start()
source_root = Path(sys.argv[1])
for name, relative in (
    ("antigravity_k", "antigravity_k"),
    ("antigravity_k.engine", "antigravity_k/engine"),
    ("antigravity_k.tools", "antigravity_k/tools"),
):
    package = ModuleType(name)
    package.__path__ = [str(source_root / relative)]
    sys.modules[name] = package
# Keep real GraphML persistence without invoking optional vector embeddings.
sys.modules["chromadb"] = None
from antigravity_k.engine.tool_policy import (
    ToolPolicy, request_allows_side_effects, reset_tool_policy, set_tool_policy,
)
policy = {
    "read-only": ToolPolicy(safe_only=True),
    "allowed": ToolPolicy(safe_only=False),
    "unscoped": None,
}[sys.argv[2]]
token = set_tool_policy(policy)
from antigravity_k.engine.user_model import UserIntentModeler, global_gbrain
assert global_gbrain.storage_dir == Path.cwd() / ".antigravity" / "gbrain"
modeler = UserIntentModeler(project_root=str(Path.cwd() / "project"))
profile_path = Path(modeler._profile_path)
"""


def _run_profile_scenario(mode: str, scenario: str) -> None:
    with tempfile.TemporaryDirectory(prefix="ssak-profile-policy-") as temporary:
        result = subprocess.run(
            [sys.executable, "-B", "-", str(_SOURCE_ROOT), mode],
            input=_SETUP + scenario,
            text=True,
            capture_output=True,
            cwd=temporary,
            env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=30,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["read-only", "allowed", "unscoped"])
def test_fifth_observation_persists_profile_only_when_request_allows_effects(mode: str) -> None:
    # Given: a fresh isolated profile, graph and active request policy.
    _run_profile_scenario(
        mode,
        """
try:
    for _ in range(4):
        modeler.observe("Synthetic architecture refactor", "analysis", ["read_file"])
    assert not profile_path.exists()
    assert not global_gbrain.graph_file.exists()
    # When: the fifth observation reaches the shared durable persistence seam.
    modeler.observe("Synthetic architecture refactor", "analysis", ["read_file"])
    # Then: session learning remains active in every mode.
    assert modeler._profile["stats"]["language_pref"]["english"] == 5
    assert modeler._profile["tool_preferences"]["read_file"] == 5
    allows_writes = request_allows_side_effects()
    assert profile_path.exists() == allows_writes, "READ_ONLY created profile JSON"
    assert profile_path.parent.exists() == allows_writes
    assert global_gbrain.graph_file.exists() == allows_writes, "READ_ONLY created graph snapshot"
    assert global_gbrain.graph.has_node("user_profile_main") == allows_writes
    assert global_gbrain.reward_tick == int(allows_writes)
    assert ("updated_at" in modeler._profile) == allows_writes
    if allows_writes:
        persisted = json.loads(profile_path.read_text())
        assert persisted["stats"]["language_pref"]["english"] == 5
        from antigravity_k.engine.gbrain import GBrain
        reader = GBrain(storage_dir=str(global_gbrain.storage_dir))
        try:
            assert json.loads(reader.graph.nodes["user_profile_main"]["content"]) == persisted
        finally:
            reader.close()
finally:
    reset_tool_policy(token)
    global_gbrain.close()
    home_patch.stop()
""",
    )


def test_read_only_direct_save_skips_durable_profile_mutation() -> None:
    _run_profile_scenario(
        "read-only",
        """
try:
    # When: any caller reaches the persistence method directly.
    modeler._save_profile()
    # Then: the shared seam blocks all profile persistence operations.
    assert not profile_path.parent.exists()
    assert not global_gbrain.graph_file.exists()
    assert global_gbrain.reward_tick == 0
    assert "updated_at" not in modeler._profile
finally:
    reset_tool_policy(token)
    global_gbrain.close()
    home_patch.stop()
""",
    )


def test_read_only_preserves_existing_profile_and_allows_later_session_learning_save() -> None:
    _run_profile_scenario(
        "allowed",
        """
try:
    # Given: permitted observations have persisted both profile projections.
    for _ in range(5):
        modeler.observe("Synthetic architecture refactor", "analysis")
    profile_before = profile_path.read_bytes()
    graph_before = global_gbrain.graph_file.read_bytes()
    updated_before = modeler._profile["updated_at"]
    read_only_token = set_tool_policy(ToolPolicy(safe_only=True))
    try:
        # When: five READ_ONLY observations continue learning in the same modeler.
        for _ in range(5):
            modeler.observe("I always prefer concise answers", "analysis")
        assert modeler._profile["stats"]["language_pref"]["english"] == 10
        assert modeler._explicit_preferences["response_detail"] == "concise"
        # Then: prior durable bytes and timestamps remain unchanged.
        assert profile_path.read_bytes() == profile_before
        assert global_gbrain.graph_file.read_bytes() == graph_before
        assert modeler._profile["updated_at"] == updated_before
        assert global_gbrain.reward_tick == 1
    finally:
        reset_tool_policy(read_only_token)
    # When: a later permitted request reaches the next save interval.
    for _ in range(5):
        modeler.observe("Synthetic architecture refactor", "analysis")
    # Then: allowed-mode persistence retains accumulated session learning.
    persisted = json.loads(profile_path.read_text())
    assert persisted["stats"]["language_pref"]["english"] == 15
    assert global_gbrain.reward_tick == 2
    assert json.loads(global_gbrain.graph.nodes["user_profile_main"]["content"]) == persisted
finally:
    reset_tool_policy(token)
    global_gbrain.close()
    home_patch.stop()
""",
    )
