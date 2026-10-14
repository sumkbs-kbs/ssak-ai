import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const files = ['dashboard/src/api/client.ts', 'dashboard/src/api/client.streamChannels.test.ts', 'dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx'];
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const read = (file) => JSON.parse(fs.readFileSync(path.join(run, file), 'utf8'));
const patch = files.map((file) => {
  const result = spawnSync('diff', ['-u', '--label', `a/${file}`, '--label', `b/${file}`, path.join(run, 'preimage', file), file], { encoding: 'utf8' });
  if (result.status !== 1) throw new Error(`Unexpected diff status for ${file}: ${result.status}`);
  return result.stdout;
}).join('');
fs.writeFileSync(path.join(run, 'task-only.patch'), patch);
const reconstruction = path.join(run, 'reconstruction');
fs.mkdirSync(reconstruction, { recursive: true });
for (const file of files) {
  const target = path.join(reconstruction, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(run, 'preimage', file), target);
}
const applied = spawnSync('patch', ['-p1', '-i', path.join(run, 'task-only.patch')], { cwd: reconstruction, encoding: 'utf8' });
const binding = files.map((file) => ({ file, preimage: hash(path.join(run, 'preimage', file)), red: hash(path.join(run, 'red/source', file)), green: hash(path.join(run, 'green/source', file)), current: hash(file), reconstructed: hash(path.join(reconstruction, file)) }));
if (applied.status !== 0 || binding.some((file) => file.green !== file.current || file.reconstructed !== file.current)) throw new Error('Patch reconstruction or current source binding failed');
fs.writeFileSync(path.join(run, 'patch-reconstruction.json'), JSON.stringify({ exitCode: applied.status, stdout: applied.stdout, stderr: applied.stderr, binding }, null, 2));
const reports = ['red', 'green'].map((phase) => {
  const result = read(`${phase}/vitest.json`);
  return { phase, total: result.numTotalTests, passed: result.numPassedTests, failed: result.numFailedTests, pending: result.numPendingTests, cases: result.testResults.flatMap((suite) => suite.assertionResults.map((test) => ({ name: test.fullName, status: test.status }))) };
});
const phases = ['red', 'green', 'checks'].map((phase) => ({ phase, ...read(`${phase}/receipts.json`) }));
if (phases.some((phase) => !phase.sourcesStable)) throw new Error('Source changed during validation');
if (reports[0].failed !== 10 || reports[1].passed !== 59 || reports[1].failed !== 0 || reports[1].pending !== 0) throw new Error('Unexpected scenario counts');
const diffCheck = spawnSync('git', ['diff', '--check', '--', ...files], { encoding: 'utf8' });
fs.writeFileSync(path.join(run, 'counts-and-checks.json'), JSON.stringify({ reports, phases, diffCheck: { command: ['git', 'diff', '--check', '--', ...files], exitCode: diffCheck.status, stdout: diffCheck.stdout, stderr: diffCheck.stderr } }, null, 2));
const version = (command, args) => spawnSync(command, args, { encoding: 'utf8' }).stdout.trim();
fs.writeFileSync(path.join(run, 'environment.json'), JSON.stringify({ cwd: process.cwd(), head: version('git', ['rev-parse', 'HEAD']), node: process.version, pnpm: version('pnpm', ['--version']), scope: 'offline fetch fixtures and jsdom component; no provider/LLM/browser run' }, null, 2));
const artifacts = fs.readdirSync(run, { recursive: true }).filter((file) => fs.statSync(path.join(run, file)).isFile() && file !== 'artifact-manifest.json');
fs.writeFileSync(path.join(run, 'artifact-manifest.json'), JSON.stringify(artifacts.map((file) => ({ file, bytes: fs.statSync(path.join(run, file)).size, sha256: hash(path.join(run, file)) })), null, 2));
console.log(JSON.stringify({ reports: reports.map(({ cases, ...counts }) => counts), patchReconstructed: true, phasesStable: true, artifacts: artifacts.length }));
