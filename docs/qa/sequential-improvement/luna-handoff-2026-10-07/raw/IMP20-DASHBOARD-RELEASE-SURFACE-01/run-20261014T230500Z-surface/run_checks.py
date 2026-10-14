from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

import yaml

REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
OUT = Path(__file__).parent
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

parser = argparse.ArgumentParser()
parser.add_argument('attempt')
parser.add_argument('phase', choices=['build', 'build-reproduce', 'browser', 'browser-c10', 'serve', 'qa'])
args = parser.parse_args()
base = OUT / args.attempt
base.mkdir()
runtime = base / 'runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
pin = str(secrets.randbelow(1000000)).zfill(6)
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()), runtime, pin)
env['PATH'] = '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin'
env['PYTHONPATH'] = str(REPO / 'src') + os.pathsep + str(REPO)
env['UV_CACHE_DIR'] = str(runtime / 'cache/uv')
env.pop('AGK_TEST_PYTHON', None)
env.pop('AGK_BUILD_ID', None)
env.pop('AGK_BUILT_AT', None)
paths = sorted({p for folder in ('dashboard/src', 'dashboard/e2e', 'src/antigravity_k/dashboard_dist') for p in (REPO / folder).rglob('*') if p.is_file()})
paths += [REPO / path for path in ('dashboard/build-provenance.json', 'dashboard/package.json', 'dashboard/pnpm-lock.yaml', 'scripts/run_dashboard_e2e_ambient.py')]
(base / 'source-binding.json').write_text(json.dumps([{'path': str(p.relative_to(REPO)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths], indent=2))
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
    if args.phase == 'serve':
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env['AGK_SEC_DEV_NO_PIN_ALLOW'] = '1'
        env['AGK_SEC_ACCESS_PIN'] = ''
        env['AGK_ACCESS_PIN'] = ''
        command = [str(REPO / '.venv/bin/python'), '-m', 'uvicorn', 'antigravity_k.api.server:app', '--host', '127.0.0.1', '--port', str(port)]
        with (base / 'server.stdout.txt').open('xb') as stdout, (base / 'server.stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command, cwd=runtime, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            (base / 'server.json').write_text(json.dumps({'pid': process.pid, 'base_url': f'http://127.0.0.1:{port}', 'model_base_reserved_not_listening': env['AGK_MODEL_API_BASE']}, indent=2))
            print(json.dumps({'pid': process.pid, 'base_url': f'http://127.0.0.1:{port}'}), flush=True)
            try:
                input('Press enter to stop owned server: ')
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait(timeout=10)
                (base / 'cleanup.json').write_text(json.dumps({'exit_code': code, 'reaped': process.poll() is not None}))
        raise SystemExit(0)
    command_cwd = REPO
    if args.phase == 'build-reproduce':
        commands = [('build', ['pnpm', 'run', 'build'], 1200)]
        command_cwd = REPO / 'dashboard'
    elif args.phase == 'build':
        commands = [('build', ['pnpm', '--dir', 'dashboard', 'run', 'build'], 300)]
    elif args.phase == 'qa':
        commands = [('manual-qa', ['/Users/mr.k/.bun/bin/bun', str(OUT / 'manual_surface_qa.mjs'), str(base)], 300)]
    else:
        specs = ['cr10-telemetry.spec.ts:163'] if args.phase == 'browser-c10' else ['accessibility.spec.ts', 'cr07-route-recovery.spec.ts', 'cr08-keyboard-accessibility.spec.ts', 'cr09-offline-assets.spec.ts', 'cr10-telemetry.spec.ts', 'file-explorer.spec.ts']
        command = [str(REPO / '.venv/bin/python'), 'scripts/run_dashboard_e2e_ambient.py']
        for spec in specs:
            command.extend(['--spec', f'e2e/tests/{spec}'])
        env['PLAYWRIGHT_HTML_OUTPUT_DIR'] = str(base / 'html-report')
        commands = [('browser', command, 1200)]
    for name, command, timeout in commands:
        started = time.time()
        timed_out = False
        with (base / f'{name}.stdout.txt').open('xb') as stdout, (base / f'{name}.stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command, cwd=command_cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait(timeout=10)
        receipt = {'name': name, 'command': command, 'cwd': str(command_cwd), 'exit_code': code, 'timed_out': timed_out, 'reaped': process.poll() is not None, 'elapsed_seconds': time.time() - started}
        receipts.append(receipt)
        (base / 'checks.json').write_text(json.dumps(receipts, indent=2))
        print(json.dumps(receipt), flush=True)
        for stream in ('stdout', 'stderr'):
            assert pin not in (base / f'{name}.{stream}.txt').read_text()
    if args.phase in ('browser', 'browser-c10'):
        import shutil
        shutil.copytree(REPO / 'dashboard/test-results', base / 'test-results')
    raise SystemExit(1 if any(row['exit_code'] or row['timed_out'] for row in receipts) else 0)
