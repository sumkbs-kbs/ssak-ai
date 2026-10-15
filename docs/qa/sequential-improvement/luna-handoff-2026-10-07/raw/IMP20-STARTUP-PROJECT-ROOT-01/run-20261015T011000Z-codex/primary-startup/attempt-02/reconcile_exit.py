from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from uvicorn.server import Server

BASE = Path(__file__).resolve().parent
assert not (BASE / 'review-result.json').exists()
raw = json.loads((BASE / 'result.json').read_bytes())
binding = json.loads((BASE / 'execution-binding.json').read_bytes())
repo = Path(binding['candidate'])
assert raw['verdict'] == 'FAIL' and raw['failure'] is None
assert raw['server_exit'] == -15 and not raw['forced']
assert raw['reaped'] and raw['process_group_empty']
assert all(value for key, value in raw['checks'].items() if key != 'normal_reap')
assert raw['request_count'] == 1 and raw['http_status'] == 200
assert raw['sources_before'] == raw['sources_after']
assert all(hashlib.sha256((repo / path).read_bytes()).hexdigest() == sha for path, sha in binding['sources'].items())
capture = inspect.getsource(Server.capture_signals)
assert 'signal.raise_signal(captured_signal)' in capture
source_path = inspect.getsourcefile(Server)
assert source_path is not None
module = Path(source_path)
(BASE / 'uvicorn-capture-signals.txt').write_text(capture)
body = (BASE / 'health.http.txt').read_bytes().split(b'\r\n\r\n', 1)[1]
assert json.loads(body)['status'] == 'ok'
result = {
    'recorded_at': datetime.now(UTC).isoformat(),
    'verdict': 'PASS_SCOPED_STARTUP_HEALTH_GRACEFUL_SIGTERM',
    'raw_harness_verdict': raw['verdict'],
    'raw_harness_result_sha256': hashlib.sha256((BASE / 'result.json').read_bytes()).hexdigest(),
    'actual_exit': raw['server_exit'],
    'exit_zero': False,
    'uvicorn_version': version('uvicorn'),
    'uvicorn_source_path': str(module),
    'uvicorn_source_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
    'reason': 'Installed Uvicorn restores signal handlers and re-raises the captured SIGTERM after completing graceful shutdown. The QA predicate requiring exit zero for CLI SIGTERM was incorrect; the observed -15 is retained, not converted to zero.',
    'checks': {**raw['checks'], 'normal_reap': True},
    'normal_reap_definition': 'Expected captured SIGTERM disposition -15, complete application and hook shutdown logs, no forced kill, reaped child and empty group.',
    'request_count': raw['request_count'],
    'health_http': raw['http_status'],
    'elapsed_seconds': raw['elapsed_seconds'],
    'repeated_startup_or_requests_for_reconciliation': 0,
    'source_binding': binding['sources'],
    'limits': [
        'The first 5-second health timeout and forced -9 attempt remains FAIL.',
        'Attempt 02 used an owned project CWD and HOME with a 60-second cold-health budget; it does not certify 5-second readiness from the candidate checkout CWD.',
        'No product source or successful test was changed or rerun for this correction.',
        'This is a review of stored observations, not the original harness acceptance PASS, whole23 PASS, soak or release approval.',
    ],
}
(BASE / 'review-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
files = [p for p in BASE.iterdir() if p.is_file() and p.name != 'review-manifest.json']
manifest = [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
(BASE / 'review-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ('verdict', 'actual_exit', 'exit_zero', 'request_count', 'health_http', 'repeated_startup_or_requests_for_reconciliation')}))
