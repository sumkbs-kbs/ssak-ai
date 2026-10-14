from __future__ import annotations

import hashlib
import json
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
bound = json.loads((BASE / 'checks-attempt-2/source-binding.json').read_text())
assert all(hashlib.sha256((REPO / item['path']).read_bytes()).hexdigest() == item['sha256'] for item in bound)
checks1 = json.loads((BASE / 'checks-attempt-1/checks.json').read_text())
checks2 = json.loads((BASE / 'checks-attempt-2/checks.json').read_text())
assert all(row['exit_code'] == 0 for row in checks1 if row['name'] != 'regression')
assert all(row['exit_code'] == 0 for row in checks2)
old_cases = list(ET.parse(BASE / 'checks-attempt-1/junit.xml').iter('testcase'))
retained = [row for row in old_cases if not row.attrib.get('classname', '').endswith('test_cr11_release_bootstrap')]
assert len(retained) == 214 and all(row.find('failure') is None and row.find('error') is None and row.find('skipped') is None for row in retained)
new_cases = list(ET.parse(BASE / 'checks-attempt-2/junit.xml').iter('testcase'))
assert len(new_cases) == 20 and all(row.find('failure') is None and row.find('error') is None and row.find('skipped') is None for row in new_cases)
audit_stdout = (BASE / 'checks-attempt-1/audit.stdout.txt').read_bytes()
audit_input = json.loads(next(line.removeprefix('AUDIT-INPUTS: ') for line in audit_stdout.decode().splitlines() if line.startswith('AUDIT-INPUTS: ')))
audit_verdict = json.loads(next(line.removeprefix('AUDIT-VERDICT: ') for line in audit_stdout.decode().splitlines() if line.startswith('AUDIT-VERDICT: ')))
assert audit_input['targets']['union']['packages'] == 150
assert audit_verdict['unresolved'] == audit_verdict['expired'] == []
(BASE / 'audit-inputs-from-stdout.json').write_text(json.dumps({'source': 'checks-attempt-1/audit.stdout.txt', 'source_sha256': hashlib.sha256(audit_stdout).hexdigest(), 'input': audit_input, 'original_record_json': 'CONTAMINATED_BY_OLD_FIXTURE_PRESERVED'}, indent=2) + '\n')
patch = subprocess.check_output(['git', 'diff', 'HEAD^', 'HEAD'], cwd=REPO)
(BASE / 'task-only.patch').write_bytes(patch)
scratch = BASE / 'patch-reconstruction'
scratch.mkdir()
subprocess.run(['git', 'init', '-q', str(scratch)], check=True)
for item in bound:
    target = scratch / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((BASE / 'preimage' / item['path']).read_bytes())
subprocess.run(['git', 'apply', str(BASE / 'task-only.patch')], cwd=scratch, check=True)
assert all((scratch / item['path']).read_bytes() == (REPO / item['path']).read_bytes() for item in bound)
result = {'status': 'COMPLETE_SCOPED', 'candidate': head, 'independent_review': 'PENDING', 'formal_release': 'NOT_APPROVED', 'audit_unresolved_before': 24, 'audit_unresolved_after': 0, 'existing_chromadb_excepted_records': 5, 'regression_retained': 214, 'affected_selector_passed': 20, 'initial_selector': {'passed': 232, 'failed': 1, 'warnings': 35}, 'distinct_scope_coverage': 234, 'single_clean_full_suite': False, 'patch_reconstruction': 'BYTE_IDENTICAL_3', 'checks1': checks1, 'checks2': checks2, 'record_correction': 'evidence-correction.md', 'lsp_limit': 'Existing untouched dict variance diagnostic in bootstrap test; formal basedpyright scope is src/scripts, no suppression added'}
(BASE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
public = [p for p in BASE.iterdir() if p.is_file()]
public.extend(p for p in (BASE / 'preimage').rglob('*') if p.is_file())
for name in ('checks-attempt-1', 'checks-attempt-2'):
    public.extend(p for p in (BASE / name).iterdir() if p.is_file())
manifest: list[Artifact] = [{'path': str(p.relative_to(BASE)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(public)]
(BASE / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print({'candidate': head, 'artifacts': len(manifest), 'unresolved': 0, 'retained': 214, 'affected': 20, 'patch_identical': 3})
