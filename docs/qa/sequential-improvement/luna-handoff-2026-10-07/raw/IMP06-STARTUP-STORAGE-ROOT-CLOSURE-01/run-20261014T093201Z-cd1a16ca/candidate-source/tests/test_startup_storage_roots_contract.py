"""Fresh constructor storage boundaries for global memory and collapsed context."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = r"""
import hashlib,importlib,importlib.abc,json,os,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
provider,scenario=sys.argv[2:4]
receipt={"provider":provider,"scenario":scenario,"denied_mutations":[],"socket_attempts":[],"model_import_attempts":[]}
home_before=os.environ.get("HOME")
def audit(event,args):
    paths=[]
    if event=="open":
        path,mode,flags=args
        if isinstance(path,int):return
        if (isinstance(mode,str) and any(c in mode for c in "wax+")) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            paths=[path]
    elif event in ("os.mkdir","os.remove","os.rmdir","os.chmod","os.truncate"):
        paths=[args[0]]
    elif event in ("os.rename","os.link","os.symlink"):
        paths=list(args[:2])
    for path in paths:
        if not Path(os.fsdecode(path)).resolve().is_relative_to(root):
            receipt["denied_mutations"].append({"event":event,"path":str(path)})
            raise AssertionError("Nonowned filesystem mutation: "+str(path))
    if event=="socket.connect":
        receipt["socket_attempts"].append(str(args[1:]))
        raise AssertionError("Physical network forbidden")
sys.addaudithook(audit)
class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".")[0] in {"chromadb","torch","mlx","sentence_transformers","transformers"} or fullname in {"antigravity_k.engine.embeddings","antigravity_k.engine.gbrain"}:
            receipt["model_import_attempts"].append(fullname)
            raise AssertionError("Model/native storage import forbidden: "+fullname)
sys.meta_path.insert(0,NoModels())
envname="AGK_GLOBAL_MEMORY_DIR" if provider=="memory" else "AGK_CONTEXT_STORE_DIR"
legacy=(".antigravity-k","memory") if provider=="memory" else (".antigravity","context_store")
if scenario in ("default","empty_env"):
    Path.home=classmethod(lambda cls:root/"mock-home")
    original_expanduser=os.path.expanduser
    os.path.expanduser=lambda path:str(root/"mock-home") if path=="~" else original_expanduser(path)
    os.environ.pop(envname,None)
    if scenario=="empty_env":os.environ[envname]=""
    expected=root/"mock-home"/Path(*legacy)
elif scenario=="relative_env":
    os.environ[envname]="relative store"
    expected=Path("relative store")
else:
    expected=root/"isolated 저장소"/"nested"
    os.environ[envname]=str(expected)
explicit=None
if scenario=="explicit":
    explicit=str(root/"explicit")
    expected=Path(explicit)
elif scenario=="empty_explicit":explicit=""
try:
    mod=importlib.import_module("antigravity_k.engine.global_memory_provider" if provider=="memory" else "antigravity_k.engine.context_shaper")
    if provider=="memory":
        instance=mod.GlobalMemoryProvider(memory_dir=explicit)
        assert instance._memory_dir==expected
        assert instance._max_entries==200
        instance.set_identity_fact("fixture_name","isolated fixture")
        assert (expected/"identity.json").is_file()
        assert mod.GlobalMemoryProvider(memory_dir=explicit).get_identity_fact("fixture_name")=="isolated fixture"
    else:
        instance=mod.ContextShaper(storage_dir=explicit)
        assert instance.storage_dir==str(expected)
        assert (instance.max_tokens,instance.reserve_tokens,instance.collapse_threshold)==(128000,4096,2000)
        content="owned context fixture "*120
        instance._context_collapse([{"role":"tool","content":content}])
        ref=hashlib.sha256(content.encode()).hexdigest()[:12]
        assert (expected/(ref+".json")).is_file()
        assert mod.ContextShaper(storage_dir=explicit).restore_collapsed(ref)==content
    assert os.environ.get("HOME")==home_before
    assert not receipt["denied_mutations"] and not receipt["socket_attempts"] and not receipt["model_import_attempts"]
    receipt.update(storage_dir=str(expected),home_unchanged=True,round_trip=True,source_path=mod.__file__,source_sha256=hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest())
finally:
    (root/"receipt.json").write_text(json.dumps(receipt,indent=2))
"""


@pytest.mark.parametrize("provider", ["memory", "context"])
@pytest.mark.parametrize("scenario", ["env", "explicit", "empty_explicit", "default", "empty_env", "relative_env"])
def test_fresh_storage_root(tmp_path: Path, provider: str, scenario: str, request: pytest.FixtureRequest):
    repo = Path(__file__).resolve().parents[1]
    child = tmp_path / "probe.py"
    child.write_text(PROBE)
    env = dict(os.environ)
    env.update(PYTHONPATH=str(repo / "src") + os.pathsep + str(repo), PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(tmp_path))
    argv = [sys.executable, str(child), str(tmp_path), provider, scenario]
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, timeout=20)
    evidence = os.environ.get("STARTUP_STORAGE_CAPTURE_ROOT")
    if evidence:
        directory = Path(evidence) / f"{provider}-{scenario}"
        directory.mkdir(parents=True)
        (directory / "stdout.log").write_bytes(result.stdout)
        (directory / "stderr.log").write_bytes(result.stderr)
        (directory / "probe.py").write_text(PROBE)
        (directory / "invocation.json").write_text(
            json.dumps(
                {
                    "nodeid": request.node.nodeid,
                    "argv": argv,
                    "cwd": str(tmp_path),
                    "returncode": result.returncode,
                    "home_changed_by_harness": False,
                    "probe_sha256": hashlib.sha256(PROBE.encode()).hexdigest(),
                },
                indent=2,
            )
        )
        receipt = tmp_path / "receipt.json"
        if receipt.exists():
            (directory / "receipt.json").write_bytes(receipt.read_bytes())
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    module = "global_memory_provider" if provider == "memory" else "context_shaper"
    assert Path(receipt["source_path"]).resolve() == repo / f"src/antigravity_k/engine/{module}.py"
