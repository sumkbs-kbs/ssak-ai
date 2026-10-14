from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
files = ('scripts/run_dashboard_e2e_ambient.py', 'scripts/commercial_ga_gates.json', 'tests/test_cr14_ambient_backend_gate_contract.py')
snapshot = BASE / 'preimage'
snapshot.mkdir()
manifest = []
for filename in files:
    target = snapshot / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (REPO / filename).read_bytes()
    target.write_bytes(data)
    manifest.append({'path': filename, 'sha256': hashlib.sha256(data).hexdigest()})
(BASE / 'preimage.json').write_text(json.dumps(manifest, indent=2) + '\n')
env = dict(os.environ)
env['PATH'] = '/Users/mr.k/.local/bin:/Users/mr.k/miniforge3/bin:/usr/local/bin:/usr/bin:/bin'
env['UV_CACHE_DIR'] = str(BASE / 'cache/uv')
commands = {
    'python-sync': ['uv', 'sync', '--frozen', '--extra', 'dev', '--extra', 'rag', '--extra', 'documents'],
    'dashboard-install': ['pnpm', '--dir', 'dashboard', 'install', '--frozen-lockfile'],
}
receipts = []
for name, command in commands.items():
    started = time.time()
    with (BASE / f'{name}.stdout.txt').open('xb') as stdout, (BASE / f'{name}.stderr.txt').open('xb') as stderr:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=600)
    receipts.append({'name': name, 'command': command, 'exit_code': result.returncode, 'seconds': time.time() - started})
    (BASE / 'setup-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print(receipts[-1], flush=True)
