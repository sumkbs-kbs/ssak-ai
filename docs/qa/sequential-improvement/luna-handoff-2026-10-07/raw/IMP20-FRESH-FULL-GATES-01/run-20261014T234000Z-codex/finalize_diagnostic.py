import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
report = json.loads((BASE / 'gate-report.json').read_bytes())
receipt = json.loads((BASE / 'launch-receipt.json').read_bytes())
assert report['summary'] == {'failed': 3, 'passed': 20, 'required_failed': 3, 'total': 23}
assert receipt['exit_code'] == 1 and receipt['candidate_unchanged'] and receipt['reaped']
result = {'status': 'DIAGNOSTIC_FAILED_SUPERSEDED', 'candidate': report['git'], 'summary': report['summary'], 'python_suite': 'INTENTIONALLY_INTERRUPTED_NOT_PASSED_355_PASS_9_FAIL_17_DESELECTED', 'known_additional_scoped_failure': 'Legacy embedding fallback contract503!=200, reproduced in an owned same-source copy; absent from the interrupted full-suite count', 'failed_gates': [g['id'] for g in report['gates'] if g['status'] != 'passed'], 'outer_launcher_exit': receipt['exit_code'], 'source_unchanged': True, 'soak': 'NOT_RUN', 'release': 'NOT_APPROVED'}
(BASE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
rows = []
for p in BASE.rglob('*'):
    if p.is_file() and 'private-runtime' not in p.parts and p.name != 'artifact-manifest.json':
        rows.append({'path': str(p.relative_to(BASE)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'summary': report['summary'], 'candidate_unchanged': True}))
