import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/mr.k/program/coding/ssak_comp/Ssak-Ai';
const runtime = path.join(run, 'runtime');
for (const name of ['project', 'persist', 'data', 'models', 'documents', 'vectors', 'logs', 'wiki', 'state', 'userbrain', 'tmp', 'cache']) fs.mkdirSync(path.join(runtime, name), { recursive: true });
const hashBytes = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const hash = (file) => hashBytes(fs.readFileSync(file));
const git = (...args) => spawnSync('git', args, { cwd: root, encoding: 'utf8' });
const targets = ['src/antigravity_k/engine/vector_store.py', 'src/antigravity_k/engine/rag_indexer.py', 'src/antigravity_k/engine/chroma_lifecycle.py', 'src/antigravity_k/engine/long_context_fusion.py', 'src/antigravity_k/api/dependencies.py'];
const snapshot = () => ({ sources: Object.fromEntries(targets.map((file) => [file, hash(path.join(root, file))])), stagedPatchSHA256: hashBytes(git('diff', '--cached', '--binary').stdout), stagedFiles: git('diff', '--cached', '--name-only').stdout.trim().split('\n').length, uncommittedPaths: git('diff', '--name-only').stdout.trim().split('\n') });
const before = snapshot();
fs.writeFileSync(path.join(run, 'before.json'), JSON.stringify(before, null, 2));
for (const file of targets) {
  const destination = path.join(run, 'source', file);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(path.join(root, file), destination);
}
const overrides = {
  CHROMA_QA_RUN: run, PYTHONPATH: [path.join(run, 'bootstrap'), path.join(root, 'src')].join(path.delimiter), PYTHONDONTWRITEBYTECODE: '1', PYTHONFAULTHANDLER: '1',
  TMPDIR: path.join(runtime, 'tmp'), XDG_CACHE_HOME: path.join(runtime, 'cache'),
  AGK_ENV_FILE: path.join(runtime, 'missing.env'), AGK_CONFIG_FILE: path.join(runtime, 'missing.yaml'),
  AGK_PATH_PROJECT_ROOT: path.join(runtime, 'project'), AGK_PATH_MODELS_DIR: path.join(runtime, 'models'), AGK_PATH_DATA_DIR: path.join(runtime, 'data'), AGK_PATH_DOCUMENTS_DIR: path.join(runtime, 'documents'), AGK_PATH_VECTORS_DIR: path.join(runtime, 'vectors'), AGK_PATH_LOGS_DIR: path.join(runtime, 'logs'), AGK_PATH_WIKI_DIR: path.join(runtime, 'wiki'), AGK_STATE_DIR: path.join(runtime, 'state'), AGK_USER_BRAIN_DIR: path.join(runtime, 'userbrain'), AGK_TASK_DB_PATH: path.join(runtime, 'data/tasks.db'),
  HF_HOME: path.join(runtime, 'models/hf'), HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', ANONYMIZED_TELEMETRY: 'False',
};
const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(AGK_|OPENAI_|OLLAMA_|ANTHROPIC_|HF_)/.test(key)));
Object.assign(env, overrides);
const executable = path.join(root, '.venv/bin/python');
const args = ['-X', 'faulthandler', path.join(run, 'probe.py')];
const stdout = fs.openSync(path.join(run, 'probe.stdout'), 'wx');
const stderr = fs.openSync(path.join(run, 'probe.stderr'), 'wx');
const started = new Date().toISOString();
const child = spawn(executable, args, { cwd: runtime, env, detached: true, stdio: ['ignore', stdout, stderr] });
let timedOut = false;
const timer = setTimeout(() => { timedOut = true; process.kill(-child.pid, 'SIGKILL'); }, 30000);
const result = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', (code, signal) => resolve({ code, signal })); });
clearTimeout(timer);
fs.closeSync(stdout);
fs.closeSync(stderr);
const group = () => spawnSync('ps', ['-axo', 'pid=,ppid=,pgid=,stat='], { encoding: 'utf8' }).stdout.trim().split('\n').map((line) => line.trim().split(/\s+/)).filter((row) => Number(row[2]) === child.pid);
let remaining = group();
if (remaining.length) {
  process.kill(-child.pid, 'SIGKILL');
  await new Promise((resolve) => setTimeout(resolve, 200));
  remaining = group();
}
const invocation = { executable, args, cwd: runtime, started, ended: new Date().toISOString(), pid: child.pid, pgid: child.pid, ...result, timedOut, deadlineSeconds: 30, remainingOwnedProcesses: remaining, reapedBy: 'node child_process close event', environment: overrides };
fs.writeFileSync(path.join(run, 'invocation.json'), JSON.stringify(invocation, null, 2));
const after = snapshot();
fs.writeFileSync(path.join(run, 'after.json'), JSON.stringify(after, null, 2));
const phases = fs.readFileSync(path.join(run, 'probe.stdout'), 'utf8').split('\n').filter((line) => line.startsWith('{')).map(JSON.parse);
const guard = fs.readdirSync(run).filter((file) => /^guard-\d+\.jsonl$/.test(file)).flatMap((file) => fs.readFileSync(path.join(run, file), 'utf8').trim().split('\n').map(JSON.parse));
const assertions = { processExitZero: result.code === 0, noTimeout: !timedOut, noOwnedProcesses: remaining.length === 0, sourceUnchanged: JSON.stringify(before.sources) === JSON.stringify(after.sources), staged97Unchanged: before.stagedFiles === 97 && after.stagedFiles === 97 && before.stagedPatchSHA256 === after.stagedPatchSHA256, complete: phases.at(-1)?.phase === 'PASS_FRESH_OWNED_NATIVE_LIFECYCLE', networkAttemptsZero: !guard.some((entry) => entry.event === 'physical_denied'), externalExecutablesZero: !guard.some((entry) => entry.event === 'external_process_denied'), guardInstalled: guard.some((entry) => entry.event === 'guard_installed' && entry.pid === child.pid) };
fs.writeFileSync(path.join(run, 'result.json'), JSON.stringify({ status: Object.values(assertions).every(Boolean) ? 'PASS_FRESH_OWNED_NATIVE_LIFECYCLE_ONLY' : 'INCONCLUSIVE_NATIVE_DIAGNOSTIC', assertions, lastPhase: phases.at(-1), phases, guard, nativeExitCode: result.signal === 'SIGSEGV' ? -11 : result.code, limitation: 'This fresh-owned lifecycle does not explain or repair the prior route fixture native crash. No closed collection count was executed.' }, null, 2));
console.log(JSON.stringify({ ...result, timedOut, assertions, lastPhase: phases.at(-1)?.phase }));
