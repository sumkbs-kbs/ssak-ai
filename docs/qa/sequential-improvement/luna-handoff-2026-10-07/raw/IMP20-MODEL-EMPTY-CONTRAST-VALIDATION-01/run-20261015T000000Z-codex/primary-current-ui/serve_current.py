import json
import os
import secrets
import select
import signal
import socket
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
PROFILE = BASE.parents[2] / 'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

runtime = BASE / 'private-runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir', 'hooks', 'vault'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, str(secrets.randbelow(1_000_000)).zfill(6))
env.update({'PYTHONPATH': str(REPO / 'src'), 'AGK_SEC_DEV_NO_PIN_ALLOW': '1', 'AGK_SEC_ACCESS_PIN': '', 'AGK_AUTO_DISCOVER_LOCAL_MODELS': 'true', 'AGK_LOCAL_MODEL_DIRS': str(runtime / 'models_dir')})
with socket.socket() as reserved, socket.socket() as probe:
    reserved.bind(('127.0.0.1', 0))
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    origin = f'http://127.0.0.1:{port}'
    api = f'http://127.0.0.1:{reserved.getsockname()[1]}'
    env.update({'AGK_MODEL_API_BASE': api + '/v1', 'AGK_MODEL_API_ENGINE': 'ollama', 'AGK_OLLAMA_API_BASE': api, 'AGK_LMSTUDIO_API_BASE': api + '/v1', 'AGK_LLAMA_CPP_API_BASE': api + '/v1', 'AGK_SECURITY_ALLOWED_ORIGINS': json.dumps([origin])})
    config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
    for group in config.get('models', {}).values():
        for model in group:
            model['api_base'] = api + '/v1'
    for provider in config.get('providers', {}).values():
        if 'base_url' in provider:
            provider['base_url'] = api + '/v1'
    (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
    command = ['/usr/bin/sandbox-exec', '-f', str(PROFILE), str(REPO / '.venv/bin/python'), '-m', 'uvicorn', 'antigravity_k.api.server:app', '--host', '127.0.0.1', '--port', str(port), '--loop', 'asyncio']
    with (BASE / 'server.stdout.txt').open('xb') as stdout, (BASE / 'server.stderr.txt').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=runtime, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        (BASE / 'server.json').write_text(json.dumps({'pid': process.pid, 'url': origin, 'command': command, 'provider_bound_not_listening': api}, indent=2) + '\n')
        print(json.dumps({'pid': process.pid, 'url': origin}), flush=True)
        try:
            if select.select([sys.stdin], [], [], 600)[0]:
                sys.stdin.readline()
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=10)
            (BASE / 'cleanup.json').write_text(json.dumps({'exit_code': code, 'reaped': process.poll() is not None}) + '\n')
