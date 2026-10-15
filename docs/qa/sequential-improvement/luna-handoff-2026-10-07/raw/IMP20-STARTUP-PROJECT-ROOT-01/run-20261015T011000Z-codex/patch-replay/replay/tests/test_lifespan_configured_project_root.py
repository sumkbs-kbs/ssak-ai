"""Configured startup roots must reach the actual lifespan consumers."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = r"""
import asyncio, hashlib, importlib.abc, json, os, sys, types
from pathlib import Path
root = Path(sys.argv[1]).resolve()
scenario, hook_override = sys.argv[2:4]
receipt = {"rag_roots": [], "ide_roots": [], "hook_roots": [], "audit_roots": [], "bridge_roots": [], "forbidden": []}
def audit(event, args):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen"}:
        receipt["forbidden"].append(event)
        raise AssertionError(event)
sys.addaudithook(audit)
class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"chromadb", "torch", "mlx", "sentence_transformers", "transformers"}:
            receipt["forbidden"].append(fullname)
            raise AssertionError(fullname)
sys.meta_path.insert(0, NoModels())
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["AGK_CONFIG_FILE"] = str(root / "absent.yaml")
os.environ["AGK_ENV_FILE"] = str(root / "absent.env")
os.environ["AGK_SERVER_HOST"] = "127.0.0.1"
if scenario == "default":
    os.environ.pop("AGK_PATH_PROJECT_ROOT", None)
else:
    os.environ["AGK_PATH_PROJECT_ROOT"] = "relative project" if scenario == "relative" else str(root / "owned project")
if hook_override == "explicit":
    os.environ["AGK_HOOK_VAULT_DIR"] = str(root / "separate hooks")
else:
    os.environ.pop("AGK_HOOK_VAULT_DIR", None)
from fastapi import APIRouter, FastAPI
def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    sys.modules[name] = result
module("antigravity_k.api.routes", api_router=APIRouter())
module("antigravity_k.api.auth_routes", router=APIRouter())
module("antigravity_k.api.dependencies", bootstrap_cognitive_active=lambda app: None)
module("antigravity_k.engine.operational_metrics", compute_readiness=lambda: {})
module("antigravity_k.engine.session_manager", SessionPersistenceError=type("SessionPersistenceError", (RuntimeError,), {}))
hook = types.SimpleNamespace(shutdown=lambda: receipt.update(hook_closed=True))
audit_db = types.SimpleNamespace(close=lambda: receipt.update(audit_closed=True))
module("antigravity_k.engine.hook_event_bus", init_hook_event_bus=lambda path: receipt["hook_roots"].append(path), get_hook_event_bus=lambda: hook)
module("antigravity_k.engine.audit_db", init_audit_db=lambda path: receipt["audit_roots"].append(path), get_audit_db=lambda: audit_db)
module("antigravity_k.engine.panel_activity_tracker", init_panel_activity_tracker=lambda: None)
module("antigravity_k.engine.event_bus", bridge_to_hook_event_bus=lambda project_root: receipt["bridge_roots"].append(project_root))
from antigravity_k.engine.rag_indexer import RAGIndexer as RealIndexer
class Indexer:
    def __init__(self, project_root):
        self.project_root = project_root
        receipt["rag_roots"].append(project_root)
    def index_project(self):
        if scenario != "default" and Path(self.project_root).resolve() == configured.resolve():
            receipt["real_rag_chunks"] = RealIndexer(self.project_root).index_project()
            return receipt["real_rag_chunks"]
        return 0
module("antigravity_k.engine.rag_indexer", RAGIndexer=Indexer)
class IDE:
    def __init__(self, port, workspace_dir): receipt["ide_roots"].append(workspace_dir)
    def start(self): receipt["ide_started"] = True
    def stop(self): receipt["ide_closed"] = True
module("antigravity_k.engine.ide_server", IDEServer=IDE)
module("antigravity_k.tools.ssak_search_runtime", shutdown_ssak_search_runtime=lambda: None)
module("antigravity_k.tools.browser_session_owner", shutdown_browser_sessions=lambda: None)
from antigravity_k.api import server
from antigravity_k.config import PROJECT_ROOT, PathConfig
configured = PathConfig().project_root
assert server.config.paths.project_root == configured
if scenario == "default":
    assert configured == PROJECT_ROOT == Path(server.__file__).resolve().parents[3]
else:
    configured.mkdir(parents=True)
    (configured / "one.py").write_text("def owned_fixture():\n    return 1\n")
receipt.update(configured_root=str(configured), source_root=str(Path(server.__file__).resolve().parents[3]), server_sha256=hashlib.sha256(Path(server.__file__).read_bytes()).hexdigest())
async def run():
    app = FastAPI()
    async with server.lifespan(app):
        app.state.rag_index_thread.join(timeout=2)
        assert not app.state.rag_index_thread.is_alive()
try:
    asyncio.run(run())
    assert receipt["rag_roots"] == [str(configured)], receipt
    assert receipt["ide_roots"] == [str(configured)], receipt
    assert receipt["bridge_roots"] == [str(configured)], receipt
    expected_vault = str(root / "separate hooks") if hook_override == "explicit" else str(configured / "vault_data")
    assert receipt["hook_roots"] == receipt["audit_roots"] == [expected_vault], receipt
    if scenario != "default": assert receipt["real_rag_chunks"] == 1
    assert receipt["hook_closed"] and receipt["audit_closed"] and receipt["ide_closed"]
    assert receipt["forbidden"] == []
finally:
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2))
"""


@pytest.mark.parametrize("scenario", ["absolute", "relative", "default"])
@pytest.mark.parametrize("hook_override", ["default", "explicit"])
def test_lifespan_uses_configured_project_root(tmp_path: Path, scenario: str, hook_override: str) -> None:
    # Given an isolated configured project and distinct hook override.
    repo = Path(__file__).resolve().parents[1]
    script = tmp_path / "probe.py"
    script.write_text(PROBE)
    env = dict(os.environ, PYTHONPATH=str(repo / "src") + os.pathsep + str(repo), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, str(script), str(tmp_path), scenario, hook_override]
    # When the real lifespan starts and shuts down with bounded subsystem doubles.
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, timeout=30)
    capture = os.environ.get("CONFIGURED_ROOT_CAPTURE")
    if capture:
        out = Path(capture) / f"{scenario}-{hook_override}"
        out.mkdir(parents=True)
        (out / "stdout.txt").write_bytes(result.stdout)
        (out / "stderr.txt").write_bytes(result.stderr)
        (out / "invocation.json").write_text(json.dumps({"argv": command, "exit_code": result.returncode}))
        if (tmp_path / "receipt.json").exists():
            (out / "receipt.json").write_bytes((tmp_path / "receipt.json").read_bytes())
    # Then every root consumer receives the configured root; only hooks may override it.
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
