import hashlib,json,os,signal,subprocess,time
from datetime import UTC,datetime
from pathlib import Path
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai");BASE=Path(__file__).resolve().parent
OUT=BASE/"build-current";OUT.mkdir()
(OUT/"tmp").mkdir()
files=[p for p in (ROOT/"dashboard").rglob("*") if p.is_file() and p.suffix in (".ts",".tsx",".css",".json",".yaml") and "node_modules" not in p.parts and "e2e-report" not in p.parts and "test-results" not in p.parts and not p.is_symlink()]
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
head=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
env=dict(os.environ,AGK_BUILD_ID="current-tree-"+head[:8]+"-"+fingerprint[:12],AGK_BUILT_AT=datetime.now(UTC).isoformat(),TMPDIR=str(OUT/"tmp"))
commands=[["pnpm","exec","tsc","--noEmit","--incremental","false","--project","tsconfig.json"],["pnpm","exec","vite","build","--outDir",str(OUT/"bundle")]]
(OUT/"source-freeze.json").write_text(json.dumps({"head":head,"frontend_hashes":hashes,"fingerprint":fingerprint,"build_id":env["AGK_BUILD_ID"],"built_at":env["AGK_BUILT_AT"],"source":"Current ROOT working tree; existing user edits included only for validation, not published"},indent=2)+"\n")
receipts=[]
for i,argv in enumerate(commands):
    with (OUT/(str(i)+".stdout")).open("xb") as stdout,(OUT/(str(i)+".stderr")).open("xb") as stderr:
        start=time.monotonic();proc=subprocess.Popen(argv,cwd=ROOT/"dashboard",env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        forced=False
        try:code=proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            forced=True
            os.killpg(proc.pid,signal.SIGTERM)
            try:code=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);code=proc.wait(timeout=5)
        try:os.killpg(proc.pid,0);empty=False
        except ProcessLookupError:empty=True
    receipts.append({"argv":argv,"exit_code":code,"reaped":proc.returncode is not None,"group_empty":empty,"forced":forced,"elapsed_sec":time.monotonic()-start})
    (OUT/"checks.json").write_text(json.dumps(receipts,indent=2)+"\n")
    if code!=0:break
changed=[p for p,s in hashes.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=s]
assert not changed,changed
(OUT/"source-preservation.json").write_text(json.dumps({"changed_frontend_sources":changed,"frontend_sources":len(hashes)},indent=2)+"\n")
print(json.dumps({"commands":receipts,"changed_sources":changed}))

