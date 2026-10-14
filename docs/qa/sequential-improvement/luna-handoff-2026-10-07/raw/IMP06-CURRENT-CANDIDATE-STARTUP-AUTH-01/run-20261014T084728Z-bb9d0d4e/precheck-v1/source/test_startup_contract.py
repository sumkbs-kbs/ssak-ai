# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest", "pydantic>=2"]
# ///
# Offline only: python -m pytest test_startup_contract.py
"""Pure contract checks; no product import, socket, HTTP, Chroma, or process launch."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from startup_contract import (
    Cleanup,
    ProbeError,
    SourcePlan,
    Started,
    child_environment,
    digest,
    remaining,
    require_approval,
    verify_sources,
)
from startup_guard import Guard


@pytest.fixture
def plan(tmp_path: Path) -> SourcePlan:
    source = tmp_path / "candidate/src/app.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = '0.1.0'\n")
    dotenv = tmp_path / "dotenv.py"
    dotenv.write_text("PYTHON_DOTENV_DISABLED\n")
    return SourcePlan(
        candidate=tmp_path / "candidate",
        candidate_head="frozen",
        app_version="0.1.0",
        python=Path("/existing/venv/bin/python"),
        source_hashes={"src/app.py": digest(source)},
        dotenv_path=dotenv,
        dotenv_sha256=digest(dotenv),
    )


def test_environment_strips_credentials_and_preserves_home(plan: SourcePlan, tmp_path: Path) -> None:
    parent = {
        "HOME": "/original/home",
        "CODEX_HOME": "/secret/config",
        "OPENAI_API_KEY": "secret",
        "HTTP_PROXY": "http://proxy",
        "PYTHONPATH": "/untrusted",
    }
    env = child_environment(parent, plan, tmp_path, "temporary")
    assert env["HOME"] == parent["HOME"]
    assert not set(("CODEX_HOME", "OPENAI_API_KEY", "HTTP_PROXY")) & env.keys()
    assert env["PYTHONPATH"] == str(plan.candidate / "src")
    assert env["PYTHON_DOTENV_DISABLED"] == "1"
    assert env["AGK_SEC_DEV_NO_PIN_ALLOW"] == "false"
    assert env["AGK_AUTO_DISCOVER_LOCAL_MODELS"] == "false"
    assert env["PATH"] == "/usr/bin:/bin"


def test_all_configured_storage_is_owned(plan: SourcePlan, tmp_path: Path) -> None:
    env = child_environment({}, plan, tmp_path, "temporary")
    keys = [key for key in env if key.startswith("AGK_PATH_")]
    keys += [
        "AGK_CONFIG_FILE",
        "AGK_ENV_FILE",
        "AGK_SEC_PIN_HASH_FILE",
        "AGK_SEC_TOKEN_SECRET_FILE",
        "AGK_HOOK_VAULT_DIR",
        "ANTIGRAVITY_VAULT_PATH",
        "TMPDIR",
    ]
    assert all(Path(env[key]).is_relative_to(tmp_path) for key in keys)
    assert len([key for key in keys if key.startswith("AGK_PATH_")]) == 7


def test_source_drift_rejected_before_execution(plan: SourcePlan) -> None:
    verify_sources(plan)
    (plan.candidate / "src/app.py").write_text("changed")
    with pytest.raises(ProbeError, match="Candidate source drift"):
        verify_sources(plan)


def test_dotenv_drift_rejected(plan: SourcePlan) -> None:
    plan.dotenv_path.write_text("no switch")
    with pytest.raises(ProbeError, match="dotenv"):
        verify_sources(plan)


@pytest.mark.parametrize(("now", "expected"), [(0, 5), (8, 2)])
def test_deadline_caps_remaining_timeout(now: float, expected: float) -> None:
    assert remaining(10, now, 5) == expected


@pytest.mark.parametrize("now", [10, 11])
def test_expired_deadline_refuses_work(now: float) -> None:
    with pytest.raises(ProbeError):
        remaining(10, now, 5)


@pytest.mark.parametrize(
    "cleanup",
    [
        Cleanup(1, True, True, False),
        Cleanup(0, False, True, False),
        Cleanup(0, True, False, False),
        Cleanup(0, True, True, True),
        Cleanup(None, False, False, True),
    ],
)
def test_partial_cleanup_never_passes(cleanup: Cleanup) -> None:
    assert not cleanup.passed()


def test_observed_clean_reap_passes() -> None:
    assert Cleanup(0, True, True, False).passed()


def test_approval_binds_source_and_harness(plan: SourcePlan, tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json())
    harness = tmp_path / "entry.py"
    harness.write_text("pass\n")
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "scope": "STARTUP_AUTH_ONCE",
                "plan_sha256": digest(plan_path),
                "harness_sha256": {harness.name: digest(harness)},
            }
        )
    )
    require_approval(plan_path, approval, [harness])
    harness.write_text("changed\n")
    with pytest.raises(ProbeError, match="harness"):
        require_approval(plan_path, approval, [harness])


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_reported_port_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Started(pid=123, port=port, version="0.1.0", app_source=Path("/src/server.py"), lifespan="on")


def test_guard_allows_only_one_owned_loopback_bind(tmp_path: Path) -> None:
    guard = Guard(tmp_path)
    guard.audit("socket.bind", (None, ("127.0.0.1", 0)))
    with pytest.raises(ProbeError):
        guard.audit("socket.bind", (None, ("127.0.0.1", 0)))
    assert guard.binds == 1


@pytest.mark.parametrize("address", [("0.0.0.0", 0), ("127.0.0.1", 8080), ("example.com", 443)])
def test_guard_refuses_other_bind(tmp_path: Path, address: tuple[str, int]) -> None:
    with pytest.raises(ProbeError):
        Guard(tmp_path).audit("socket.bind", (None, address))


def test_guard_refuses_outbound_even_loopback(tmp_path: Path) -> None:
    guard = Guard(tmp_path)
    with pytest.raises(ProbeError):
        guard.audit("socket.connect", (None, ("127.0.0.1", 11434)))
    assert len(guard.violations) == 1


def test_guard_refuses_nonowned_writes(tmp_path: Path) -> None:
    guard = Guard(tmp_path)
    guard.audit("open", (str(tmp_path / "local"), "w", 0))
    with pytest.raises(ProbeError):
        guard.audit("open", ("/outside/shared.db", "w", 0))
