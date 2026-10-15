import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
PATHS = ['src/antigravity_k/api/server.py', 'tests/test_lifespan_agency_root_contract.py', 'tests/test_lifespan_configured_project_root.py']
OUT = BASE / 'static-02'
OUT.mkdir()
commands = {
    'ruff': ['ruff', 'check', *PATHS],
    'format': ['ruff', 'format', '--check', *PATHS],
    'type': ['basedpyright', '--level', 'error', *PATHS],
    'diff-check': ['git', 'diff', '--check'],
}
checks = []
for name, command in commands.items():
    result = subprocess.run(command, cwd=REPO, capture_output=True, timeout=180)
    (OUT / (name + '.stdout.txt')).write_bytes(result.stdout)
    (OUT / (name + '.stderr.txt')).write_bytes(result.stderr)
    checks.append({'name': name, 'command': command, 'exit_code': result.returncode})
for path in PATHS:
    compile((REPO / path).read_bytes(), path, 'exec')
checks.append({'name': 'memory-compile', 'paths': PATHS, 'exit_code': 0})
(OUT / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
print(json.dumps(checks, indent=2), flush=True)
if any(row['exit_code'] for row in checks):
    raise SystemExit(1)
patch_root = BASE / 'patch-replay'
for side in ('a', 'b', 'replay'):
    (patch_root / side).mkdir(parents=True)
for path in PATHS:
    if path != PATHS[2]:
        data = (BASE / 'red-01/source' / path).read_bytes()
        for side in ('a', 'replay'):
            target = patch_root / side / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    target = patch_root / 'b' / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((REPO / path).read_bytes())
diff = subprocess.run(['git', 'diff', '--no-index', '--binary', 'a', 'b'], cwd=patch_root, capture_output=True, check=False)
assert diff.returncode == 1, diff.stderr
patch = diff.stdout.replace(b'a/a/', b'a/').replace(b'b/b/', b'b/')
(BASE / 'task-only.patch').write_bytes(patch)
subprocess.run(['git', 'init', '-q'], cwd=patch_root / 'replay', check=True)
apply = subprocess.run(['git', 'apply', str(BASE / 'task-only.patch')], cwd=patch_root / 'replay', capture_output=True)
assert apply.returncode == 0, apply.stderr
rows = []
for path in PATHS:
    original = (REPO / path).read_bytes()
    assert original == (patch_root / 'replay' / path).read_bytes()
    rows.append({'path': path, 'sha256': hashlib.sha256(original).hexdigest(), 'bytes': len(original), 'replay_identical': True})
(BASE / 'source-binding.json').write_text(json.dumps(rows, indent=2) + '\n')
protected = []
for path in ['src/antigravity_k/config.py', 'src/antigravity_k/engine/rag_indexer.py', 'src/antigravity_k/engine/event_bus.py', 'src/antigravity_k/engine/ide_server.py', 'src/antigravity_k/engine/hook_event_bus.py', 'src/antigravity_k/engine/audit_db.py']:
    baseline = subprocess.run(['git', 'show', 'HEAD:' + path], cwd=REPO, capture_output=True, check=True).stdout
    current = (REPO / path).read_bytes()
    assert baseline == current
    protected.append({'path': path, 'sha256': hashlib.sha256(current).hexdigest(), 'equals_clean_start_HEAD': True})
(BASE / 'protected-files.json').write_text(json.dumps(protected, indent=2) + '\n')
summary = {}
for phase in ('red-01', 'green-01', 'green-02'):
    root = ET.parse(BASE / phase / 'junit.xml').getroot()
    suites = root.findall('testsuite')
    summary[phase] = {key: sum(int(s.get(key, '0')) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
(BASE / 'result.json').write_text(json.dumps({'status': 'COMPLETE_SCOPED_OFFLINE', 'review': 'PENDING', 'scenarios': summary, 'checks': checks, 'actual_lifespan': True, 'provider_inference': 'NOT_RUN', 'live_HTTP': 'NOT_RUN', 'source_binding': rows, 'limitations': ['Subsystem doubles isolate side effects; real RAG indexes one owned Python file for each configured-root case.', 'No RAG thread cancellation or lifecycle ownership change.', 'Existing agency-only test intentionally preserved old RAG/IDE roots; its assertion is superseded by this task.']}, indent=2) + '\n')
shutil.rmtree(patch_root / 'replay' / '.git')
manifest = []
for path in sorted(BASE.rglob('*')):
    if path.is_file() and 'private-runtime' not in path.parts and '__pycache__' not in path.parts and path.name != 'artifact-manifest.json':
        data = path.read_bytes()
        manifest.append({'path': str(path.relative_to(BASE)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_entries': len(manifest), 'result': summary}), flush=True)
