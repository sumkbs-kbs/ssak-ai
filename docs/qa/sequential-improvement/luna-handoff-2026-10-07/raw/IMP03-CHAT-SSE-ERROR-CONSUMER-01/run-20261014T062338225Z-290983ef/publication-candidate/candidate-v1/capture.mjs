import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai';
const dashboard = path.join(root, 'dashboard');
const dependencies = '/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/dashboard/node_modules';
const destination = path.join(dashboard, 'node_modules');
if (fs.lstatSync(destination).isSymbolicLink()) fs.unlinkSync(destination);
fs.mkdirSync(destination, { recursive: true });
for (const name of fs.readdirSync(dependencies)) fs.symlinkSync(path.join(dependencies, name), path.join(destination, name));
const owned = ['dashboard/src/api/client.ts', 'dashboard/src/api/client.streamChannels.test.ts', 'dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx'];
const git = (...args) => spawnSync('git', args, { cwd: root, encoding: 'utf8' });
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const files = git('ls-files', 'dashboard/src', 'dashboard/package.json', 'dashboard/pnpm-lock.yaml', 'dashboard/tsconfig.json', 'dashboard/vitest.config.ts', 'dashboard/vite.alias.ts', 'dashboard/buildStamp.ts', 'dashboard/eslint.config.js').stdout.trim().split('\n');
const snapshot = () => Object.fromEntries(files.map((file) => [file, hash(path.join(root, file))]));
const before = snapshot();
for (const file of owned) {
  const target = path.join(run, 'source', file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(root, file), target);
}
fs.writeFileSync(path.join(run, 'source-before.json'), JSON.stringify(before, null, 2));
const checks = [
  ['tests', 'node', [path.join(destination, 'vitest/vitest.mjs'), 'run', 'src/api/client.test.ts', 'src/api/client.streamChannels.test.ts', 'src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx', '--reporter=verbose', '--reporter=json', '--reporter=junit', `--outputFile.json=${path.join(run, 'vitest.json')}`, `--outputFile.junit=${path.join(run, 'junit.xml')}`]],
  ['typecheck', 'node', [path.join(destination, 'typescript/bin/tsc'), '--noEmit', '--pretty', 'false']],
  ['lint', 'node', [path.join(destination, 'eslint/bin/eslint.js'), ...owned.map((file) => file.replace('dashboard/', ''))]],
];
const receipts = [];
for (const [name, command, args] of checks) {
  const started = new Date().toISOString();
  const result = spawnSync(command, args, { cwd: dashboard, encoding: 'utf8', timeout: 120000 });
  fs.writeFileSync(path.join(run, `${name}.stdout`), result.stdout ?? '');
  fs.writeFileSync(path.join(run, `${name}.stderr`), result.stderr ?? '');
  receipts.push({ name, command: [command, ...args], cwd: dashboard, started, ended: new Date().toISOString(), exitCode: result.status, signal: result.signal, error: result.error?.message ?? null });
}
const after = snapshot();
fs.writeFileSync(path.join(run, 'source-after.json'), JSON.stringify(after, null, 2));
fs.writeFileSync(path.join(run, 'receipts.json'), JSON.stringify({ receipts, sourcesStable: JSON.stringify(before) === JSON.stringify(after) }, null, 2));
fs.writeFileSync(path.join(run, 'candidate.patch'), git('diff', 'HEAD', '--', ...owned).stdout);
fs.writeFileSync(path.join(run, 'environment.json'), JSON.stringify({ head: git('rev-parse', 'HEAD').stdout.trim(), cwd: root, node: process.version, dependencies, dependencyReuse: 'ignored node_modules directory contains links to existing root dependencies; no installation', beforeStatus: 'clean at b345bbb7601f1611e6de639161f9fbd241ac1eba', afterStatus: git('status', '--short').stdout, ignoredDependencyDirectory: git('check-ignore', 'dashboard/node_modules/').stdout, diffCheck: git('diff', '--check', '--', ...owned).status }, null, 2));
console.log(JSON.stringify(receipts));
