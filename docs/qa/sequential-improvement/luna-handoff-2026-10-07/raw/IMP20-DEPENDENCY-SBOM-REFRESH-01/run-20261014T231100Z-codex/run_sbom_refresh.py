from pathlib import Path
import hashlib,json,subprocess,time
BASE=Path(__file__).resolve().parent
REPO=Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
FILES=["src/antigravity_k/release/python.cdx.json","src/antigravity_k/release/dashboard.cdx.json","src/antigravity_k/release/THIRD_PARTY_NOTICES.txt"]
pre=BASE/"preimage"
pre.mkdir()
for name in FILES:
    target=pre/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((REPO/name).read_bytes())
command=[str(REPO/".venv/bin/python"),"-B","-m","antigravity_k.engine.release_sbom","generate","--project-root",str(REPO),"--release-root",str(REPO/"src/antigravity_k/release")]
started=time.time()
with (BASE/"generate.stdout.txt").open("xb") as stdout,(BASE/"generate.stderr.txt").open("xb") as stderr:
    result=subprocess.run(command,cwd=REPO,stdout=stdout,stderr=stderr,timeout=120)
receipt={"command":command,"exit_code":result.returncode,"elapsed_seconds":time.time()-started,"lock_sha256":hashlib.sha256((REPO/"uv.lock").read_bytes()).hexdigest(),"generated_files":[{"path":name,"sha256":hashlib.sha256((REPO/name).read_bytes()).hexdigest(),"bytes":(REPO/name).stat().st_size} for name in FILES]}
(BASE/"generation-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt))
assert result.returncode==0

