from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
HEAD = '7360c78544abeea41e38c65faa6eba2610a8a33b'


def write_new(path: Path, value: object) -> None:
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main() -> None:
    assert not (BASE / 'soak-hold.json').exists(), 'Known startup root defect blocks soak on this candidate'
    result = json.loads((BASE / 'result.json').read_bytes())
    assert result['status'] == 'PASS_FRESH_SAME_CANDIDATE_23'
    assert result['head'] == HEAD and result['source_unchanged']
    rows = json.loads((BASE / 'artifact-manifest.json').read_bytes())
    for row in rows:
        path = BASE / row['path']
        assert path.stat().st_size == row['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
    actual = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == HEAD
    assert not subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip()
    spec = importlib.util.spec_from_file_location('soak_source_gate', REPO / 'scripts/ga_gate.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fingerprint = module.worktree_fingerprint(REPO)
    assert fingerprint == result['fingerprint'] == module.tree_fingerprint_of_commit(REPO, 'HEAD')
    soak = BASE / 'soak'
    soak.mkdir()
    token = uuid.uuid4().hex
    workdir = Path('/tmp') / f'ssak-imp20-soak-{HEAD[:8]}-{token}'
    env = {key: value for key, value in os.environ.items() if not key.startswith(('AGK_', 'NX10_')) and key != 'PYTHONPATH'}
    env.update({
        'PATH': '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin',
        'NX10_REPO': str(REPO), 'NX10_PYTHON': str(REPO / '.venv/bin/python'),
        'NX10_SOAK_OUT_DIR': str(soak), 'NX10_OUT': str(soak), 'NX10_SOAK_OUT': str(soak),
        'NX10_SOAK_WORKDIR': str(workdir), 'NX10_SCREEN_NAME': f'imp20-{token[:12]}',
        'NX10_HARVEST_SCREEN': f'imp20-harvest-{token[:12]}',
        'SOAK_SECONDS': '28800', 'AGK_CONVERSATION_JOURNAL_HARD_CAP_MB': '8192',
    })
    write_new(soak / 'execution-plan.json', {
        'recorded_at': datetime.now(UTC).isoformat(), 'head': HEAD, 'fingerprint': fingerprint,
        'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'gate_report_sha256': hashlib.sha256((BASE / 'gate-report.json').read_bytes()).hexdigest(),
        'gate_manifest_sha256': hashlib.sha256((REPO / 'scripts/commercial_ga_gates.json').read_bytes()).hexdigest(),
        'measurement_sources': {relative: hashlib.sha256((REPO / relative).read_bytes()).hexdigest() for relative in (
            'scripts/soak_control.sh', 'scripts/val02_staging.py', 'scripts/collect_soak_result.py',
            'docs/qa/2026-09-16-followup/nx10/run_nx10_soak.sh',
        )},
        'workdir': str(workdir), 'environment': {key: value for key, value in env.items() if key.startswith(('NX10_', 'AGK_')) or key == 'SOAK_SECONDS'},
        'preflight': 'Existing controller run invokes its own60s throughput check; attribution/throughput skips are unset.',
        'scope': 'SC1-6 real SQLite, journal and process concurrency/recovery/load; not model quality or release approval.',
    })
    command = ['bash', 'scripts/soak_control.sh', 'run']
    with (soak / 'launch.stdout.txt').open('xb') as stdout, (soak / 'launch.stderr.txt').open('xb') as stderr:
        started = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr)
    write_new(soak / 'launch-receipt.json', {'command': command, 'exit_code': started.returncode, 'recorded_at': datetime.now(UTC).isoformat()})
    if started.returncode != 0:
        raise SystemExit(started.returncode)
    harvest_command = ['bash', 'scripts/soak_control.sh', 'harvest', '--detach']
    harvest = subprocess.run(harvest_command, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (soak / 'harvest-launch.stdout.txt').write_bytes(harvest.stdout)
    (soak / 'harvest-launch.stderr.txt').write_bytes(harvest.stderr)
    write_new(soak / 'harvest-launch.json', {'command': harvest_command, 'exit_code': harvest.returncode})
    print(json.dumps({'soak': str(soak), 'launch_exit': started.returncode, 'harvest_launch_exit': harvest.returncode}))
    raise SystemExit(harvest.returncode)


if __name__ == '__main__':
    main()
