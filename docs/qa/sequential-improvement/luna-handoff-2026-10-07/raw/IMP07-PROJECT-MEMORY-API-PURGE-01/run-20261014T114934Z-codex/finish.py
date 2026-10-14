import hashlib,json,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
BASE=Path(__file__).resolve().parent;WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
def read(path):return json.loads((BASE/path).read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
before=read("before-01/observations.json");after=read("after-01/observations.json")
assert before["classification"]=="FAIL_OBSERVED_PROJECT_PURGE" and before["purge_status"]==500 and before["a_residual_project_vectors"]==2
assert after["classification"]=="PASS_SCOPED_ASGI_AUTH_PROJECT_PURGE" and after["purge_status"]==200
assert all(after[k]==0 for k in ("a_residual_graph_nodes","a_residual_graph_vectors","a_residual_project_vectors"))
for name,expected in (("before-01",[401,200,500]),("after-01",[401,200,200])):
    obs=read(name+"/observations.json");guard=read(name+"/guard.json");receipt=read(name+"/supervisor-receipt.json");binding=read(name+"/source-freeze.json")
    assert [row["status"] for row in obs["asgi_requests"]]==expected
    assert len(obs["request_identity"])==1 and obs["request_identity"][0]==[obs["project_a"]["id"],obs["project_a"]["root"]]
    assert guard["violations"]==[] and guard["model_calls"]==0 and guard["binds"]==0
    assert receipt["exit_code"]==0 and receipt["reaped"] and receipt["group_empty"] and not receipt["forced"]
    assert obs["b_graph_and_vectors_preserved"] and obs["b_persisted_files_preserved"] and obs["outside_and_global_graph_preserved"]
    for p,s in binding["harness_sha"].items():assert sha(BASE/p)==s
reopen=read("after-01/reopen-result.json");assert reopen["classification"]=="PASS_SCOPED_FRESH_PROCESS_REOPEN"
assert read("after-01/reopen-receipt.json")["exit_code"]==0
assert read("after-01/reopen-guard.json")["violations"]==[]
for p,s in read("after-01/source-freeze.json")["source_hashes"].items():assert sha(WT/p)==s
tests={}
for name,expected in (("verification-v1",56),("verification-final-fixture",9),("verification-root",56)):
    tree=ET.parse(BASE/name/"junit.xml");cases=tree.findall(".//testcase")
    assert len(cases)==expected and not tree.findall(".//failure") and not tree.findall(".//error") and not tree.findall(".//skipped")
    tests[name]=len(cases)
    for p,s in read(name+"/source-freeze.json").items():
        root=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai") if name=="verification-root" else WT
        if name!="verification-v1" or not p.startswith("tests/"):assert sha(root/p)==s
assert all(row["exit_code"]==0 for row in read("verification-final-fixture/checks.json"))
assert all(row["exit_code"]==0 for row in read("verification-root/checks.json"))
patch=BASE/"task-only.patch"
scratch=BASE/"patch-reconstruction";scratch.mkdir()
parent="04ba85924fd79bde9d92052b86b2925506e15f03"
owned=read("root-before.json")["owned"]
for p in owned[:2]:
    data=subprocess.check_output(["git","-C",str(WT),"show",parent+":"+p]);target=scratch/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
import os
env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(BASE))
for args in (["--check"],[]):
    subprocess.run(["git","apply",*args,str(patch)],cwd=scratch,env=env,check=True,capture_output=True)
assert all((scratch/p).read_bytes()==(WT/p).read_bytes() for p in owned)
result={"classification":"PASS_SCOPED_AUTHENTICATED_ACTIVE_PROJECT_PURGE","candidate_commit":"6f0bd05d84506ab9435bbc4866f2acf2cb49585b","before":before,"after":after,"fresh_process_reopen":reopen,"checks":tests,"static_final_clean":read("verification-final-fixture/checks.json"),"static_root":read("verification-root/checks.json"),"patch_reconstruction_byte_identical":True,"root_preservation":read("root-preservation.json"),"product_surface":"actual ASGI app/auth/login/memory/runtime callbacks; lifespan OFF","total_asgi_requests":6,"authorized_purge_requests":2,"old_successful_model_requests_replayed":0,"actual_model_calls":0,"independent_review":"NOT_RUN_MAIN_SESSION_REVIEW_COMPLETE","overall_IMP09":"PARTIAL","historical_ledger":"NOT_RECOVERED","limits":["precomputed 3D fixtures prove deletion/isolation, not semantic quality","active registry selection, not concurrent per-session project selection","provider clears remain sequential, not a cross-provider atomic transaction","original 500 and partial clear preserved; no automatic retry","root preserves pre-existing lifecycle lock; actual ASGI observation targets published clean candidate"]}
(BASE/"result.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
public={}
omitted=[]
for p in sorted(BASE.rglob("*")):
    if not p.is_file() or p.is_symlink():continue
    local=p.relative_to(BASE)
    nested_attempt=len(local.parts)>2 and local.parts[0] in ("before-01","after-01")
    if nested_attempt or any(x in local.parts for x in ("auth-private","cache","tmp","patch-reconstruction")) or p.suffix in (".db",".sqlite",".sqlite3",".pyc") or p.name=="artifact-manifest.json":omitted.append(str(local));continue
    public[str(local)]={"bytes":p.stat().st_size,"sha256":sha(p)}
(BASE/"artifact-manifest.json").write_text(json.dumps({"files":public,"omitted_local_files":omitted,"scope":"Public fixture/result/log/source allowlist; native/auth/runtime state preserved locally"},indent=2)+"\n")
print(json.dumps({"classification":result["classification"],"public_files":len(public),"checks":tests,"patch_byte_identical":True}))

