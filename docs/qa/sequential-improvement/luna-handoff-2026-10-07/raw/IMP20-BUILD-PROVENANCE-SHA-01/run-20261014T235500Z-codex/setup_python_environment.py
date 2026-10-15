import json
import os
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
env = os.environ.copy()
env['UV_CACHE_DIR'] = '/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/private-runtime/cache/uv'
command = ['uv', 'sync', '--frozen', '--extra', 'dev', '--extra', 'rag', '--extra', 'documents']
started = time.monotonic()
with (BASE / 'python-setup.stdout.txt').open('xb') as stdout, (BASE / 'python-setup.stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=600)
(BASE / 'python-setup.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode, 'seconds': time.monotonic() - started, 'shared_frozen_download_cache_only': True, 'own_venv': str(REPO / '.venv')}, indent=2) + '\n')
print(result.returncode)
