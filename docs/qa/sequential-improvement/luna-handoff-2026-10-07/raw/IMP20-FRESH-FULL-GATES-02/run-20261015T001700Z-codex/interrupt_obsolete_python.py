from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[5]
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
RED = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-STARTUP-PROJECT-ROOT-01/run-20261015T011000Z-codex/red-01')
report = json.loads((BASE / 'gate-report.json').read_bytes())
assert not any(row['id'] == 'python-tests' for row in report['gates']), 'Python gate already ended'
suite = next(ET.parse(RED / 'junit.xml').getroot().iter('testsuite'))
assert suite.get('tests') == '6' and suite.get('failures') == '4' and suite.get('errors') == '0'
expected_sha = '6b5945cefe9d39294a1a3372bf812e9e5d28bd6e190f59846a6b4ce81a7655a7'
assert hashlib.sha256((REPO / 'src/antigravity_k/api/server.py').read_bytes()).hexdigest() == expected_sha
command = subprocess.check_output(['ps', '-o', 'ppid=,args=', '-p', '59935'], text=True).strip()
assert command.startswith('59401 ') and 'uv run --isolated --frozen' in command and 'pytest tests/' in command
assert os.getpgid(59935) == 59935
decision = {
    'recorded_at': datetime.now(UTC).isoformat(), 'candidate': '7360c78544abeea41e38c65faa6eba2610a8a33b',
    'reason': 'New bounded real-lifespan regression proves explicit configured startup root is ignored (4FAIL/2PASS). Preserve this obsolete full Python run as interrupted and spend the remaining budget on the corrected candidate.',
    'red_receipt': str(RED / 'receipt.json'), 'red_junit': str(RED / 'junit.xml'),
    'red_receipt_sha256': hashlib.sha256((RED / 'receipt.json').read_bytes()).hexdigest(),
    'red_junit_sha256': hashlib.sha256((RED / 'junit.xml').read_bytes()).hexdigest(),
    'unchanged_server_sha256': expected_sha, 'gate_process_parent': 59401,
    'target_group': 59935, 'target_command_verified': command,
    'signal': 'SIGINT', 'other_gates': 'Continue normally on the unchanged candidate; do not merge with a later candidate.',
}
with (BASE / 'python-interruption-decision.json').open('x') as stream:
    json.dump(decision, stream, indent=2)
    stream.write('\n')
os.killpg(59935, signal.SIGINT)
started = time.monotonic()
row = None
while time.monotonic() - started < 30:
    report = json.loads((BASE / 'gate-report.json').read_bytes())
    row = next((item for item in report['gates'] if item['id'] == 'python-tests'), None)
    if row is not None:
        break
    time.sleep(0.25)
receipt = {'signal_sent': True, 'python_gate_record_observed': row is not None, 'python_gate_status': row['status'] if row else None, 'python_gate_exit': row['exit_code'] if row else None}
with (BASE / 'python-interruption-receipt.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt))
