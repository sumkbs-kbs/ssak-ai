from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'python-interruption-completion.json'
assert not OUTPUT.exists()
report = json.loads((BASE / 'gate-report.json').read_bytes())
gate = next(row for row in report['gates'] if row['id'] == 'python-tests')
assert gate['status'] == 'failed' and 'KeyboardInterrupt' in gate['stdout']
lines = [line for line in gate['stdout'].splitlines() if re.search(r' FAILED\s+\[\s*\d+%\]$', line)]
counts = Counter(line.split('::', 1)[0] for line in lines)
processes = subprocess.run(
    ['ps', '-p', '59935,59941', '-o', 'pid,ppid,pgid,etime,command'],
    capture_output=True, text=True, check=False,
)
assert processes.returncode == 1 and len(processes.stdout.splitlines()) == 1
result = {
    'recorded_at': datetime.now(UTC).isoformat(),
    'kind': 'LATER_TERMINAL_OBSERVATION',
    'initial_receipt_preserved': True,
    'initial_receipt_sha256': hashlib.sha256((BASE / 'python-interruption-receipt.json').read_bytes()).hexdigest(),
    'candidate_head': report['git']['sha'],
    'python_gate': {key: gate[key] for key in ('id', 'command', 'started_at', 'finished_at', 'duration_seconds', 'status', 'exit_code')},
    'uv_wrapper_exit_observed': gate['exit_code'],
    'pytest_child_exit': None,
    'pytest_child_exit_observation': 'NOT_OBSERVED',
    'owned_pids_absent_at_read': [59935, 59941],
    'ps_exit': processes.returncode,
    'ps_stdout': processes.stdout,
    'partial_progress_failure_count': len(lines),
    'partial_progress_failure_counts_by_file': dict(counts),
    'partial_progress_failure_lines': lines,
    'pytest_completed': False,
    'limits': 'The gate wrapper reported exit 1 after the deliberate SIGINT. Partial FAILED progress lines are not a completed pytest summary. The outer gate runner continues independently; its interruption flag does not describe this inner interruption.',
}
OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({key: result[key] for key in ('kind', 'uv_wrapper_exit_observed', 'pytest_child_exit_observation', 'partial_progress_failure_count', 'partial_progress_failure_counts_by_file')}))
