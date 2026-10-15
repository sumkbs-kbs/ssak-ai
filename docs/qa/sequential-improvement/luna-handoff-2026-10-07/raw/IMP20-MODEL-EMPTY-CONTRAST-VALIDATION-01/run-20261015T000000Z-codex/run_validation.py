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

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
PROFILE = BASE.parents[1] / 'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment


def main() -> None:
    runtime = BASE / 'private-runtime'
    runtime.mkdir()
    for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir', 'hooks', 'vault'):
        (runtime / name).mkdir()
    (runtime / 'empty.env').write_text('')
    env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, str(secrets.randbelow(1_000_000)).zfill(6))
    env.update({'PATH': '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin', 'PYTHONPATH': str(REPO / 'src') + os.pathsep + str(REPO), 'UV_CACHE_DIR': str(runtime / 'cache/uv'), 'AGK_AUTO_DISCOVER_LOCAL_MODELS': 'true', 'AGK_LOCAL_MODEL_DIRS': str(runtime / 'models_dir'), 'UVICORN_LOOP': 'asyncio'})
    checks = []
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        api = f'http://127.0.0.1:{reserved.getsockname()[1]}'
        env.update({'AGK_MODEL_API_BASE': api + '/v1', 'AGK_MODEL_API_ENGINE': 'ollama', 'AGK_OLLAMA_API_BASE': api, 'AGK_LMSTUDIO_API_BASE': api + '/v1', 'AGK_LLAMA_CPP_API_BASE': api + '/v1'})
        config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
        for group in config.get('models', {}).values():
            for model in group:
                model['api_base'] = api + '/v1'
        for provider in config.get('providers', {}).values():
            if 'base_url' in provider:
                provider['base_url'] = api + '/v1'
        (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
        commands = [('build', ['pnpm', 'run', 'build'], REPO / 'dashboard'), ('accessibility', ['/usr/bin/sandbox-exec', '-f', str(PROFILE), str(REPO / '.venv/bin/python'), '-B', 'scripts/run_dashboard_e2e_ambient.py', '--spec', 'e2e/tests/accessibility.spec.ts'], REPO)]
        for name, command, cwd in commands:
            start = time.monotonic()
            with (BASE / f'{name}.stdout.txt').open('xb') as stdout, (BASE / f'{name}.stderr.txt').open('xb') as stderr:
                process = subprocess.run(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, timeout=600)
            checks.append({'name': name, 'command': command, 'cwd': str(cwd), 'exit_code': process.returncode, 'elapsed_seconds': time.monotonic() - start, 'css_sha256': hashlib.sha256((REPO / 'dashboard/src/styles/index.css').read_bytes()).hexdigest(), 'pin_sha256': hashlib.sha256((REPO / 'dashboard/build-provenance.json').read_bytes()).hexdigest()})
            (BASE / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
            print(json.dumps(checks[-1]), flush=True)
            assert process.returncode == 0, name
    (BASE / 'bundle-manifest.json').write_text(json.dumps([{'path': str(p.relative_to(REPO)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (REPO / 'src/antigravity_k/dashboard_dist').rglob('*') if p.is_file()], indent=2) + '\n')


if __name__ == '__main__':
    main()
