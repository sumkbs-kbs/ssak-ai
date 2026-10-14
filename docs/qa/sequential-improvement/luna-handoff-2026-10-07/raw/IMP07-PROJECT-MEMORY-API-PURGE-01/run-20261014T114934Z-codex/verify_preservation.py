import hashlib,json,subprocess
from pathlib import Path
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai"); WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai");BASE=Path(__file__).resolve().parent
before=json.loads((BASE/"root-before.json").read_bytes())
changed=[p for p,sha in before["independent_source_hashes"].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
assert not changed,changed
staged=subprocess.check_output(["git","-C",str(ROOT),"diff","--cached","--binary"])
assert hashlib.sha256(staged).hexdigest()==before["staged_sha256"]
path="src/antigravity_k/engine/vector_store.py"; current=(ROOT/path).read_text();original=(BASE/"root-preimage"/path).read_text()
start=current.index("def clear_persisted_collection(");end=current.index("@final",start)
inverse=(current[:start]+current[end:]).replace("from pathlib import Path\n","",1)
assert inverse==original,"Root vector preimage was not exactly preserved"
path="src/antigravity_k/api/dependencies.py";current=(ROOT/path).read_text();original=(BASE/"root-preimage"/path).read_text()
start=current.index("def _clear_project_vector(");end=current.index("def _clear_search_cache(",start)
os=original.index("def _clear_project_vector(");oe=original.index("def _clear_search_cache(",os)
assert current[:start]+original[os:oe]+current[end:]==original,"Root dependencies preimage drift"
test="tests/test_project_vector_purge_contract.py"
assert (ROOT/test).read_bytes()==(WT/test).read_bytes()
patch=subprocess.check_output(["git","-C",str(WT),"show","--format=","HEAD","--",*before["owned"]])
(BASE/"task-only.patch").write_bytes(patch)
receipt={"independent_src_tests_files":len(before["independent_source_hashes"]),"changed_independent_files":changed,"root_inverse_to_full_preimage":True,"test_byte_identical":True,"preserved_staged_sha256":hashlib.sha256(staged).hexdigest(),"root_adaptation":"Admin native operations use the pre-existing CHROMA_LIFECYCLE_LOCK; no legacy locks or constructor/query/close code replaced."}
(BASE/"root-preservation.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt))

