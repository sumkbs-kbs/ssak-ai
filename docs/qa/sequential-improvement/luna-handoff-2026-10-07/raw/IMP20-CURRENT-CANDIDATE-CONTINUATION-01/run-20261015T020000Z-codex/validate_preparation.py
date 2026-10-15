"""Read-only AST/source checks; does not import or run prepared programs."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLAN = json.loads((BASE / 'prepared-plan.json').read_bytes())
FILES = ('continuation.py', 'collector_proxy.py')
SOURCES = {name: (BASE / name).read_text() for name in FILES}
TREES = {name: ast.parse(source, filename=name) for name, source in SOURCES.items()}
for name, source in SOURCES.items():
    compile(source, str(BASE / name), 'exec')
source, proxy = (SOURCES[name] for name in FILES)
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
helper = Path(PLAN['soak_helper']).read_text()
checks = {
    'in_memory_compile_both_programs': True,
    'every_frozen_input_matches_bytes': all(digest(path) == sha for path, sha in PLAN['input_sha256'].items()),
    'wrapper_matches_plan': digest(BASE / 'continuation.py') == PLAN['wrapper_sha256'],
    'one_shot_launch_and_supervisor_claims': all(token in source for token in ('write("start-claim.json"', 'write("supervisor-claim.json"', 'exclusive=True')),
    'detached_caffeinate_stdout_stderr': all(token in source for token in ('"/usr/bin/caffeinate", "-i"', 'start_new_session=True', 'stdin=subprocess.DEVNULL', '"supervisor.stdout.txt"', '"supervisor.stderr.txt"')),
    'gate_wait_original_sum_plus_1200': PLAN['gate_wait_seconds'] == sum(gate['timeout_seconds'] for gate in json.loads((Path(PLAN['repo']) / 'scripts/commercial_ga_gates.json').read_bytes())['gates']) + 1200,
    'partial_json_wait_bounded_30s': all(token in source for token in ('json.JSONDecodeError', 'time.sleep(min(30', '43800, "WAITING_EXISTING_COLLECTOR"')),
    'finalizer_once_existing_result_reuse': source.count('child("finalizer",') == 1 and source.count('if not (FRESH / "result.json").exists():') == 2,
    'soak_helper_once_isolated_assigned_python': source.count('child("soak-helper",') == 1 and '[PYTHON, "-I", "-B", str(HELPER), "--launch"]' in source,
    'official_verify_once_exact_report_and_8h': source.count('child("official-final-verify",') == 1 and '"--min-soak-seconds", "28800"' in source and 'execution["commands"]["official_final_verify"] == expected' in source,
    'actual_child_pid_exit_receipts': all(token in source for token in ('process.wait(timeout=timeout)', '"pid": process.pid', '"exit_code": code', '"UNOBSERVED_TIMEOUT_NO_RETRY"')),
    'strict_gate_checks_and_no_merge': all(token in source for token in ('all(v is True for v in result["checks"].values())', 'result["historical_results_merged"] is False', 'result["gate_process_exit"] == result["runner_exit"] == 0')),
    'source_current_commit_head_equality': all(token in source for token in ('"working_fingerprint": FP, "commit_fingerprint": FP', '"head": HEAD, "status": ""')),
    'real_duration_six_scenarios_required': all(token in source for token in ('recovery["duration_seconds"] >= 28800', 'len(rows) == 6', 'set(PLAN["scenarios"])', 'sc6.get("actual_duration_s", sc6.get("duration_s", 0)) >= 28800')),
    'collector_exit_is_acceptance_condition': 'collector["actual_exit"] == collector["propagated_exit"] == 0' in source and 'all(checks.values())' in source,
    'no_controller_gate_or_collector_dispatch_in_supervisor': all(token not in source for token in ('"scripts/soak_control.sh", "run"', '"scripts/ga_gate.py", "--manifest"', '"collect_after_completion"', '"--preflight"')),
    'collector_proxy_runs_real_collector_exactly_once': proxy.count('subprocess.Popen(command,') == 1 and 'command = [str(PYTHON), str(COLLECTOR)]' in proxy,
    'collector_proxy_preserves_environment_and_streams': 'env=dict(os.environ)' in proxy and 'stdout=' not in proxy and 'stderr=' not in proxy,
    'collector_proxy_claim_and_actual_negative_exit': all(token in proxy for token in ('record("collector-claim.json", binding, exclusive=True)', 'actual = process.wait()', '"actual_exit": actual', '128 - actual', 'os.fsync(stream.fileno())')),
    'collector_proxy_source_bound_to_execution_and_commit': all(token in proxy for token in ('plan["measurement_sources"]["scripts/collect_soak_result.py"] != digest', 'hashlib.sha256(committed).hexdigest() != digest')),
    'helper_has_formal_judge_hook_and_exact_proxy': 'NX10_JUDGE' in helper and str(BASE / 'collector_proxy.py') in helper and digest(BASE / 'collector_proxy.py') in helper,
    'nothing_launched_by_preparation': all(not (BASE / name).exists() for name in ('start-claim.json','supervisor-claim.json','launch-receipt.json')) and not (Path(PLAN['soak_helper']).parent / 'soak').exists(),
}
print(json.dumps({'scope':'Static preparation only; runtime scenarios NOT_RUN', 'checks': checks, 'passed':sum(checks.values()), 'total':len(checks)},indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
