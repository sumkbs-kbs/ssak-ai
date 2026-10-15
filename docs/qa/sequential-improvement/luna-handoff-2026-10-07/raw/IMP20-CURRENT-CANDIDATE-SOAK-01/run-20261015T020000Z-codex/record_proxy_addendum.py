from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROXY = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-CURRENT-CANDIDATE-CONTINUATION-01/run-20261015T020000Z-codex/collector_proxy.py')
assert not (BASE / 'proxy-preparation-addendum.json').exists()
assert not (BASE / 'soak').exists()
old = BASE / 'pre-proxy/start_soak_once.py'
current = BASE / 'start_soak_once.py'
assert hashlib.sha256(old.read_bytes()).hexdigest() == '670af16e5fc9476d354196305f1a0b1e122d448fe154386c4f92072caaa93f58'
assert hashlib.sha256(PROXY.read_bytes()).hexdigest() == 'c3a10b0ff2f121599310e719688566ec12c53ba1edd5bef676f27566526b57ae'
for source in (current, PROXY):
    compile(source.read_text(), str(source), 'exec')
tree = ast.parse(current.read_text())
assert any(isinstance(node, ast.Constant) and node.value == 'NX10_JUDGE' for node in ast.walk(tree))
result = {
    'recorded_at': datetime.now(UTC).isoformat(),
    'status': 'PREPARED_WITH_COLLECTOR_EXIT_RECEIPT_NOT_RUN',
    'old_preparation_preserved': ['prepared-plan.json', 'preparation-evidence.json', 'pre-proxy/start_soak_once.py'],
    'old_helper_sha256': hashlib.sha256(old.read_bytes()).hexdigest(),
    'current_helper_sha256': hashlib.sha256(current.read_bytes()).hexdigest(),
    'proxy_sha256': hashlib.sha256(PROXY.read_bytes()).hexdigest(),
    'delta': 'Only a fixed source-bound collector receipt proxy is connected through the existing NX10_JUDGE extension. The real collector, its cwd, inputs, thresholds, stdout/stderr and exit are retained. It runs once and persists actual child exit before propagating it.',
    'supersedes_prepared_plan_collection_instruction': 'Do not execute a second manual collector. Existing detached harvest owns the single invocation through the receipt adapter. The continuation waits for recovery JSON and actual collector-receipt.json.',
    'compile_current_helper_and_proxy': True,
    'controller_runs': 0,
    'collector_runs': 0,
    'model_or_http_requests': 0,
    'limits': 'Original 21 read-only preparation checks belong to the original helper hash. This additive delta check is not an execution or a rerun of those checks. Pre-proxy archive is historical and must not be launched.',
}
(BASE / 'proxy-preparation-addendum.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
