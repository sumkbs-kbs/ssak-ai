import hashlib,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
OLD=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4/plan.json")
old=json.loads(OLD.read_bytes())
sources={p:hashlib.sha256((WT/p).read_bytes()).hexdigest() for p in old["source_hashes"]}
drift=sorted(p for p in sources if sources[p]!=old["source_hashes"][p])
assert drift==["src/antigravity_k/api/dependencies.py","src/antigravity_k/engine/vector_store.py"],drift
old["source_hashes"]=sources
old["candidate_head"]=subprocess.check_output(["git","-C",str(WT),"rev-parse","HEAD"],text=True).strip()
with (BASE/"candidate-plan.json").open("x") as f:f.write(json.dumps(old,indent=2)+"\n")
print(json.dumps({"candidate":old["candidate_head"],"frozen_sources":len(sources),"changed_sources":drift}))

