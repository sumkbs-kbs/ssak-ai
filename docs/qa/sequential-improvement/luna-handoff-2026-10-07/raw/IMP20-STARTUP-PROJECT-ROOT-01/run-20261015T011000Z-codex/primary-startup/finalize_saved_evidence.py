from __future__ import annotations

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PACKET = BASE.parent
REPO = Path('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(name: str, value: object) -> None:
    with (BASE / name).open('x') as target:
        target.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


rows = json.loads((PACKET / 'artifact-manifest.json').read_bytes())
bad = [row['path'] for row in rows if not (PACKET / row['path']).is_file() or (PACKET / row['path']).stat().st_size != row['bytes'] or digest(PACKET / row['path']) != row['sha256']]
binding = json.loads((BASE / 'execution-binding.json').read_bytes())
result = json.loads((BASE / 'result.json').read_bytes())
source_matches = {name: digest(REPO / name) == expected for name, expected in binding['sources'].items()}
saved_checks = {
    'parent_manifest_entries': len(rows),
    'parent_manifest_mismatches': bad,
    'parent_manifest_sha256': digest(PACKET / 'artifact-manifest.json'),
    'executed_harness_matches': digest(BASE / 'run_once.py') == binding['harness_sha256'],
    'current_sources_match': source_matches,
    'result_source_chain_matches': result['sources_before'] == binding['sources'] == result['sources_after'],
    'request_count': result['request_count'],
    'http_response_bytes': (BASE / 'health.http.txt').stat().st_size,
    'curl_failure_nonempty': (BASE / 'health.stderr.txt').stat().st_size > 0,
    'failure_preserved': result['verdict'] == 'FAIL' and result['server_exit'] == -9 and result['curl_exit'] == 28,
    'attempt_02_included': False,
}
assert not bad and all(source_matches.values())
assert saved_checks['executed_harness_matches'] and saved_checks['result_source_chain_matches']
assert saved_checks['failure_preserved']
write_once('stored-evidence-check.json', saved_checks)
names = ['run_once.py', 'acceptance.md', 'execution-binding.json', 'launch.json', 'result.json', 'health.http.txt', 'health.stderr.txt', 'server.stdout.txt', 'server.stderr.txt', 'qa-correction.json', 'IMP20-STARTUP-PROJECT-ROOT-01-manual-qa.md', 'handoff-ko.md', 'stored-evidence-check.json', 'finalize_saved_evidence.py']
write_once('supplemental-manifest.json', {'scope': 'original failed primary-startup attempt only; private-runtime and attempt-02 excluded', 'parent_manifest_sha256': digest(PACKET / 'artifact-manifest.json'), 'artifacts': [{'path': name, 'bytes': (BASE / name).stat().st_size, 'sha256': digest(BASE / name)} for name in names]})
print(json.dumps(saved_checks, ensure_ascii=False))
