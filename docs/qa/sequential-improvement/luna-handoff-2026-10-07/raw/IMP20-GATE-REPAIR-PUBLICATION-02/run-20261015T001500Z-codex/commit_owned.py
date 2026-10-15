import json
import subprocess
import time
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
GROUPS = [
    ('embedding', ['tests/test_api_server.py'], 'test: align public embeddings with the strict model contract'),
    ('migration-record', ['docs/ssak-ai-core/evidence/digest_reverification.json', 'docs/ssak-ai-core/evidence/digest_drift.json'], 'docs: reverify migration after fixed SQL query hardening'),
    ('empty-notice', ['dashboard/src/styles/index.css', 'dashboard/build-provenance.json', 'src/antigravity_k/dashboard_dist'], 'fix: keep empty model notices readable in the theme'),
]
assert subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == '302337877766a540a21dd42c61605dc590e4026b'
assert not subprocess.check_output(['git', '-C', str(REPO), 'diff', '--cached', '--name-only'])
records = []
for name, paths, message in GROUPS:
    subprocess.run(['git', '-C', str(REPO), 'add', '--', *paths], check=True)
    staged = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--cached', '--name-only'], text=True).splitlines()
    assert staged and all(any(p == allowed or p.startswith(allowed + '/') for allowed in paths) for p in staged)
    started = time.monotonic()
    with (BASE / f'{name}.commit.stdout.txt').open('xb') as stdout, (BASE / f'{name}.commit.stderr.txt').open('xb') as stderr:
        result = subprocess.run(['git', 'commit', '-m', message], cwd=REPO, stdout=stdout, stderr=stderr, timeout=600)
    record = {'name': name, 'paths': staged, 'message': message, 'exit_code': result.returncode, 'seconds': time.monotonic() - started, 'head': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()}
    records.append(record)
    (BASE / 'commit-receipts.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({k:v for k,v in record.items() if k != 'paths'}), flush=True)
    assert result.returncode == 0, name
