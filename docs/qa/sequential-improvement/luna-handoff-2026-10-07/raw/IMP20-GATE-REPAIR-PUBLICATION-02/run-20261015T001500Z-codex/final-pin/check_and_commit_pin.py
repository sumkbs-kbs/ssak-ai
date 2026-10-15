import json
import subprocess
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
command = json.loads((BASE / 'pre-commit.json').read_bytes())['command']
command[0] = '/Users/mr.k/miniforge3/bin/python3.13'
with (BASE / 'pre-commit-v2.stdout.txt').open('xb') as stdout, (BASE / 'pre-commit-v2.stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, stdout=stdout, stderr=stderr, timeout=600)
(BASE / 'pre-commit-v2.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode, 'correction': 'Use the existing installed hook interpreter; project dev dependencies do not include pre_commit. No successful build/test rerun.'}, indent=2) + '\n')
print(json.dumps({'pre_commit_exit': result.returncode}), flush=True)
assert result.returncode == 0
staged = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--cached', '--name-only'], text=True).splitlines()
assert staged and all(p == 'dashboard/build-provenance.json' or p.startswith('src/antigravity_k/dashboard_dist/') for p in staged)
with (BASE / 'commit.stdout.txt').open('xb') as stdout, (BASE / 'commit.stderr.txt').open('xb') as stderr:
    commit = subprocess.run(['git', 'commit', '-m', 'build: pin dashboard to its committed source revision'], cwd=REPO, stdout=stdout, stderr=stderr, timeout=600)
head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
(BASE / 'commit.json').write_text(json.dumps({'exit_code': commit.returncode, 'head': head, 'source_commit': '8585d8fbcac3589d7baeb614302ed184062095f8'}, indent=2) + '\n')
print(json.dumps({'commit_exit': commit.returncode, 'head': head}), flush=True)
assert commit.returncode == 0
