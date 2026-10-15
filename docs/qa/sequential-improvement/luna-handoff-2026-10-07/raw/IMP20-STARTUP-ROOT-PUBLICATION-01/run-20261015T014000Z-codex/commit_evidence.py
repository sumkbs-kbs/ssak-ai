from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
OLD = '58d941b340a29a8717dcfbc87348b8542fe0bd77'


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def row(path: str) -> dict[str, object]:
    content = (REPO / path).read_bytes()
    return {'path': path, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}


def main() -> None:
    assert not (BASE / 'qa-commit.json').exists()
    assert git('rev-parse', 'HEAD').decode().strip() == OLD
    assert not git('diff', '--cached', '--name-only').strip()
    paths = (BASE / 'evidence-copy/staged-candidate-paths.txt').read_text().splitlines()
    assert len(paths) == len(set(paths)) == 345
    assert all(path.startswith('docs/qa/') and 'private-runtime' not in path for path in paths)
    publication = json.loads((BASE / 'evidence-copy/publication-inventory.json').read_bytes())
    origins = {item['path']: item for item in publication['files']}
    for path in paths:
        origin = origins.get(path)
        source = ROOT / (origin['source'] if origin is not None else path)
        assert source.resolve().is_relative_to(ROOT)
        content = (REPO / path).read_bytes()
        assert source.read_bytes() == content, path
        if origin is not None:
            assert len(content) == origin['bytes'] and hashlib.sha256(content).hexdigest() == origin['sha256'], path
    own_path = str(Path(__file__).relative_to(ROOT))
    (REPO / own_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__), REPO / own_path)
    paths.append(own_path)
    inventory_path = str(BASE.relative_to(ROOT) / 'commit-inputs.json')
    inventory = {'recorded_at': datetime.now(UTC).isoformat(), 'code_candidate': OLD, 'rows': [row(path) for path in paths], 'limits': 'Docs-only publication of stored scoped proof; formal candidate WT3 remains frozen at the code candidate.'}
    data = json.dumps(inventory, indent=2) + '\n'
    (ROOT / inventory_path).write_text(data)
    (REPO / inventory_path).write_text(data)
    paths.append(inventory_path)
    git('add', '--', *paths)
    staged = git('diff', '--cached', '--name-only', '-z').decode().split('\0')[:-1]
    assert set(staged) == set(paths) and len(staged) == 347
    completed = subprocess.run(['git', '-C', str(REPO), 'commit', '-m', 'docs: preserve startup repair and gate environment evidence'], capture_output=True)
    (BASE / 'qa-commit.stdout.txt').write_bytes(completed.stdout)
    (BASE / 'qa-commit.stderr.txt').write_bytes(completed.stderr)
    assert completed.returncode == 0, 'See preserved normal commit hook output'
    new = git('rev-parse', 'HEAD').decode().strip()
    changed = git('diff', '--name-only', OLD, new).decode().splitlines()
    assert set(changed) == set(paths)
    assert not git('status', '--porcelain').strip()
    result = {'recorded_at': datetime.now(UTC).isoformat(), 'old_head': OLD, 'head': new, 'normal_commit_exit': completed.returncode, 'paths': len(paths), 'docs_only': all(path.startswith('docs/') for path in changed), 'formal_candidate_unchanged': OLD, 'integration': 'PENDING', 'push': 'PENDING'}
    (BASE / 'qa-commit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
