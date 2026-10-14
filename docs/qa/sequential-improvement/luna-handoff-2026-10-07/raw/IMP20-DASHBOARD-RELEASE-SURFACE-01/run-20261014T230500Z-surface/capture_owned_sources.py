from pathlib import Path
import hashlib
import json

OUT = Path(__file__).parent
WT = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
paths = ['dashboard/src/components/Agent/AgentMonitorPanel.tsx', 'dashboard/src/styles/index.css', 'dashboard/e2e/pages/DashboardPage.ts', 'dashboard/e2e/tests/cr07-route-recovery.spec.ts', 'dashboard/e2e/tests/cr08-keyboard-accessibility.spec.ts', 'dashboard/e2e/tests/cr10-telemetry.spec.ts', 'dashboard/build-provenance.json']
records = []
for name in paths:
    data = (WT / name).read_bytes()
    target = OUT / 'preimage' / name
    if target.exists():
        assert target.read_bytes() == data, name
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    records.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
with (OUT / 'owned-preimage.json').open('x') as stream:
    json.dump(records, stream, indent=2)
print(f'Preserved {len(records)} owned source preimages')
