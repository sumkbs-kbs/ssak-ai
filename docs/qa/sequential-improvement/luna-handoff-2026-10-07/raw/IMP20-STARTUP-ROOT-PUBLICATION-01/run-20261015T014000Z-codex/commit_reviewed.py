from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
EXPECTED = {
    'src/antigravity_k/api/server.py': '0ffb369335863d266f56e2903067610ed3a2d67dea15dd4d746683b7333bb306',
    'tests/test_lifespan_agency_root_contract.py': '16b6d8cb74f013022648d12ae0bd7cb568ecb2559afca9522bff8f03a81039cf',
    'tests/test_lifespan_configured_project_root.py': 'e6fd37b5b5379b1c0909b1ac26e748df149110717bbba22d753d1b99ea36321f',
    'tests/test_doctor.py': '261e0b7a3b124b6668401bb1766d19244d6c23c6a540fffe25052ee22afb6e57',
}


def git(*args: str) -> str:
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True).strip()


def main() -> None:
    assert not (BASE / 'code-commits.json').exists()
    assert git('rev-parse', 'HEAD') == '7360c78544abeea41e38c65faa6eba2610a8a33b'
    assert not git('diff', '--cached', '--name-only')
    review = ROOT / '.omo/evidence/IMP20-STARTUP-ROOT-DOCTOR-review.md'
    assert 'deliveryVerdict: APPROVE_SCOPED' in review.read_text()
    for path, sha in EXPECTED.items():
        assert hashlib.sha256((REPO / path).read_bytes()).hexdigest() == sha, path
    records = []
    groups = (
        ('startup', list(EXPECTED)[:3], 'fix: honor configured project root during startup'),
        ('doctor', [list(EXPECTED)[3]], 'test: isolate doctor capability checks from catalog order'),
    )
    for label, paths, message in groups:
        previous = git('rev-parse', 'HEAD')
        git('add', '--', *paths)
        staged = git('diff', '--cached', '--name-only').splitlines()
        assert set(staged) == set(paths), staged
        (BASE / f'{label}-staged.diff').write_text(git('diff', '--cached', '--binary'))
        completed = subprocess.run(['git', '-C', str(REPO), 'commit', '-m', message], capture_output=True)
        (BASE / f'{label}-commit.stdout.txt').write_bytes(completed.stdout)
        (BASE / f'{label}-commit.stderr.txt').write_bytes(completed.stderr)
        assert completed.returncode == 0, f'{label} normal commit failed: see preserved hook output'
        head = git('rev-parse', 'HEAD')
        assert set(git('diff', '--name-only', previous, head).splitlines()) == set(paths)
        for path in paths:
            committed = subprocess.check_output(['git', '-C', str(REPO), 'show', head + ':' + path])
            assert hashlib.sha256(committed).hexdigest() == EXPECTED[path], path
        records.append({'label': label, 'head': head, 'parent': previous, 'paths': paths, 'message': message, 'normal_commit_exit': completed.returncode})
        print(json.dumps(records[-1]), flush=True)
    assert not git('status', '--porcelain')
    result = {'recorded_at': datetime.now(UTC).isoformat(), 'commits': records, 'source_hashes': EXPECTED, 'independent_review_sha256': hashlib.sha256(review.read_bytes()).hexdigest(), 'candidate_clean': True, 'root_integration': 'PENDING', 'push': 'PENDING'}
    (BASE / 'code-commits.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
