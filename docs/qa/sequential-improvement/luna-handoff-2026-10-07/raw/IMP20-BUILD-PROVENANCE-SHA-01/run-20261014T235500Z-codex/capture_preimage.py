import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
OUT = Path(__file__).resolve().parent
paths = [ROOT / 'dashboard/build-provenance.json']
paths.extend(path for path in (ROOT / 'src/antigravity_k/dashboard_dist').rglob('*') if path.is_file())
rows = []
for path in paths:
    relative = path.relative_to(ROOT)
    target = OUT / 'preimage' / relative
    assert not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    rows.append({'path': str(relative), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(OUT / 'preimage-manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps({'files': len(rows)}))
