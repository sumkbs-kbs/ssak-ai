import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import yaml

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent
ORIGINAL = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

attempt = BASE / sys.argv[1]
attempt.mkdir()
runtime = attempt / 'private-runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
shutil.copyfile(REPO / 'src/antigravity_k/config.yaml', runtime / 'config.yaml')
if os.environ.get('DOCTOR_AMBIENT_MINIMAL') == '1':
    (runtime / 'config.yaml').write_text('models: {}\n')
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, '506217')
env['PYTHONPATH'] = os.pathsep.join([str(BASE), str(REPO / 'src'), str(REPO)])
env['DOCTOR_GUARD_OUTPUT'] = str(attempt / 'guard.json')
env['PATH'] = '/Users/mr.k/.local/bin:/usr/bin:/bin'
reserved = socket.socket()
if os.environ.get('DOCTOR_FULL_ENV') == '1':
    reserved.bind(('127.0.0.1', 0))
    reserved_base = f'http://127.0.0.1:{reserved.getsockname()[1]}'
    env.update({
        'AGK_AUTO_DISCOVER_LOCAL_MODELS': 'true',
        'AGK_MODEL_API_BASE': reserved_base + '/v1',
        'AGK_MODEL_API_ENGINE': 'ollama',
        'AGK_OLLAMA_API_BASE': reserved_base,
        'AGK_LMSTUDIO_API_BASE': reserved_base + '/v1',
        'AGK_LLAMA_CPP_API_BASE': reserved_base + '/v1',
    })
    config = yaml.safe_load((runtime / 'config.yaml').read_text())
    for group in config.get('models', {}).values():
        for model in group:
            model['api_base'] = reserved_base + '/v1'
    for provider in config.get('providers', {}).values():
        if 'base_url' in provider:
            provider['base_url'] = reserved_base + '/v1'
    (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
(attempt / 'environment-scope.json').write_text(json.dumps({'full_gate_environment': os.environ.get('DOCTOR_FULL_ENV') == '1', 'minimal_ambient_config': os.environ.get('DOCTOR_AMBIENT_MINIMAL') == '1', 'config_sha256': hashlib.sha256((runtime / 'config.yaml').read_bytes()).hexdigest()}, indent=2) + '\n')
selector = sys.argv[2:]
paths = ['tests/test_doctor.py', 'src/antigravity_k/cli.py', 'src/antigravity_k/engine/provider_capabilities.py', 'src/antigravity_k/engine/model_registry.py', 'src/antigravity_k/config.yaml']
binding = [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(attempt / 'source-binding.json').write_text(json.dumps(binding, indent=2) + '\n')
shutil.copyfile(REPO / 'tests/test_doctor.py', attempt / 'test_doctor.snapshot.py')
profile = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
command = ['/usr/bin/sandbox-exec', '-f', str(profile), str(REPO / '.venv/bin/python'), '-B', '-m', 'pytest', '-p', 'doctor_guard', '-q', *selector, '--basetemp', str(runtime / 'pytest'), '--junitxml', str(attempt / 'junit.xml')]
with (attempt / 'stdout.txt').open('xb') as stdout, (attempt / 'stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=180)
reserved.close()
after = [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(attempt / 'receipt.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode, 'source_unchanged': binding == after}, indent=2) + '\n')
print(json.dumps({'exit_code': result.returncode, 'attempt': str(attempt)}))
