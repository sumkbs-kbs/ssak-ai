"""Fresh-process storage-root precedence without touching the user's GBrain."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = r"""
import hashlib,json,os,socket,sys,types
from pathlib import Path
root=Path(sys.argv[1]).resolve()
scenario=sys.argv[2]
receipt={"scenario":scenario,"denied_mutations":[],"socket_attempts":[],"embedding_attempts":[],"client_paths":[],"home_unchanged":False}
original_home=os.environ.get("HOME")
def owned(value):
    return isinstance(value,(str,bytes,os.PathLike)) and Path(os.fsdecode(value)).resolve().is_relative_to(root)
def audit(event,args):
    paths=[]
    if event=="open":
        path,mode,flags=args
        if isinstance(path,int): return
        if (isinstance(mode,str) and any(c in mode for c in "wax+")) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            paths=[path]
    elif event in ("os.mkdir","os.remove","os.rmdir","os.chmod","os.chown","os.truncate"):
        paths=[args[0]]
    elif event in ("os.rename","os.link","os.symlink"):
        paths=list(args[:2])
    for path in paths:
        if not owned(path):
            receipt["denied_mutations"].append({"event":event,"path":str(path)})
            raise AssertionError("Nonowned filesystem mutation: "+str(path))
    if event=="socket.connect":
        receipt["socket_attempts"].append(str(args[1:]))
        raise AssertionError("Physical network forbidden")
sys.addaudithook(audit)
def deny_embedding(*args,**kwargs):
    receipt["embedding_attempts"].append("default embedding/download")
    raise AssertionError("Inference/download forbidden")
if scenario != "native_import":
    fake=types.ModuleType("chromadb")
    config=types.ModuleType("chromadb.config")
    shared=types.ModuleType("chromadb.api.shared_system_client")
    def client(*,path,settings):
        assert owned(path)
        receipt["client_paths"].append(path)
        return types.SimpleNamespace(close=lambda:None,get_or_create_collection=lambda **kwargs:types.SimpleNamespace())
    fake.PersistentClient=client
    config.Settings=lambda **kwargs: object()
    shared.SharedSystemClient=types.SimpleNamespace(clear_system_cache=lambda:None)
    sys.modules.update({"chromadb":fake,"chromadb.config":config,"chromadb.api.shared_system_client":shared})
else:
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    def deny_default(self,input):
        return deny_embedding(self,input)
    DefaultEmbeddingFunction.__call__=deny_default
    ONNXMiniLM_L6_V2._download_model_if_not_exists=deny_embedding
    original_client=chromadb.PersistentClient
    def client(*,path,settings):
        assert owned(path)
        receipt["client_paths"].append(path)
        return original_client(path=path,settings=settings)
    chromadb.PersistentClient=client
    receipt["chroma_version"]=chromadb.__version__
if scenario in ("default","empty_env"):
    Path.home=classmethod(lambda cls: root/"mock-home")
    os.environ.pop("AGK_GBRAIN_DIR",None)
    if scenario=="empty_env": os.environ["AGK_GBRAIN_DIR"]=""
    expected=root/"mock-home"/".antigravity"/"gbrain"
elif scenario=="relative_env":
    os.environ["AGK_GBRAIN_DIR"]="relative brain"
    expected=Path("relative brain")
else:
    expected=root/"isolated 뇌 store"/"nested"
    os.environ["AGK_GBRAIN_DIR"]=str(expected)
try:
    from antigravity_k.engine import gbrain
    assert gbrain.global_gbrain.storage_dir==expected
    assert (expected/"chroma").is_dir()
    receipt["global_storage_dir"]=str(gbrain.global_gbrain.storage_dir)
    receipt["source_path"]=gbrain.__file__
    receipt["source_sha256"]=hashlib.sha256(Path(gbrain.__file__).read_bytes()).hexdigest()
    if scenario=="explicit":
        explicit=root/"explicit"
        instance=gbrain.GBrain(storage_dir=str(explicit))
        assert instance.storage_dir==explicit
        assert instance.graph_file==explicit/"knowledge_graph.graphml"
        receipt["explicit_storage_dir"]=str(instance.storage_dir)
        instance.close()
    if scenario=="empty_explicit":
        instance=gbrain.GBrain(storage_dir="")
        assert instance.storage_dir==expected
        instance.close()
    if scenario=="native_import":
        assert gbrain.global_gbrain.chroma_client is not None
        assert gbrain.global_gbrain.collection is None and gbrain.global_gbrain.vector_not_ready_reason  # r29: no default-EF collection
        assert (expected/"chroma"/"chroma.sqlite3").is_file()
        receipt["native_collection_count"]=0
    gbrain.global_gbrain.close()
    assert not receipt["denied_mutations"]
    assert not receipt["socket_attempts"]
    assert not receipt["embedding_attempts"]
    assert os.environ.get("HOME")==original_home
    receipt["home_unchanged"]=True
finally:
    (root/"receipt.json").write_text(json.dumps(receipt,indent=2))
"""


@pytest.mark.parametrize(
    "scenario", ["env", "explicit", "empty_explicit", "default", "empty_env", "relative_env", "native_import"]
)
def test_fresh_gbrain_storage_root(tmp_path: Path, scenario: str, request: pytest.FixtureRequest):
    repo = Path(__file__).resolve().parents[1]
    child = tmp_path / "probe.py"
    child.write_text(PROBE)
    env = dict(os.environ)
    env.update(
        PYTHONPATH=str(repo / "src") + os.pathsep + str(repo),
        PYTHONDONTWRITEBYTECODE="1",
        ANONYMIZED_TELEMETRY="False",
        TMPDIR=str(tmp_path),
    )
    argv = [sys.executable, str(child), str(tmp_path), scenario]
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, timeout=30)
    evidence = os.environ.get("GBRAIN_STORAGE_CAPTURE_ROOT")
    if evidence:
        directory = Path(evidence) / scenario
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
    assert Path(receipt["source_path"]).resolve() == repo / "src/antigravity_k/engine/gbrain.py"
    assert receipt["home_unchanged"] is True
