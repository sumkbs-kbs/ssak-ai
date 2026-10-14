import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = process.cwd();
const phase = process.argv[2];
const directory = path.join(run, phase);
fs.mkdirSync(directory, { recursive: true });
const owned = ['dashboard/src/api/client.ts', 'dashboard/src/api/client.streamChannels.test.ts', 'dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx'];
const inputs = [...new Set([...owned, ...spawnSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', 'dashboard/src', 'dashboard/package.json', 'dashboard/pnpm-lock.yaml', 'dashboard/tsconfig.json', 'dashboard/vitest.config.ts', 'dashboard/vite.alias.ts', 'dashboard/buildStamp.ts', 'dashboard/eslint.config.js'], { encoding: 'utf8' }).stdout.trim().split('\n')])].filter((file) => fs.existsSync(file) && fs.statSync(file).isFile());
const digest = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const snapshot = () => Object.fromEntries(inputs.map((file) => [file, digest(file)]));
const before = snapshot();
for (const file of owned) {
  const target = path.join(directory, 'source', file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(file, target);
}
fs.writeFileSync(path.join(directory, 'source-before.json'), JSON.stringify(before, null, 2));
const testArgs = ['exec', 'vitest', 'run', 'src/api/client.test.ts', 'src/api/client.streamChannels.test.ts', 'src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx', '--reporter=verbose', '--reporter=json', `--outputFile.json=${path.join(directory, 'vitest.json')}`];
const checks = phase === 'checks'
  ? [['typecheck', ['exec', 'tsc', '--noEmit', '--pretty', 'false']], ['lint', ['exec', 'eslint', ...owned.map((file) => file.replace('dashboard/', ''))]]]
  : [['tests', testArgs]];
const receipts = [];
for (const [name, args] of checks) {
  const started = new Date().toISOString();
  const result = spawnSync('pnpm', args, { cwd: path.join(root, 'dashboard'), encoding: 'utf8', timeout: 120000 });
  fs.writeFileSync(path.join(directory, `${name}.stdout`), result.stdout ?? '');
  fs.writeFileSync(path.join(directory, `${name}.stderr`), result.stderr ?? '');
  receipts.push({ name, command: ['pnpm', ...args], cwd: path.join(root, 'dashboard'), started, ended: new Date().toISOString(), exitCode: result.status, signal: result.signal, error: result.error?.message ?? null });
}
const after = snapshot();
fs.writeFileSync(path.join(directory, 'source-after.json'), JSON.stringify(after, null, 2));
fs.writeFileSync(path.join(directory, 'receipts.json'), JSON.stringify({ receipts, sourcesStable: JSON.stringify(before) === JSON.stringify(after) }, null, 2));
console.log(JSON.stringify(receipts));
