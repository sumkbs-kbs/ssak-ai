from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
PACKET = BASE.parent.parent
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
PYTHON = REPO / '.venv/bin/python'
RAW = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw'
ORIGINAL = RAW / 'IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4'
PROFILE = RAW / 'IMP20-FRESH-FULL-GATES-02/run-20261015T001700Z-codex/provider-boundary.sb'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name: str, value: object) -> None:
    with (BASE / name).open('x') as target:
        target.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main() -> int:
    started = time.monotonic()
    binding = json.loads((PACKET / 'source-binding.json').read_bytes())
    before = {item['path']: digest(REPO / item['path']) for item in binding}
    assert all(before[item['path']] == item['sha256'] for item in binding)
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == '7360c78544abeea41e38c65faa6eba2610a8a33b'
    runtime = BASE / 'private-runtime'
    runtime.mkdir(mode=0o700)
    for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir', 'hooks', 'vault', 'home'):
        (runtime / name).mkdir()
    (runtime / 'empty.env').write_text('')
    project = runtime / 'project_root'
    (project / 'one.py').write_text('def owned_sample():\n    return 42\n')
    pin = str(secrets.randbelow(1_000_000)).zfill(6)
    plan = SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO, 'candidate_head': head, 'python': PYTHON})
    env = child_environment(os.environ, plan, runtime, pin)
    env.pop('AGK_HOOK_VAULT_DIR', None)
    env['HOME'] = str(runtime / 'home')
    env['AGK_LOCAL_MODEL_DIRS'] = str(runtime / 'models_dir')
    logging_config = {
        'version': 1, 'disable_existing_loggers': False,
        'formatters': {'plain': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'}},
        'handlers': {'stderr': {'class': 'logging.StreamHandler', 'formatter': 'plain', 'stream': 'ext://sys.stderr'}},
        'root': {'level': 'INFO', 'handlers': ['stderr']},
        'loggers': {'uvicorn': {'level': 'INFO', 'handlers': ['stderr'], 'propagate': False}, 'uvicorn.access': {'level': 'INFO', 'handlers': ['stderr'], 'propagate': False}},
    }
    (runtime / 'logging.json').write_text(json.dumps(logging_config))
    process = None
    forced = False
    failure = None
    request_count = 0
    curl_exit = None
    http_status = None
    before_live = None
    with socket.socket() as reserved, socket.socket() as listener:
        reserved.bind(('127.0.0.1', 0))
        upstream = f'http://127.0.0.1:{reserved.getsockname()[1]}'
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.close()
        env.update({'AGK_MODEL_API_BASE': upstream + '/v1', 'AGK_MODEL_API_ENGINE': 'ollama', 'AGK_OLLAMA_API_BASE': upstream, 'AGK_LMSTUDIO_API_BASE': upstream + '/v1', 'AGK_LLAMA_CPP_API_BASE': upstream + '/v1'})
        config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
        for group in config.get('models', {}).values():
            for model in group:
                model['api_base'] = upstream + '/v1'
        for provider in config.get('providers', {}).values():
            if 'base_url' in provider:
                provider['base_url'] = upstream + '/v1'
        (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        command = ['/usr/bin/sandbox-exec', '-f', str(PROFILE), str(PYTHON), '-B', '-m', 'uvicorn', 'antigravity_k.api.server:app', '--host', '127.0.0.1', '--port', str(port), '--loop', 'asyncio', '--lifespan', 'on', '--log-config', str(runtime / 'logging.json')]
        curl = ['/usr/bin/curl', '-i', '--noproxy', '*', '--max-time', '60', '--silent', '--show-error', f'http://127.0.0.1:{port}/health']
        save('execution-binding.json', {'candidate': str(REPO), 'head': head, 'sources': before, 'source_binding_sha256': digest(PACKET / 'source-binding.json'), 'harness_sha256': digest(Path(__file__)), 'contract_sha256': digest(ORIGINAL / 'startup_probe/contract.py'), 'profile_sha256': digest(PROFILE), 'config_sha256': digest(runtime / 'config.yaml'), 'tiny_project_sha256': digest(project / 'one.py'), 'cwd': str(project), 'command': command, 'curl_command': curl, 'project_root': str(project), 'hook_override_present': False, 'provider_bound_not_listening': upstream, 'started_at': datetime.now(UTC).isoformat(), 'limits_seconds': {'startup': 60, 'curl': 60, 'graceful': 30, 'forced_reap': 5}, 'harness_product_posts': 0, 'harness_inference_requests': 0, 'global_provider_call_instrumentation': 'NOT_INSTRUMENTED'})
        with (runtime / 'server.stdout.raw.txt').open('xb') as stdout, (runtime / 'server.stderr.raw.txt').open('xb') as stderr:
            try:
                process = subprocess.Popen(command, cwd=project, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
                save('launch.json', {'pid': process.pid, 'command': command})
                deadline = time.monotonic() + 60
                while True:
                    logs = (runtime / 'server.stderr.raw.txt').read_text(errors='replace')
                    if 'Application startup complete.' in logs and '[RAG] Background indexing complete:' in logs:
                        break
                    if process.poll() is not None:
                        raise RuntimeError(f'Uvicorn exited before startup: {process.returncode}')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Startup/RAG log deadline exceeded')
                    time.sleep(0.05)
                before_live = {'audit_db_exists': (project / 'vault_data/audit.sqlite3').is_file(), 'hook_events_exists': (project / 'vault_data/hooks/events.jsonl').is_file()}
                request_count += 1
                response = subprocess.run(curl, cwd=REPO, env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=62, check=False)
                curl_exit = response.returncode
                (BASE / 'health.http.txt').write_bytes(response.stdout)
                (BASE / 'health.stderr.txt').write_bytes(response.stderr)
                if response.stdout.startswith(b'HTTP/'):
                    http_status = int(response.stdout.splitlines()[0].split()[1])
                if curl_exit != 0 or http_status != 200:
                    raise RuntimeError(f'Health request failed: curl={curl_exit}, HTTP={http_status}')
            except Exception as exc:
                failure = f'{type(exc).__name__}: {exc}'
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        forced = True
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
    stdout_text = (runtime / 'server.stdout.raw.txt').read_text(errors='replace').replace(pin, '[REDACTED_PIN]')
    stderr_text = (runtime / 'server.stderr.raw.txt').read_text(errors='replace').replace(pin, '[REDACTED_PIN]')
    (BASE / 'server.stdout.txt').write_text(stdout_text)
    (BASE / 'server.stderr.txt').write_text(stderr_text)
    after = {item['path']: digest(REPO / item['path']) for item in binding}
    vault = project / 'vault_data'
    inventory = [{'path': str(path.relative_to(project)), 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in sorted(project.rglob('*')) if path.is_file()]
    integrity = None
    if (vault / 'audit.sqlite3').is_file():
        with sqlite3.connect(f'file:{vault / "audit.sqlite3"}?mode=ro', uri=True) as database:
            integrity = database.execute('PRAGMA integrity_check').fetchone()[0]
    group_empty = False
    if process is not None:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            group_empty = True
    checks = {
        'one_health_get_200': request_count == 1 and curl_exit == 0 and http_status == 200,
        'live_storage_paths_exist': before_live is not None and all(before_live.values()),
        'startup_completed': 'Application startup complete.' in stderr_text,
        'rag_tiny_project_one': '[RAG] Background indexing complete: 1 files indexed' in stderr_text,
        'default_hook_path': f'[HookEventBus] Initialized at {vault / "hooks"}' in stderr_text,
        'default_audit_path': f'[AuditDb] Initialized at {vault / "audit.sqlite3"}' in stderr_text,
        'hook_shutdown': '[HookEventBus] Shut down' in stderr_text,
        'application_shutdown': 'Application shutdown complete.' in stderr_text,
        'normal_reap': process is not None and process.returncode == 0 and not forced and group_empty,
        'audit_integrity_after_exit': integrity == 'ok',
        'source_unchanged': before == after,
    }
    verdict = 'PASS_SCOPED_STARTUP_HEALTH' if failure is None and all(checks.values()) else 'FAIL'
    save('result.json', {'verdict': verdict, 'failure': failure, 'checks': checks, 'request_count': request_count, 'harness_product_posts': 0, 'harness_inference_requests': 0, 'curl_exit': curl_exit, 'http_status': http_status, 'server_exit': process.returncode if process else None, 'reaped': process is not None and process.poll() is not None, 'forced': forced, 'process_group_empty': group_empty, 'elapsed_seconds': time.monotonic() - started, 'files_observed_while_live': before_live, 'project_files_after_exit': inventory, 'sources_before': before, 'sources_after': after, 'audit_close_method': 'NOT_INSTRUMENTED; see actual application_shutdown check and post-exit read-only integrity', 'ide_listener': 'NOT_TESTED', 'global_provider_call_count': 'NOT_INSTRUMENTED', 'limitations': ['No model inference requests were issued by this QA client; no independent global call counter.', 'No authentication, IDE listener, full gates, soak, or model quality assertion.', 'Private runtime includes credentials and is excluded from publication.']})
    print(json.dumps({'verdict': verdict, 'checks': checks, 'server_exit': process.returncode if process else None, 'failure': failure}), flush=True)
    return 0 if verdict.startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())

