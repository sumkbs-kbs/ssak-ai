from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
HEAD = '7360c78544abeea41e38c65faa6eba2610a8a33b'
CONTROL = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/os-guard-control.json'


def write_new(name: str, value: object) -> None:
    with (BASE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main() -> None:
    actual = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == HEAD
    remote = subprocess.check_output(['git', '-C', str(ROOT), 'ls-remote', 'ssak-ai', 'refs/heads/codex/m1-task-events'], text=True).split()[0]
    assert remote == HEAD
    assert not (BASE / 'launch.json').exists(), 'This run has already been started'
    write_new('candidate-freeze.json', {'head': HEAD, 'recorded_at': datetime.now(UTC).isoformat(), 'remote_sha_verified': remote, 'selection': 'All23 required gates; no merge'})
    control_data = json.loads(CONTROL.read_bytes())
    assert control_data['blocked_listener_accepts'] == 0 and control_data['allowed_listener_accepts'] == 1
    write_new('os-guard-control.json', control_data)
    write_new('control-provenance.json', {'source': str(CONTROL), 'source_sha256': hashlib.sha256(CONTROL.read_bytes()).hexdigest(), 'scope': 'Reuse of prior owned blocked/allowed listener policy control, not a newly measured control invocation.'})
    command = [str(REPO / '.venv/bin/python'), '-B', str(BASE / 'run_full_gates.py')]
    print(json.dumps({'starting': command, 'candidate': HEAD}), flush=True)
    with (BASE / 'runner.stdout.txt').open('xb') as stdout, (BASE / 'runner.stderr.txt').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=REPO, stdout=stdout, stderr=stderr)
        exit_code = process.wait()
    write_new('runner-receipt.json', {'exit_code': exit_code, 'reaped': process.poll() is not None, 'scope': 'Wrapper exit is not gate acceptance; use launch-receipt and full gate-report.'})
    print(json.dumps({'runner_exit': exit_code, 'result': str(BASE / 'gate-report.json')}), flush=True)
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
