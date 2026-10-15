from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
before = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
assert before == '1e9dfb87b185f3d20792d3f4bff4a25189947c15'
rows = json.loads((BASE / 'publication-inventory.json').read_bytes())
paths = [row['path'] for row in rows]
paths.append(str((BASE / 'publication-inventory.json').relative_to(ROOT)))
relative_self = Path(__file__).resolve().relative_to(ROOT)
shutil.copyfile(__file__, REPO / relative_self)
paths.append(str(relative_self))
inputs = []
for relative in paths:
    path = REPO / relative
    data = path.read_bytes()
    inputs.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
for row in rows:
    assert row in inputs, row['path']
input_manifest = BASE / 'commit-inputs.json'
assert not input_manifest.exists()
input_manifest.write_text(json.dumps(inputs, indent=2) + '\n')
shutil.copyfile(input_manifest, REPO / input_manifest.relative_to(ROOT))
paths.append(str(input_manifest.relative_to(ROOT)))
subprocess.run(['git', '-C', str(REPO), 'add', '-f', '--', *paths], check=True)
staged = set(subprocess.check_output(['git', '-C', str(REPO), 'diff', '--cached', '--name-only', '-z']).decode().split('\0')) - {''}
assert staged == set(paths), (len(staged), len(paths))
command = ['git', '-C', str(REPO), 'commit', '-m', 'docs: preserve full gate diagnostics and reviewed repairs']
result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
(BASE / 'qa-commit.stdout.txt').write_bytes(result.stdout)
(BASE / 'qa-commit.stderr.txt').write_bytes(result.stderr)
assert result.returncode == 0, result.stderr.decode()
head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
status = subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip()
assert not status, status
receipt = {'before': before, 'head': head, 'explicit_paths': len(paths), 'exit_code': result.returncode, 'tracked_and_untracked_status': status}
(BASE / 'qa-commit.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
