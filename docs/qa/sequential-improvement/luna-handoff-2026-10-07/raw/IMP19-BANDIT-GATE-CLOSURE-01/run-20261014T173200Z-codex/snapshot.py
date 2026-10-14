from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
FILES = (
    'src/antigravity_k/tools/browser_observation.py',
    'src/antigravity_k/tools/browser_task_memory.py',
    'src/antigravity_k/tools/browser_task_memory_store.py',
    'src/antigravity_k/knowledge/wiki_graph.py',
    'src/antigravity_k/knowledge/wiki.py',
    'src/antigravity_k/engine/cognitive/migration.py',
)
snapshot = BASE / 'preimage'
snapshot.mkdir()
manifest = []
for relative in FILES:
    original = (REPO / relative).read_bytes()
    target = snapshot / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(original)
    manifest.append({'path': relative, 'sha256': hashlib.sha256(original).hexdigest(), 'bytes': len(original)})
historical_diff = subprocess.check_output(['git', 'diff', 'd868ec50', 'HEAD', '--', *FILES], cwd=REPO)
assert not historical_diff
(BASE / 'preimage.json').write_text(json.dumps(manifest, indent=2) + '\n')
print({'preimages': len(manifest), 'historical_gate_sources_identical': True})
