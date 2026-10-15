from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
WORK = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path(__file__).resolve().parent
DOCS = Path('docs/qa/sequential-improvement/luna-handoff-2026-10-07')
RAW = DOCS / 'raw'
CONT = RAW / 'IMP20-CURRENT-CANDIDATE-CONTINUATION-01/run-20261015T020000Z-codex'
SOAK = RAW / 'IMP20-CURRENT-CANDIDATE-SOAK-01/run-20261015T020000Z-codex'
OLD = 'd8a8472e017c7ae13547758dae552420b50cd015'
BRANCH = 'refs/heads/codex/m1-task-events'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def save(name: str, value: object) -> None:
    with (BASE / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main() -> None:
    assert git(WORK, 'rev-parse', 'HEAD') == OLD
    assert git(WORK, 'status', '--porcelain') == ''
    assert git(ROOT, 'rev-parse', 'HEAD') == OLD
    assert git(ROOT, 'ls-remote', '--heads', 'ssak-ai', BRANCH).split()[0] == OLD
    assert not (BASE / 'commit-receipt.json').exists()
    review_source = ROOT / '.omo/evidence/IMP20-CONTINUATION-STORED-code-review.md'
    shutil.copyfile(review_source, BASE / 'independent-review.md')
    save('launch-observation.json', {
        'recorded_at': datetime.now(UTC).isoformat(),
        'state_snapshot': json.loads((ROOT / CONT / 'state.json').read_bytes()),
        'state_snapshot_sha256': sha(ROOT / CONT / 'state.json'),
        'gate_summary_snapshot': json.loads((ROOT / RAW / 'IMP20-FRESH-FULL-GATES-03/run-20261015T014000Z-codex/gate-report.json').read_bytes())['summary'],
        'runtime_result': 'NOT_OBSERVED', 'release_approval': 'NOT_ISSUED',
        'limits': 'Historical snapshot only. Read the live owned state/result for later transitions. Preparation checks do not prove runtime outcomes.',
    })
    paths = [DOCS / 'STATUS.md', DOCS / 'tasks.json']
    paths += [CONT / name for name in (
        'continuation.py', 'collector_proxy.py', 'prepared-plan.json', 'validate_preparation.py',
        'handoff.md', 'runtime-handoff-ko.md', 'launch-receipt.json', 'start-claim.json',
        'supervisor-claim.json', '.omo/evidence/preparation-evidence.json',
        '.omo/evidence/preparation.stdout.json', '.omo/evidence/preparation.stderr.txt',
    )]
    paths += [SOAK / name for name in (
        'start_soak_once.py', 'prepared-plan.json', 'preparation-evidence.json', 'handoff.md',
        'pre-proxy/start_soak_once.py', 'record_proxy_addendum.py', 'proxy-preparation-addendum.json',
    )]
    paths += [BASE.relative_to(ROOT) / name for name in ('publish.py', 'independent-review.md', 'launch-observation.json', 'launcher-attempt-01.json')]
    rows = [{'path': str(path), 'bytes': (ROOT / path).stat().st_size, 'sha256': sha(ROOT / path)} for path in paths]
    save('publication-inputs.json', {'files': rows, 'excluded_mutable_outputs': ['state.json', 'events.jsonl', 'supervisor stdout/stderr', 'future gate/soak/collector outputs']})
    paths += [BASE.relative_to(ROOT) / 'publication-inputs.json']
    for path in paths:
        source, destination = ROOT / path, WORK / path
        assert source.is_file() and not source.is_symlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        assert sha(source) == sha(destination)
    subprocess.run(['git', '-C', str(WORK), 'add', '-f', '--', *map(str, paths)], check=True)
    actual = set(git(WORK, 'diff', '--cached', '--name-only').splitlines())
    assert actual == set(map(str, paths)), actual.symmetric_difference(map(str, paths))
    for name, command in (
        ('commit', ['git', '-C', str(WORK), 'commit', '-m', 'docs: preserve bounded gate and soak continuation']),
        ('push', ['git', '-C', str(WORK), 'push', 'ssak-ai', 'HEAD:' + BRANCH]),
    ):
        with (BASE / (name + '.stdout.txt')).open('xb') as out, (BASE / (name + '.stderr.txt')).open('xb') as err:
            result = subprocess.run(command, stdout=out, stderr=err, check=False)
        save(name + '-receipt.json', {'command': command, 'actual_exit': result.returncode, 'head': git(WORK, 'rev-parse', 'HEAD')})
        assert result.returncode == 0, name
    new = git(WORK, 'rev-parse', 'HEAD')
    assert git(WORK, 'status', '--porcelain') == ''
    assert git(ROOT, 'ls-remote', '--heads', 'ssak-ai', BRANCH).split()[0] == new
    integration = ROOT / RAW / 'IMP20-GATE-PREREQUISITES-PUBLICATION-01/run-20261014T231300Z-codex/integrate_surface.py'
    spec = importlib.util.spec_from_file_location('continuation_qa_integration', integration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__dict__.update(OLD=OLD, NEW=new)
    module.__file__ = str(BASE / 'integration.py')
    module.main()
    save('publication-receipt.json', {'recorded_at': datetime.now(UTC).isoformat(), 'head': new, 'remote_sha_verified': new, 'paths': len(paths), 'formal_candidate_unchanged': '58d941b340a29a8717dcfbc87348b8542fe0bd77', 'gate_and_soak_completion': 'NOT_OBSERVED'})
    print(json.dumps({'status': 'DOCS_COMMITTED_PUSHED_ROOT_INTEGRATED', 'head': new, 'paths': len(paths)}))


if __name__ == '__main__':
    main()
