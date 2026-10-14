from pathlib import Path
import os, json, subprocess, sys, hashlib
root=Path(__file__).resolve().parent
repo=Path.cwd()
kind=sys.argv[1]
selected=sys.argv[2:]
pythonpath=str(root/'baseline-overlay'/'src')+':.' if kind.startswith('baseline') else 'src:.'
env=dict(os.environ,PYTHONPATH=str(root)+':'+pythonpath,AGENT_FAILURE_CAPTURE_ROOT=str(root/kind/'captures'))
out=root/kind;out.mkdir(exist_ok=True)
argv=[str(repo/'.venv/bin/python'),'-m','pytest','-p','offline_guard','-o','pythonpath='+pythonpath,*selected,'-q','--tb=short','--junitxml='+str(out/'junit.xml')]
inputs={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('src','tests') for p in (repo/folder).rglob('*.py') if '__pycache__' not in p.parts}
(out/'invocation.json').write_text(json.dumps({'argv':argv,'cwd':str(repo),'env_overrides':{k:env[k] for k in ('PYTHONPATH','AGENT_FAILURE_CAPTURE_ROOT')},'source_sha256':inputs},indent=2))
result=subprocess.run(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
(out/'stdout.log').write_bytes(result.stdout);(out/'stderr.log').write_bytes(result.stderr)
(out/'exit.json').write_text(json.dumps({'returncode':result.returncode},indent=2))
print(kind,result.returncode,result.stdout.decode(errors='replace')[-2200:],result.stderr.decode(errors='replace')[-300:])
