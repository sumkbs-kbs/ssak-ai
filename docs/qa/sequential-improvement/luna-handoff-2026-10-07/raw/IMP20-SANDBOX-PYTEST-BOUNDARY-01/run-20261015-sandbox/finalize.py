from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
FILES = ('src/antigravity_k/engine/sandbox.py', 'tests/test_cr03_sandbox_read_boundary.py')
patch = subprocess.check_output(['git', 'diff', '--binary', '--', *FILES], cwd=REPO)
(ROOT / 'task-only.patch').write_bytes(patch)
with tempfile.TemporaryDirectory(prefix='patch-check-', dir=ROOT) as directory:
    target = Path(directory)
    subprocess.run(['git', 'init', '--quiet'], cwd=target, check=True)
    for name in FILES:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / 'red/source' / name).read_bytes())
    check = subprocess.run(['git', 'apply', str(ROOT / 'task-only.patch')], cwd=target, capture_output=True)
    assert check.returncode == 0, check.stderr
    comparison = {name: (target / name).read_bytes() == (REPO / name).read_bytes() for name in FILES}
    assert all(comparison.values())
(ROOT / 'patch-reconstruction.json').write_text(json.dumps(comparison, indent=2) + '\n')
manifest = []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or 'runtime' in path.relative_to(ROOT).parts or '__pycache__' in path.parts:
        continue
    if path.name == 'artifact-manifest.json':
        continue
    raw = path.read_bytes()
    manifest.append({'path': str(path.relative_to(ROOT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
(ROOT / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'files': len(manifest), 'reconstructed': comparison}))
