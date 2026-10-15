import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
relative = 'tests/test_doctor.py'
before = (BASE / 'red-03-full-env/test_doctor.snapshot.py').read_bytes()
after = (REPO / relative).read_bytes()
patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile='a/' + relative, tofile='b/' + relative))
(BASE / 'task-only.patch').write_text(patch)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'tests').mkdir()
    (root / relative).write_bytes(before)
    completed = subprocess.run(['git', 'apply', str(BASE / 'task-only.patch')], cwd=root, capture_output=True, check=True)
    assert (root / relative).read_bytes() == after
(BASE / 'patch-reconstruction.json').write_text(json.dumps({'byte_identical': True, 'target': relative, 'before_sha256': hashlib.sha256(before).hexdigest(), 'after_sha256': hashlib.sha256(after).hexdigest(), 'exit_code': completed.returncode}, indent=2) + '\n')
scenarios = []
for name in ('red-01', 'red-02-ambient', 'red-03-full-env', 'green-01-full-env', 'green-02-ambient'):
    receipt = json.loads((BASE / name / 'receipt.json').read_bytes())
    suite = ET.parse(BASE / name / 'junit.xml').getroot().find('testsuite')
    assert suite is not None
    scenarios.append({'scenario': name, 'invocation': receipt['command'], 'exit_code': receipt['exit_code'], 'junit': suite.attrib, 'guard': json.loads((BASE / name / 'guard.json').read_bytes()), 'artifact': name + '/receipt.json'})
result = {
    'status': 'COMPLETE_OFFLINE', 'independent_review': 'PENDING',
    'root_cause': 'The original test relied on external catalog order. yaml.safe_dump sorts groups, putting coding before reasoning; Doctor legitimately selects the first profile per provider, so qwen3-coder-next replaces the hardcoded qwen3.8 representative.',
    'change': 'Only test_doctor.py. Real isolated ModelRegistry with explicit Ollama/LM Studio/MLX profiles. Existing output assertions retained; exact observe(profile, refresh=False) sequence added. Port availability is mocked.',
    'scenarios': scenarios,
    'static_checks': 'candidate-01-static/checks.json',
    'type_baseline': '0 errors / 0 warnings before and after',
    'limits': ['This is a scoped fixture repair, not a full Python suite or all-23 gate pass.', 'Outer harness reserves one non-listening loopback port for full-env scenarios; tests have zero actual network connections/listeners.', 'red-01 is a preserved passing baseline; red-02 is a separate ambient-config sensitivity failure; red-03 reproduces the full-gate config transformation failure.'],
}
(BASE / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
entries = []
for path in sorted(BASE.rglob('*')):
    if not path.is_file() or 'private-runtime' in path.parts or '__pycache__' in path.parts or path.name == 'artifact-manifest.json':
        continue
    entries.append({'path': str(path.relative_to(BASE)), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(entries, indent=2) + '\n')
print(json.dumps({'manifest_entries': len(entries), 'after_sha256': hashlib.sha256(after).hexdigest()}))
