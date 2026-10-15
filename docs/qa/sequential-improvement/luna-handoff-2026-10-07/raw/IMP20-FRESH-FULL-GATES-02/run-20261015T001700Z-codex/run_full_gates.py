from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
PYTHON = REPO / '.venv/bin/python'
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*arguments: str) -> str:
    return subprocess.check_output(['git', '-C', str(REPO), *arguments], text=True).strip()


def main() -> None:
    control = json.loads((BASE / 'os-guard-control.json').read_bytes())
    assert control['blocked_listener_accepts'] == 0 and control['allowed_listener_accepts'] == 1
    assert git('rev-parse', 'HEAD') == json.loads((BASE / 'candidate-freeze.json').read_bytes())['head']
    assert not git('status', '--porcelain'), 'Candidate must be clean before all23'
    runtime = BASE / 'private-runtime'
    runtime.mkdir()
    for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir', 'hooks', 'vault'):
        (runtime / name).mkdir()
    (runtime / 'empty.env').write_text('')
    pin = str(secrets.randbelow(1_000_000)).zfill(6)
    plan = SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={
        'candidate': REPO, 'candidate_head': git('rev-parse', 'HEAD'), 'python': PYTHON,
    })
    env = child_environment(os.environ, plan, runtime, pin)
    env.update({
        'PATH': '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin',
        'UV_CACHE_DIR': str(runtime / 'cache/uv'),
        'AGK_AUTO_DISCOVER_LOCAL_MODELS': 'true',
        'AGK_LOCAL_MODEL_DIRS': str(runtime / 'models_dir'),
        'UVICORN_LOOP': 'asyncio',
    })
    for key in ('AGK_TEST_PYTHON', 'AGK_BUILD_ID', 'AGK_BUILT_AT', 'UNSLOTH_API_BASE', 'AGK_VLLM_API_BASE', 'AGK_TGI_API_BASE', 'AGK_KOBOLDCPP_API_BASE', 'AGK_TEXTGEN_WEBUI_API_BASE', 'AGK_LOCAL_OPENAI_BASE_URLS'):
        env.pop(key, None)
    spec = importlib.util.spec_from_file_location('candidate_ga_gate', REPO / 'scripts/ga_gate.py')
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    before = {'head': git('rev-parse', 'HEAD'), 'working_fingerprint': gate.worktree_fingerprint(REPO), 'commit_fingerprint': gate.tree_fingerprint_of_commit(REPO, 'HEAD')}
    assert before['working_fingerprint'] == before['commit_fingerprint'], before
    manifest = REPO / 'scripts/commercial_ga_gates.json'
    gates = json.loads(manifest.read_bytes())['gates']
    assert len(gates) == 23 and all(item['required'] for item in gates)
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        reserved_base = f'http://127.0.0.1:{reserved.getsockname()[1]}'
        env.update({
            'AGK_MODEL_API_BASE': reserved_base + '/v1',
            'AGK_MODEL_API_ENGINE': 'ollama',
            'AGK_OLLAMA_API_BASE': reserved_base,
            'AGK_LMSTUDIO_API_BASE': reserved_base + '/v1',
            'AGK_LLAMA_CPP_API_BASE': reserved_base + '/v1',
        })
        config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
        for group in config.get('models', {}).values():
            for model in group:
                model['api_base'] = reserved_base + '/v1'
        for provider in config.get('providers', {}).values():
            if 'base_url' in provider:
                provider['base_url'] = reserved_base + '/v1'
        (runtime / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True))
        profile = '(version 1)(allow default)'
        for port in (11434, 1234, 8080):
            profile += f'(deny network-outbound (remote tcp "localhost:{port}"))'
        denied_paths = [
            '/Users/mr.k/.cache/huggingface/hub', '/Users/mr.k/models',
            '/Users/mr.k/Library/Application Support/LM Studio/models',
            '/Users/mr.k/.ollama/models', '/Users/mr.k/.lmstudio/models',
        ]
        for path in denied_paths:
            profile += '(deny file-read-data (subpath ' + json.dumps(path) + '))'
        profile_path = BASE / 'provider-boundary.sb'
        profile_path.write_text(profile + '\n')
        command = ['/usr/bin/sandbox-exec', '-f', str(profile_path), str(PYTHON), '-B', 'scripts/ga_gate.py', '--manifest', 'scripts/commercial_ga_gates.json', '--output', str(BASE / 'gate-report.json')]
        binding = {
            'recorded_at': datetime.now(UTC).isoformat(), 'candidate': before,
            'manifest_sha256': digest(manifest), 'runner_sha256': digest(Path(__file__)),
            'provider_boundary_sha256': digest(profile_path),
            'isolated_config_sha256': digest(runtime / 'config.yaml'),
            'command': command, 'cwd': str(REPO), 'selected': 23, 'merge': False,
            'reserved_base_bound_not_listening': reserved_base,
            'auto_discovery': True, 'provider_home_weight_reads_denied': denied_paths,
            'build_stamp_environment_overrides': False,
            'notes': 'OS policy inherited across sanitized subprocess environments. Audit/install Internet and gate-owned dynamic localhost listeners are permitted. Policy control does not count all denied attempts or establish model quality.',
        }
        (BASE / 'execution-binding.json').write_text(json.dumps(binding, indent=2) + '\n')
        started = time.monotonic()
        with (BASE / 'driver.stdout.txt').open('xb') as stdout, (BASE / 'driver.stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            (BASE / 'launch.json').write_text(json.dumps({'pid': process.pid, 'started_at': datetime.now(UTC).isoformat(), 'candidate_head': before['head']}, indent=2) + '\n')
            print(json.dumps({'pid': process.pid, 'candidate': before['head'], 'gates': 23}), flush=True)
            timed_out = False
            try:
                exit_code = process.wait(timeout=sum(item['timeout_seconds'] for item in gates) + 300)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                timed_out = True
                os.killpg(process.pid, signal.SIGINT)
                try:
                    exit_code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    exit_code = process.wait(timeout=10)
        after = {'head': git('rev-parse', 'HEAD'), 'working_fingerprint': gate.worktree_fingerprint(REPO), 'commit_fingerprint': gate.tree_fingerprint_of_commit(REPO, 'HEAD'), 'status': git('status', '--porcelain')}
        receipt = {'exit_code': exit_code, 'reaped': process.poll() is not None, 'timed_out_or_interrupted': timed_out, 'elapsed_seconds': time.monotonic() - started, 'before': before, 'after': after, 'candidate_unchanged': all(after[key] == value for key, value in before.items())}
        (BASE / 'launch-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
