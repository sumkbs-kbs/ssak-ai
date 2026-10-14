from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent / 'red-contract'
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

BASE.mkdir()
runtime = BASE / 'runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
pin = str(secrets.randbelow(1000000)).zfill(6)
(runtime / 'auth-private/pin.txt').write_text(pin)
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()), runtime, pin)
env['PATH'] = '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin'
env['PYTHONPATH'] = str(REPO / 'src') + os.pathsep + str(REPO)
env['UV_CACHE_DIR'] = str(runtime / 'cache/uv')
env.pop('AGK_TEST_PYTHON', None)
files = ['scripts/run_dashboard_e2e_ambient.py', 'scripts/commercial_ga_gates.json', 'tests/test_cr14_ambient_backend_gate_contract.py']
binding = [{'path': f, 'sha256': hashlib.sha256((REPO / f).read_bytes()).hexdigest()} for f in files]
(BASE / 'source-binding.json').write_text(json.dumps(binding, indent=2) + '\n')
python = str(REPO / '.venv/bin/python')
commands = {
    'contract': [python, '-B', '-m', 'pytest', '-q', 'tests/test_cr14_ambient_backend_gate_contract.py::test_the_ambient_gate_is_required_and_starts_a_server', '--basetemp', str(runtime / 'pytest'), '--junitxml', str(BASE / 'junit.xml')],
}
receipts = []
with socket.socket() as reserved:
    reserved.bind(('127.0.0.1', 0))
    env['AGK_MODEL_API_BASE'] = f'http://127.0.0.1:{reserved.getsockname()[1]}/v1'
    env['AGK_MODEL_API_ENGINE'] = 'ollama'
    config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
    for group in config.get('models', {}).values():
        for model in group:
            model['api_base'] = env['AGK_MODEL_API_BASE']
    (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
    for name, command in commands.items():
        started = time.time()
        with (BASE / f'{name}.stdout.txt').open('xb') as stdout, (BASE / f'{name}.stderr.txt').open('xb') as stderr:
            result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=1200)
        receipt = {'name': name, 'command': command, 'exit_code': result.returncode, 'elapsed_seconds': time.time() - started, 'source_binding': 'source-binding.json'}
        receipts.append(receipt)
        (BASE / 'checks.json').write_text(json.dumps(receipts, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)
        assert pin not in (BASE / f'{name}.stdout.txt').read_text()
        assert pin not in (BASE / f'{name}.stderr.txt').read_text()
print({'failed_checks': [r['name'] for r in receipts if r['exit_code']]})

