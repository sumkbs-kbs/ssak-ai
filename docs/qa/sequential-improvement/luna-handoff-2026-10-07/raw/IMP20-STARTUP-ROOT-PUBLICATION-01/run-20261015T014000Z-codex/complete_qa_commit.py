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


def git(*args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(['git', '-C', str(REPO), *args], input=data, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f'git {args[0]} exit {result.returncode}: {result.stderr.decode()[:1000]}')
    return result.stdout


def main() -> None:
    assert not (BASE / 'qa-commit.json').exists()
    assert git('rev-parse', 'HEAD').decode().strip() == '58d941b340a29a8717dcfbc87348b8542fe0bd77'
    inventory_path = str(BASE.relative_to(ROOT) / 'commit-inputs.json')
    inventory = json.loads((ROOT / inventory_path).read_bytes())
    for item in inventory['rows']:
        content = (REPO / item['path']).read_bytes()
        assert len(content) == item['bytes'] and hashlib.sha256(content).hexdigest() == item['sha256'], item['path']
    paths = [item['path'] for item in inventory['rows']] + [inventory_path]
    staged = set(git('diff', '--cached', '--name-only', '-z').decode().split('\0')) - {''}
    assert staged <= set(paths)
    ignored = git('check-ignore', '--stdin', data=('\n'.join(paths) + '\n').encode()).decode().splitlines()
    assert len(ignored) == 12 and all('/agency-captures/' in path and path.endswith('.log') for path in ignored)
    diagnostic = {'recorded_at': datetime.now(UTC).isoformat(), 'first_stage_exit': 1, 'reason': 'Twelve explicit manifest-verified agency stdout/stderr .log artifacts match the general ignore rule. Partial owned staging was preserved. Add only these approved public evidence paths with git add -f; no hooks or tests are disabled.', 'ignored_public_paths': ignored, 'staged_before_completion': len(staged), 'private_files_added': 0}
    with (BASE / 'staging-diagnostic.json').open('x') as stream:
        stream.write(json.dumps(diagnostic, indent=2) + '\n')
    for source in (Path(__file__), BASE / 'staging-diagnostic.json'):
        path = str(source.relative_to(ROOT))
        shutil.copyfile(source, REPO / path)
        paths.append(path)
    git('add', '--force', '--', *ignored)
    git('add', '--', *paths)
    final_staged = set(git('diff', '--cached', '--name-only', '-z').decode().split('\0')) - {''}
    assert final_staged == set(paths) and len(paths) == 349
    result = subprocess.run(['git', '-C', str(REPO), 'commit', '-m', 'docs: preserve startup repair and gate environment evidence'], capture_output=True, check=False)
    (BASE / 'qa-commit.stdout.txt').write_bytes(result.stdout)
    (BASE / 'qa-commit.stderr.txt').write_bytes(result.stderr)
    assert result.returncode == 0, 'See preserved normal hook output'
    head = git('rev-parse', 'HEAD').decode().strip()
    assert set(git('diff', '--name-only', '58d941b3', head).decode().splitlines()) == set(paths)
    assert not git('status', '--porcelain').strip()
    receipt = {'recorded_at': datetime.now(UTC).isoformat(), 'head': head, 'parent': '58d941b340a29a8717dcfbc87348b8542fe0bd77', 'paths': len(paths), 'normal_commit_exit': result.returncode, 'docs_only': True, 'formal_candidate_frozen_at': '58d941b340a29a8717dcfbc87348b8542fe0bd77', 'integration': 'PENDING', 'push': 'PENDING'}
    (BASE / 'qa-commit.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
