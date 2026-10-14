import hashlib,json,subprocess
from pathlib import Path
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OUT=Path(__file__).resolve().parent
owned=["src/antigravity_k/engine/vector_store.py","src/antigravity_k/api/dependencies.py","tests/test_project_vector_purge_contract.py"]
staged=subprocess.check_output(["git","-C",str(ROOT),"diff","--cached","--binary"])
assert hashlib.sha256(staged).hexdigest()=="84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f"
assert not (ROOT/owned[2]).exists()
pre=OUT/"root-preimage";pre.mkdir()
for p in owned[:2]:
    out=pre/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes((ROOT/p).read_bytes())
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ("src","tests") for p in (ROOT/base).rglob("*.py") if p.is_file() and not p.is_symlink() and ".venv" not in p.parts and "__pycache__" not in p.parts and str(p.relative_to(ROOT)) not in owned}
(OUT/"root-before.json").write_text(json.dumps({"owned":owned,"independent_source_hashes":sources,"staged_sha256":hashlib.sha256(staged).hexdigest()},indent=2)+"\n")
print(json.dumps({"independent_sources":len(sources),"staged_sha256":hashlib.sha256(staged).hexdigest()}))

