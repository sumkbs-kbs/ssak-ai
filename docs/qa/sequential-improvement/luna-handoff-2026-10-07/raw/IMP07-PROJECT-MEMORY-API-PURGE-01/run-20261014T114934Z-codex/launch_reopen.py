import hashlib,json,os,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;OUT=BASE/"after-01";OLD=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4")
sys.path.insert(0,str(OLD))
from startup_probe.contract import SourcePlan,child_environment,verify_sources
plan=SourcePlan.model_validate_json((BASE/"candidate-plan.json").read_bytes());verify_sources(plan)
env=child_environment(os.environ,plan,OUT,"unused-reopen")
argv=[str(plan.python),"-B",str(BASE/"reopen_persisted.py"),str(OUT),str(OLD)]
guard_before=hashlib.sha256((OUT/"guard.json").read_bytes()).hexdigest()
binding={"argv":argv,"source_hashes":plan.source_hashes,"entry_sha":hashlib.sha256((BASE/"reopen_persisted.py").read_bytes()).hexdigest(),"product_request_budget":0}
with (OUT/"reopen-binding.json").open("x") as f:f.write(json.dumps(binding,indent=2)+"\n")
result=subprocess.run(argv,cwd=OUT,env=env,capture_output=True,timeout=30)
(OUT/"reopen.stdout").write_bytes(result.stdout);(OUT/"reopen.stderr").write_bytes(result.stderr)
assert guard_before==hashlib.sha256((OUT/"guard.json").read_bytes()).hexdigest()
with (OUT/"reopen-receipt.json").open("x") as f:f.write(json.dumps({"exit_code":result.returncode,"original_guard_sha_unchanged":True},indent=2)+"\n")
print(json.dumps({"exit_code":result.returncode,"old_guard_unchanged":True}))

