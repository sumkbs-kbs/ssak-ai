from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REL = Path("docs/qa/2026-09-16-followup/nx10")


def fixture_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "candidate"
    root.mkdir()
    (root / REL).mkdir(parents=True)
    (root / "scripts").mkdir()
    for name in ("run_nx10_soak.sh", "schedule_nx10_soak.sh"):
        shutil.copy2(REPO / REL / name, root / REL / name)
    shutil.copy2(REPO / "scripts/soak_control.sh", root / "scripts/soak_control.sh")
    for rel in ("src/antigravity_k", "src/antigravity_k/engine", ".venv/bin"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("")
    for rel in ("src/antigravity_k/__init__.py", "src/antigravity_k/engine/__init__.py"):
        (root / rel).write_text("")
    (root / "src/antigravity_k/engine/conversation_retention.py").write_text(
        "from types import SimpleNamespace\ndef resolve_policy(): return SimpleNamespace(soft_cap_bytes=1048576,hard_cap_bytes=8388608)\n"
    )
    (root / "scripts/ga_gate.py").write_text("def worktree_fingerprint(root): return 'fixture-fingerprint'\n")
    (root / ".venv/bin/python").symlink_to(Path(sys.executable).resolve())
    (root / "scripts/val02_staging.py").write_text(
        "import json,os,sys,pathlib\npathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps({'cwd':os.getcwd(),'argv':sys.argv,'python':sys.executable,'fixture':True}))\n"
    )
    guard = tmp_path / "shell-guard.sh"
    guard.write_text(
        'cd() { if [ "$1" = "--" ]; then shift; fi; case "$1" in "$ALLOWED_FIXTURE_ROOT"*) builtin cd "$@" ;; *) printf "blocked foreign checkout: %s\\n" "$1" >&2; exit 73 ;; esac; }\n'
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("NX10_") and k not in ("SOAK_SECONDS", "BASH_ENV")}
    env.update(BASH_ENV=str(guard), ALLOWED_FIXTURE_ROOT=str(root), NX10_NO_CAFFEINATE="1", SOAK_SECONDS="1")
    return root, env


def invoke(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-x", str(script), *args], env=env, capture_output=True, text=True, timeout=15, check=False
    )


def test_runner_defaults_to_its_candidate_and_creates_a_fresh_output_parent(tmp_path: Path) -> None:
    root, env = fixture_repo(tmp_path)
    out = tmp_path / "fresh-output"
    env["NX10_OUT"] = str(out)
    result = invoke(root / REL / "run_nx10_soak.sh", env)
    assert result.returncode == 0, result.stderr
    response = json.loads((out / "soak-1.json").read_text())
    assert response["fixture"] and response["cwd"] == str(root)
    assert not (out / ".soak-run.lock").exists()


@pytest.mark.parametrize("output_key", ["NX10_OUT", "NX10_SOAK_OUT_DIR"])
def test_runner_explicit_candidate_and_interpreter_keep_outputs_owned(tmp_path: Path, output_key: str) -> None:
    root, env = fixture_repo(tmp_path)
    out = tmp_path / "alternate-output"
    interpreter = root / "alternate-python"
    interpreter.symlink_to((root / ".venv/bin/python").resolve())
    shutil.rmtree(root / ".venv")
    env.update(NX10_REPO=str(root), NX10_PYTHON=str(interpreter))
    env[output_key] = str(out)
    result = invoke(root / REL / "run_nx10_soak.sh", env)
    assert result.returncode == 0, result.stderr
    response = json.loads((out / "soak-1.json").read_text())
    assert response["cwd"] == str(root)
    assert str(interpreter) in (out / "soak-exit.txt").read_text()


def test_scheduler_resolves_candidate_runner_independently_of_evidence_directory(tmp_path: Path) -> None:
    root, env = fixture_repo(tmp_path)
    out = tmp_path / "scheduler-output"
    env.update(NX10_OUT=str(out), NX10_SCHEDULE_DRY_RUN="1")
    result = invoke(root / REL / "schedule_nx10_soak.sh", env)
    assert result.returncode == 0, result.stderr
    assert "RUNNER=" + str(root / REL / "run_nx10_soak.sh") in result.stderr
    assert not (out / "soak-1.json").exists()


def test_controller_status_uses_candidate_scripts_for_fresh_output(tmp_path: Path) -> None:
    root, env = fixture_repo(tmp_path)
    out = tmp_path / "controller-output"
    env.update(
        NX10_OUT=str(out),
        NX10_SCHED_PATTERN="no-such-fixture-scheduler",
        NX10_SOAK_PROC_PATTERN="no-such-fixture-worker",
    )
    result = invoke(root / "scripts/soak_control.sh", env, "status")
    assert result.returncode == 1, result.stderr
    assert "ATTENTION" in result.stdout
    assert "RUNNER=" + str(root / REL / "run_nx10_soak.sh") in result.stderr
    assert "SCHEDULER=" + str(root / REL / "schedule_nx10_soak.sh") in result.stderr


@pytest.mark.parametrize("name", ["run_nx10_soak.sh", "schedule_nx10_soak.sh"])
def test_missing_explicit_interpreter_stops_before_any_harness(tmp_path: Path, name: str) -> None:
    root, env = fixture_repo(tmp_path)
    out = tmp_path / "blocked-output"
    env.update(NX10_PYTHON=str(root / "missing-python"), NX10_OUT=str(out))
    result = invoke(root / REL / name, env)
    assert result.returncode == 2
    assert "Candidate interpreter unavailable" in result.stderr
    assert not out.exists()
