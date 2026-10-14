import hashlib,json,subprocess
from pathlib import Path
base=Path(__file__).parent
repo=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
venv=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin")
files=["src/antigravity_k/engine/gbrain.py","src/antigravity_k/engine/global_memory_provider.py","src/antigravity_k/engine/context_shaper.py","tests/test_gbrain_storage_root_contract.py","tests/test_startup_storage_roots_contract.py"]
commands={"ruff":[str(venv/"ruff"),"check",*files],"format":[str(venv/"ruff"),"format","--check",*files],"basedpyright":[str(venv/"basedpyright"),"--level","error",*files],"compile":[str(venv/"python"),"-c","from pathlib import Path; import sys; [compile(Path(p).read_text(),p,'exec') for p in sys.argv[1:]]; print('5 files compiled in memory')",*files]}
out=base/"static-v1";out.mkdir()
for name,argv in commands.items():
    result=subprocess.run(argv,cwd=repo,capture_output=True)
    (out/(name+".stdout.log")).write_bytes(result.stdout)
    (out/(name+".stderr.log")).write_bytes(result.stderr)
    (out/(name+".json")).write_text(json.dumps({"argv":argv,"cwd":str(repo),"returncode":result.returncode,"source_sha256":{f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in files}},indent=2))
    print(name,result.returncode,result.stdout.decode()[-3000:],result.stderr.decode()[-1000:])
