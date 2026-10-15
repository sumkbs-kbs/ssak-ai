from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

base = Path(__file__).resolve().parent
report = json.loads((base / 'gate-report.json').read_bytes())
print(datetime.now(UTC).isoformat(), report['summary'])
print((base / 'driver.stdout.txt').read_text().splitlines()[-1])
for row in report['gates']:
    if row['id'] == 'python-tests' or row['status'] != 'passed':
        print(row['id'], row['status'], row['exit_code'])
        print(str(row.get('stdout', ''))[-4000:])
temporary = base / 'private-runtime/tmp'
if temporary.is_dir() and not any(row['id'] == 'python-tests' for row in report['gates']):
    for parent in temporary.iterdir():
        if parent.name.startswith('pytest-of-'):
            trial = parent / 'pytest-0'
            if trial.is_dir():
                recent = sorted(trial.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
                print('Recent fixture creation, not acceptance:', [path.name for path in recent[:4] if not path.is_symlink()])
