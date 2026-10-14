from pathlib import Path
import os,json,subprocess,sys,hashlib
base=Path(__file__).resolve().parent
repo=Path('/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai')
python='/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/.venv/bin/python'
kind=sys.argv[1];out=base/kind;out.mkdir()
argv=[python,'-m','pytest','-o','pythonpath=src:.']
env=dict(os.environ,ANONYMIZED_TELEMETRY='False',AGK_AUTO_DISCOVER_LOCAL_MODELS='false',PYTHONPATH=str(base)+':'+str(repo/'src')+':'+str(repo),RAG_BINDING_CAPTURE_ROOT=str(out/'captures'),BINDING_CHECK_DIR=str(out))
if kind.startswith('red-'):
    name='vector_store' if kind=='red-optin' else 'rag_indexer'
    env.update(RED_MODULE=name,RED_SOURCE=str(base/'preimage/src/antigravity_k/engine'/ (name+'.py')))
    argv+=['-p','red_preimage']
else:
    argv+=['-p','source_guard']
argv+=[*sys.argv[2:],'-q','--tb=short','--junitxml='+str(out/'junit.xml')]
files=['src/antigravity_k/engine/vector_store.py','src/antigravity_k/engine/project_embedding_binding.py','src/antigravity_k/engine/rag_indexer.py','src/antigravity_k/api/dependencies.py','tests/test_project_rag_embedding_identity_contract.py']
(out/'invocation.json').write_text(json.dumps({'argv':argv,'cwd':str(repo),'env_overrides':{k:env[k] for k in ('PYTHONPATH','RAG_BINDING_CAPTURE_ROOT','ANONYMIZED_TELEMETRY','AGK_AUTO_DISCOVER_LOCAL_MODELS','BINDING_CHECK_DIR','RED_SOURCE','RED_MODULE') if k in env},'source_sha256':{f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in files},'effective_preimage_sha256':hashlib.sha256(Path(env['RED_SOURCE']).read_bytes()).hexdigest() if 'RED_SOURCE' in env else None},indent=2))
r=subprocess.run(argv,cwd=repo,env=env,capture_output=True)
(out/'stdout.log').write_bytes(r.stdout);(out/'stderr.log').write_bytes(r.stderr)
(out/'exit.json').write_text(json.dumps({'returncode':r.returncode}))
print(kind,r.returncode,r.stdout.decode(errors='replace')[-4500:],r.stderr.decode(errors='replace')[-500:])
