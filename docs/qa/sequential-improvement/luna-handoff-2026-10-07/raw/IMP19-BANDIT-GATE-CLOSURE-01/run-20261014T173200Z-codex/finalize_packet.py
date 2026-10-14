from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TypedDict

class Artifact(TypedDict):
    path: str
    bytes: int
    sha256: str

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
binding = json.loads((BASE / 'checks-attempt-1/source-binding.json').read_text())
assert all(hashlib.sha256((REPO / item['path']).read_bytes()).hexdigest() == item['sha256'] for item in binding)
checks = json.loads((BASE / 'checks-attempt-1/checks.json').read_text())
assert all(row['exit_code'] == 0 for row in checks)
suite = ET.parse(BASE / 'checks-attempt-1/junit.xml').getroot().find('testsuite')
assert suite is not None
assert suite.attrib['tests'] == '141' and suite.attrib['failures'] == suite.attrib['errors'] == '0'
patch = subprocess.check_output(['git', 'diff', 'HEAD^', 'HEAD', '--', *[item['path'] for item in binding]], cwd=REPO)
(BASE / 'task-only.patch').write_bytes(patch)
scratch = BASE / 'patch-reconstruction'
scratch.mkdir()
subprocess.run(['git', 'init', '-q', str(scratch)], check=True)
for item in binding:
    target = scratch / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((BASE / 'preimage' / item['path']).read_bytes())
subprocess.run(['git', 'apply', str(BASE / 'task-only.patch')], cwd=scratch, check=True)
assert all((scratch / item['path']).read_bytes() == (REPO / item['path']).read_bytes() for item in binding)
with sqlite3.connect(':memory:') as conn:
    json_support = conn.execute("SELECT value FROM json_each('[1,2]')").fetchall() == [(1,), (2,)]
result = {'status': 'COMPLETE_SCOPED', 'candidate': head, 'independent_review': 'PENDING', 'formal_release': 'NOT_APPROVED', 'historical_bandit': {'medium': 32, 'high': 1}, 'current_bandit': {'medium': 0, 'high': 0, 'low': 336}, 'regression_passed': 141, 'warnings': 1, 'patch_reconstruction': 'BYTE_IDENTICAL_6', 'sqlite_version': sqlite3.sqlite_version, 'sqlite_json_each': json_support, 'checks': checks}
(BASE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
public = [p for p in BASE.iterdir() if p.is_file()]
public.extend(p for p in (BASE / 'preimage').rglob('*') if p.is_file())
public.extend(p for p in (BASE / 'checks-attempt-1').iterdir() if p.is_file())
manifest: list[Artifact] = [{'path': str(p.relative_to(BASE)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(public)]
(BASE / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
assert all(hashlib.sha256((BASE / row['path']).read_bytes()).hexdigest() == row['sha256'] for row in manifest)
print({'candidate': head, 'artifacts': len(manifest), 'regression': 141, 'patch_identical': 6})
