import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent
PARENT = BASE.parent
ORIGINAL = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP06-CURRENT-CANDIDATE-STARTUP-AUTH-01/run-20261014T084728Z-bb9d0d4e/revision-v4'
sys.path.insert(0, str(ORIGINAL))
from startup_probe.contract import SourcePlan, child_environment


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


old_manifest = json.loads((PARENT / 'artifact-manifest.json').read_bytes())
assert len(old_manifest) == 64
for entry in old_manifest:
    path = PARENT / entry['path']
    assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256']
protected = [PARENT / entry['path'] for entry in old_manifest] + [PARENT / 'artifact-manifest.json']
source_paths = [REPO / p for p in ('tests/test_doctor.py', 'tests/conftest.py', 'src/antigravity_k/cli.py', 'src/antigravity_k/engine/model_registry.py', 'src/antigravity_k/engine/provider_capabilities.py', 'src/antigravity_k/config.yaml')]
before = {str(path): sha(path) for path in protected + source_paths}
runtime = BASE / 'private-runtime'
runtime.mkdir()
for name in ('auth-private', 'tmp', 'cache', 'project_root', 'models_dir', 'data_dir', 'documents_dir', 'vectors_dir', 'logs_dir', 'wiki_dir'):
    (runtime / name).mkdir()
(runtime / 'empty.env').write_text('')
overlay = BASE / 'overlay/tests'
overlay.mkdir(parents=True)
shutil.copyfile(PARENT / 'red-03-full-env/test_doctor.snapshot.py', overlay / 'test_doctor.py')
shutil.copyfile(REPO / 'tests/conftest.py', overlay / 'conftest.py')
assert sha(overlay / 'test_doctor.py') == json.loads((PARENT / 'patch-reconstruction.json').read_bytes())['before_sha256']
env = child_environment(os.environ, SourcePlan.model_validate_json((ORIGINAL / 'plan.json').read_bytes()).model_copy(update={'candidate': REPO}), runtime, '506217')
env['PYTHONPATH'] = os.pathsep.join([str(PARENT), str(REPO / 'src'), str(REPO)])
env['DOCTOR_GUARD_OUTPUT'] = str(BASE / 'guard.json')
env['PATH'] = '/Users/mr.k/.local/bin:/usr/bin:/bin'
config = yaml.safe_load((REPO / 'src/antigravity_k/config.yaml').read_text())
original_groups = list(config['models'])
with socket.socket() as reserved:
    reserved.bind(('127.0.0.1', 0))
    reserved_base = f'http://127.0.0.1:{reserved.getsockname()[1]}'
    env.update({
        'AGK_AUTO_DISCOVER_LOCAL_MODELS': 'true',
        'AGK_MODEL_API_BASE': reserved_base + '/v1',
        'AGK_MODEL_API_ENGINE': 'ollama',
        'AGK_OLLAMA_API_BASE': reserved_base,
        'AGK_LMSTUDIO_API_BASE': reserved_base + '/v1',
        'AGK_LLAMA_CPP_API_BASE': reserved_base + '/v1',
    })
    for group in config.get('models', {}).values():
        for model in group:
            model['api_base'] = reserved_base + '/v1'
    for provider in config.get('providers', {}).values():
        if 'base_url' in provider:
            provider['base_url'] = reserved_base + '/v1'
    config_text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    (runtime / 'config.yaml').write_text(config_text)
    final_groups = list(yaml.safe_load(config_text)['models'])
    assert original_groups == final_groups
    binding = {
        'test_preimage_sha256': sha(overlay / 'test_doctor.py'),
        'copied_conftest_sha256': sha(overlay / 'conftest.py'),
        'config_sha256': sha(runtime / 'config.yaml'),
        'original_model_groups': original_groups,
        'rewritten_model_groups': final_groups,
        'source_and_prior_evidence': before,
        'guard_plugin_sha256': sha(PARENT / 'doctor_guard.py'),
    }
    (BASE / 'source-binding.json').write_text(json.dumps(binding, indent=2) + '\n')
    profile = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex/provider-boundary.sb'
    command = ['/usr/bin/sandbox-exec', '-f', str(profile), str(REPO / '.venv/bin/python'), '-B', '-m', 'pytest', '-c', str(REPO / 'pyproject.toml'), '-p', 'doctor_guard', '-q', str(overlay / 'test_doctor.py') + '::TestDoctorCommand::test_doctor_uses_capability_probe_for_local_model_health', '--basetemp', str(runtime / 'pytest'), '--junitxml', str(BASE / 'junit.xml')]
    with (BASE / 'stdout.txt').open('xb') as stdout, (BASE / 'stderr.txt').open('xb') as stderr:
        completed = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=180)
after = {str(path): sha(path) for path in protected + source_paths}
assert before == after
suite = ET.parse(BASE / 'junit.xml').getroot().find('testsuite')
assert suite is not None
receipt = {'command': command, 'exit_code': completed.returncode, 'junit': suite.attrib, 'guard': json.loads((BASE / 'guard.json').read_bytes()), 'prior_manifest_entries_unchanged': 64, 'prior_manifest_itself_unchanged': True, 'current_source_unchanged': True, 'test_uses_original_preimage': True, 'scope': 'One original preimage test execution with full gate env and sort_keys=False; no static checks repeated.'}
(BASE / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
assert completed.returncode == 0 and suite.attrib['tests'] == '1' and suite.attrib['failures'] == '0' and suite.attrib['errors'] == '0'
entries = [{'path': str(path.relative_to(BASE)), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in sorted(BASE.rglob('*')) if path.is_file() and 'private-runtime' not in path.parts and '__pycache__' not in path.parts and path.name != 'artifact-manifest.json']
(BASE / 'artifact-manifest.json').write_text(json.dumps(entries, indent=2) + '\n')
print(json.dumps(receipt))
