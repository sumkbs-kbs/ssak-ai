#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# How to run: use frozen WT3 .venv/bin/python -I -B start_soak_once.py --launch
# The assigned interpreter is mandatory; do not create another runtime with uv.
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pwd
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

BASE: Final = Path(__file__).resolve().parent
REPO: Final = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
FRESH: Final = BASE.parent.parent / 'IMP20-FRESH-FULL-GATES-03/run-20261015T014000Z-codex'
HEAD: Final = '58d941b340a29a8717dcfbc87348b8542fe0bd77'
FINGERPRINT: Final = '777f0f3a7c86b629b1fb2083f09ccae0caf975685f34bc47dfa98e0537467768'
MANIFEST_SHA: Final = '7ec8fc7b17c5aac4eb37f83a33c0bc5f82e590a42c4e088550c0407f6cd95690'
PYTHON: Final = REPO / '.venv/bin/python'
CHECKS: Final = frozenset(('process_ok', 'source_unchanged', 'manifest_unchanged', 'exact_selection', 'commands_unchanged', 'report_binding', 'freeze_unchanged', 'harness_unchanged', 'all_passed', 'verifier_passed'))
ARTIFACTS: Final = frozenset(('run_full_gates.py', 'start_once.py', 'finalize.py', 'prelaunch_checks.py', 'prepare_environment.py', 'preparation-inputs.json', 'environment-decision.md', 'chroma-cache-inventory.json', 'candidate-freeze.json', 'start-claim.json', 'execution-binding.json', 'launch.json', 'driver.stdout.txt', 'driver.stderr.txt', 'gate-report.json', 'launch-receipt.json', 'runner.stdout.txt', 'runner.stderr.txt', 'runner-receipt.json', 'verification.stdout.txt', 'verification.stderr.txt', 'verification.json', 'result.json'))
MEASUREMENT: Final = ('scripts/soak_control.sh', 'scripts/val02_staging.py', 'scripts/collect_soak_result.py', 'docs/qa/2026-09-16-followup/nx10/run_nx10_soak.sh')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise SystemExit('REFUSED: ' + reason)


def write_new(path: Path, serialized: str) -> None:
    with path.open('x') as stream:
        stream.write(serialized + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    require(sys.argv[1:] == ['--launch'], 'explicit --launch required; preparation never launches')
    sys.dont_write_bytecode = True
    account = pwd.getpwuid(os.getuid())
    env = {
        'HOME': account.pw_dir, 'USER': account.pw_name, 'LOGNAME': account.pw_name,
        'PATH': '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        'TMPDIR': '/tmp', 'LANG': 'en_US.UTF-8', 'TERM': 'dumb',
        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
    }
    os.environ.clear()
    os.environ.update(env)
    require(not (BASE / 'soak').exists(), 'one-shot output already exists; reconcile receipts, never retry blindly')
    rows = json.loads((FRESH / 'artifact-manifest.json').read_bytes())
    require(len(rows) == len(ARTIFACTS) and {row['path'] for row in rows} == ARTIFACTS, 'FRESH3 artifact selection')
    for row in rows:
        path = FRESH / row['path']
        require(path.resolve().parent == FRESH.resolve() and not path.is_symlink(), 'artifact path containment')
        require(path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], 'artifact bytes/SHA: ' + row['path'])
    result = json.loads((FRESH / 'result.json').read_bytes())
    require(result['status'] == 'PASS_FRESH_SAME_CANDIDATE_23' and result['head'] == HEAD and result['soak_eligible'] is True, 'FRESH3 terminal PASS required')
    require(set(result['checks']) == CHECKS and all(value is True for value in result['checks'].values()), 'every FRESH3 check must be true')
    require(result['historical_results_merged'] is False and result['gate_process_exit'] == result['runner_exit'] == 0, 'fresh process receipts')
    manifest_path = REPO / 'scripts/commercial_ga_gates.json'
    require(digest(manifest_path) == MANIFEST_SHA, 'gate manifest drift')
    manifest = json.loads(manifest_path.read_bytes())
    report = json.loads((FRESH / 'gate-report.json').read_bytes())
    require(digest(FRESH / 'gate-report.json') == result['gate_report_sha256'], 'gate report binding')
    require(report['git']['sha'] == HEAD and report['git']['tree_fingerprint'] == FINGERPRINT and report['git']['dirty'] is False and report['merged'] is False and report['manifest']['sha256'] == MANIFEST_SHA, 'report candidate binding')
    executed = report['gates']
    require(len(executed) == len(manifest['gates']) == len({row['id'] for row in executed}) == 23, 'exact 23 unique gates')
    for actual, expected in zip(executed, manifest['gates'], strict=True):
        require(all(actual.get(key) == expected.get(key) for key in ('id', 'command', 'cwd', 'required')), 'gate selection/command drift')
        require(actual['status'] == 'passed' and actual['exit_code'] == 0, 'all 23 gates must pass')
    verify_command = [str(PYTHON), '-B', 'scripts/ga_gate_verify.py', '--report', str(FRESH / 'gate-report.json'), '--manifest', 'scripts/commercial_ga_gates.json', '--expected-sha', HEAD]
    verification = json.loads((FRESH / 'verification.json').read_bytes())
    require(verification['exit_code'] == 0 and verification['command'] == verify_command, 'official FRESH3 verifier exit/command')
    spec = importlib.util.spec_from_file_location('soak_source_gate', REPO / 'scripts/ga_gate.py')
    if spec is None or spec.loader is None:
        raise SystemExit('REFUSED: fingerprint module unavailable')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    current = {
        'head': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True, env=env).strip(),
        'status': subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True, env=env).strip(),
        'working_fingerprint': gate.worktree_fingerprint(REPO),
        'commit_fingerprint': gate.tree_fingerprint_of_commit(REPO, 'HEAD'),
    }
    require(current == result['current'] and current['head'] == HEAD and current['status'] == '' and current['working_fingerprint'] == current['commit_fingerprint'] == FINGERPRINT, 'clean frozen source/current/commit equality')
    measurement_hashes = {relative: digest(REPO / relative) for relative in MEASUREMENT}
    for relative, measured in measurement_hashes.items():
        blob = subprocess.check_output(['git', '-C', str(REPO), 'show', f'{HEAD}:{relative}'], env=env)
        require(hashlib.sha256(blob).hexdigest() == measured, 'measurement source differs from commit: ' + relative)
    soak = BASE / 'soak'
    soak.mkdir()
    token = uuid.uuid4().hex
    workdir = Path('/tmp') / f'ssak-imp20-soak-{HEAD[:8]}-{token}'
    require(not workdir.exists(), 'fresh workdir required')
    env.update({
        'NX10_REPO': str(REPO), 'NX10_PYTHON': str(PYTHON),
        'NX10_SOAK_OUT_DIR': str(soak), 'NX10_OUT': str(soak), 'NX10_SOAK_OUT': str(soak),
        'NX10_SOAK_WORKDIR': str(workdir), 'NX10_SCREEN_NAME': f'imp20-58-{token[:12]}',
        'NX10_HARVEST_SCREEN': f'imp20-58-harvest-{token[:12]}',
        'SOAK_SECONDS': '28800', 'AGK_CONVERSATION_JOURNAL_HARD_CAP_MB': '8192',
    })
    commands = {
        'run': ['bash', 'scripts/soak_control.sh', 'run'],
        'harvest_detach': ['bash', 'scripts/soak_control.sh', 'harvest', '--detach'],
        'status': ['bash', 'scripts/soak_control.sh', 'status'],
        'collect_after_completion': [str(PYTHON), '-B', 'scripts/collect_soak_result.py'],
        'official_final_verify': verify_command + ['--soak-artifact', str(soak / 'soak-28800.json'), '--min-soak-seconds', '28800'],
    }
    write_new(soak / 'execution-plan.json', json.dumps({
        'recorded_at': datetime.now(UTC).isoformat(), 'head': HEAD, 'current': current,
        'launcher_sha256': digest(Path(__file__)), 'gate_report_sha256': digest(FRESH / 'gate-report.json'),
        'fresh_artifact_manifest_sha256': digest(FRESH / 'artifact-manifest.json'),
        'fresh_result_sha256': digest(FRESH / 'result.json'), 'gate_manifest_sha256': MANIFEST_SHA,
        'measurement_sources': measurement_hashes,
        'required_checks': result['checks'], 'all23_ids': [row['id'] for row in executed],
        'cwd': str(REPO), 'environment': env, 'commands': commands, 'workdir': str(workdir),
        'final_verification_receipt': str(soak / 'final-verification.json'),
        'scope': 'SC1-6 SQLite/journal/process storage only; no LLM quality, GA/release, activation authority.',
        'preflight': 'Controller run owns the single default 60-second SC6 probe, space, active-process and source checks; no overrides/skips.',
        'completion': 'Launch exit zero is not eight-hour completion; require complete runner receipt, SC1-6 metrics, collector and official final verifier exits zero.',
    }, indent=2))
    for name, command in [('gate-reverification', verify_command), ('launch', commands['run']), ('harvest-launch', commands['harvest_detach'])]:
        with (soak / f'{name}.stdout.txt').open('xb') as stdout, (soak / f'{name}.stderr.txt').open('xb') as stderr:
            completed = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, check=False)
        write_new(soak / f'{name}-receipt.json', json.dumps({'command': command, 'cwd': str(REPO), 'exit_code': completed.returncode, 'recorded_at': datetime.now(UTC).isoformat()}, indent=2))
        if completed.returncode != 0:
            return completed.returncode
    print(json.dumps({'status': 'LAUNCH_COMMANDS_RETURNED_ZERO_COMPLETION_PENDING', 'soak': str(soak)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
