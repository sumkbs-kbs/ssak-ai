from pathlib import Path
import difflib,hashlib,json,subprocess,tempfile,shutil,xml.etree.ElementTree as ET
base=Path(__file__).parent
repo=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
files=["src/antigravity_k/engine/vector_store.py","src/antigravity_k/engine/project_embedding_binding.py","src/antigravity_k/engine/rag_indexer.py","src/antigravity_k/api/dependencies.py","tests/test_project_rag_embedding_identity_contract.py"]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(["git",*args],cwd=repo)
baseline=json.loads((base/"baseline.json").read_text())
head=git("rev-parse","HEAD").decode().strip()
assert head==baseline["head"]
protected={f:sha(repo/f) for f in baseline["protected_source_sha256"] if f not in files}
assert protected=={f:s for f,s in baseline["protected_source_sha256"].items() if f not in files}
(base/"ownership-after.json").write_text(json.dumps({"head":head,"protected_files":len(protected),"unowned_source_changes":[],"status":git("status","--short").decode(),"index_sha256":sha(Path(git("rev-parse","--git-path","index").decode().strip()))},indent=2))
patch=[]
for f in files:
    target=base/"candidate-source"/f; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(repo/f,target)
    exists=subprocess.run(["git","cat-file","-e",head+":"+f],cwd=repo,capture_output=True).returncode==0
    old=git("show",head+":"+f) if exists else b""
    if exists:
        pre=base/"preimage"/f
        assert pre.read_bytes()==old
    patch.append("diff --git a/"+f+" b/"+f+"\n")
    if not exists: patch.append("new file mode 100644\n")
    patch.extend(difflib.unified_diff(old.decode().splitlines(True),(repo/f).read_text().splitlines(True),fromfile="a/"+f if exists else "/dev/null",tofile="b/"+f))
(base/"task-only.patch").write_text("".join(patch))
with tempfile.TemporaryDirectory(prefix="imp07-reconstruct-") as tmp:
    d=Path(tmp)
    for f in files:
        pre=base/"preimage"/f
        if pre.exists():
            target=d/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pre,target)
    argv=["git","apply",str(base/"task-only.patch")]
    result=subprocess.run(argv,cwd=d,capture_output=True)
    matches={f:sha(d/f)==sha(repo/f) for f in files} if result.returncode==0 else {}
    (base/"reconstruction.json").write_text(json.dumps({"argv":argv,"preimage_head":head,"returncode":result.returncode,"stdout":result.stdout.decode(),"stderr":result.stderr.decode(),"matches":matches},indent=2))
    assert result.returncode==0 and all(matches.values()) and len(matches)==5
inv=json.loads((base/"candidate-v2/invocation.json").read_text())
assert inv["source_sha256"]=={f:sha(repo/f) for f in files}
for name in ("ruff","format","basedpyright","compile"):
    data=json.loads((base/"static-v2"/(name+".json")).read_text());assert data["returncode"]==0 and data["source_sha256"]==inv["source_sha256"]
assert json.loads((base/"candidate-v2/exit.json").read_text())["returncode"]==0
binding=json.loads((base/"candidate-v2/module-socket-binding.json").read_text());assert binding["socket_attempts"]==[]
cases=[]
for path in sorted((base/"candidate-v2/captures").glob("*.json")):
    data=json.loads(path.read_text());assert data["forbidden"]==[]
    cases.append({"scenario":data["nodeid"],"artifact":str(path.relative_to(base)),"binary_observable":"pytest PASS; forbidden=[]; native/model routing assertions in frozen test source","model_calls":len(data["engine_calls"]),"native_operations":len(data["native"])})
xml=ET.parse(base/"candidate-v2/junit.xml")
allcases=[{ "name":c.get("name"),"classname":c.get("classname"),"passed":not any(c.find(x) is not None for x in ("failure","error","skipped"))} for c in xml.iter("testcase")]
assert len(cases)==47 and len(allcases)==58 and all(c["passed"] for c in allcases)
(base/"scenario-evidence.json").write_text(json.dumps({"invocation":"candidate-v2/invocation.json","junit":"candidate-v2/junit.xml","contracts":cases,"all_selected_cases":allcases},indent=2))
print("verified",len(cases),len(allcases),"protected",len(protected),"patch",sha(base/"task-only.patch"))
