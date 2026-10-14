from pathlib import Path
import subprocess,os,sys,json,hashlib
base=Path(__file__).parent;repo=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
out=base/sys.argv[1];out.mkdir()
python="/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python"
argv=[python,"-m","pytest","-o","pythonpath=src:.",*sys.argv[2:],"-q","--tb=short","--junitxml="+str(out/"junit.xml")]
env=dict(os.environ,PYTHONPATH=str(repo/"src")+":"+str(repo),STARTUP_STORAGE_CAPTURE_ROOT=str(out/"captures"),PYTHONDONTWRITEBYTECODE="1")
files=["src/antigravity_k/engine/global_memory_provider.py","src/antigravity_k/engine/context_shaper.py","tests/test_startup_storage_roots_contract.py"]
(out/"invocation.json").write_text(json.dumps({"argv":argv,"cwd":str(repo),"env_overrides":{k:env[k] for k in ("PYTHONPATH","STARTUP_STORAGE_CAPTURE_ROOT","PYTHONDONTWRITEBYTECODE")},"source_sha256":{f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in files}},indent=2))
r=subprocess.run(argv,cwd=repo,env=env,capture_output=True)
(out/"stdout.log").write_bytes(r.stdout);(out/"stderr.log").write_bytes(r.stderr);(out/"exit.json").write_text(json.dumps({"returncode":r.returncode}))
print(r.returncode,r.stdout.decode()[-6000:],r.stderr.decode()[-1000:])
