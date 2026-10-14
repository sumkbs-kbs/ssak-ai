from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import yaml
BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
ORIGINAL = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment
phase = sys.argv[1]
output = BASE / phase
output.mkdir()
runtime = output / 'runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
pin = str(secrets.randbelow(1000000)).zfill(6)
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()), runtime, pin)
env['PYTHONPATH'] = str(REPO / 'src') + os.pathsep + str(REPO)
files = ['tests/test_execution_request_preservation.py', 'tests/test_durable_memory_purge.py', 'tests/test_fr_context_end_to_end.py']
sourcefiles = files + ['src/antigravity_k/engine/' + f + '.py' for f in ('vector_store', 'gbrain', 'conversation_store', 'orchestrator_execution_handlers', 'turn_tool_constraints')]
(output / 'source-binding.json').write_text(json.dumps({'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(), 'files': {f: hashlib.sha256((REPO/f).read_bytes()).hexdigest() for f in sourcefiles}}, indent=2)+'\n')
for f in files:
    (output / Path(f).name).write_bytes((REPO/f).read_bytes())
python = str(ROOT / '.venv/bin/python')
commands = {
    'pytest': [python, '-B', str(BASE / 'pytest_entry.py'), '-q', *files, '-k', 'not TestManualCompactApiLevel', '--basetemp', str(runtime / 'pytest'), '--junitxml', str(output / 'junit.xml'), '-o', 'cache_dir='+str(runtime/'pytest-cache')],
    'ruff': [python, '-m', 'ruff', 'check', *files],
    'format': [python, '-m', 'ruff', 'format', '--check', *files],
}
receipts=[]
with socket.socket() as reserved:
    reserved.bind(('127.0.0.1', 0))
    env['AGK_MODEL_API_BASE'] = f'http://127.0.0.1:{reserved.getsockname()[1]}/v1'
    env['AGK_MODEL_API_ENGINE'] = 'ollama'
    env['TASK_NETWORK_LOG'] = str(output/'blocked-network.jsonl')
    config = yaml.safe_load((REPO/'src/antigravity_k/config.yaml').read_text())
    for group in config.get('models', {}).values():
        for model in group:
            model['api_base'] = env['AGK_MODEL_API_BASE']
    (runtime/'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
    for name, command in commands.items():
        started=time.time()
        with (output/(name+'.stdout.txt')).open('x') as stdout, (output/(name+'.stderr.txt')).open('x') as stderr:
            result=subprocess.run(command,cwd=REPO,env=env,stdout=stdout,stderr=stderr,timeout=180)
        receipt={'name':name,'command':command,'exit_code':result.returncode,'elapsed_seconds':time.time()-started}
        receipts.append(receipt)
        (output/'checks.json').write_text(json.dumps(receipts,indent=2)+'\n')
        print(json.dumps(receipt),flush=True)
