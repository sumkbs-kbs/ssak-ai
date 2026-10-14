import hashlib,json,subprocess
from pathlib import Path
base=Path(__file__).parent
repo=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
venv=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin")
files=["src/antigravity_k/engine/vector_store.py","src/antigravity_k/engine/project_embedding_binding.py","src/antigravity_k/engine/rag_indexer.py","src/antigravity_k/api/dependencies.py","tests/test_project_rag_embedding_identity_contract.py"]
commands={"ruff":[str(venv/"ruff"),"check",*files],"format":[str(venv/"ruff"),"format","--check",*files],"basedpyright":[str(venv/"basedpyright"),"--level","error",*files],"compile":[str(venv/"python"),"-c","from pathlib import Path; import sys; [compile(Path(p).read_text(),p,'exec') for p in sys.argv[1:]]; print('5 files compiled in memory')",*files]}
out=base/"static-final";out.mkdir()
for name,argv in commands.items():
    result=subprocess.run(argv,cwd=repo,capture_output=True)
    (out/(name+".stdout.log")).write_bytes(result.stdout)
    (out/(name+".stderr.log")).write_bytes(result.stderr)
    (out/(name+".json")).write_text(json.dumps({"argv":argv,"cwd":str(repo),"returncode":result.returncode,"source_sha256":{f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in files}},indent=2))
    print(name,result.returncode,result.stdout.decode()[-3000:],result.stderr.decode()[-1000:])
