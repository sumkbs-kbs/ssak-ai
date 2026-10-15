from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
RAW = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw'
PACKETS = (
    'IMP20-FRESH-FULL-GATES-01/run-20261014T234000Z-codex',
    'IMP20-EMBEDDING-STRICT-FIXTURE-01/run-20261015T010000Z-embedding',
    'IMP20-EMBEDDING-STRICT-FIXTURE-01/run-20261015T010000Z-embedding/revision-v2',
    'IMP20-COGNITIVE-REVERIFICATION-01/run-20261014T235000Z-codex',
    'IMP20-COGNITIVE-REVERIFICATION-01/run-20261014T235000Z-codex/supplement-20261014T235420Z',
    'IMP20-BUILD-PROVENANCE-SHA-01/run-20261014T235500Z-codex',
    'IMP20-MODEL-EMPTY-CONTRAST-01/run-20261014T235534Z-model-empty',
    'IMP20-MODEL-EMPTY-CONTRAST-VALIDATION-01/run-20261015T000000Z-codex',
    str(BASE.relative_to(RAW)),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path, folder: Path) -> dict[str, str | int]:
    return {'path': str(path.relative_to(folder)), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def write_new(path: Path, value: object) -> None:
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def main() -> None:
    expected = '1e9dfb87b185f3d20792d3f4bff4a25189947c15'
    remote = subprocess.check_output(['git', '-C', str(ROOT), 'ls-remote', 'ssak-ai', 'refs/heads/codex/m1-task-events'], text=True).split()[0]
    assert remote == expected
    write_new(BASE / 'remote-verification.json', {'remote_head': remote, 'scope': 'Code candidate push verified before QA publication'})
    shutil.copyfile(ROOT / '.omo/evidence/IMP20-GATE-ROUND2-1e9-review.md', BASE / 'independent-review.md')
    migration = BASE / 'migration-current'
    migration_paths = [migration / name for name in ('verify.py', 'source-binding.json', 'stdout.txt', 'stderr.txt', 'junit.xml', 'receipt.json')]
    write_new(migration / 'artifact-manifest.json', [record(p, migration) for p in migration_paths])
    extras = [BASE / name for name in ('publish_packets.py', 'integrate_round2.py', 'integration-receipt-a7.json', 'remote-verification.json', 'independent-review.md', 'handoff-ko.md')]
    extras += migration_paths + [migration / 'artifact-manifest.json']
    build = RAW / 'IMP20-BUILD-PROVENANCE-SHA-01/run-20261014T235500Z-codex'
    extras += [build / name for name in ('setup_python_environment.py', 'python-setup.stdout.txt', 'python-setup.stderr.txt', 'python-setup.json')]
    write_new(BASE / 'supplemental-manifest.json', [record(p, ROOT) for p in extras])
    inventory: dict[str, dict[str, str | int]] = {}

    def include(path: Path, expected_bytes: int | None = None, expected_sha: str | None = None) -> None:
        relative = path.relative_to(ROOT)
        assert not {'private-runtime', 'auth-private', 'private-raw', '__pycache__'}.intersection(relative.parts), relative
        data = path.read_bytes()
        if expected_bytes is not None:
            assert len(data) == expected_bytes, relative
        if expected_sha is not None:
            assert hashlib.sha256(data).hexdigest() == expected_sha, relative
        destination = REPO / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert destination.read_bytes() == data, relative
        else:
            destination.write_bytes(data)
        inventory[str(relative)] = record(path, ROOT)

    for folder_name in PACKETS:
        folder = RAW / folder_name
        manifest = folder / 'artifact-manifest.json'
        payload = json.loads(manifest.read_bytes())
        if isinstance(payload, dict) and 'files' in payload:
            rows = payload['files']
        elif isinstance(payload, dict):
            rows = [{'path': name, **entry} for name, entry in payload.items()]
        else:
            rows = payload
        if isinstance(rows, dict):
            rows = [{'path': name, **entry} for name, entry in rows.items()]
        for row in rows:
            include(folder / row['path'], row['bytes'], row['sha256'])
        include(manifest)
    for row in json.loads((BASE / 'supplemental-manifest.json').read_bytes()):
        include(ROOT / row['path'], row['bytes'], row['sha256'])
    include(BASE / 'supplemental-manifest.json')
    for name in ('STATUS.md', 'tasks.json'):
        source = RAW.parent / name
        relative = source.relative_to(ROOT)
        (REPO / relative).write_bytes(source.read_bytes())
        inventory[str(relative)] = record(source, ROOT)
    write_new(BASE / 'publication-inventory.json', list(inventory.values()))
    destination = REPO / (BASE / 'publication-inventory.json').relative_to(ROOT)
    destination.write_bytes((BASE / 'publication-inventory.json').read_bytes())
    print(json.dumps({'files': len(inventory) + 1, 'bytes': sum(int(r['bytes']) for r in inventory.values()), 'candidate': expected}))


if __name__ == '__main__':
    main()
