import hashlib,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai");WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
before=json.loads((BASE/"root-before.json").read_bytes())
changed=[p for p,s in before["sources"].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=s]
assert not changed,changed
s=(ROOT/"src/antigravity_k/engine/tool_loop.py").read_text()
old=(BASE/"root-preimage/src/antigravity_k/engine/tool_loop.py").read_text()
start=s.index("            model_ready = is_combo or self.orch.manager.is_loaded(delegate_model)")
end=s.index("                logger.error(\"No model %s is loaded to execute.\", delegate_model)",start)
inverse=s[:start]+"            if not is_combo and not self.orch.manager.is_loaded(delegate_model):\n"+s[end:]
inverse=inverse.replace("\n    def get(self, name: str) -> object: ...\n","",1)
assert inverse==old,"User tool-loop preimage drift"
test="tests/test_tool_loop_lazy_model_contract.py";assert (ROOT/test).read_bytes()==(WT/test).read_bytes()
staged=subprocess.check_output(["git","-C",str(ROOT),"diff","--cached","--binary"])
assert hashlib.sha256(staged).hexdigest()==before["staged_sha"]
patch=subprocess.check_output(["git","-C",str(WT),"diff","--","src/antigravity_k/engine/tool_loop.py"])
(BASE/"source-only.patch").write_bytes(patch)
data={"root_inverse_preimage_equal":True,"independent_sources":len(before["sources"]),"changed_independent_sources":changed,"staged_sha256":hashlib.sha256(staged).hexdigest(),"new_test_byte_identical":True}
(BASE/"root-preservation.json").write_text(json.dumps(data,indent=2)+"\n")
print(json.dumps(data))

