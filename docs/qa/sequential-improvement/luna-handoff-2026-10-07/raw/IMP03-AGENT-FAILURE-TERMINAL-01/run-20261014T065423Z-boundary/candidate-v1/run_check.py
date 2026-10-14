from pathlib import Path
import os,json,subprocess,sys,hashlib
base=Path(__file__).resolve().parent
repo=Path('/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai')
python='/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python'
kind=sys.argv[1];out=base/kind;out.mkdir()
argv=[python,'-m','pytest','-p','offline_guard','-o','pythonpath=src:.',*sys.argv[2:],'-q','--tb=short','--junitxml='+str(out/'junit.xml')]
env=dict(os.environ,PYTHONPATH=str(base)+':'+str(repo/'src')+':'+str(repo),AGENT_FAILURE_CAPTURE_ROOT=str(out/'captures'),CANDIDATE_CHECK_DIR=str(out))
inputs={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('src','tests') for p in (repo/folder).rglob('*.py') if '__pycache__' not in p.parts}
(out/'invocation.json').write_text(json.dumps({'argv':argv,'cwd':str(repo),'env_overrides':{k:env[k] for k in ('PYTHONPATH','AGENT_FAILURE_CAPTURE_ROOT','CANDIDATE_CHECK_DIR')},'source_sha256':inputs},indent=2))
r=subprocess.run(argv,cwd=repo,env=env,capture_output=True)
(out/'stdout.log').write_bytes(r.stdout);(out/'stderr.log').write_bytes(r.stderr)
(out/'exit.json').write_text(json.dumps({'returncode':r.returncode}))
print(kind,r.returncode,r.stdout.decode(errors='replace')[-3500:],r.stderr.decode(errors='replace')[-600:])
