import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
WT2 = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')
BASE = Path('docs/qa/sequential-improvement/luna-handoff-2026-10-07')
RAW = BASE / 'raw'
PUB = RAW / 'IMP20-STARTUP-ROOT-PUBLICATION-01/run-20261015T014000Z-codex'
OUT = PUB / 'evidence-copy'
HEAD = '58d941b340a29a8717dcfbc87348b8542fe0bd77'
STARTUP = RAW / 'IMP20-STARTUP-PROJECT-ROOT-01/run-20261015T011000Z-codex'
DOCTOR = RAW / 'IMP20-DOCTOR-GATE-FIXTURE-01/run-20261015T011500Z-codex'
SANDBOX = RAW / 'IMP20-SANDBOX-GATE-ENVIRONMENT-01/run-20261015T011500Z-codex'
MANIFESTS = [
    (RAW / 'IMP20-FRESH-FULL-GATES-02/run-20261015T001700Z-codex/artifact-manifest.json', 32),
    (STARTUP / 'artifact-manifest.json', 158),
    (STARTUP / 'primary-startup/supplemental-manifest.json', 14),
    (STARTUP / 'primary-startup/attempt-02/review-manifest.json', 11),
    (DOCTOR / 'artifact-manifest.json', 64),
    (DOCTOR / 'order-preservation/artifact-manifest.json', 10),
    (SANDBOX / 'artifact-manifest.json', 21),
    (SANDBOX / 'static-audit-manifest.json', 6),
]
REVIEWED = {
    'src/antigravity_k/api/server.py': '0ffb369335863d266f56e2903067610ed3a2d67dea15dd4d746683b7333bb306',
    'tests/test_lifespan_agency_root_contract.py': '16b6d8cb74f013022648d12ae0bd7cb568ecb2559afca9522bff8f03a81039cf',
    'tests/test_lifespan_configured_project_root.py': 'e6fd37b5b5379b1c0909b1ac26e748df149110717bbba22d753d1b99ea36321f',
    'tests/test_doctor.py': '261e0b7a3b124b6668401bb1766d19244d6c23c6a540fffe25052ee22afb6e57',
}
CURRENT_DOCUMENTS = {str(BASE / 'STATUS.md'), str(BASE / 'tasks.json')}


def historical_digest(relative, data):
    if relative.endswith('tasks.json'):
        tasks = json.loads(data)
        tasks.pop('current_snapshot')
        history = json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode()
        expected = 'f1308d24b740563988a7c912078dec7ae65bf3c1e855be7cf15bc03e1938ec18'
    else:
        marker = '## 역사 스냅샷 — 2026-10-07 원문 보존'.encode()
        if data.count(marker) != 1:
            raise ValueError('Historical STATUS marker missing or duplicated')
        history = data.split(marker, 1)[1]
        expected = 'fd06974b8794cd7430ffaa76e524be87bec469022a0fa4498290ce35dbdac261'
    actual = digest(history)
    if actual != expected:
        raise ValueError(f'Historical guard mismatch: {relative}: {actual}')
    return actual


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_checked(root, relative):
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Unsafe path: {relative}')
    if any('private-runtime' in part.lower() or 'secret' in part.lower()
           or part.lower() in {'.env', 'auth', 'pin', 'pins'}
           or part.lower().endswith(('.pin', '.key', '.pem')) for part in relative.parts):
        raise ValueError(f'Non-public path: {relative}')
    path = root / relative
    if path.resolve() != path or not path.is_file():
        raise ValueError(f'Missing file or symlink: {path}')
    return path.read_bytes()


def main():
    rows = {}
    manifest_checks = []
    failures = []
    source_binding = []
    history_checks = []
    timestamp = datetime.now(timezone.utc).isoformat()
    before_index = subprocess.check_output(['git', '-C', str(WT2), 'diff', '--cached', '--binary'])
    observed_head = subprocess.check_output(['git', '-C', str(WT2), 'rev-parse', 'HEAD'], text=True).strip()
    if observed_head != HEAD:
        raise ValueError(f'Candidate changed: {observed_head}')

    def add(source, destination=None, expected=None, authority='explicit assignment'):
        destination = destination or source
        data = read_checked(ROOT, source)
        actual = {'bytes': len(data), 'sha256': digest(data)}
        if expected is not None and any(actual[k] != expected[k] for k in actual):
            failures.append({'source': str(source), 'kind': 'manifest_mismatch', 'actual': actual, 'expected': expected})
        record = {'source': str(source), 'path': str(destination), **actual, 'authority': authority}
        prior = rows.get(str(destination))
        if prior and (prior['sha256'], prior['bytes']) != (record['sha256'], record['bytes']):
            failures.append({'path': str(destination), 'kind': 'duplicate_conflict'})
        rows[str(destination)] = record

    for manifest, expected_count in MANIFESTS:
        add(manifest, authority='immutable manifest')
        obj = json.loads(read_checked(ROOT, manifest))
        entries = obj if isinstance(obj, list) else obj['artifacts']
        if len(entries) != expected_count:
            raise ValueError(f'Manifest row count changed: {manifest}')
        for entry in entries:
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError(f'Invalid manifest row: {relative}')
            add(manifest.parent / relative, expected=entry, authority=str(manifest))
        manifest_checks.append({'path': str(manifest), 'rows': len(entries), 'sha256': rows[str(manifest)]['sha256']})

    for relative in [STARTUP / 'handoff-ko.md', STARTUP / 'primary-startup/primary-manual-review.md']:
        add(relative)
    for name in ['code-commits.json', 'commit_reviewed.py', 'startup-staged.diff',
                 'startup-commit.stdout.txt', 'startup-commit.stderr.txt',
                 'doctor-staged.diff', 'doctor-commit.stdout.txt', 'doctor-commit.stderr.txt',
                 'integrate_code.py', 'integration-receipt-a7.json']:
        add(PUB / name)
    for source, destination in [
        ('.omo/evidence/IMP20-STARTUP-ROOT-DOCTOR-review.md', OUT / 'independent-review.md'),
        ('.omo/evidence/IMP20-STARTUP-ROOT-DOCTOR-gate-review.md', OUT / 'independent-review-full.md'),
        ('.omo/evidence/IMP20-STARTUP-ROOT-DOCTOR-gate-review.md', OUT / 'IMP20-STARTUP-ROOT-DOCTOR-gate-review.md'),
    ]:
        add(Path(source), destination)
    add(OUT / 'copy_public_evidence.py')
    for relative in sorted(CURRENT_DOCUMENTS):
        source = read_checked(ROOT, Path(relative))
        current = read_checked(WT2, Path(relative))
        committed = subprocess.check_output(['git', '-C', str(WT2), 'show', f'{HEAD}:{relative}'])
        hashes = [historical_digest(relative, data) for data in (source, current, committed)]
        if len(set(hashes)) != 1:
            raise ValueError(f'History differs: {relative}')
        history_checks.append({'path': relative, 'root_history_sha256': hashes[0],
                               'wt2_history_sha256': hashes[1], 'head_history_sha256': hashes[2],
                               'destination_before_sha256': digest(current), 'history_preserved': True})
        add(Path(relative), authority='parent explicitly authorized two current-document replacements after guards')

    for relative, expected in REVIEWED.items():
        current = read_checked(WT2, Path(relative))
        committed = subprocess.check_output(['git', '-C', str(WT2), 'show', f'{HEAD}:{relative}'])
        check = {'path': relative, 'expected_sha256': expected, 'working_sha256': digest(current),
                 'committed_sha256': digest(committed), 'matches': digest(current) == digest(committed) == expected}
        source_binding.append(check)
        if not check['matches']:
            failures.append({'kind': 'reviewed_source_mismatch', **check})

    for row in rows.values():
        destination = WT2 / row['path']
        if destination.exists():
            current = read_checked(WT2, Path(row['path']))
            if row['path'] in CURRENT_DOCUMENTS:
                row['action'] = 'replace_authorized_current_document'
                row['destination_before_sha256'] = digest(current)
            elif len(current) != row['bytes'] or digest(current) != row['sha256']:
                failures.append({'path': row['path'], 'kind': 'existing_destination_mismatch', 'actual_sha256': digest(current)})
                row['action'] = 'blocked_mismatch'
            else:
                row['action'] = 'identical_existing'
        else:
            row['action'] = 'copy_new'

    inventory = {'recorded_at': timestamp, 'candidate_head': HEAD,
                 'scope': 'Stored public evidence integrity and four-file scoped review binding only; not full gates, soak, GA, or live model approval.',
                 'current_documents': 'AUTHORIZED_GUARDED_REPLACEMENT', 'history_checks': history_checks,
                 'manifests': manifest_checks, 'reviewed_source_binding': source_binding,
                 'files': sorted(rows.values(), key=lambda row: row['path']), 'failures': failures}
    inventory_path = ROOT / OUT / 'publication-inventory.json'
    inventory_path.write_text(json.dumps(inventory, indent=2) + '\n')
    if failures:
        raise ValueError(f'Preflight failed; see {inventory_path}')

    for row in sorted(rows.values(), key=lambda item: item['path']):
        data = read_checked(ROOT, Path(row['source']))
        if len(data) != row['bytes'] or digest(data) != row['sha256']:
            raise ValueError(f'Source changed before copy: {row["source"]}')
        destination = WT2 / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        if row['action'] == 'copy_new':
            with destination.open('xb') as handle:
                handle.write(data)
        elif row['action'] == 'replace_authorized_current_document':
            current = read_checked(WT2, Path(row['path']))
            if digest(current) != row['destination_before_sha256']:
                raise ValueError(f'Current document changed during copy: {destination}')
            destination.write_bytes(data)
            historical_digest(row['path'], destination.read_bytes())
        actual = read_checked(WT2, Path(row['path']))
        if digest(actual) != row['sha256'] or len(actual) != row['bytes']:
            raise ValueError(f'Copy verification failed: {destination}')

    after_index = subprocess.check_output(['git', '-C', str(WT2), 'diff', '--cached', '--binary'])
    if before_index != after_index:
        raise ValueError('Index changed during publication preparation')
    receipt = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'status': 'PASS_PUBLIC_ARTIFACT_COPY',
               'scenario': 'Manifest-sourced public evidence copy into WT2 at code commit 58d941b3',
               'invocation': f'python3 {OUT / "copy_public_evidence.py"}',
               'binary_observable': 'All 316 manifest rows and explicit additions match SHA/bytes; every destination matches inventory; only two authorized current documents replaced with historical guards preserved; index unchanged.',
               'manifest_rows_verified': sum(m['rows'] for m in manifest_checks),
               'unique_artifacts': len(rows), 'copied_new': sum(r['action'] == 'copy_new' for r in rows.values()),
               'identical_existing': sum(r['action'] == 'identical_existing' for r in rows.values()),
               'inventory_sha256': digest(inventory_path.read_bytes()), 'index_unchanged': True,
               'candidate_head': HEAD, 'current_documents': 'COPIED_HISTORY_GUARDS_PASS',
               'no_execution_tests_http_models': True,
               'empty_artifacts': [r['path'] for r in rows.values() if r['bytes'] == 0]}
    receipt_path = ROOT / OUT / 'publication-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    generated = [OUT / 'publication-inventory.json', OUT / 'publication-receipt.json', OUT / 'staged-candidate-paths.txt']
    candidates = sorted(set(rows) | {str(p) for p in generated})
    (ROOT / generated[-1]).write_text('\n'.join(candidates) + '\n')
    for relative in generated:
        data = (ROOT / relative).read_bytes()
        destination = WT2 / relative
        with destination.open('xb') as handle:
            handle.write(data)
        if destination.read_bytes() != data:
            raise ValueError(f'Generated artifact copy failed: {destination}')
    print(json.dumps({'status': receipt['status'], 'artifacts': len(rows), 'manifest_rows': receipt['manifest_rows_verified'],
                      'receipt': str(receipt_path), 'candidate_paths': len(candidates)}))


if __name__ == '__main__':
    main()
