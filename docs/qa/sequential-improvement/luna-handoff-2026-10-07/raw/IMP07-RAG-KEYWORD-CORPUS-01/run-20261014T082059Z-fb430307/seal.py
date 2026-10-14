from pathlib import Path
import ast,difflib,hashlib,json,subprocess,tempfile,shutil,xml.etree.ElementTree as ET
base=Path(__file__).parent
repo=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
files=["src/antigravity_k/engine/rag_indexer.py","tests/test_project_rag_keyword_corpus_contract.py"]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(["git",*args],cwd=repo)
baseline=json.loads((base/"baseline.json").read_text())
head=git("rev-parse","HEAD").decode().strip();assert head==baseline["head"]
protected={f:sha(repo/f) for f in baseline["protected_source_sha256"] if f not in files}
assert protected=={f:s for f,s in baseline["protected_source_sha256"].items() if f not in files}
(base/"ownership-after.json").write_text(json.dumps({"head":head,"protected_files":len(protected),"unowned_source_changes":[],"status":git("status","--short").decode()},indent=2))
patch=[]
for f in files:
    target=base/"candidate-source"/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/f,target)
    exists=subprocess.run(["git","cat-file","-e",head+":"+f],cwd=repo,capture_output=True).returncode==0
    old=git("show",head+":"+f) if exists else b""
    if exists: assert (base/"preimage"/f).read_bytes()==old
    patch.append("diff --git a/"+f+" b/"+f+"\n")
    if not exists:patch.append("new file mode 100644\n")
    patch.extend(difflib.unified_diff(old.decode().splitlines(True),(repo/f).read_text().splitlines(True),fromfile="a/"+f if exists else "/dev/null",tofile="b/"+f))
(base/"task-only.patch").write_text("".join(patch))
with tempfile.TemporaryDirectory(prefix="imp07-keyword-reconstruct-") as tmp:
    d=Path(tmp)
    for f in files:
        pre=base/"preimage"/f
        if pre.exists():
            target=d/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pre,target)
    argv=["git","apply",str(base/"task-only.patch")];result=subprocess.run(argv,cwd=d,capture_output=True)
    matches={f:sha(d/f)==sha(repo/f) for f in files} if result.returncode==0 else {}
    (base/"reconstruction.json").write_text(json.dumps({"argv":argv,"head":head,"returncode":result.returncode,"stdout":result.stdout.decode(),"stderr":result.stderr.decode(),"matches":matches},indent=2));assert result.returncode==0 and len(matches)==2 and all(matches.values())
inv=json.loads((base/"candidate-v2/invocation.json").read_text())
assert all(sha(repo/f)==s for f,s in inv["source_sha256"].items())
for f in inv["source_sha256"]:
    if f not in files:
        target=base/"fixture-dependencies"/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/f,target)
for name in ("ruff","format","basedpyright","compile"):
    data=json.loads((base/"static-v1"/(name+".json")).read_text());assert data["returncode"]==0 and data["source_sha256"]=={f:sha(repo/f) for f in files}
assert json.loads((base/"candidate-v2/exit.json").read_text())["returncode"]==0
binding=json.loads((base/"candidate-v2/module-socket-binding.json").read_text());assert binding["socket_attempts"]==[]
assert all(sha(Path(m["path"]))==m["sha256"] for m in binding["modules"].values())
xml=ET.parse(base/"candidate-v2/junit.xml")
allcases=[{"name":c.get("name"),"classname":c.get("classname"),"passed":not any(c.find(x) is not None for x in ("failure","error","skipped"))} for c in xml.iter("testcase")]
assert len(allcases)==36 and all(c["passed"] for c in allcases)
cases=[]
for path in sorted((base/"candidate-v2/captures").glob("*.json")):
    data=json.loads(path.read_text());assert data["forbidden"]==[]
    cases.append({"scenario":data["nodeid"],"artifact":str(path.relative_to(base)),"model_calls":len(data["engine_calls"]),"native_operations":len(data["native"]),"forbidden":data["forbidden"]})
(base/"scenario-evidence.json").write_text(json.dumps({"invocation":"candidate-v2/invocation.json","junit":"candidate-v2/junit.xml","captured_native_cases":cases,"all_selected_cases":allcases},indent=2))
original=(base/"preimage"/files[0]).read_text();current=(repo/files[0]).read_text()
def methods(source):
    tree=ast.parse(source);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="RAGIndexer")
    return {n.name:ast.get_source_segment(source,n) for n in cls.body if isinstance(n,ast.FunctionDef)}
a=methods(original);z=methods(current);unchanged={name:a[name]==z[name] for name in a if name!="_keyword_search"};assert all(unchanged.values())
needle="        query_tokens = self._query_tokens(query)";assert a["_keyword_search"].split(needle,1)[1]==z["_keyword_search"].split(needle,1)[1]
(base/"scope-verification.json").write_text(json.dumps({"all_other_methods_unchanged":unchanged,"keyword_scoring_suffix_identical":True},indent=2))
print(json.dumps({"patch_sha256":sha(base/"task-only.patch"),"owned_sha256":{f:sha(repo/f) for f in files},"protected_files":len(protected),"captured_native_cases":len(cases)},indent=2))
