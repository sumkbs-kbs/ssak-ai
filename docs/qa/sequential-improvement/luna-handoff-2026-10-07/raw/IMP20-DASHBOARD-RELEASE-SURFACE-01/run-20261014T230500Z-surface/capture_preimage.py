from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
WT = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
OUT = Path(__file__).parent
PARENT = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-DASHBOARD-GATE-OWNERSHIP-01/run-20261014T224200Z-codex/checks-attempt-1'


def capture(source: Path, target: Path) -> dict[str, str | int]:
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    return {'source': str(source), 'artifact': str(target.relative_to(OUT)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


records = []
for source in sorted((WT / 'src/antigravity_k/dashboard_dist').rglob('*')):
    if source.is_file():
        records.append(capture(source, OUT / 'preimage' / source.relative_to(WT)))
for source in sorted(PARENT.glob('*.txt')):
    records.append(capture(source, OUT / 'parent-logs' / source.name))
for source in sorted((WT / 'dashboard/test-results').rglob('*')):
    if source.is_file():
        records.append(capture(source, OUT / 'available-test-results' / source.relative_to(WT / 'dashboard/test-results')))
for name in ['dashboard/src/styles/index.css', 'dashboard/src/components/Agent/AgentMonitorPanel.tsx', 'dashboard/DESIGN.md', 'dashboard/package.json', 'dashboard/build-provenance.json']:
    records.append(capture(WT / name, OUT / 'preimage' / name))
diff = subprocess.run(['git', 'diff', '--', 'dashboard'], cwd=ROOT, capture_output=True, check=True)
with (OUT / 'root-frontend-readonly.patch').open('xb') as stream:
    stream.write(diff.stdout)
summary = {'files': records, 'witness_attachments': 'NOT_AVAILABLE: later ambient runner replaced test-results before capture', 'root_diff_sha256': hashlib.sha256(diff.stdout).hexdigest(), 'root_diff_bytes': len(diff.stdout)}
with (OUT / 'preimage-manifest.json').open('x') as stream:
    json.dump(summary, stream, indent=2)
print(json.dumps({'captured_files': len(records), 'root_diff_bytes': len(diff.stdout)}))
