from __future__ import annotations
import hashlib,json,os,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
WT=Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
PY=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python")
OLD=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4")
sys.path.insert(0,str(OLD))
from startup_probe.contract import SourcePlan,child_environment
out=BASE/"verification-final-fixture";out.mkdir()
for name in ("auth-private","tmp","cache","project_root","models_dir","data_dir","documents_dir","vectors_dir","logs_dir","wiki_dir"):(out/name).mkdir()
(out/"config.yaml").write_text("{}\n");(out/"empty.env").write_text("")
env=child_environment(os.environ,SourcePlan.model_validate_json((OLD/"plan.json").read_bytes()),out,"isolated-verification-pin")
env["PYTHONPATH"]=str(WT/"src")+os.pathsep+str(WT)
owned=["src/antigravity_k/engine/vector_store.py","src/antigravity_k/api/dependencies.py","tests/test_project_vector_purge_contract.py"]
hashes={p:hashlib.sha256((WT/p).read_bytes()).hexdigest() for p in owned}
(out/"source-freeze.json").write_text(json.dumps(hashes,indent=2)+"\n")
commands=[
("lint",[str(PY.parent/"ruff"),"check","--config",str(WT/"pyproject.toml"),*[str(WT/p) for p in owned]]),
("format",[str(PY.parent/"ruff"),"format","--check","--config",str(WT/"pyproject.toml"),*[str(WT/p) for p in owned]]),
("types",[str(PY.parent/"basedpyright"),"--project",str(BASE/"type-source-config.json"),"--level","error"]),
("compile",[str(PY),"-B","-c","from pathlib import Path;import sys;[compile(Path(p).read_bytes(),p,'exec') for p in sys.argv[1:]]",*[str(WT/p) for p in owned]]),
("pytest",[str(PY),"-B",str(BASE/"pytest_guard.py"),str(OLD),str(out),str(WT/"tests/test_project_vector_purge_contract.py"),"-q","--basetemp="+str(out/"tmp/pytest"),"-o","cache_dir="+str(out/"cache/pytest"),"--junitxml="+str(out/"junit.xml")])
]
records=[]
for name,argv in commands:
    result=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=90)
    (out/(name+".stdout")).write_bytes(result.stdout);(out/(name+".stderr")).write_bytes(result.stderr)
    records.append({"name":name,"argv":argv,"exit_code":result.returncode,"source_hashes":hashes})
    (out/"checks.json").write_text(json.dumps(records,indent=2)+"\n")
print(json.dumps([{"name":r["name"],"exit_code":r["exit_code"]} for r in records]))
