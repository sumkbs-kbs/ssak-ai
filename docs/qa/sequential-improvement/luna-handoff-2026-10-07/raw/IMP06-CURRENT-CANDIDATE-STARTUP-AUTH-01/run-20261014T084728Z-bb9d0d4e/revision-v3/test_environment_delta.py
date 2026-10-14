"""Owned environment delta; no product import or external execution."""

from pathlib import Path

import pytest
from startup_probe.contract import SourcePlan, child_environment

KEYS = {
    "AGK_GBRAIN_DIR": "gbrain",
    "AGK_GLOBAL_MEMORY_DIR": "global-memory",
    "AGK_CONTEXT_STORE_DIR": "context-store",
    "AGK_CONVERSATION_STORE_DIR": "conversations",
    "AGK_TASK_DB_PATH": "data/tasks.db",
    "AGK_BENCHMARK_DB": "data/benchmarks.db",
}


@pytest.mark.parametrize(("key", "relative"), KEYS.items())
def test_owned_override_replaces_parent(key: str, relative: str, tmp_path: Path) -> None:
    plan = SourcePlan(
        candidate=Path("/candidate"),
        candidate_head="pending",
        app_version="0.1.0",
        python=Path("/venv/bin/python"),
        source_hashes={},
        dotenv_path=Path("/dotenv.py"),
        dotenv_sha256="pending",
    )
    parent = {"HOME": "/unchanged/home", key: "/untrusted/shared", "AGK_STATE": "/unsupported"}
    env = child_environment(parent, plan, tmp_path, "fixture-only")
    assert env[key] == str(tmp_path / relative)
    assert Path(env[key]).is_absolute() and Path(env[key]).is_relative_to(tmp_path)
    assert env["HOME"] == parent["HOME"]
    assert "AGK_STATE" not in env
    assert not (tmp_path / relative).exists()
