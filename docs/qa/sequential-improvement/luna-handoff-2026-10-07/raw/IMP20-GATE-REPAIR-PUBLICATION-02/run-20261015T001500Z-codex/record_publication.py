import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
VALIDATION = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-MODEL-EMPTY-CONTRAST-VALIDATION-01/run-20261015T000000Z-codex'
head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
assert head == '1e9dfb87b185f3d20792d3f4bff4a25189947c15'
paths = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only', '--no-renames', '30233787', head], text=True).splitlines()
current: list[dict[str, str | int]] = []
removed: list[str] = []
for relative in paths:
    path = REPO / relative
    if path.is_file():
        current.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    else:
        removed.append(relative)
source = {'base': '302337877766a540a21dd42c61605dc590e4026b', 'head': head, 'current': current, 'removed': removed}
(BASE / 'source-binding.json').write_text(json.dumps(source, indent=2) + '\n')
assert json.loads((VALIDATION / 'checks.json').read_bytes())[-1]['exit_code'] == 0
assert '35 passed' in (VALIDATION / 'accessibility.stdout.txt').read_text()
assert json.loads((VALIDATION / 'primary-current-ui/cleanup.json').read_bytes()) == {'exit_code': -15, 'reaped': True}
for folder in (VALIDATION, BASE):
    rows = []
    for path in folder.rglob('*'):
        if path.is_file() and 'private-runtime' not in path.parts and path.name != 'artifact-manifest.json':
            rows.append({'path': str(path.relative_to(folder)), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    target = folder / 'artifact-manifest.json'
    assert not target.exists()
    target.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'packet': folder.name, 'public_files': len(rows)}))
