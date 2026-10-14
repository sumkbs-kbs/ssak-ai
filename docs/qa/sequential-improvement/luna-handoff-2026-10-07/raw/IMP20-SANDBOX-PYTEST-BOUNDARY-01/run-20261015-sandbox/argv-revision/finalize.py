from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
FILES = ('src/antigravity_k/engine/sandbox.py', 'tests/test_cr03_sandbox_read_boundary.py')
commands = {
    'ruff': [str(REPO / '.venv/bin/ruff'), 'check', *FILES],
    'format': [str(REPO / '.venv/bin/ruff'), 'format', '--check', *FILES],
    'types': [str(REPO / '.venv/bin/basedpyright'), '--level', 'error', FILES[0]],
    'diff': ['git', 'diff', '--check', '--', *FILES],
}
receipts = []
for name, command in commands.items():
    result = subprocess.run(command, cwd=REPO, capture_output=True, timeout=120)
    (BASE / f'{name}.stdout.txt').write_bytes(result.stdout)
    (BASE / f'{name}.stderr.txt').write_bytes(result.stderr)
    receipts.append({'name': name, 'argv': command, 'exit_code': result.returncode})
(BASE / 'checks.json').write_text(json.dumps(receipts, indent=2) + '\n')
assert all(row['exit_code'] == 0 for row in receipts)
patch = subprocess.check_output(['git', 'diff', '--binary', '--', *FILES], cwd=REPO)
(BASE / 'task-only.patch').write_bytes(patch)
with tempfile.TemporaryDirectory(dir=BASE) as directory:
    target = Path(directory)
    subprocess.run(['git', 'init', '--quiet'], cwd=target, check=True)
    for name in FILES:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((BASE.parent / 'red/source' / name).read_bytes())
    subprocess.run(['git', 'apply', str(BASE / 'task-only.patch')], cwd=target, check=True)
    comparison = {name: (target / name).read_bytes() == (REPO / name).read_bytes() for name in FILES}
    assert all(comparison.values())
(BASE / 'patch-reconstruction.json').write_text(json.dumps(comparison, indent=2) + '\n')
manifest = []
for scope in [BASE, BASE.parent / 'argv-red', BASE.parent / 'argv-red-2', BASE.parent / 'argv-green']:
    for path in sorted(scope.rglob('*')):
        if not path.is_file() or 'runtime' in path.parts or path.name == 'artifact-manifest.json':
            continue
        raw = path.read_bytes()
        manifest.append({'path': str(path.relative_to(BASE.parent)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'checks': receipts, 'reconstruction': comparison, 'manifest_files': len(manifest)}))
