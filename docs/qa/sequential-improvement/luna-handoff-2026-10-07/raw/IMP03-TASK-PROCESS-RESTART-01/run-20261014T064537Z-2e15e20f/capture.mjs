import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/mr.k/program/coding/ssak_comp/Ssak-Ai';
const runtime = path.join(run, 'runtime');
const python = path.join(root, '.venv/bin/python');
for (const directory of ['tmp', 'state', 'userbrain', 'data', 'models', 'documents', 'vectors', 'logs', 'wiki', 'cache']) fs.mkdirSync(path.join(runtime, directory), { recursive: true });
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const git = (...args) => spawnSync('git', args, { cwd: root, encoding: 'utf8' });
const files = [...new Set(git('ls-files', '--cached', '--others', '--exclude-standard', 'src', 'tests', 'pyproject.toml', 'uv.lock').stdout.trim().split('\n'))].filter((file) => fs.existsSync(path.join(root, file)) && fs.statSync(path.join(root, file)).isFile());
const snapshot = () => Object.fromEntries(files.map((file) => [file, hash(path.join(root, file))]));
fs.writeFileSync(path.join(run, 'source-before.json'), JSON.stringify(snapshot(), null, 2));
fs.writeFileSync(path.join(run, 'index-before.txt'), git('diff', '--cached', '--raw').stdout);
for (const file of ['tests/test_task_process_restart.py', 'tests/conftest.py', 'src/antigravity_k/engine/task_runner.py', 'src/antigravity_k/engine/task_state_store.py', 'src/antigravity_k/engine/task_events.py', 'src/antigravity_k/engine/task_process_ownership.py']) {
  const target = path.join(run, 'source', file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(root, file), target);
}
const overrides = {
  RESTART_QA_RUN: run, RESTART_QA_ROOT: root,
  PYTHONPATH: [path.join(run, 'bootstrap'), path.join(root, 'src'), root].join(path.delimiter),
  PYTHONDONTWRITEBYTECODE: '1', PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1',
  TMPDIR: path.join(runtime, 'tmp'), XDG_CACHE_HOME: path.join(runtime, 'cache'),
  AGK_ENV_FILE: path.join(runtime, 'missing.env'), AGK_CONFIG_FILE: path.join(runtime, 'missing.yaml'),
  AGK_PATH_PROJECT_ROOT: runtime, AGK_PATH_MODELS_DIR: path.join(runtime, 'models'),
  AGK_PATH_DATA_DIR: path.join(runtime, 'data'), AGK_PATH_DOCUMENTS_DIR: path.join(runtime, 'documents'),
  AGK_PATH_VECTORS_DIR: path.join(runtime, 'vectors'), AGK_PATH_LOGS_DIR: path.join(runtime, 'logs'), AGK_PATH_WIKI_DIR: path.join(runtime, 'wiki'),
  AGK_TASK_DB_PATH: path.join(runtime, 'data/tasks.db'), AGK_STATE_DIR: path.join(runtime, 'state'), AGK_USER_BRAIN_DIR: path.join(runtime, 'userbrain'),
  HF_HOME: path.join(runtime, 'models/hf'), HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1',
};
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !/^(AGK_|OPENAI_|OLLAMA_|ANTHROPIC_|HF_|PYTEST_)/.test(name)));
Object.assign(env, overrides);
const selector = path.join(root, 'tests/test_task_process_restart.py') + '::test_task_resume_survives_real_process_kill_without_duplicate_effects';
const args = ['-m', 'pytest', '-p', 'qa_receipts', '-p', 'no:cacheprovider', '-vv', selector, '--basetemp', path.join(runtime, 'tmp/pytest'), '--junitxml', path.join(run, 'junit.xml')];
const started = new Date().toISOString();
const stdout = fs.openSync(path.join(run, 'pytest.stdout'), 'wx');
const stderr = fs.openSync(path.join(run, 'pytest.stderr'), 'wx');
const child = spawn(python, args, { cwd: runtime, env, detached: true, stdio: ['ignore', stdout, stderr] });
let timedOut = false;
let escalation;
const deadline = setTimeout(() => {
  timedOut = true;
  process.kill(-child.pid, 'SIGTERM');
  escalation = setTimeout(() => { try { process.kill(-child.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }, 3000);
}, 30000);
const result = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', (code, signal) => resolve({ code, signal })); });
clearTimeout(deadline);
clearTimeout(escalation);
fs.closeSync(stdout);
fs.closeSync(stderr);
const groupMembers = () => spawnSync('ps', ['-axo', 'pid=,ppid=,pgid=,stat='], { encoding: 'utf8' }).stdout.trim().split('\n').map((line) => line.trim().split(/\s+/)).filter((row) => Number(row[2]) === child.pid).map(([pid, ppid, pgid, state]) => ({ pid: Number(pid), ppid: Number(ppid), pgid: Number(pgid), state }));
let remaining = groupMembers();
for (let attempt = 0; remaining.length && attempt < 20; attempt += 1) {
  await new Promise((resolve) => setTimeout(resolve, 100));
  remaining = groupMembers();
}
const beforeCleanup = remaining;
if (remaining.length) {
  process.kill(-child.pid, 'SIGKILL');
  await new Promise((resolve) => setTimeout(resolve, 250));
  remaining = groupMembers();
}
fs.writeFileSync(path.join(run, 'invocation.json'), JSON.stringify({ executable: python, args, cwd: runtime, started, ended: new Date().toISOString(), deadlineSeconds: 30, cleanupGraceSeconds: 3, pid: child.pid, processGroup: child.pid, timedOut, ...result, explicitEnvironment: overrides, parentReapedBy: 'node child_process close event', beforeCleanup, remainingOwnedProcessGroup: remaining }, null, 2));
fs.writeFileSync(path.join(run, 'source-after.json'), JSON.stringify(snapshot(), null, 2));
fs.writeFileSync(path.join(run, 'index-after.txt'), git('diff', '--cached', '--raw').stdout);
console.log(JSON.stringify({ run, ...result, timedOut, remainingOwnedProcessGroup: remaining }));
