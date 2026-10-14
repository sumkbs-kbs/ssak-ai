import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/mr.k/program/coding/ssak_comp/Ssak-Ai';
const read = (file) => JSON.parse(fs.readFileSync(path.join(run, file), 'utf8'));
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const invocation = read('invocation.json');
const before = read('source-before.json');
const after = read('source-after.json');
const changed = Object.keys(before).filter((file) => before[file] !== after[file]);
const ledgers = fs.readdirSync(path.join(run, 'process-ledger')).flatMap((file) => fs.readFileSync(path.join(run, 'process-ledger', file), 'utf8').trim().split('\n').map(JSON.parse));
const starts = ledgers.filter((event) => event.event === 'process_started');
const joins = ledgers.filter((event) => event.event === 'process_joined');
const guards = ledgers.filter((event) => event.event === 'guard_installed');
const counts = {
  physicalNetworkAttempts: ledgers.filter((event) => event.event === 'physical_network_denied').length,
  unixSocketOperations: ledgers.filter((event) => event.event === 'ipc_socket').length,
  externalExecutableAttempts: ledgers.filter((event) => event.event === 'external_process_denied').length,
  starts: starts.length, joined: joins.length, guardProcesses: guards.length,
};
const statePaths = fs.readdirSync(path.join(run, 'runtime'), { recursive: true }).filter((file) => /(?:baseline|interrupted)\.(?:db|effects)$/.test(file)).map((file) => path.join(run, 'runtime', file));
const code = 'import json,sqlite3,sys,pathlib\nresult={}\nfor name in sys.argv[1:]:\n p=pathlib.Path(name)\n if p.suffix==".effects":\n  result[p.name]=[int(x) for x in p.read_text().splitlines()]\n else:\n  with sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True) as db:\n   db.row_factory=sqlite3.Row\n   result[p.name]={table:[dict(row) for row in db.execute("SELECT * FROM "+table+" ORDER BY 1")] for table in ["task_history","task_checkpoints","task_execution_events"]}\nprint(json.dumps(result,indent=2))';
const dbReceipt = spawnSync(path.join(root, '.venv/bin/python'), ['-c', code, ...statePaths], { cwd: run, encoding: 'utf8' });
if (dbReceipt.status !== 0) throw new Error(dbReceipt.stderr);
fs.writeFileSync(path.join(run, 'state-observation.json'), dbReceipt.stdout);
fs.writeFileSync(path.join(run, 'state-read-receipt.json'), JSON.stringify({ argv: [path.join(root, '.venv/bin/python'), '-c', code, ...statePaths], cwd: run, exitCode: dbReceipt.status, stderr: dbReceipt.stderr }, null, 2));
const state = JSON.parse(dbReceipt.stdout);
const expected = Array.from({ length: 12 }, (_, index) => index + 1);
const effectsCorrect = ['baseline.effects', 'interrupted.effects'].every((file) => JSON.stringify(state[file]) === JSON.stringify(expected));
const interrupted = state['interrupted.db'];
const checkpointTen = interrupted.task_checkpoints.find((row) => row.step === 10);
const completed = interrupted.task_history[0];
const workerSteps = interrupted.task_execution_events.filter((row) => row.event_type === 'worker.chunk').map((row) => JSON.parse(row.payload_json).step);
const guardInherited = starts.every((start) => guards.some((guard) => guard.pid === start.child_pid));
const modules = read('pytest-session.json').modules;
const moduleBinding = modules.filter((module) => module.path.startsWith(root + '/src/') || module.path.startsWith(root + '/tests/')).every((module) => before[path.relative(root, module.path)] === module.sha256);
const assertions = { pytestExitZero: invocation.code === 0, noTimeout: !invocation.timedOut, noRemainingOwnedProcesses: invocation.remainingOwnedProcessGroup.length === 0, sourceUnchanged: changed.length === 0, indexUnchanged: fs.readFileSync(path.join(run, 'index-before.txt'), 'utf8') === fs.readFileSync(path.join(run, 'index-after.txt'), 'utf8'), guardInherited, moduleBinding, physicalNetworkZero: counts.physicalNetworkAttempts === 0, externalExecutableZero: counts.externalExecutableAttempts === 0, distinctWorkerPids: new Set(starts.map((row) => row.child_pid)).size === 3, actualKillObserved: joins.some((row) => row.exitcode === -9 && row.alive === false), bothCompletedWorkersReaped: joins.filter((row) => row.exitcode === 0 && row.alive === false).length === 2, checkpointTen: Boolean(checkpointTen), finalDone: completed.status === 'done', exactlyOnceEffects: effectsCorrect, exactlyOnceEventSteps: JSON.stringify(workerSteps) === JSON.stringify(expected) };
fs.writeFileSync(path.join(run, 'result.json'), JSON.stringify({ status: Object.values(assertions).every(Boolean) ? 'PASS_SCOPED_REAL_OS_RESTART' : 'INCONCLUSIVE', assertions, counts, changed, pids: { starts, joins }, checkpointStep: checkpointTen?.step, finalOutput: completed.output, baselineEffectSteps: state['baseline.effects'], resumedEffectSteps: state['interrupted.effects'], limits: ['Fixture orchestrator discards messages/target_model; semantic context and approval are not proved.', 'Python physical network guard covers inherited Python workers; no non-Python subprocess was launched.', 'Anonymous multiprocessing Pipes are IPC; no Unix socket operations were observed.'] }, null, 2));
const artifacts = fs.readdirSync(run, { recursive: true }).filter((file) => fs.statSync(path.join(run, file)).isFile() && file !== 'artifact-manifest.json');
fs.writeFileSync(path.join(run, 'artifact-manifest.json'), JSON.stringify(artifacts.map((file) => ({ file, bytes: fs.statSync(path.join(run, file)).size, sha256: hash(path.join(run, file)) })), null, 2));
console.log(JSON.stringify({ assertions, counts, artifactCount: artifacts.length }));
