import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

runtime = BASE / 'private-runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, '506217')
env['PYTHONPATH'] = str(REPO / 'src') + os.pathsep + str(REPO)
paths = ['src/antigravity_k/engine/cognitive/migration.py', 'tests/cognitive/test_migration.py', 'tests/cognitive/test_migration_snapshot_lineage.py']
before = [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(BASE / 'source-binding.json').write_text(json.dumps(before, indent=2) + '\n')
profile = BASE.parents[2] / 'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
command = ['/usr/bin/sandbox-exec', '-f', str(profile), str(REPO / '.venv/bin/python'), '-B', '-m', 'pytest', '-q', *paths[1:], '--basetemp', str(runtime / 'pytest'), '--junitxml', str(BASE / 'junit.xml')]
with (BASE / 'stdout.txt').open('xb') as stdout, (BASE / 'stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=300)
assert before == [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(BASE / 'receipt.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode, 'source_binding_unchanged': True, 'scope': 'New current migration test/source binding; does not retroactively bind the historical141 execution tests.'}, indent=2) + '\n')
print(json.dumps({'exit_code': result.returncode}), flush=True)
assert result.returncode == 0
