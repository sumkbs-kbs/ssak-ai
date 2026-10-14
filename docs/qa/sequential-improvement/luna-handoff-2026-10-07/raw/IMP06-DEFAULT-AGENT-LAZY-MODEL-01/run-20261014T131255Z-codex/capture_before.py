import hashlib,json,subprocess
from pathlib import Path
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai");WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai");BASE=Path(__file__).resolve().parent
owned=["src/antigravity_k/engine/tool_loop.py","tests/test_tool_loop_lazy_model_contract.py"]
assert not (ROOT/owned[1]).exists()
for label,repo in (("root",ROOT),("clean",WT)):
    path=BASE/(label+"-preimage")/owned[0];path.parent.mkdir(parents=True);path.write_bytes((repo/owned[0]).read_bytes())
staged=subprocess.check_output(["git","-C",str(ROOT),"diff","--cached","--binary"])
assert hashlib.sha256(staged).hexdigest()=="84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f"
items={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ("src","tests") for p in (ROOT/base).rglob("*.py") if p.is_file() and not p.is_symlink() and str(p.relative_to(ROOT)) not in owned and "__pycache__" not in p.parts}
(BASE/"root-before.json").write_text(json.dumps({"sources":items,"owned":owned,"staged_sha":hashlib.sha256(staged).hexdigest()},indent=2)+"\n")
print(json.dumps({"independent_sources":len(items),"staged_preserved":True}))

