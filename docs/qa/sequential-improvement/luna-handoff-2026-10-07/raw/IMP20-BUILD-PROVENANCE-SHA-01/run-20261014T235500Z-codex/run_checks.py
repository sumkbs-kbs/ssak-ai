from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
OLD_RUN = BASE.parents[1] / 'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex'


def bundle() -> dict[str, dict[str, object]]:
    root = REPO / 'src/antigravity_k/dashboard_dist'
    return {str(p.relative_to(root)): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.rglob('*') if p.is_file()}


def main() -> None:
    old = (OLD_RUN / 'gate-report.json').read_bytes()
    report = json.loads(old)
    failed = next(row for row in report['gates'] if row['id'] == 'dashboard-test')
    assert failed['status'] == 'failed' and 'surface-4c68417e510b' in failed['stderr']
    (BASE / 'red-gate-capture.json').write_text(json.dumps({'source_report_sha256_at_capture': hashlib.sha256(old).hexdigest(), 'git': report['git'], 'manifest': report['manifest'], 'gate': failed}, indent=2) + '\n')
    env = os.environ.copy()
    for key in ('AGK_BUILD_ID', 'AGK_BUILT_AT'):
        env.pop(key, None)
    checks = []
    after_first = None
    for name, command in (
        ('dashboard-unit', ['pnpm', 'run', 'test', '--', '--reporter=verbose']),
        ('build-first', ['pnpm', 'run', 'build']),
        ('build-reproduce', ['pnpm', 'run', 'build']),
    ):
        started = time.monotonic()
        with (BASE / f'{name}.stdout.txt').open('xb') as stdout, (BASE / f'{name}.stderr.txt').open('xb') as stderr:
            process = subprocess.run(command, cwd=REPO / 'dashboard', env=env, stdout=stdout, stderr=stderr, timeout=1200)
        checks.append({'name': name, 'command': command, 'cwd': str(REPO / 'dashboard'), 'exit_code': process.returncode, 'elapsed_seconds': time.monotonic() - started, 'pin_sha256': hashlib.sha256((REPO / 'dashboard/build-provenance.json').read_bytes()).hexdigest()})
        (BASE / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
        print(json.dumps(checks[-1]), flush=True)
        assert process.returncode == 0, name
        if name == 'build-first':
            after_first = bundle()
        if name == 'build-reproduce':
            after_second = bundle()
            assert after_first == after_second
            (BASE / 'bundle-reproduction.json').write_text(json.dumps({'files': len(after_second), 'byte_identical': True, 'inventory': after_second}, indent=2) + '\n')
    diff = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--binary', '--', 'dashboard/build-provenance.json', 'src/antigravity_k/dashboard_dist'])
    (BASE / 'task-only.patch').write_bytes(diff)
    (BASE / 'scope.json').write_text(json.dumps({'source_commit': 'a7c1dc2f8fe4959dbc6a6df47bb2a628d35c449c', 'dashboard_source_changed': bool(subprocess.check_output(['git', '-C', str(REPO), 'diff', '--', 'dashboard/src'])), 'build_stamp_override': False, 'patched_paths': ['dashboard/build-provenance.json', 'src/antigravity_k/dashboard_dist/**']}, indent=2) + '\n')


if __name__ == '__main__':
    main()
