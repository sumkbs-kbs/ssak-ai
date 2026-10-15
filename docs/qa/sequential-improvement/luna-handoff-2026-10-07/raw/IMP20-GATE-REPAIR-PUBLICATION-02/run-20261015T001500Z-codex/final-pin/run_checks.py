import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
SOURCE = '8585d8fbcac3589d7baeb614302ed184062095f8'
env = os.environ.copy()
env.pop('AGK_BUILD_ID', None)
env.pop('AGK_BUILT_AT', None)
checks = []
first_bundle = None
for name, command in (
    ('provenance-tests', ['pnpm', 'exec', 'vitest', 'run', 'src/utils/buildStamp.provenance.test.ts', '--reporter=verbose']),
    ('build', ['pnpm', 'run', 'build']),
    ('build-reproduce', ['pnpm', 'run', 'build']),
):
    started = time.monotonic()
    with (BASE / f'{name}.stdout.txt').open('xb') as stdout, (BASE / f'{name}.stderr.txt').open('xb') as stderr:
        result = subprocess.run(command, cwd=REPO / 'dashboard', env=env, stdout=stdout, stderr=stderr, timeout=600)
    row = {'name': name, 'command': command, 'exit_code': result.returncode, 'seconds': time.monotonic() - started, 'pin_sha256': hashlib.sha256((REPO / 'dashboard/build-provenance.json').read_bytes()).hexdigest()}
    checks.append(row)
    (BASE / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0, name
    if name.startswith('build'):
        bundle = {str(p.relative_to(REPO)): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (REPO / 'src/antigravity_k/dashboard_dist').rglob('*') if p.is_file()}
        if name == 'build':
            first_bundle = bundle
        else:
            assert first_bundle == bundle
            (BASE / 'bundle-reproduction.json').write_text(json.dumps({'files': len(bundle), 'source_commit': SOURCE, 'byte_identical': True, 'inventory': bundle}, indent=2) + '\n')
subprocess.run(['git', '-C', str(REPO), 'add', '--', 'dashboard/build-provenance.json', 'src/antigravity_k/dashboard_dist'], check=True)
(BASE / 'task-only.patch').write_bytes(subprocess.check_output(['git', '-C', str(REPO), 'diff', '--cached', '--binary']))
changed = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only', '--no-renames', '30233787'], text=True).splitlines()
files = [p for p in changed if (REPO / p).is_file()]
command = [str(REPO / '.venv/bin/python'), '-m', 'pre_commit', 'run', '--files', *files]
with (BASE / 'pre-commit.stdout.txt').open('xb') as stdout, (BASE / 'pre-commit.stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, stdout=stdout, stderr=stderr, timeout=600)
(BASE / 'pre-commit.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode}, indent=2) + '\n')
print(json.dumps({'pre_commit_exit_code': result.returncode}), flush=True)
assert result.returncode == 0
