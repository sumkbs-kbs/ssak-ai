from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
HEAD = '7360c78544abeea41e38c65faa6eba2610a8a33b'
assert not (BASE / 'result.json').exists()
receipt = json.loads((BASE / 'launch-receipt.json').read_bytes())
runner_receipt = json.loads((BASE / 'runner-receipt.json').read_bytes())
report = json.loads((BASE / 'gate-report.json').read_bytes())
binding = json.loads((BASE / 'execution-binding.json').read_bytes())
assert receipt['reaped'] and runner_receipt['reaped']
assert binding['candidate']['head'] == HEAD
command = [str(REPO / '.venv/bin/python'), '-B', 'scripts/ga_gate_verify.py', '--report', str(BASE / 'gate-report.json'), '--manifest', 'scripts/commercial_ga_gates.json', '--expected-sha', HEAD]
verified = subprocess.run(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
(BASE / 'verification.stdout.txt').write_bytes(verified.stdout)
(BASE / 'verification.stderr.txt').write_bytes(verified.stderr)
(BASE / 'verification.json').write_text(json.dumps({'command': command, 'exit_code': verified.returncode}, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('gate_fingerprint', REPO / 'scripts/ga_gate.py')
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
current_head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
current_fingerprint = gate.worktree_fingerprint(REPO)
status = subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip()
source_unchanged = receipt['candidate_unchanged'] and current_head == HEAD and current_fingerprint == binding['candidate']['working_fingerprint'] and not status
manifest = REPO / 'scripts/commercial_ga_gates.json'
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == binding['manifest_sha256']
assert report['merged'] is False
required_ids = {row['id'] for row in json.loads(manifest.read_bytes())['gates'] if row['required']}
executed_ids = [row['id'] for row in report['gates']]
exact_selection = len(executed_ids) == len(set(executed_ids)) == 23 and set(executed_ids) == required_ids
passed = verified.returncode == 0 and receipt['exit_code'] == 0 and not receipt['timed_out_or_interrupted'] and source_unchanged and exact_selection
result = {
    'recorded_at': datetime.now(UTC).isoformat(), 'head': HEAD,
    'status': 'PASS_FRESH_SAME_CANDIDATE_23' if passed else 'FAIL_FRESH_SAME_CANDIDATE_GATES',
    'summary': report['summary'], 'verification_exit': verified.returncode,
    'gate_process_exit': receipt['exit_code'], 'source_unchanged': source_unchanged,
    'fingerprint': current_fingerprint, 'required': 23,
    'exact_selection': exact_selection,
    'new8hsoak': 'NOT_RUN', 'release_approval': 'NOT_ISSUED',
    'historical_results_merged': False,
    'known_startup_root_defect': (BASE / 'soak-hold.json').exists(),
    'soak_eligible': passed and not (BASE / 'soak-hold.json').exists(),
    'limits': 'Formal gate result at the recorded source and environment. Prior diagnostic/live results and historical ledgers are unchanged; no release or model-quality approval.',
}
(BASE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
names = (
    'run_full_gates.py', 'start_once.py', 'finalize.py', 'start_soak_once.py',
    'candidate-freeze.json', 'os-guard-control.json', 'control-provenance.json',
    'python-live-sample.txt', 'diagnostic-observation.json',
    'duration-triage.md',
    'observe.py',
    'observer-interpreter-correction.json',
    'soak-hold.json',
    'interrupt_obsolete_python.py', 'python-interruption-decision.json', 'python-interruption-receipt.json',
    'record_interruption_completion.py', 'python-interruption-completion.json',
    'provider-boundary.sb', 'execution-binding.json', 'launch.json',
    'driver.stdout.txt', 'driver.stderr.txt', 'gate-report.json', 'launch-receipt.json',
    'runner.stdout.txt', 'runner.stderr.txt', 'runner-receipt.json',
    'verification.stdout.txt', 'verification.stderr.txt', 'verification.json', 'result.json',
)
inventory = []
for name in names:
    path = BASE / name
    inventory.append({'path': name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(inventory, indent=2) + '\n')
print(json.dumps(result))
