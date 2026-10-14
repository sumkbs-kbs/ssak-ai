from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path
from typing import Final

import pytest

from antigravity_k.api.contracts.errors import ProjectRootInvalidError
from antigravity_k.engine import request_execution_context as context
from antigravity_k.engine.project_registry import ProjectRegistry

h = importlib.import_module("run_harness")
RUN: Final = Path(__file__).resolve().parent
ROOT: Final = h.resolve_repository_root()


def prepared_run(tmp_path: Path) -> Path:
    run = tmp_path / "owned-run"
    run.mkdir()
    for name in (*h.IMPLEMENTATION_SOURCE_NAMES, "endpoint-contract.json", "runtime-bridge-contract.json", "budgets.json"):
        shutil.copyfile(RUN / name, run / name)
    shutil.copytree(RUN / "fixture", run / "fixture")
    h.prepare_owned_request(ROOT, run, run / "offline-state")
    return run


def test_prepared_project_matches_worker_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = prepared_run(tmp_path)
    state = run / "runtime-state"
    env = h.isolate_worker_environment(state, ROOT)
    binding = json.loads((run / "request.binding.json").read_bytes())
    workspace = (run / binding["project_workspace"]).resolve()
    assert workspace == Path(env["AGK_WORKSPACE_ROOT"])
    assert workspace.is_relative_to(Path(env["AGK_ALLOWED_ROOTS"]))
    assert env["AGK_ALLOWED_ROOTS"] == str(state.resolve())
    assert env["AGK_PATH_PROJECT_ROOT"] == str(state.resolve())
    assert binding["project_registry_path"] == "offline-state/registry/projects.json"
    monkeypatch.setattr(context, "configured_allowed_bases", lambda: (Path(env["AGK_ALLOWED_ROOTS"]),))
    registry = ProjectRegistry(run / binding["project_registry_path"])
    _, canonical = context.resolve_canonical_project_root(binding["project_id"], registry=registry)
    assert canonical == str(workspace)


@pytest.mark.parametrize("target", ["old-offline", "sibling", "prefix-sibling", "symlink"])
def test_outside_projects_remain_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    run = prepared_run(tmp_path)
    state = run / "runtime-state"
    env = h.isolate_worker_environment(state, ROOT)
    external = tmp_path / "external-user-project"
    external.mkdir()
    outside = {
        "old-offline": run / "offline-state/workspace",
        "sibling": external,
        "prefix-sibling": run / "runtime-state-other/workspace",
        "symlink": state / "workspace-link",
    }[target]
    if target == "symlink":
        outside.symlink_to(external, target_is_directory=True)
    else:
        outside.mkdir(parents=True, exist_ok=True)
    binding = json.loads((run / "request.binding.json").read_bytes())
    registry_path = run / binding["project_registry_path"]
    records = json.loads(registry_path.read_bytes())
    records[0]["path"] = str(outside)
    registry_path.write_text(json.dumps(records))
    monkeypatch.setattr(context, "configured_allowed_bases", lambda: (Path(env["AGK_ALLOWED_ROOTS"]),))
    with pytest.raises(ProjectRootInvalidError):
        context.resolve_canonical_project_root(binding["project_id"], registry=ProjectRegistry(registry_path))


def test_read_validation_keeps_frozen_inputs_byte_identical(tmp_path: Path) -> None:
    run = prepared_run(tmp_path)
    paths = [run / name for name in ("request.json", "request.binding.json", "execution-binding.json", "offline-state/registry/projects.json")]
    before = {path: path.read_bytes() for path in paths}
    gate = h.request_gate(run, ROOT)
    assert gate["request_sha256"] == h.sha256(before[run / "request.json"])
    assert {path: path.read_bytes() for path in paths} == before
