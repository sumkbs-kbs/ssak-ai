from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile

OUT = Path(__file__).parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
owned: list[str] = [row['path'] for row in json.loads((OUT / 'owned-preimage.json').read_text())]
extras = {
    'tests/test_planning_and_rendering_quality.py': 'test_planning_and_rendering_quality.py',
    'dashboard/src/components/Layout/SystemTelemetricsBar.tsx': 'SystemTelemetricsBar.tsx',
    'dashboard/src/components/Layout/__tests__/SystemTelemetricsBar.cr10.test.tsx': 'SystemTelemetricsBar.cr10.test.tsx',
}
owned += list(extras)
patch = subprocess.check_output(['git', 'diff', '--binary', '--', *owned], cwd=REPO)
(OUT / 'task-only.patch').write_bytes(patch)
rows = []
with tempfile.TemporaryDirectory(prefix='surface-reconstruct-') as temp:
    reconstructed = Path(temp)
    for name in owned:
        before = OUT / 'preimage' / (extras[name] if name in extras else name)
        assert subprocess.check_output(['git', 'show', f'HEAD:{name}'], cwd=REPO) == before.read_bytes(), name
        target = reconstructed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(before, target)
    applied = subprocess.run(['git', 'apply', str(OUT / 'task-only.patch')], cwd=reconstructed, capture_output=True)
    assert applied.returncode == 0, applied.stderr
    for name in owned:
        final = (REPO / name).read_bytes()
        assert (reconstructed / name).read_bytes() == final, name
        target = OUT / 'postimage' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(final)
        rows.append({'path': name, 'bytes': len(final), 'sha256': hashlib.sha256(final).hexdigest(), 'reconstructed_identical': True})
(OUT / 'patch-reconstruction.json').write_text(json.dumps({'exit_code': applied.returncode, 'files': rows}, indent=2))
before_bundle = json.loads((OUT / 'bundle-before-reproduce.json').read_text())
after_bundle = [{'path': str(p.relative_to(REPO)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted((REPO / 'src/antigravity_k/dashboard_dist').rglob('*')) if p.is_file()]
assert before_bundle == after_bundle
(OUT / 'bundle-reproduction.json').write_text(json.dumps({'identical': True, 'file_count': len(after_bundle), 'command_receipt': 'build-reproduce-1/checks.json', 'files': after_bundle}, indent=2))
old = json.loads((OUT / 'preimage-manifest.json').read_text())
current_root_diff = subprocess.check_output(['git', 'diff', '--', 'dashboard'], cwd=ROOT)
preserved = {'root_frontend_diff_unchanged': hashlib.sha256(current_root_diff).hexdigest() == old['root_diff_sha256'], 'preserved_artifacts': []}
for row in old['files']:
    data = (OUT / row['artifact']).read_bytes()
    assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], row['artifact']
    preserved['preserved_artifacts'].append(row['artifact'])
(OUT / 'preservation-check.json').write_text(json.dumps(preserved, indent=2))
print(json.dumps({'reconstructed': len(rows), 'bundle_identical_files': len(after_bundle), 'root_frontend_diff_unchanged': preserved['root_frontend_diff_unchanged']}))
