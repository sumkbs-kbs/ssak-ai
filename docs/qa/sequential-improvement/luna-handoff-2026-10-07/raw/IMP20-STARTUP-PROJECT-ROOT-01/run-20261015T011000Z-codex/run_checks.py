import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4')
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment

phase = sys.argv[1]
attempt = BASE / phase
attempt.mkdir()
runtime = attempt / 'private-runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, '506217')
env['PYTHONPATH'] = str(REPO / 'src') + os.pathsep + str(REPO)
env['CONFIGURED_ROOT_CAPTURE'] = str(attempt / 'captures')
env['LIFESPAN_AGENCY_CAPTURE_ROOT'] = str(attempt / 'agency-captures')
paths = ['src/antigravity_k/api/server.py', 'tests/test_lifespan_configured_project_root.py', 'tests/test_lifespan_agency_root_contract.py']
before = [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(attempt / 'source-binding.json').write_text(json.dumps(before, indent=2) + '\n')
for p in paths:
    target = attempt / 'source' / p
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((REPO / p).read_bytes())
profile = BASE.parents[1] / 'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
selected = [paths[1]] if phase.startswith('red') else [*paths[1:], 'tests/test_startup_storage_roots_contract.py', 'tests/test_rag_incremental.py', 'tests/test_rag_provenance.py', 'tests/test_startup_security.py']
command = ['/usr/bin/sandbox-exec', '-f', str(profile), str(REPO / '.venv/bin/python'), '-B', '-m', 'pytest', '-q', *selected, '--basetemp', str(runtime / 'pytest'), '--junitxml', str(attempt / 'junit.xml')]
start = time.monotonic()
with (attempt / 'stdout.txt').open('xb') as stdout, (attempt / 'stderr.txt').open('xb') as stderr:
    result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=180)
assert before == [{'path': p, 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()} for p in paths]
(attempt / 'receipt.json').write_text(json.dumps({'command': command, 'exit_code': result.returncode, 'source_binding_unchanged': True, 'elapsed_seconds': time.monotonic() - start}, indent=2) + '\n')
print(json.dumps({'exit_code': result.returncode, 'attempt': str(attempt)}), flush=True)
