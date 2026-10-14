import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai");WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai");BASE=Path(__file__).resolve().parent
manifest=json.loads((BASE/"artifact-manifest.json").read_bytes())
docs=Path("docs/qa/sequential-improvement/luna-handoff-2026-10-07")
a=json.loads((ROOT/docs/"tasks.json").read_bytes());b=json.loads((WT/docs/"tasks.json").read_bytes())
assert {k:v for k,v in a.items() if k!="current_snapshot"}=={k:v for k,v in b.items() if k!="current_snapshot"}
assert (ROOT/docs/"STATUS.md").read_text().split("## 역사 스냅샷",1)[1]==(WT/docs/"STATUS.md").read_text().split("## 역사 스냅샷",1)[1]
assert hashlib.sha256(subprocess.check_output(["git","-C",str(ROOT),"diff","--cached","--binary"])).hexdigest()=="84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f"
names=[]
for local,row in manifest["files"].items():
    source=BASE/local;assert source.stat().st_size==row["bytes"] and hashlib.sha256(source.read_bytes()).hexdigest()==row["sha256"]
    name=source.relative_to(ROOT);assert not (WT/name).exists(),name
    names.append(name)
names += [(BASE/"artifact-manifest.json").relative_to(ROOT),Path(__file__).relative_to(ROOT),docs/"tasks.json",docs/"STATUS.md"]
for name in names:
    out=WT/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,out)
(BASE/"publication-paths.txt").write_text("\n".join(str(p) for p in names)+"\n")
print(json.dumps({"copied_files":len(names),"original_history_equal":True,"native_auth_runtime_files_kept_local":True}))

