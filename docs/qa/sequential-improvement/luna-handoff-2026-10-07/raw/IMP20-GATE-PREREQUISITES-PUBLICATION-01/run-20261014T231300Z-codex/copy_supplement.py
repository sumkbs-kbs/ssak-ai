from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
CANDIDATE = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent
RAW = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw'
FILES = [
    *[BASE / n for n in (
        'README.md', 'followup-a7.md', 'independent-review.md',
        'independent-review-a7.md', 'integrate_owned.py', 'integrate_surface.py',
        'integration-receipt.json', 'integration-receipt-a7.json',
        'copy_public_evidence.py', 'copy_ui_evidence.py', 'copy_supplement.py',
        'public-copy-receipt.json', 'public-ui-copy-receipt.json',
        'public-copy-path-correction.md',
    )],
    *[RAW / 'IMP20-DASHBOARD-RELEASE-SURFACE-01/run-20261014T230500Z-surface/primary-review-current' / n for n in (
        'source-binding.json', 'server.json', 'server.stdout.txt',
        'server.stderr.txt', 'cleanup.json', 'observations.json',
        'websocket-limitation.md',
    )],
    *[RAW / 'IMP20-GATE-RUNTIME-ENVIRONMENT-01/run-20261014T165600Z-codex/historical-selftest-correction' / n for n in (
        'README.md', 'diagnostic-soak-exit-with-selftest-append.txt',
    )],
    *[RAW / run / n for run in (
        'IMP19-BANDIT-GATE-CLOSURE-01/run-20261014T173200Z-codex',
        'IMP19-PYTHON-DEPENDENCY-FLOORS-01/run-20261014T174700Z-codex',
        'IMP20-GATE-RUNTIME-ENVIRONMENT-01/run-20261014T165600Z-codex',
    ) for n in ('review-lane-records.json', 'integrate_owned.py', 'integration-receipt.json')],
    RAW / 'IMP20-GATE-RUNTIME-ENVIRONMENT-01/run-20261014T165600Z-codex/independent-approval.md',
    RAW / 'IMP19-PYTHON-DEPENDENCY-FLOORS-01/run-20261014T174700Z-codex/orchestration-path-correction.md',
    ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/STATUS.md',
    ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/tasks.json',
]


def main() -> None:
    inventory = {}
    for source in FILES:
        assert source.is_file() and not source.is_symlink(), str(source)
        rel = source.relative_to(ROOT)
        assert not {'private-runtime', 'cache', 'auth-private'}.intersection(rel.parts)
        data = source.read_bytes()
        inventory[str(rel)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    for relative, row in inventory.items():
        source = ROOT / relative
        destination = CANDIDATE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and relative.endswith('/raw/' + BASE.parent.name):
            raise AssertionError('Unexpected directory collision')
        if '/raw/' in relative and destination.exists():
            assert destination.read_bytes() == source.read_bytes(), str(destination)
        else:
            shutil.copyfile(source, destination)
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == row['sha256']
    receipt = BASE / 'public-supplement-copy-receipt.json'
    assert not receipt.exists()
    receipt.write_text(json.dumps({'files': len(inventory), 'inventory': inventory}, indent=2) + '\n')
    target = CANDIDATE / receipt.relative_to(ROOT)
    shutil.copyfile(receipt, target)
    print(json.dumps({'files': len(inventory), 'receipt_copied': True}))


if __name__ == '__main__':
    main()
